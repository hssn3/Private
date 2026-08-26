import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from core import paths  # noqa: E402


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    """Point the whole app at a throwaway folder 0."""
    root = tmp_path / "0"
    root.mkdir()
    monkeypatch.setattr(paths, "root_dir", lambda: root)
    paths.ensure_layout()
    return root
