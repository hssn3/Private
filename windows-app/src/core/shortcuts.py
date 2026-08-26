"""Put a .lnk for every selected app into 0\\Shortcuts.

After a restore you extract folder 0 on the new machine, reinstall the apps,
and these shortcuts give you one place to launch everything from.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from . import paths
from .detect import DetectedApp
from .logging_setup import log

IS_WINDOWS = sys.platform == "win32"


def create_all(apps: Sequence[DetectedApp]) -> tuple[int, list[str]]:
    """Returns (created_count, errors)."""
    target = paths.shortcuts_dir()
    created = 0
    errors: list[str] = []

    for app in apps:
        if not app.exe_path:
            continue
        try:
            if _create(app, target):
                created += 1
        except Exception as exc:  # noqa: BLE001 - a bad name must not stop the rest
            errors.append(f"{app.name}: {exc}")
            log.warning("shortcut failed for %s: %s", app.name, exc)

    _write_index(apps, target)
    log.info("created %d shortcuts (%d errors)", created, len(errors))
    return created, errors


def _create(app: DetectedApp, target: Path) -> bool:
    filename = _safe_filename(app.name)
    if IS_WINDOWS:
        link = target / f"{filename}.lnk"
        return _create_lnk(app, link)
    # Non-Windows (dev machines): drop a readable stub so tests can assert.
    stub = target / f"{filename}.txt"
    stub.write_text(app.exe_path or "", encoding="utf-8")
    return True


def _create_lnk(app: DetectedApp, link: Path) -> bool:
    import pythoncom
    from win32com.client import Dispatch

    pythoncom.CoInitialize()
    try:
        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(link))
        shortcut.TargetPath = app.exe_path
        shortcut.WorkingDirectory = str(Path(app.exe_path).parent)
        shortcut.IconLocation = app.exe_path
        shortcut.Description = f"{app.name} - {app.category}"
        shortcut.save()
        return True
    finally:
        pythoncom.CoUninitialize()


def _write_index(apps: Sequence[DetectedApp], target: Path) -> None:
    """A plain-text list of what was installed, for the day the .lnk targets
    no longer exist because you are on a fresh Windows."""
    lines = [
        "Apps that were installed on the source machine.",
        "Reinstall these, then restore their data from 0\\Apps\\.",
        "",
    ]
    for app in sorted(apps, key=lambda a: (a.category, a.name)):
        lines.append(f"[{app.category}] {app.name}")
        if app.exe_path:
            lines.append(f"    exe : {app.exe_path}")
        for source, dest in app.data_paths:
            lines.append(f"    data: {source}  ->  0\\Apps\\{app.key}\\{dest}")
        lines.append("")
    try:
        (target / "_installed-apps.txt").write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        log.warning("could not write shortcut index: %s", exc)


_ILLEGAL = '<>:"/\\|?*'


def _safe_filename(name: str) -> str:
    cleaned = "".join("-" if c in _ILLEGAL else c for c in name).strip().rstrip(".")
    return cleaned[:80] or "app"
