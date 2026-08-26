"""Colours, fonts, and Persian text shaping.

Tk has no Arabic shaping engine: without help it renders Persian as isolated,
left-to-right letterforms. Every user-facing string therefore goes through
``fa()``, which joins the glyphs and applies the bidi algorithm before Tk ever
sees it.
"""

from __future__ import annotations

import tkinter.font as tkfont

# ------------------------------------------------------------------ palette
BG = "#070b16"
BG_GRADIENT_TOP = "#0d1428"
BG_GRADIENT_BOTTOM = "#05070f"

GLASS = "#141c33"          # frosted panel
GLASS_LIGHT = "#1b2544"    # hovered / raised panel
GLASS_EDGE = "#2a3760"     # 1px border

TEXT = "#eaf0ff"
TEXT_MUTED = "#93a1c4"
TEXT_DIM = "#63719a"

ACCENT = "#5b8cff"
ACCENT_HOVER = "#7aa2ff"
ACCENT_2 = "#8b5cf6"
OK = "#34d399"
WARN = "#fbbf24"
BAD = "#f87171"

RADIUS = 16
RADIUS_SM = 12

# ------------------------------------------------------------------- fonts
FONT_FAMILY = "Segoe UI"
FONT_FALLBACKS = ("Vazirmatn", "Segoe UI", "Tahoma", "Arial")


def pick_font_family() -> str:
    """First installed family that can actually draw Persian."""
    global FONT_FAMILY
    try:
        available = {name.lower() for name in tkfont.families()}
    except Exception:  # noqa: BLE001 - no Tk root yet
        return FONT_FAMILY
    for candidate in FONT_FALLBACKS:
        if candidate.lower() in available:
            FONT_FAMILY = candidate
            break
    return FONT_FAMILY


def font(size: int = 13, weight: str = "normal") -> tuple[str, int, str]:
    return (FONT_FAMILY, size, weight)


# ------------------------------------------------------------ text shaping
try:  # pragma: no cover - depends on optional deps being installed
    import arabic_reshaper
    from bidi.algorithm import get_display

    _SHAPING = True
except ImportError:  # pragma: no cover
    _SHAPING = False


def fa(text: str) -> str:
    """Shape a Persian string for display in Tk widgets."""
    if not _SHAPING or not text:
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # noqa: BLE001 - never let a label crash the UI
        return text


def human_size(num_bytes: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} TB"


def human_duration(seconds: float) -> str:
    if seconds < 60:
        return fa(f"{seconds:.0f} ثانیه")
    minutes, secs = divmod(int(seconds), 60)
    return fa(f"{minutes} دقیقه و {secs} ثانیه")
