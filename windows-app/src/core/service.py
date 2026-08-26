"""Ties the pieces together: collect -> zip -> rotate -> upload.

The UI never calls backup/upload directly; it calls in here, so the manual
button and the scheduled run always take exactly the same path.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import backup, paths, uploader
from .config import ConfigStore
from .logging_setup import log
from .scheduler import IntervalScheduler

ProgressFn = Callable[[str, float], None]
EventFn = Callable[[str, str], None]  # (level, message) - level in {info, ok, warn, error}


@dataclass
class RunSummary:
    ok: bool
    archive: Path | None
    size: int
    seconds: float
    uploaded: bool
    message: str


class BackupService:
    def __init__(self, store: ConfigStore, on_event: EventFn | None = None) -> None:
        self.store = store
        self.on_event = on_event or (lambda _level, _message: None)
        self.scheduler = IntervalScheduler(self._scheduled_run)
        self._busy = threading.Lock()
        self.last_summary: RunSummary | None = None

    # ------------------------------------------------------------ status
    @property
    def is_busy(self) -> bool:
        return self._busy.locked()

    def archives_on_disk(self) -> list[Path]:
        return backup.list_archives(Path(self.store.current.backup_dir))

    # ----------------------------------------------------------- running
    def run_once(self, progress: ProgressFn | None = None) -> RunSummary:
        """Zip folder 0, apply the cycle rule, upload if the cloud is on."""
        if not self._busy.acquire(blocking=False):
            summary = RunSummary(False, None, 0, 0.0, False, "یک بکاپ دیگر در حال اجراست")
            self.on_event("warn", summary.message)
            return summary

        try:
            config = self.store.current
            paths.ensure_layout()
            self.on_event("info", "شروع بکاپ…")

            result = backup.run_backup(
                backup_dir=config.backup_dir,
                keep=config.keep_count,
                compression_level=config.compression_level,
                skip_unchanged=config.skip_unchanged,
                progress=progress,
            )

            if not result.ok:
                self.on_event("error", result.message)
                summary = RunSummary(False, None, 0, result.seconds, False, result.message)
                self.last_summary = summary
                return summary

            if result.skipped_unchanged:
                self.on_event("info", result.message)
                summary = RunSummary(True, None, 0, result.seconds, False, result.message)
                self.last_summary = summary
                return summary

            size_mb = result.size / 1048576
            self.on_event("ok", f"{result.path.name} ساخته شد - {size_mb:,.1f} مگابایت")
            if result.removed:
                self.on_event("info", f"قانون چرخه: {len(result.removed)} بکاپ قدیمی حذف شد")

            uploaded = False
            message = result.message
            if config.cloud_enabled and config.cloud_url and config.cloud_token:
                upload_result = uploader.upload(
                    config.cloud_url, config.cloud_token, result.path, progress
                )
                uploaded = upload_result.ok
                if upload_result.ok:
                    self.on_event("ok", upload_result.message)
                else:
                    self.on_event("warn", upload_result.message)
                    message = f"{message} (آپلود ناموفق)"

            summary = RunSummary(True, result.path, result.size, result.seconds, uploaded, message)
            self.last_summary = summary
            return summary
        finally:
            self._busy.release()

    def run_in_background(
        self, progress: ProgressFn | None = None, done: Callable[[RunSummary], None] | None = None
    ) -> None:
        def worker() -> None:
            summary = self.run_once(progress)
            if done:
                done(summary)

        threading.Thread(target=worker, name="backup-run", daemon=True).start()

    def _scheduled_run(self) -> None:
        log.info("scheduled backup firing at %s", datetime.now().isoformat(timespec="seconds"))
        self.on_event("info", "بکاپ زمان‌بندی‌شده اجرا شد")
        self.run_once()

    # --------------------------------------------------------- schedule
    def start_schedule(self, interval_minutes: int) -> None:
        self.store.update(interval_minutes=interval_minutes, schedule_enabled=True)
        self.scheduler.start(interval_minutes)
        self.on_event("ok", f"زمان‌بندی فعال شد - هر {interval_minutes} دقیقه")

    def stop_schedule(self) -> None:
        self.scheduler.stop()
        self.store.update(schedule_enabled=False)
        self.on_event("info", "زمان‌بندی متوقف شد")

    def shutdown(self) -> None:
        self.scheduler.stop()
