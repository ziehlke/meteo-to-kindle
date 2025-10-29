"""Image processing utilities for weather display."""

from pathlib import Path
from typing import Tuple

from PIL import Image

from config import (
    TARGET_IMAGE_WIDTH, CROP_OPERATIONS, FINAL_CROP_COORDS,
    CAQI_CHART_POSITION, WHITE_COLORS_TO_REPLACE, GRAY_COLORS_TO_REPLACE,
    WHITE_TARGET_COLOR, GRAY_TARGET_COLOR, TEMPLATE_PROCESSED_FILENAME,
    CAQI_FILENAME
)


class WeatherImageProcessor:
    """Handles image processing operations for weather data."""

    def __init__(self, home_dir: Path):
        """Initialize with home directory path."""
        self.home_dir = home_dir

    def crop_image(self, image: Image.Image) -> Image.Image:
        """Apply custom cropping to the weather image."""
        img = image.copy()

        # Apply first crop and paste
        for i, (crop_coords, target_coords) in enumerate(CROP_OPERATIONS):
            img_down = img.crop(self._resolve_coords(crop_coords, img.size))
            img_down.load()
            target = self._resolve_coords(target_coords, img.size)
            img.paste(img_down, target)

        # Final crop
        final_coords = self._resolve_coords(FINAL_CROP_COORDS, img.size)
        img = img.crop(final_coords)
        img.load()
        return img

    def remove_logo(self, image: Image.Image) -> Image.Image:
        """Remove logo by replacing specific colors."""
        img = image.copy()
        pixdata = img.load()

        for y in range(img.size[1]):
            for x in range(img.size[0]):
                pixel = pixdata[x, y]
                if pixel in WHITE_COLORS_TO_REPLACE:
                    pixdata[x, y] = WHITE_TARGET_COLOR
                elif pixel in GRAY_COLORS_TO_REPLACE:
                    pixdata[x, y] = GRAY_TARGET_COLOR

        return img

    def adjust_size(self, image: Image.Image) -> Image.Image:
        """Resize image and paste onto template."""
        ratio = TARGET_IMAGE_WIDTH / float(image.size[0])
        new_height = int(float(image.size[1]) * float(ratio))
        resized_img = image.resize((TARGET_IMAGE_WIDTH, new_height), Image.LANCZOS)
        template = Image.open(self.home_dir / TEMPLATE_PROCESSED_FILENAME)
        template.paste(resized_img)
        return template

    def paste_caqi(self, image: Image.Image) -> Image.Image:
        """Paste CAQI chart onto the main image."""
        caqi = Image.open(self.home_dir / CAQI_FILENAME)
        width, height = caqi.size
        caqi.load()
        target_coords = (*CAQI_CHART_POSITION, CAQI_CHART_POSITION[0] + width,
                        CAQI_CHART_POSITION[1] + height)
        image.paste(caqi, target_coords)
        image.load()
        return image

    def _resolve_coords(
        self, coords: Tuple, img_size: Tuple[int, int]
    ) -> Tuple[int, int, int, int]:
        """Resolve relative coordinates to absolute pixel values."""
        width, height = img_size
        result = []
        for coord in coords:
            if coord is None:
                result.append(width if len(result) == 2 else height)
            elif coord < 0:
                result.append(width + coord if len(result) == 2 else height + coord)
            else:
                result.append(coord)
        return tuple(result)
