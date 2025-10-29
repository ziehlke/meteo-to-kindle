import subprocess
from pathlib import Path
from time import sleep

import httpx
from PIL import Image

from airly import Airly
from config import HOME_DIR, OUTPUT_FILENAME, SMB_SHARE_PATH, RETRY_DELAY_SECONDS, KRAKOW_COORDS
from image_processor import WeatherImageProcessor


def download_weather_image(
    url: str, output_path: Path, max_retries: int = 3
) -> Image.Image:
    """Download weather image with retry logic."""
    for attempt in range(max_retries):
        try:
            with httpx.Client(follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                output_path.write_bytes(response.content)
            img = Image.open(output_path)
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
    url = (
        f"http://www.meteo.pl/um/metco/mgram_pict.php?ntype=0u&"
        f"row={KRAKOW_COORDS[0]}&col={KRAKOW_COORDS[1]}&lang=pl"
    )
    output = HOME_DIR / OUTPUT_FILENAME
    smb_public_share = SMB_SHARE_PATH

    # Initialize components
    airly = Airly()
    processor = WeatherImageProcessor(HOME_DIR)

    # Generate air quality data
    airly.fill_template()
    airly.plot_caqi_history()

    # Download and process weather image
    img = download_weather_image(url, output)

    # Apply image processing
    img = processor.crop_image(img)
    img = processor.remove_logo(img)
    img = processor.adjust_size(img)
    img = processor.paste_caqi(img)
    img.save(output, bits=8)

    # Optimize and move file
    subprocess.run(["pngcrush", "-c", "0", output])
    subprocess.run(["mv", "pngout.png", smb_public_share])


if __name__ == "__main__":
    main()
