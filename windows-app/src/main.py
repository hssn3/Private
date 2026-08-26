"""Entry point for Backup Suite.

Run from source:   python windows-app/src/main.py
Frozen:            0\BackupSuite.exe
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# When frozen, PyInstaller puts our package root on sys.path already; when
# running from source we add it ourselves so `from core import ...` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import paths  # noqa: E402
from core.logging_setup import log  # noqa: E402


def _fatal(exc: BaseException) -> None:
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log.error("fatal error:\n%s", detail)
    try:
        import tkinter.messagebox as messagebox

        messagebox.showerror(
            "Backup Suite",
            f"برنامه اجرا نشد:\n\n{exc}\n\nجزئیات در Data\\backup-suite.log ثبت شد.",
        )
    except Exception:  # noqa: BLE001 - no display available
        print(detail, file=sys.stderr)


def main() -> int:
    try:
        paths.ensure_layout()
        log.info("starting Backup Suite from %s", paths.root_dir())

        # Keep customtkinter's own asset lookup happy inside the one-file bundle.
        if getattr(sys, "frozen", False):
            os.environ.setdefault("MPLBACKEND", "Agg")

        from ui.main_window import MainWindow

        window = MainWindow()
        window.mainloop()
        return 0
    except Exception as exc:  # noqa: BLE001 - last line of defence
        _fatal(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
