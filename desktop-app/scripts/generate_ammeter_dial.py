"""Generate a calibrated ammeter dial image.

The geometry is tuned for the reference photo supplied with the project:
768x768 px, with the scale center outside the visible lower-right body.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CANVAS = 768
SCALE = 4

# The visible scale is a circular arc whose center sits near the lower-right
# screw/body area.  These angles are measured from the reference image so the
# labeled ticks stay at the same visual positions as the photo.
CENTER = (614.0, 614.0)
ANGLE_STOPS = (
    (0.0, 180.0),
    (50.0, 197.0),
    (100.0, 224.0),
    (150.0, 249.0),
    (200.0, 270.0),
)
OUTER_RADIUS = 560.0
MINOR_LEN = 34.0
MID_LEN = 42.0
MAJOR_LEN = 45.0

INK = (31, 19, 18, 255)
TRANSPARENT = (0, 0, 0, 0)
BODY = (40, 37, 34, 255)


def scaled_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for name in candidates:
        try:
            return ImageFont.truetype(name, size * SCALE)
        except OSError:
            continue
    return ImageFont.load_default(size * SCALE)


def interpolate_angle(value: float) -> float:
    for (v0, a0), (v1, a1) in zip(ANGLE_STOPS, ANGLE_STOPS[1:]):
        if v0 <= value <= v1:
            t = (value - v0) / (v1 - v0)
            return a0 + (a1 - a0) * t
    raise ValueError(f"value out of range: {value}")


def polar(angle_deg: float, radius: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    return (
        (CENTER[0] + math.cos(angle) * radius) * SCALE,
        (CENTER[1] + math.sin(angle) * radius) * SCALE,
    )


def draw_tick(draw: ImageDraw.ImageDraw, value: int) -> None:
    if value % 50 == 0:
        length = MAJOR_LEN
        width = 8
    elif value % 25 == 0:
        length = MID_LEN
        width = 3
    else:
        length = MINOR_LEN
        width = 2

    angle = interpolate_angle(value)
    start = polar(angle, OUTER_RADIUS - length)
    end = polar(angle, OUTER_RADIUS)
    draw.line((start, end), fill=INK, width=width * SCALE)


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    *,
    anchor: str = "mm",
    fill: tuple[int, int, int, int] = INK,
) -> None:
    draw.text((xy[0] * SCALE, xy[1] * SCALE), text, font=font, anchor=anchor, fill=fill)


def draw_face(draw: ImageDraw.ImageDraw) -> None:
    for value in range(0, 201, 5):
        draw_tick(draw, value)


def draw_labels(draw: ImageDraw.ImageDraw) -> None:
    font_large = scaled_font(["arial.ttf", "DejaVuSans.ttf"], 84)
    font_num = scaled_font(["arial.ttf", "DejaVuSans.ttf"], 44)
    font_small = scaled_font(["arial.ttf", "DejaVuSans.ttf"], 21)
    font_logo = scaled_font(["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"], 38)
    font_model = scaled_font(["arial.ttf", "DejaVuSans.ttf"], 42)

    draw_text(draw, (123, 112), "A", font_large)

    number_positions = {
        "0": (162, 611),
        "50": (193, 478),
        "100": (305, 307),
        "150": (463, 174),
        "200": (617, 169),
    }
    for text, xy in number_positions.items():
        draw_text(draw, xy, text, font_num)

    # Manufacturer mark and model block.
    draw_text(draw, (633, 330), "PulseMeter", font_logo)


def draw_body_cutout(draw: ImageDraw.ImageDraw) -> None:
    # Lower-right dark mechanism housing visible in the reference image.
    polygon = [
        (405, 768),
        (768, 768),
        (768, 401),
        (681, 503),
        (587, 503),
        (552, 510),
        (526, 535),
        (511, 569),
        (507, 614),
        (507, 768),
    ]
    draw.polygon([(x * SCALE, y * SCALE) for x, y in polygon], fill=BODY)
    draw.rounded_rectangle(
        (507 * SCALE, 503 * SCALE, 742 * SCALE, 792 * SCALE),
        radius=84 * SCALE,
        fill=BODY,
    )
    draw.polygon(
        [
            (405 * SCALE, 768 * SCALE),
            (507 * SCALE, 614 * SCALE),
            (507 * SCALE, 768 * SCALE),
        ],
        fill=BODY,
    )


def draw_screws(draw: ImageDraw.ImageDraw) -> None:
    for x, y, r in ((690, 417, 14), (417, 690, 14)):
        draw.ellipse(
            ((x - r) * SCALE, (y - r) * SCALE, (x + r) * SCALE, (y + r) * SCALE),
            fill=INK,
        )


def generate(output: Path) -> None:
    image = Image.new("RGBA", (CANVAS * SCALE, CANVAS * SCALE), TRANSPARENT)
    draw = ImageDraw.Draw(image, "RGBA")

    draw_face(draw)
    draw_labels(draw)
    draw_screws(draw)
    # draw_body_cutout(draw)

    image = image.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)
    image.save(output)
    print(f"Saved to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the calibrated ammeter dial PNG.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("meter_dial_generated.png"),
        help="Output PNG path.",
    )
    args = parser.parse_args()
    print(f"Generating dial to {args.output}")
    generate(args.output)


if __name__ == "__main__":
    main()
