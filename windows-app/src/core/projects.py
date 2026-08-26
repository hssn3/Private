"""Your own project folders, wherever they live on disk.

Folder 0 is the thing that gets zipped, but nobody wants to move their working
tree into it. So instead you register the folders you actually code in -
C:\\work, D:\\repos, anything - and they are mirrored into 0\\Projects before
each backup.

.git is deliberately kept: the history is the single most valuable thing in a
source tree. node_modules and friends are not - they are reinstallable and
would multiply the archive size for nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from . import paths
from .collector import _mirror  # same robocopy-or-python mirror the apps use
from .logging_setup import log

ProgressFn = Callable[[str, float], None]

# Reinstallable or regenerable. Excluding these routinely turns a 4 GB tree
# into a 40 MB one without losing a single line you wrote.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "node_modules", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "dist", "build", "out", ".next",
    ".nuxt", ".parcel-cache", ".turbo", ".gradle", "target", "bin", "obj",
    ".cache", "vendor", "Pods", "DerivedData", ".terraform", "coverage",
    ".angular", ".svelte-kit", "bower_components",
)


@dataclass
class ProjectSource:
    path: Path
    name: str
    exists: bool
    size: int = 0

    @property
    def display(self) -> str:
        return str(self.path)


@dataclass
class ProjectResult:
    name: str
    ok: bool
    bytes_copied: int
    message: str


def _folder_name(path: Path) -> str:
    """A safe, unique-ish folder name under 0\\Projects.

    ``D:\\work\\api`` becomes ``api``; a second ``C:\\other\\api`` would collide,
    so the drive letter is folded in when the bare name is already taken.
    """
    base = "".join(c if c.isalnum() or c in "-_. " else "_" for c in path.name).strip()
    return base or "project"


def resolve(raw_paths: Iterable[str]) -> list[ProjectSource]:
    """Turn stored strings into sources, deduplicating destination names."""
    sources: list[ProjectSource] = []
    used: set[str] = set()
    for raw in raw_paths:
        path = paths.expand(raw)
        name = _folder_name(path)
        if name.lower() in used:
            drive = path.drive.replace(":", "").replace("\\", "") or "x"
            name = f"{name}_{drive}"
            suffix = 2
            while name.lower() in used:
                name = f"{_folder_name(path)}_{drive}{suffix}"
                suffix += 1
        used.add(name.lower())
        sources.append(ProjectSource(path=path, name=name, exists=path.is_dir()))
    return sources


def measure(source: ProjectSource, excludes: Sequence[str] = DEFAULT_EXCLUDES) -> int:
    """Size of what would actually be copied, with the excludes applied."""
    if not source.path.is_dir():
        source.size = 0
        return 0
    lowered = {e.lower() for e in excludes}
    total = 0
    for dirpath, dirnames, filenames in os.walk(source.path, onerror=lambda _e: None):
        dirnames[:] = [d for d in dirnames if d.lower() not in lowered]
        for filename in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, filename))
            except OSError:
                continue
    source.size = total
    return total


def collect(
    sources: Sequence[ProjectSource],
    excludes: Sequence[str] = DEFAULT_EXCLUDES,
    progress: ProgressFn | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> list[ProjectResult]:
    """Mirror every registered folder into 0\\Projects\\<name>."""
    target_root = paths.projects_dir()
    results: list[ProjectResult] = []
    total = max(1, len(sources))

    for index, source in enumerate(sources, start=1):
        if cancelled and cancelled():
            break
        if progress:
            progress(f"پروژه: {source.name}", (index - 1) / total)

        if not source.path.is_dir():
            results.append(ProjectResult(source.name, False, 0, "مسیر پیدا نشد"))
            continue

        destination = target_root / source.name
        skipped: list[str] = []
        try:
            copied = _mirror(source.path, destination, tuple(excludes), skipped)
            ok = not skipped
            message = "کپی شد" if ok else f"کپی شد ({len(skipped)} مورد رد شد)"
            results.append(ProjectResult(source.name, True, copied, message))
            log.info("mirrored project %s -> %s (%d bytes)", source.path, destination, copied)
        except Exception as exc:  # noqa: BLE001 - one bad folder must not stop the rest
            results.append(ProjectResult(source.name, False, 0, str(exc)))
            log.warning("project mirror failed for %s: %s", source.path, exc)

        if progress:
            progress(f"پروژه: {source.name}", index / total)

    _write_index(sources, target_root)
    return results


def _write_index(sources: Sequence[ProjectSource], target_root: Path) -> None:
    """Record where each mirrored folder came from, so a restore knows where
    to put it back."""
    lines = [
        "Project folders mirrored into this directory, and where they came from.",
        "",
    ]
    for source in sources:
        lines.append(f"{source.name}  <-  {source.path}")
    lines.append("")
    lines.append("Excluded everywhere: " + ", ".join(DEFAULT_EXCLUDES))
    try:
        (target_root / "_sources.txt").write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        log.warning("could not write project index: %s", exc)
