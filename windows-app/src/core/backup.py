"""Zip the whole ``0`` folder to the backup drive and enforce the cycle rule.

The cycle rule
--------------
Keep at most ``keep_count`` archives (default 10). The moment an 11th is
written, the oldest is deleted permanently - not moved to the Recycle Bin,
which would defeat the point of keeping the drive from filling up.
"""

from __future__ import annotations

import json
import os
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import paths
from .logging_setup import log

ProgressFn = Callable[[str, float], None]

PREFIX = "backup_0_"
STAMP_FORMAT = "%Y%m%d-%H%M%S"
# The optional -N suffix disambiguates two backups made in the same second.
ARCHIVE_RE = re.compile(rf"^{re.escape(PREFIX)}\d{{8}}-\d{{6}}(-\d+)?\.zip$")

# Files the app itself rewrites on every run. They live inside folder 0, so
# leaving them in the change signature would make "nothing changed" impossible.
SIGNATURE_IGNORE = ("state.json", "backup-suite.log")

# Never worth compressing into the archive.
ALWAYS_SKIP_DIRS = {"$recycle.bin", "system volume information", "__pycache__"}
ALWAYS_SKIP_FILES = {"thumbs.db", "desktop.ini"}


@dataclass
class BackupResult:
    ok: bool
    path: Path | None
    size: int
    files: int
    seconds: float
    removed: list[str]
    message: str
    skipped_unchanged: bool = False


def archive_name(when: datetime | None = None) -> str:
    return f"{PREFIX}{(when or datetime.now()).strftime(STAMP_FORMAT)}.zip"


def _unique_archive_path(destination: Path) -> Path:
    """Never overwrite an existing archive - a manual backup fired in the same
    second as a scheduled one must not silently replace it."""
    candidate = destination / archive_name()
    if not candidate.exists():
        return candidate
    stem = candidate.name[: -len(".zip")]
    for suffix in range(1, 1000):
        alternative = destination / f"{stem}-{suffix}.zip"
        if not alternative.exists():
            return alternative
    raise OSError("too many archives created in the same second")


def list_archives(backup_dir: Path) -> list[Path]:
    """Newest first, by modification time.

    Sorting by mtime rather than by the timestamp in the name means a machine
    whose clock jumped cannot trick the cycle rule into deleting the archive it
    just wrote.
    """
    if not backup_dir.exists():
        return []
    found = [p for p in backup_dir.iterdir() if p.is_file() and ARCHIVE_RE.match(p.name)]

    def sort_key(path: Path) -> tuple[float, str]:
        try:
            return (path.stat().st_mtime, path.name)
        except OSError:
            return (0.0, path.name)

    found.sort(key=sort_key, reverse=True)
    return found


def enforce_cycle_rule(backup_dir: Path, keep: int) -> list[str]:
    """Delete everything past the newest ``keep`` archives. Permanent delete."""
    archives = list_archives(backup_dir)
    removed: list[str] = []
    for stale in archives[max(1, keep):]:
        try:
            os.remove(stale)
            removed.append(stale.name)
            log.info("cycle rule removed %s", stale.name)
        except OSError as exc:
            log.warning("could not delete %s: %s", stale.name, exc)
    return removed


def folder_signature(root: Path) -> str:
    """Cheap fingerprint of folder 0 - file count, total bytes, newest mtime.

    Used by ``skip_unchanged`` so a scheduled run that has nothing new to say
    doesn't burn CPU rebuilding an identical archive every 10 minutes.
    """
    count = 0
    total = 0
    newest = 0.0
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        dirnames[:] = [d for d in dirnames if d.lower() not in ALWAYS_SKIP_DIRS]
        for filename in filenames:
            if filename.startswith(SIGNATURE_IGNORE):
                continue
            full = os.path.join(dirpath, filename)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            count += 1
            total += stat.st_size
            newest = max(newest, stat.st_mtime)
    return f"{count}:{total}:{newest:.0f}"


