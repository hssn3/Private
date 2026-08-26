"""Persistent settings, stored as JSON inside 0\\Data."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from typing import Any

from . import paths

# The "cycle rule": keep this many archives, then the oldest is permanently
# deleted every time a new one lands.
DEFAULT_KEEP = 10
DEFAULT_INTERVAL_MINUTES = 10
DEFAULT_BACKUP_DIR = "D:\\"


@dataclass
class Config:
    backup_dir: str = DEFAULT_BACKUP_DIR
    keep_count: int = DEFAULT_KEEP
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES
    schedule_enabled: bool = False
    selected_apps: list[str] = field(default_factory=list)

    # Your own source folders, mirrored into 0\Projects before every backup.
    project_sources: list[str] = field(default_factory=list)
    sync_projects_before_backup: bool = True

    # Cloud target (the Railway file manager)
    cloud_enabled: bool = False
    cloud_url: str = ""
    cloud_token: str = ""

    # Behaviour
    skip_unchanged: bool = True
    exclude_caches: bool = True
    compression_level: int = 6
    make_shortcuts: bool = True

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class ConfigStore:
    """Thread-safe load/save wrapper. The scheduler thread and the UI thread
    both touch config, so every access goes through the lock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config = self._load()

    def _load(self) -> Config:
        path = paths.config_file()
        if not path.exists():
            return Config()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return Config()
        known = {f for f in Config.__dataclass_fields__}
        return Config(**{k: v for k, v in raw.items() if k in known})

    @property
    def current(self) -> Config:
        with self._lock:
            return self._config

    def update(self, **changes: Any) -> Config:
        with self._lock:
            for key, value in changes.items():
                if key in Config.__dataclass_fields__:
                    setattr(self._config, key, value)
            self.save()
            return self._config

    def save(self) -> None:
        with self._lock:
            paths.data_dir()
            tmp = paths.config_file().with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._config.to_json(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(paths.config_file())
