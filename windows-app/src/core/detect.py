"""Find which of the known apps are actually installed on this machine.

Two passes:
  1. The curated catalog - check every known exe location. These are the apps
     we know how to back up properly.
  2. The registry's uninstall keys - anything else the user has installed. We
     cannot guess where their data lives, but we can still show them and put a
     shortcut in 0\\Shortcuts.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import catalog, paths
from .logging_setup import log

IS_WINDOWS = sys.platform == "win32"


@dataclass
class DetectedApp:
    key: str
    name: str
    category: str
    emoji: str
    exe_path: str | None
    known: bool
    data_paths: list[tuple[Path, str]]   # (source, dest sub-path)
    excludes: tuple[str, ...]
    note: str = ""
    icon_path: str | None = None
    est_size: int = 0

    @property
    def has_data(self) -> bool:
        return bool(self.data_paths)


def _first_existing(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        expanded = paths.expand(candidate)
        if expanded.exists():
            return str(expanded)
    return None


def _resolve_data(app: catalog.KnownApp) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for source in app.data:
        expanded = paths.expand(source.src)
        if expanded.exists():
            found.append((expanded, source.dest))
    return found


def _scan_catalog() -> list[DetectedApp]:
    detected: list[DetectedApp] = []
    for app in catalog.CATALOG:
        exe = _first_existing(app.exe_candidates)
        data = _resolve_data(app)
        # An app counts as present if we found its executable OR its data. A
        # CLI installed via npm may have no exe we recognise but a very
        # valuable config directory.
        if not exe and not data:
            continue
        detected.append(
            DetectedApp(
                key=app.key,
                name=app.name,
                category=app.category,
                emoji=app.emoji,
                exe_path=exe,
                known=True,
                data_paths=data,
                excludes=app.excludes,
                note=app.note,
            )
        )
    return detected


def _scan_registry(skip_names: set[str]) -> list[DetectedApp]:
    """Everything else in Add/Remove Programs."""
    if not IS_WINDOWS:
        return []
    import winreg

    hives = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0),
    )

    seen: set[str] = set()
    results: list[DetectedApp] = []

    for hive, subkey, flag in hives:
        try:
            root = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | flag)
        except OSError:
            continue
        with root:
            count = winreg.QueryInfoKey(root)[0]
            for index in range(count):
                try:
                    name = winreg.EnumKey(root, index)
                    with winreg.OpenKey(root, name) as entry:
                        display = _reg_value(entry, "DisplayName")
                        if not display:
                            continue
                        if _reg_value(entry, "SystemComponent") == 1:
                            continue
                        if _reg_value(entry, "ParentKeyName"):
                            continue
                        lowered = display.lower()
                        if lowered in seen or any(s in lowered for s in skip_names):
                            continue
                        if _is_noise(lowered):
                            continue
                        seen.add(lowered)
                        exe = _guess_exe(entry)
                        results.append(
                            DetectedApp(
                                key=f"reg::{lowered}",
                                name=display,
                                category="سایر برنامه‌ها",
                                emoji="🧱",
                                exe_path=exe,
                                known=False,
                                data_paths=[],
                                excludes=(),
                                note="فقط شورتکات ساخته می‌شود (مسیر دیتایش ناشناخته است)",
                            )
                        )
                except OSError:
                    continue

    results.sort(key=lambda a: a.name.lower())
    return results


_NOISE = (
    "microsoft visual c++", "microsoft .net", "windows sdk", "update for",
    "redistributable", "driver", "runtime", "kb2", "kb3", "kb4", "kb5",
    "microsoft edge webview", "windows software development",
)


def _is_noise(lowered: str) -> bool:
    return any(token in lowered for token in _NOISE)


def _reg_value(key, name: str):
    import winreg
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except OSError:
        return None


def _guess_exe(entry) -> str | None:
    icon = _reg_value(entry, "DisplayIcon")
    if icon:
        candidate = str(icon).split(",")[0].strip().strip('"')
        if candidate.lower().endswith(".exe") and os.path.exists(candidate):
            return candidate
    location = _reg_value(entry, "InstallLocation")
    if location and os.path.isdir(location):
        try:
            for item in sorted(Path(location).glob("*.exe")):
                return str(item)
        except OSError:
            pass
    return None


def estimate_size(app: DetectedApp) -> int:
    """Rough byte count of what we would copy, so the UI can warn about a
    multi-gigabyte browser profile before the user commits to it."""
    total = 0
    for source, _dest in app.data_paths:
        total += _tree_size(source, app.excludes)
    app.est_size = total
    return total


def _tree_size(root: Path, excludes: tuple[str, ...]) -> int:
    if root.is_file():
        try:
            return root.stat().st_size
        except OSError:
            return 0
    lowered = {e.lower().replace("/", os.sep) for e in excludes}
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        dirnames[:] = [d for d in dirnames if d.lower() not in lowered]
        for filename in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, filename))
            except OSError:
                continue
    return total


def scan(include_registry: bool = True) -> list[DetectedApp]:
    known = _scan_catalog()
    log.info("detected %d known apps", len(known))
    apps = list(known)
    if include_registry:
        skip = {a.name.lower() for a in known}
        extra = _scan_registry(skip)
        log.info("detected %d additional installed programs", len(extra))
        apps.extend(extra)
    return apps
