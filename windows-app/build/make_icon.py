"""Generate build/app.ico - a shield on a blue/violet gradient.

Committed output means the build needs no design assets, but rerun this if you
want to restyle the icon:  python windows-app/build/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZES = (16, 24, 32, 48, 64, 128, 256)
TOP = (91, 140, 255)
BOTTOM = (139, 92, 246)
OUT = Path(__file__).resolve().parent / "app.ico"


def render(size: int) -> Image.Image:
    scale = 4
    edge = size * scale
    image = Image.new("RGBA", (edge, edge), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Rounded square with a vertical gradient.
    gradient = Image.new("RGBA", (1, edge))
    for y in range(edge):
        ratio = y / max(1, edge - 1)
        gradient.putpixel(
            (0, y),
            (
                round(TOP[0] + (BOTTOM[0] - TOP[0]) * ratio),
                round(TOP[1] + (BOTTOM[1] - TOP[1]) * ratio),
                round(TOP[2] + (BOTTOM[2] - TOP[2]) * ratio),
                255,
            ),
        )
    gradient = gradient.resize((edge, edge))

    mask = Image.new("L", (edge, edge), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, edge - 1, edge - 1), radius=edge // 4, fill=255
    )
    image.paste(gradient, (0, 0), mask)

    # Shield.
    margin = edge * 0.26
    top = edge * 0.20
    bottom = edge * 0.82
    shield = [
        (edge / 2, top),
        (edge - margin, top + edge * 0.08),
        (edge - margin, edge * 0.52),
        (edge / 2, bottom),
        (margin, edge * 0.52),
        (margin, top + edge * 0.08),
    ]
    draw.polygon(shield, fill=(255, 255, 255, 235))

    # Check mark inside the shield.
    draw.line(
        [(edge * 0.40, edge * 0.49), (edge * 0.47, edge * 0.58), (edge * 0.62, edge * 0.38)],
        fill=(59, 92, 190, 255),
        width=max(2, edge // 16),
        joint="curve",
    )

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    frames = [render(size) for size in SIZES]
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
