import shutil
from time import sleep

import httpx
from PIL import Image
from io import BytesIO
from airly import Airly
from config import (
    HOME_DIR, OUTPUT_FILENAME, SMB_SHARE_PATH, RETRY_DELAY_SECONDS,
    KRAKOW_COORDS, WEATHER_URL_TEMPLATE,
)
from image_processor import WeatherImageProcessor


def fetch_weather_image(url: str, max_retries: int = 3) -> Image.Image:
    """Fetch weather image from URL with retry logic.

    Downloads the image directly into memory without saving to disk.
    Returns a PIL Image object in RGB format.
    """
    for attempt in range(max_retries):
        try:
            with httpx.Client(follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                with Image.open(BytesIO(response.content)) as img:
                    return img.convert("RGB")
        except (OSError, httpx.HTTPError) as e:
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Failed to download weather image after {max_retries} attempts: {e}"
                )
            print(
                f"\nDownload failed (attempt {attempt + 1}/{max_retries}), retrying in {RETRY_DELAY_SECONDS} seconds...\n"
            )
            sleep(RETRY_DELAY_SECONDS)


def main() -> None:
    """Main execution function."""
    # Configuration
    url = WEATHER_URL_TEMPLATE.format(row=KRAKOW_COORDS[0], col=KRAKOW_COORDS[1])
    output = HOME_DIR / OUTPUT_FILENAME
    smb_public_share = SMB_SHARE_PATH

    # Initialize components
    airly = Airly()
    processor = WeatherImageProcessor(HOME_DIR)

    # Generate air quality data
    airly.fill_template()
    airly.plot_caqi_history()

    # Download and process weather image
    img = fetch_weather_image(url)

    # Apply image processing
    img = processor.crop_image(img)
    img = processor.remove_logo(img)
    img = processor.adjust_size(img)
    img = processor.paste_caqi(img)
    img.save(output, bits=8)

    # Optimize and move file
    if shutil.which("pngcrush"):
        import subprocess
        subprocess.run(["pngcrush", "-c", "0", str(output)], check=True)
        shutil.move("pngout.png", smb_public_share)

if __name__ == "__main__":
    main()
