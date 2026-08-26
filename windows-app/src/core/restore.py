"""The other half of the story: getting folder 0 back out of a zip.

Two modes:
  * extract     - unpack the archive somewhere (the normal first step on a
                  fresh Windows install).
  * push_back   - read each app's _manifest.json and copy its data back to the
                  original location (%APPDATA%\\Cursor\\User and friends).
"""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import paths
from .logging_setup import log

ProgressFn = Callable[[str, float], None]


@dataclass
class RestoreResult:
    ok: bool
    destination: Path | None
    files: int
    message: str


def inspect(archive_path: str | Path) -> tuple[bool, str, int, int]:
    """(valid, message, file_count, uncompressed_size)."""
    path = Path(archive_path)
    if not path.exists():
        return False, "فایل پیدا نشد", 0, 0
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                return False, f"آرشیو آسیب دیده است: {bad}", 0, 0
            infos = archive.infolist()
            total = sum(info.file_size for info in infos)
            return True, "آرشیو سالم است", len(infos), total
    except zipfile.BadZipFile:
        return False, "این فایل یک زیپ معتبر نیست", 0, 0
    except OSError as exc:
        return False, f"خطا در خواندن فایل: {exc}", 0, 0


def extract(
    archive_path: str | Path,
    destination: str | Path,
    progress: ProgressFn | None = None,
) -> RestoreResult:
    source = Path(archive_path)
    target = Path(destination)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return RestoreResult(False, None, 0, f"مقصد قابل ساخت نیست: {exc}")

    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            total = max(1, len(members))
            for index, member in enumerate(members, start=1):
                if _is_unsafe(member.filename):
                    log.warning("refusing unsafe archive entry: %s", member.filename)
                    continue
                archive.extract(member, target)
                if index % 50 == 0 or index == total:
                    _report(progress, f"استخراج {index:,} از {total:,}", index / total)
    except (zipfile.BadZipFile, OSError) as exc:
        return RestoreResult(False, None, 0, f"استخراج ناموفق: {exc}")

    log.info("extracted %s to %s", source.name, target)
    return RestoreResult(True, target, len(members), f"در {target} استخراج شد")


def _is_unsafe(name: str) -> bool:
    """Reject absolute paths and ../ traversal - a zip from an untrusted
    machine should not be able to write outside the destination."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        return True
    return any(part == ".." for part in normalized.split("/"))


def push_back(extracted_root: str | Path, progress: ProgressFn | None = None) -> list[str]:
    """Copy each collected app's data back where it came from.

    ``extracted_root`` is the folder that contains ``Apps`` (i.e. the restored
    ``0``). Returns a human-readable report, one line per app.
    """
    root = Path(extracted_root)
    apps_root = root / paths.APPS_DIRNAME
    if not apps_root.is_dir():
        return ["فولدر Apps در مسیر انتخاب‌شده پیدا نشد"]

    manifests = sorted(apps_root.glob("*/_manifest.json"))
    report: list[str] = []
    total = max(1, len(manifests))

    for index, manifest_path in enumerate(manifests, start=1):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            report.append(f"{manifest_path.parent.name}: مانیفست خوانده نشد ({exc})")
            continue

        app_name = manifest.get("app", manifest_path.parent.name)
        _report(progress, f"بازگردانی {app_name}", index / total)
        restored = 0

        for entry in manifest.get("sources", []):
            source = manifest_path.parent / entry.get("to", "")
            destination = paths.expand(entry.get("from", ""))
            if not source.exists() or not str(destination):
                continue
            try:
                if source.is_file():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                else:
                    _merge_tree(source, destination)
                restored += 1
            except OSError as exc:
                report.append(f"{app_name}: {destination} → {exc}")

        report.append(f"{app_name}: {restored} مسیر بازگردانی شد")
        log.info("pushed back %s (%d paths)", app_name, restored)

    return report


def _merge_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for dirpath, _dirnames, filenames in os.walk(source, onerror=lambda _e: None):
        relative = Path(dirpath).relative_to(source)
        out_dir = destination / relative
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            try:
                shutil.copy2(Path(dirpath) / filename, out_dir / filename)
            except OSError as exc:
                log.debug("restore skipped %s: %s", filename, exc)


def _report(progress: ProgressFn | None, message: str, fraction: float) -> None:
    if progress:
        progress(message, min(1.0, max(0.0, fraction)))
