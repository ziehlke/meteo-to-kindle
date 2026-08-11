"""Fetch the meteo.pl forecast, overlay air quality data and publish the result."""

import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from time import sleep

import httpx
from PIL import Image

from airly import Airly
from config import (
    HOME_DIR,
    IMAGE_BITS,
    KRAKOW_COORDS,
    OUTPUT_FILENAME,
    RETRY_DELAY_SECONDS,
    SMB_SHARE_PATH,
    WEATHER_URL_TEMPLATE,
)
from image_processor import WeatherImageProcessor


def fetch_weather_image(url: str, max_retries: int = 3) -> Image.Image:
    """Fetch weather image from URL with retry logic.

    Downloads the image directly into memory without saving to disk.
    Returns a PIL Image object in RGB format.
    """
    with httpx.Client(follow_redirects=True) as client:
        for attempt in range(1, max_retries + 1):
            try:
                response = client.get(url)
                response.raise_for_status()
                with Image.open(BytesIO(response.content)) as img:
                    return img.convert("RGB")
            except (OSError, httpx.HTTPError) as e:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to download weather image after {max_retries} attempts: {e}"
                    ) from e
                print(
                    f"\nDownload failed (attempt {attempt}/{max_retries}), "
                    f"retrying in {RETRY_DELAY_SECONDS} seconds...\n"
                )
                sleep(RETRY_DELAY_SECONDS)


def publish_to_share(output: Path, share_path: Path) -> None:
    """Compress the output PNG with pngcrush and copy it to the SMB share."""
    if shutil.which("pngcrush") is None:
        return
    subprocess.run(["pngcrush", "-c", "0", str(output)], check=True)
    Path("pngout.png").replace(share_path / "pngout.png")


def main() -> None:
    """Main execution function."""
    # Generate air quality data
    airly = Airly()
    airly.fill_template()
    airly.plot_caqi_history()

    # Download and process weather image
    url = WEATHER_URL_TEMPLATE.format(row=KRAKOW_COORDS[0], col=KRAKOW_COORDS[1])
    processor = WeatherImageProcessor(HOME_DIR)
    image = fetch_weather_image(url)
    image = processor.crop_image(image)
    image = processor.remove_logo(image)
    image = processor.adjust_size(image)
    image = processor.paste_caqi(image)

    output = HOME_DIR / OUTPUT_FILENAME
    image.save(output, bits=IMAGE_BITS)

    publish_to_share(output, SMB_SHARE_PATH)


if __name__ == "__main__":
    main()
