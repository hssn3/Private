"""A minute-granularity repeating timer.

Deliberately not a cron library: one daemon thread, an Event for the sleep so
stopping is instant, and a guard so a long backup can never overlap with the
next tick.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from .logging_setup import log


class IntervalScheduler:
    def __init__(self, job: Callable[[], None]) -> None:
        self._job = job
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._interval = 600.0
        self._next_run = 0.0
        self._running_job = False

    # ------------------------------------------------------------ state
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def job_in_progress(self) -> bool:
        return self._running_job

    @property
    def seconds_until_next(self) -> float:
        if not self.is_running:
            return -1.0
        return max(0.0, self._next_run - time.time())

    # --------------------------------------------------------- control
    def start(self, interval_minutes: int) -> None:
        self.stop()
        with self._lock:
            self._interval = max(60.0, float(interval_minutes) * 60.0)
            self._stop.clear()
            self._wake.clear()
            self._next_run = time.time() + self._interval
            self._thread = threading.Thread(target=self._loop, name="backup-scheduler", daemon=True)
            self._thread.start()
        log.info("scheduler started: every %d minute(s)", interval_minutes)

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stop.set()
        self._wake.set()
        thread.join(timeout=5)
        self._thread = None
        log.info("scheduler stopped")

    def set_interval(self, interval_minutes: int) -> None:
        """Change the cadence without dropping the thread."""
        with self._lock:
            self._interval = max(60.0, float(interval_minutes) * 60.0)
            self._next_run = time.time() + self._interval
        self._wake.set()

    def trigger_now(self) -> None:
        with self._lock:
            self._next_run = time.time()
        self._wake.set()

    # ------------------------------------------------------------- loop
    def _loop(self) -> None:
        while not self._stop.is_set():
            wait_for = max(0.0, self._next_run - time.time())
            self._wake.wait(timeout=wait_for)
            self._wake.clear()
            if self._stop.is_set():
                return
            if time.time() < self._next_run:
                continue  # interval was changed while we slept

            if self._running_job:
                # Previous run is still going (a huge first archive, say).
                # Skip this tick rather than stacking two zips on one drive.
                log.warning("scheduled run skipped - previous backup still in progress")
            else:
                self._running_job = True
                try:
                    self._job()
                except Exception as exc:  # noqa: BLE001 - the thread must survive
                    log.exception("scheduled job raised: %s", exc)
                finally:
                    self._running_job = False

            with self._lock:
                self._next_run = time.time() + self._interval
