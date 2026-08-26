"""Where everything lives.

The whole product is one portable folder called ``0``:

    0\
      BackupSuite.exe      <- this program
      Data\                <- config, logs, cached icons
      Apps\                <- collected app data / profiles / settings
      Projects\            <- your own source code and project files
      Shortcuts\           <- .lnk shortcuts to every app you selected

Everything is resolved relative to the executable, so moving folder ``0`` to a
different drive or a different machine just works.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def root_dir() -> Path:
    """The ``0`` folder: the directory containing the exe (or the repo when
    running from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # Running from source: <repo>/windows-app/src/core/paths.py -> <repo>/0
    dev_root = Path(__file__).resolve().parents[3] / "0"
    dev_root.mkdir(parents=True, exist_ok=True)
    return dev_root


DATA_DIRNAME = "Data"
APPS_DIRNAME = "Apps"
PROJECTS_DIRNAME = "Projects"
SHORTCUTS_DIRNAME = "Shortcuts"


def data_dir() -> Path:
    return _ensure(root_dir() / DATA_DIRNAME)


def apps_dir() -> Path:
    return _ensure(root_dir() / APPS_DIRNAME)


def projects_dir() -> Path:
    return _ensure(root_dir() / PROJECTS_DIRNAME)


def shortcuts_dir() -> Path:
    return _ensure(root_dir() / SHORTCUTS_DIRNAME)


def icon_cache_dir() -> Path:
    return _ensure(data_dir() / "icons")


def log_file() -> Path:
    return data_dir() / "backup-suite.log"


def config_file() -> Path:
    return data_dir() / "config.json"


def state_file() -> Path:
    return data_dir() / "state.json"


def ensure_layout() -> None:
    """Create the four standard subfolders on first run."""
    for maker in (data_dir, apps_dir, projects_dir, shortcuts_dir):
        maker()
    readme = projects_dir() / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Put your source code and project files in this folder.\n"
            "Everything inside folder 0 is included in every backup.\n",
            encoding="utf-8",
        )


def expand(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
