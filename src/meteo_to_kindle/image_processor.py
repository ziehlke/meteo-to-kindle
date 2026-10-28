"""Compose the final weather display image for the Kindle."""

from pathlib import Path

from PIL import Image

from .config import (
    CAQI_CHART_POSITION,
    CAQI_FILENAME,
    TARGET_IMAGE_WIDTH,
    TEMPLATE_PROCESSED_FILENAME,
)


class WeatherImageProcessor:
    """Composes the meteogram and CAQI chart onto the template."""

    def __init__(self, output_dir: Path):
        """Initialize with the directory for generated intermediate files."""
        self.output_dir = output_dir

    def paste_meteogram(self, meteogram_path: Path) -> Image.Image:
        """Paste the rendered meteogram at the top of the template."""
        with Image.open(meteogram_path) as meteogram:
            resized = self._fit_width(meteogram.convert("L"))
        with Image.open(self.output_dir / TEMPLATE_PROCESSED_FILENAME) as template:
            result = template.copy()
        result.paste(resized, (0, 0))
        return result

    def paste_caqi(self, image: Image.Image) -> Image.Image:
        """Paste the CAQI history chart onto the image."""
        result = image.copy()
        with Image.open(self.output_dir / CAQI_FILENAME) as caqi:
            result.paste(caqi, CAQI_CHART_POSITION)
        return result

    @staticmethod
    def _fit_width(image: Image.Image) -> Image.Image:
        """Resize the image to the target width, keeping its aspect ratio."""
        if image.size[0] == TARGET_IMAGE_WIDTH:
            return image
        new_height = int(image.size[1] * TARGET_IMAGE_WIDTH / image.size[0])
        return image.resize((TARGET_IMAGE_WIDTH, new_height), Image.Resampling.LANCZOS)
