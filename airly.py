import os
import textwrap

import httpx
import matplotlib.pyplot as plt
from PIL import ImageFont, ImageDraw, Image
from dotenv import load_dotenv

from config import (
    HOME_DIR,
    AIRLY_LATITUDE,
    AIRLY_LONGITUDE,
    AIRLY_API_URL_TEMPLATE,
    AIR_QUALITY_EMOJIS,
    CAQI_BINS,
    PM25_MAX_THRESHOLD,
    PM10_MAX_THRESHOLD,
    CHART_FIGSIZE,
    CHART_BAR_WIDTH,
    EMOJI_POSITION,
    CAQI_POSITION,
    PM25_POSITION,
    PM10_POSITION,
    PM1_POSITION,
    TEMP_POSITION,
    PM25_PERCENT_POSITION,
    PM10_PERCENT_POSITION,
    HUMIDITY_POSITION,
    ADVICE_POSITION,
    ADVICE_WRAP_WIDTH,
    EMOJI_FONT_SIZE,
    EXTRA_BOLD_FONT_SIZE,
    BOLD_SMALL_FONT_SIZE,
    REGULAR_SMALL_FONT_SIZE,
    EMOJI_FONT_PATH,
    EXTRA_BOLD_FONT_PATH,
    BOLD_FONT_PATH,
    REGULAR_FONT_PATH,
    TEMPLATE_FILENAME,
    CAQI_FILENAME,
    TEMPLATE_PROCESSED_FILENAME,
)

load_dotenv()


class Airly:
    API_KEY = os.environ.get("AIRLY_KEY")

    def __init__(self) -> None:
        self.url = AIRLY_API_URL_TEMPLATE.format(lat=AIRLY_LATITUDE, lng=AIRLY_LONGITUDE)
        self.data = self.get_data()

    def get_data(self) -> dict:
        """Fetch air quality data from Airly API."""
        if not self.API_KEY:
            raise ValueError("AIRLY_KEY environment variable not set")

        headers = {"apikey": self.API_KEY, "Accept": "application/json"}
        try:
            with httpx.Client() as client:
                response = client.get(self.url, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch air quality data: {e}")

    def plot_caqi_history(self) -> None:
        """Generate and save CAQI history chart."""
        if not self.data or "history" not in self.data:
            raise ValueError("No air quality data available")

        caqis = [
            history["indexes"][0].get("value", 0) for history in self.data["history"]
        ]
        colors = [history["indexes"][0]["color"] for history in self.data["history"]]
        times = [
            history["fromDateTime"].rsplit("T")[1][0:2]
            for history in self.data["history"]
        ]
        y_pos = range(len(caqis))

        plt.figure(figsize=CHART_FIGSIZE)
        plt.bar(y_pos, caqis, color=colors, width=CHART_BAR_WIDTH)
        plt.xticks(y_pos, times)
        plt.savefig(HOME_DIR / CAQI_FILENAME, bbox_inches="tight")

    def get_value_by_name(self, name: str) -> float:
        """Helper to find value by name from current air quality data."""
        if not self.data or "current" not in self.data:
            return 0.0

        for v in self.data["current"]["values"]:
            if v["name"] == name:
                return v["value"]
        return 0.0

    def fill_template(self) -> None:
        """Fill the weather template with air quality data."""
        if not self.data or "current" not in self.data:
            raise ValueError("No current air quality data available")

        # load fonts
        open_moji = ImageFont.truetype(EMOJI_FONT_PATH, EMOJI_FONT_SIZE)
        manrope_extra_bold = ImageFont.truetype(
            EXTRA_BOLD_FONT_PATH, EXTRA_BOLD_FONT_SIZE
        )
        manrope_bold_small = ImageFont.truetype(BOLD_FONT_PATH, BOLD_SMALL_FONT_SIZE)
        manrope_regular_small = ImageFont.truetype(
            REGULAR_FONT_PATH, REGULAR_SMALL_FONT_SIZE
        )

        current_caqi = self.data["current"]["indexes"][0]["value"]
        emoji_index = sum(1 for bin_val in CAQI_BINS if current_caqi > bin_val)

        with Image.open(HOME_DIR / TEMPLATE_FILENAME) as image:
            draw = ImageDraw.Draw(image)

            # Draw emoji and CAQI value
            draw.text(
                EMOJI_POSITION,
                AIR_QUALITY_EMOJIS[emoji_index],
                fill="black",
                font=open_moji,
            )
            draw.text(
                CAQI_POSITION,
                str(round(current_caqi)),
                fill="black",
                font=manrope_extra_bold,
            )

            # Draw advice text
            advice = self.data["current"]["indexes"][0]["advice"]
            draw.text(
                ADVICE_POSITION,
                "\n".join(textwrap.wrap(advice, width=ADVICE_WRAP_WIDTH)),
                fill="black",
                font=manrope_regular_small,
            )

            # Draw current values
            pm1 = self.get_value_by_name("PM1")
            pm25 = self.get_value_by_name("PM25")
            pm10 = self.get_value_by_name("PM10")
            temperature = self.get_value_by_name("TEMPERATURE")
            humidity = self.get_value_by_name("HUMIDITY")

            draw.text(
                PM25_POSITION,
                str(round(pm25)),
                fill="black",
                font=manrope_extra_bold,
            )
            draw.text(
                PM10_POSITION,
                str(round(pm10)),
                fill="black",
                font=manrope_extra_bold,
            )
            draw.text(
                PM1_POSITION,
                str(round(pm1)),
                fill="black",
                font=manrope_extra_bold,
            )

            # Draw percentage indicators
            pm25_percent = round(100 * pm25 / PM25_MAX_THRESHOLD)
            pm10_percent = round(100 * pm10 / PM10_MAX_THRESHOLD)
            draw.text(
                PM25_PERCENT_POSITION,
                f"{pm25_percent}%",
                fill="gray",
                font=manrope_bold_small,
            )
            draw.text(
                PM10_PERCENT_POSITION,
                f"{pm10_percent}%",
                fill="gray",
                font=manrope_bold_small,
            )

            # Draw temperature and humidity
            draw.text(
                TEMP_POSITION,
                str(round(temperature)),
                fill="black",
                font=manrope_extra_bold,
            )
            draw.text(
                HUMIDITY_POSITION,
                str(round(humidity)),
                fill="black",
                font=manrope_extra_bold,
            )

            image.save(HOME_DIR / TEMPLATE_PROCESSED_FILENAME)