def _read_state() -> dict:
    try:
        return json.loads(paths.state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    try:
        paths.state_file().write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("could not persist state: %s", exc)


def run_backup(
    backup_dir: str | Path,
    keep: int = 10,
    compression_level: int = 6,
    skip_unchanged: bool = True,
    progress: ProgressFn | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> BackupResult:
    started = time.time()
    root = paths.root_dir()
    destination = Path(backup_dir)

    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return BackupResult(False, None, 0, 0, 0.0, [], f"مقصد بکاپ در دسترس نیست: {exc}")

    if not os.access(destination, os.W_OK):
        return BackupResult(False, None, 0, 0, 0.0, [], f"اجازهٔ نوشتن در {destination} وجود ندارد")

    state = _read_state()
    signature = folder_signature(root)
    if skip_unchanged and state.get("last_signature") == signature and list_archives(destination):
        log.info("nothing changed since the last backup - skipping")
        return BackupResult(
            True, None, 0, 0, time.time() - started, [],
            "چیزی از بکاپ قبلی تغییر نکرده بود", skipped_unchanged=True,
        )

    _report(progress, "فهرست‌برداری از فایل‌ها…", 0.02)
    entries = _collect_entries(root, destination)
    if not entries:
        return BackupResult(False, None, 0, 0, time.time() - started, [], "فولدر 0 خالی است")

    try:
        target = _unique_archive_path(destination)
    except OSError as exc:
        return BackupResult(False, None, 0, 0, time.time() - started, [], str(exc))
    temp = target.with_suffix(".zip.part")
    total = len(entries)
    written = 0

    try:
        with zipfile.ZipFile(
            temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level, allowZip64=True
        ) as archive:
            for index, (full_path, arc_name) in enumerate(entries, start=1):
                if cancelled and cancelled():
                    raise InterruptedError("cancelled by user")
                try:
                    archive.write(full_path, arc_name)
                    written += 1
                except (OSError, ValueError) as exc:
                    # A file locked by a running app: log it and keep going.
                    # A backup missing one lock file beats no backup at all.
                    log.debug("skipped %s: %s", full_path, exc)
                if index % 40 == 0 or index == total:
                    _report(progress, f"فشرده‌سازی {index:,} از {total:,}", 0.02 + 0.93 * index / total)
    except InterruptedError:
        temp.unlink(missing_ok=True)
        return BackupResult(False, None, 0, 0, time.time() - started, [], "توسط کاربر لغو شد")
    except OSError as exc:
        temp.unlink(missing_ok=True)
        message = f"خطا در نوشتن آرشیو: {exc}"
        if getattr(exc, "errno", None) == 28:
            message = "فضای درایو مقصد پر است"
        log.error(message)
        return BackupResult(False, None, 0, 0, time.time() - started, [], message)

    _report(progress, "نهایی‌سازی…", 0.96)
    try:
        temp.replace(target)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        return BackupResult(False, None, 0, 0, time.time() - started, [], f"خطا در ثبت آرشیو: {exc}")

    size = target.stat().st_size
    removed = enforce_cycle_rule(destination, keep)

    state.update(
        {
            "last_signature": signature,
            "last_backup": datetime.now().isoformat(timespec="seconds"),
            "last_archive": str(target),
            "last_size": size,
        }
    )
    _write_state(state)

    elapsed = time.time() - started
    _report(progress, "بکاپ کامل شد", 1.0)
    log.info("backup %s: %d files, %d bytes, %.1fs", target.name, written, size, elapsed)
    return BackupResult(True, target, size, written, elapsed, removed, "بکاپ با موفقیت ساخته شد")


def _collect_entries(root: Path, destination: Path) -> list[tuple[str, str]]:
    """Every file under folder 0, as (absolute path, name inside the zip).

    If the backup directory happens to sit inside folder 0, it is excluded -
    otherwise each archive would swallow all its predecessors.
    """
    entries: list[tuple[str, str]] = []
    try:
        destination_resolved = destination.resolve()
    except OSError:
        destination_resolved = destination

    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        current = Path(dirpath)
        try:
            if current.resolve() == destination_resolved:
                dirnames[:] = []
                continue
        except OSError:
            pass
        dirnames[:] = [d for d in dirnames if d.lower() not in ALWAYS_SKIP_DIRS]
        for filename in filenames:
            if filename.lower() in ALWAYS_SKIP_FILES or filename.endswith(".zip.part"):
                continue
            full = current / filename
            entries.append((str(full), str(Path("0") / full.relative_to(root))))
    return entries


def _report(progress: ProgressFn | None, message: str, fraction: float) -> None:
    if progress:
        progress(message, min(1.0, max(0.0, fraction)))
