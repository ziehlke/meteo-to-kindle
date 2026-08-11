"""Image processing utilities for the weather display."""

from pathlib import Path

import numpy as np
from PIL import Image

from config import (
    CAQI_CHART_POSITION,
    CAQI_FILENAME,
    CROP_OPERATIONS,
    FINAL_CROP_COORDS,
    GRAY_COLORS_TO_REPLACE,
    GRAY_TARGET_COLOR,
    TARGET_IMAGE_WIDTH,
    TEMPLATE_PROCESSED_FILENAME,
    WHITE_COLORS_TO_REPLACE,
    WHITE_TARGET_COLOR,
)

# A crop box where None means "edge of the image" and negatives count
# back from that edge, e.g. (35, 122, -40, 547).
Box = tuple[int | None, int | None, int | None, int | None]


class WeatherImageProcessor:
    """Handles image processing operations for weather data."""

    def __init__(self, home_dir: Path):
        """Initialize with home directory path."""
        self.home_dir = home_dir

    def crop_image(self, image: Image.Image) -> Image.Image:
        """Rearrange sections of the meteogram and crop it to the content area."""
        img = image.copy()

        # Move each source section over its target section
        for source_box, target_box in CROP_OPERATIONS:
            section = img.crop(self._resolve_box(source_box, img.size))
            section.load()
            img.paste(section, self._resolve_box(target_box, img.size))

        final = img.crop(self._resolve_box(FINAL_CROP_COORDS, img.size))
        final.load()
        return final

    def remove_logo(self, image: Image.Image) -> Image.Image:
        """Remove the logo by replacing its exact colors."""
        pixels = np.array(image)
        replacements = [
            (WHITE_COLORS_TO_REPLACE, WHITE_TARGET_COLOR),
            (GRAY_COLORS_TO_REPLACE, GRAY_TARGET_COLOR),
        ]
        for source_colors, target_color in replacements:
            for color in source_colors:
                mask = np.all(pixels == color, axis=-1)
                pixels[mask] = target_color
        return Image.fromarray(pixels)

    def adjust_size(self, image: Image.Image) -> Image.Image:
        """Resize image to the target width and paste it onto the template."""
        ratio = TARGET_IMAGE_WIDTH / image.size[0]
        new_height = int(image.size[1] * ratio)
        resized = image.resize(
            (TARGET_IMAGE_WIDTH, new_height), Image.Resampling.LANCZOS
        )
        with Image.open(self.home_dir / TEMPLATE_PROCESSED_FILENAME) as template:
            result = template.copy()
        result.paste(resized, (0, 0))
        return result

    def paste_caqi(self, image: Image.Image) -> Image.Image:
        """Paste the CAQI history chart onto the image."""
        result = image.copy()
        with Image.open(self.home_dir / CAQI_FILENAME) as caqi:
            result.paste(caqi, CAQI_CHART_POSITION)
        return result

    @staticmethod
    def _resolve_box(box: Box, img_size: tuple[int, int]) -> tuple[int, int, int, int]:
        """Resolve empty/negative box coordinates to absolute pixel values."""
        width, height = img_size

        def resolve(value: int | None, axis_max: int) -> int:
            if value is None:
                return axis_max
            if value < 0:
                return axis_max + value
            return value

        x1, y1, x2, y2 = box
        return (
            resolve(x1, width),
            resolve(y1, height),
            resolve(x2, width),
            resolve(y2, height),
        )
