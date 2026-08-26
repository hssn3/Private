"""Pull the real icon out of an .exe so the picker shows what the user
recognises instead of a generic box.

Uses ExtractIconEx + a 32-bit DIB blit through pywin32, then caches the result
as a PNG in 0\\Data\\icons. If anything about that fails (no pywin32, an exe
with no icon, a permission error) the UI falls back to the catalog emoji.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from . import paths
from .logging_setup import log

IS_WINDOWS = sys.platform == "win32"
ICON_SIZE = 48


def _cache_path(exe_path: str) -> Path:
    digest = hashlib.sha1(exe_path.lower().encode("utf-8")).hexdigest()[:16]
    return paths.icon_cache_dir() / f"{digest}.png"


def extract(exe_path: str | None) -> str | None:
    """Return a path to a PNG of the exe's icon, or None."""
    if not exe_path or not IS_WINDOWS:
        return None
    if not Path(exe_path).exists():
        return None

    cached = _cache_path(exe_path)
    if cached.exists():
        return str(cached)

    try:
        png = _extract_windows(exe_path, cached)
    except Exception as exc:  # noqa: BLE001 - icon extraction is best-effort
        log.debug("icon extraction failed for %s: %s", exe_path, exc)
        return None
    return png


def _extract_windows(exe_path: str, out_path: Path) -> str | None:
    import win32con
    import win32gui
    import win32ui
    from PIL import Image

    large, small = win32gui.ExtractIconEx(exe_path, 0)
    handles = large + small
    if not handles:
        return None

    hicon = handles[0]
    size = win32con.SM_CXICON and ICON_SIZE

    screen_dc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
    mem_dc = screen_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(screen_dc, size, size)
    mem_dc.SelectObject(bitmap)

    try:
        mem_dc.DrawIcon((0, 0), hicon)
        info = bitmap.GetInfo()
        bits = bitmap.GetBitmapBits(True)
        image = Image.frombuffer(
            "RGBA",
            (info["bmWidth"], info["bmHeight"]),
            bits,
            "raw",
            "BGRA",
            0,
            1,
        )
        # DrawIcon gives us an opaque black background where the icon is
        # transparent; strip pure black so the glass panel shows through.
        image = _restore_alpha(image)
        image.save(out_path, "PNG")
        return str(out_path)
    finally:
        for handle in handles:
            try:
                win32gui.DestroyIcon(handle)
            except Exception:  # noqa: BLE001
                pass
        try:
            win32gui.DeleteObject(bitmap.GetHandle())
            mem_dc.DeleteDC()
            screen_dc.DeleteDC()
        except Exception:  # noqa: BLE001
            pass


def _restore_alpha(image):
    from PIL import Image

    if image.mode != "RGBA":
        image = image.convert("RGBA")
    pixels = image.load()
    width, height = image.size
    opaque = False
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a:
                opaque = True
                break
        if opaque:
            break
    if opaque:
        return image
    # Every alpha byte was zero - the blit lost the channel. Treat pure black
    # as transparent instead.
    out = Image.new("RGBA", image.size)
    out_pixels = out.load()
    for y in range(height):
        for x in range(width):
            r, g, b, _a = pixels[x, y]
            out_pixels[x, y] = (r, g, b, 0 if (r, g, b) == (0, 0, 0) else 255)
    return out
