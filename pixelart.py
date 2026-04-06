#!/usr/bin/env python3
"""
pixelart.py - Convert an image to colored Unicode braille.

Usage:
  python3 pixelart.py <image_path> [target_columns]

Notes:
- Each braille character represents a 2x4 dot cell.
- target_columns is the number of braille characters to print per row.
- Requires: Pillow (pip install pillow)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from PIL import Image, ImageOps


BRAILLE_BIT_BY_OFFSET = {
    (0, 0): 0,
    (0, 1): 1,
    (0, 2): 2,
    (0, 3): 6,
    (1, 0): 3,
    (1, 1): 4,
    (1, 2): 5,
    (1, 3): 7,
}
ALPHA_THRESHOLD = 32
BRAILLE_DENSITY_BOOST = 1.15


@dataclass(frozen=True)
class RenderSize:
    cell_columns: int
    cell_rows: int
    dot_width: int
    dot_height: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render an image as colored braille text.",
    )
    parser.add_argument("image_path", help="Path to the source image")
    parser.add_argument(
        "target_columns",
        nargs="?",
        type=int,
        default=80,
        help="Number of braille characters per output row (default: 80)",
    )
    return parser.parse_args()


def compute_render_size(
    image_width: int, image_height: int, cell_columns: int
) -> RenderSize:
    if cell_columns < 1:
        raise ValueError("target_columns must be at least 1")
    if image_width < 1 or image_height < 1:
        raise ValueError("image must have non-zero size")

    dot_width = cell_columns * 2
    source_aspect = image_height / image_width
    dot_height = max(4, round(dot_width * source_aspect))
    cell_rows = max(1, round(dot_height / 4))
    dot_height = cell_rows * 4
    return RenderSize(
        cell_columns=cell_columns,
        cell_rows=cell_rows,
        dot_width=dot_width,
        dot_height=dot_height,
    )


def resize_image_for_braille(image: Image.Image, size: RenderSize) -> Image.Image:
    return image.resize(
        (size.dot_width, size.dot_height),
        resample=Image.Resampling.LANCZOS,
        reducing_gap=3.0,
    )


def mean_border_luminance(grayscale: Image.Image, alpha: Image.Image) -> float:
    gray_pixels = grayscale.load()
    alpha_pixels = alpha.load()
    values: list[int] = []

    for x in range(grayscale.width):
        if alpha_pixels[x, 0] >= ALPHA_THRESHOLD:
            values.append(gray_pixels[x, 0])
        if (
            grayscale.height > 1
            and alpha_pixels[x, grayscale.height - 1] >= ALPHA_THRESHOLD
        ):
            values.append(gray_pixels[x, grayscale.height - 1])

    for y in range(1, grayscale.height - 1):
        if alpha_pixels[0, y] >= ALPHA_THRESHOLD:
            values.append(gray_pixels[0, y])
        if (
            grayscale.width > 1
            and alpha_pixels[grayscale.width - 1, y] >= ALPHA_THRESHOLD
        ):
            values.append(gray_pixels[grayscale.width - 1, y])

    if values:
        return sum(values) / len(values)

    opaque_values = [
        gray_pixels[x, y]
        for y in range(grayscale.height)
        for x in range(grayscale.width)
        if alpha_pixels[x, y] >= ALPHA_THRESHOLD
    ]
    if not opaque_values:
        return 255.0
    return sum(opaque_values) / len(opaque_values)


def infer_background_is_light(grayscale: Image.Image, alpha: Image.Image) -> bool:
    return mean_border_luminance(grayscale, alpha) >= 127


DITHER_THRESHOLDS = [
    [0.375, 0.875],
    [0.125, 0.625],
    [0.875, 0.375],
    [0.625, 0.125],
]


def ansi_foreground(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


def render_braille(image: Image.Image) -> list[str]:
    grayscale = ImageOps.grayscale(image)
    alpha = image.getchannel("A")
    background_is_light = infer_background_is_light(grayscale, alpha)
    grayscale_pixels = grayscale.load()
    alpha_pixels = alpha.load()
    pixels = image.load()
    lines: list[str] = []

    for y in range(0, image.height, 4):
        segments: list[str] = []
        for x in range(0, image.width, 2):
            bits = 0
            active_colors: list[tuple[int, int, int]] = []

            for dy in range(4):
                for dx in range(2):
                    cx, cy = x + dx, y + dy
                    if alpha_pixels[cx, cy] < ALPHA_THRESHOLD:
                        continue

                    r, g, b, *_ = pixels[cx, cy]
                    intensity = (
                        (max(r, g, b) + min(r, g, b)) / 2 * BRAILLE_DENSITY_BOOST
                    )
                    if background_is_light:
                        intensity = 255 - intensity
                    boosted = intensity
                    threshold = DITHER_THRESHOLDS[dy][dx] * 255

                    if boosted >= threshold:
                        bits |= 1 << BRAILLE_BIT_BY_OFFSET[(dx, dy)]
                        active_colors.append(pixels[cx, cy])

            if bits == 0:
                segments.append(" ")
                continue

            red = sum(color[0] for color in active_colors) // len(active_colors)
            green = sum(color[1] for color in active_colors) // len(active_colors)
            blue = sum(color[2] for color in active_colors) // len(active_colors)
            segments.append(f"{ansi_foreground(red, green, blue)}{chr(0x2800 + bits)}")

        lines.append("".join(segments) + "\033[0m")

    return lines


def main() -> int:
    args = parse_args()

    try:
        source = ImageOps.exif_transpose(Image.open(args.image_path)).convert("RGBA")
        size = compute_render_size(source.width, source.height, args.target_columns)
        resized = resize_image_for_braille(source, size)
        for line in render_braille(resized):
            print(line)
    except Exception as error:  # pragma: no cover - user-facing boundary
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
