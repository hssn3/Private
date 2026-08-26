# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe: one windowed .exe with no external dependencies.

Build:  pyinstaller --noconfirm windows-app/build/BackupSuite.spec
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

SPEC_DIR = Path(SPECPATH).resolve()
SRC = SPEC_DIR.parent / "src"

datas = [(str(SPEC_DIR / "app.ico"), ".")]
binaries = []
hiddenimports = [
    "customtkinter",
    "PIL._tkinter_finder",
    "arabic_reshaper",
    "bidi",
    "bidi.algorithm",
    "win32com.client",
    "win32timezone",
    "pythoncom",
    "pywintypes",
]

# customtkinter ships theme JSON and fonts that must ride along.
for package in ("customtkinter", "arabic_reshaper"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "matplotlib", "numpy", "pandas", "scipy", "pytest",
        "notebook", "IPython", "setuptools",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BackupSuite",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    icon=str(SPEC_DIR / "app.ico"),
    version=None,
)
