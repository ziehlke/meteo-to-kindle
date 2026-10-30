"""Fetch the weather forecast, overlay air quality data and publish the result."""

import shutil
import subprocess
from pathlib import Path

from .airly import Airly
from .config import (
    IMAGE_BITS,
    METEOGRAM_FILENAME,
    OUTPUT_DIR,
    OUTPUT_FILENAME,
    SMB_SHARE_PATH,
)
from .image_processor import WeatherImageProcessor
from .meteo import MeteoClient
from .meteogram import render_meteogram


def publish_to_share(output: Path, share_path: Path) -> None:
    """Compress the output PNG with pngcrush and copy it to the SMB share."""
    pngcrush = shutil.which("pngcrush")
    if pngcrush is None:
        return
    # fixed argument list, shell=False
    subprocess.run([pngcrush, "-c", "0", str(output)], check=True, cwd=output.parent)  # noqa: S603
    # shutil.move survives shares on a different filesystem (Path.replace
    # would fail with EXDEV); same device it is a plain rename.
    shutil.move(output.parent / "pngout.png", share_path / "pngout.png")


def main() -> None:
    """Main execution function."""
    # Generate air quality data
    airly = Airly()
    airly.fill_template()

    # Fetch forecast data and render our own meteogram
    data = MeteoClient().fetch()
    meteogram = render_meteogram(data, OUTPUT_DIR / METEOGRAM_FILENAME)

    # Compose the final display image
    processor = WeatherImageProcessor(OUTPUT_DIR)
    image = processor.paste_meteogram(meteogram)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / OUTPUT_FILENAME
    image.save(output, bits=IMAGE_BITS)

    publish_to_share(output, SMB_SHARE_PATH)


if __name__ == "__main__":
    main()
