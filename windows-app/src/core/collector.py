"""Step 2 of the flow: copy the selected apps' data into 0\\Apps.

On Windows this shells out to robocopy, which is dramatically faster than
shutil for large trees, skips files that have not changed, and - critically -
does not abort the whole run when a single file is locked by a running
browser. Elsewhere (and if robocopy is missing) we fall back to a pure-Python
mirror so the module stays testable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Sequence

from . import paths
from .detect import DetectedApp
from .logging_setup import log

IS_WINDOWS = sys.platform == "win32"
ProgressFn = Callable[[str, float], None]

# robocopy returns a bitmask; anything below 8 means "copied / nothing to do /
# extra files present", all of which are fine. 8 and above are real failures.
ROBOCOPY_OK = 8


@dataclass
class CollectResult:
    app_key: str
    app_name: str
    ok: bool
    bytes_copied: int
    skipped: list[str]
    message: str


def collect(
    apps: Sequence[DetectedApp],
    progress: ProgressFn | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> list[CollectResult]:
    """Mirror every selected app's data into 0\\Apps\\<key>\\."""
    results: list[CollectResult] = []
    target_root = paths.apps_dir()
    total = max(1, sum(max(1, len(app.data_paths)) for app in apps))
    done = 0

    for app in apps:
        if cancelled and cancelled():
            break
        if not app.data_paths:
            results.append(
                CollectResult(app.key, app.name, True, 0, [], "دیتای شناخته‌شده‌ای ندارد - فقط شورتکات")
            )
            done += 1
            _report(progress, f"{app.name}: رد شد", done / total)
            continue

        app_root = target_root / _safe_dirname(app.key)
        app_root.mkdir(parents=True, exist_ok=True)
        copied = 0
        skipped: list[str] = []
        ok = True

        for source, dest in app.data_paths:
            if cancelled and cancelled():
                break
            _report(progress, f"{app.name} → {dest}", done / total)
            destination = app_root / dest
            try:
                if source.is_file():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    copied += destination.stat().st_size
                else:
                    copied += _mirror(source, destination, app.excludes, skipped)
            except Exception as exc:  # noqa: BLE001 - one bad tree must not kill the run
                ok = False
                skipped.append(f"{source}: {exc}")
                log.warning("collect failed for %s (%s): %s", app.name, source, exc)
            done += 1
            _report(progress, f"{app.name} → {dest}", done / total)

        _write_manifest(app_root, app, copied, skipped)
        message = "کپی شد" if ok else "با چند خطا کپی شد"
        results.append(CollectResult(app.key, app.name, ok, copied, skipped, message))
        log.info("collected %s: %s bytes, %d skipped", app.name, copied, len(skipped))

    return results


def _mirror(source: Path, destination: Path, excludes: Iterable[str], skipped: list[str]) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    if IS_WINDOWS and shutil.which("robocopy"):
        return _robocopy(source, destination, excludes, skipped)
    return _python_mirror(source, destination, excludes, skipped)


def _robocopy(source: Path, destination: Path, excludes: Iterable[str], skipped: list[str]) -> int:
    exclude_dirs: list[str] = []
    for pattern in excludes:
        # robocopy /XD takes names or paths; a name matches at any depth.
        exclude_dirs.append(pattern.replace("/", os.sep).split(os.sep)[-1])

    command = [
        "robocopy", str(source), str(destination),
        "/MIR",        # mirror, so deletions on the source propagate
        "/R:0", "/W:0",  # never retry a locked file - just move on
        "/XJ",         # don't follow junctions (avoids infinite loops)
        "/MT:16",      # multi-threaded copy
        "/NFL", "/NDL", "/NP", "/NJH", "/NJS",  # quiet output
    ]
    if exclude_dirs:
        command.append("/XD")
        command.extend(exclude_dirs)

    started = time.time()
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode >= ROBOCOPY_OK:
        skipped.append(f"robocopy {source} -> code {completed.returncode}")
        log.warning("robocopy %s exited %d: %s", source, completed.returncode, completed.stdout[-400:])

    size = _dir_size(destination)
    log.info("robocopy %s -> %s in %.1fs (%d bytes)", source, destination, time.time() - started, size)
    return size


def _python_mirror(source: Path, destination: Path, excludes: Iterable[str], skipped: list[str]) -> int:
    lowered = {e.lower().replace("/", os.sep).split(os.sep)[-1] for e in excludes}
    copied = 0
    for dirpath, dirnames, filenames in os.walk(source, onerror=lambda _e: None):
        dirnames[:] = [d for d in dirnames if d.lower() not in lowered]
        relative = Path(dirpath).relative_to(source)
        out_dir = destination / relative
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            src_file = Path(dirpath) / filename
            dst_file = out_dir / filename
            try:
                if dst_file.exists() and dst_file.stat().st_mtime >= src_file.stat().st_mtime:
                    copied += dst_file.stat().st_size
                    continue
                shutil.copy2(src_file, dst_file)
                copied += dst_file.stat().st_size
            except OSError as exc:
                skipped.append(f"{src_file}: {exc}")
    return copied


def _dir_size(root: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        for filename in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, filename))
            except OSError:
                continue
    return total


def _write_manifest(app_root: Path, app: DetectedApp, copied: int, skipped: list[str]) -> None:
    manifest = {
        "app": app.name,
        "key": app.key,
        "category": app.category,
        "executable": app.exe_path,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "bytes": copied,
        "sources": [{"from": str(src), "to": dest} for src, dest in app.data_paths],
        "excluded": list(app.excludes),
        "skipped": skipped[:50],
    }
    try:
        (app_root / "_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        log.warning("could not write manifest for %s: %s", app.name, exc)


def _safe_dirname(key: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return cleaned[:60] or "app"


def _report(progress: ProgressFn | None, message: str, fraction: float) -> None:
    if progress:
        progress(message, min(1.0, max(0.0, fraction)))
