"""Fetch air quality data from the Airly API and render overlay assets."""

import os
import textwrap
from bisect import bisect_right
from dataclasses import dataclass

import httpx
import matplotlib

matplotlib.use("Agg")  # headless backend, must be set before importing pyplot

import matplotlib.pyplot as plt
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont

from config import (
    ADVICE_POSITION,
    ADVICE_WRAP_WIDTH,
    AIR_QUALITY_EMOJIS,
    AIRLY_API_URL_TEMPLATE,
    AIRLY_LATITUDE,
    AIRLY_LONGITUDE,
    BOLD_FONT_PATH,
    BOLD_SMALL_FONT_SIZE,
    CAQI_BINS,
    CAQI_FILENAME,
    CAQI_POSITION,
    CHART_BAR_WIDTH,
    CHART_FIGSIZE,
    EMOJI_FONT_PATH,
    EMOJI_FONT_SIZE,
    EMOJI_POSITION,
    EXTRA_BOLD_FONT_PATH,
    EXTRA_BOLD_FONT_SIZE,
    HOME_DIR,
    HUMIDITY_POSITION,
    PM1_POSITION,
    PM10_MAX_THRESHOLD,
    PM10_PERCENT_POSITION,
    PM10_POSITION,
    PM25_MAX_THRESHOLD,
    PM25_PERCENT_POSITION,
    PM25_POSITION,
    REGULAR_FONT_PATH,
    REGULAR_SMALL_FONT_SIZE,
    TEMP_POSITION,
    TEMPLATE_FILENAME,
    TEMPLATE_PROCESSED_FILENAME,
)

load_dotenv()


@dataclass(frozen=True)
class Fonts:
    """Fonts used to draw on the template."""

    emoji: FreeTypeFont
    extra_bold: FreeTypeFont
    bold_small: FreeTypeFont
    regular_small: FreeTypeFont

    @classmethod
    def load(cls) -> "Fonts":
        return cls(
            emoji=ImageFont.truetype(EMOJI_FONT_PATH, EMOJI_FONT_SIZE),
            extra_bold=ImageFont.truetype(EXTRA_BOLD_FONT_PATH, EXTRA_BOLD_FONT_SIZE),
            bold_small=ImageFont.truetype(BOLD_FONT_PATH, BOLD_SMALL_FONT_SIZE),
            regular_small=ImageFont.truetype(
                REGULAR_FONT_PATH, REGULAR_SMALL_FONT_SIZE
            ),
        )


class Airly:
    """Airly client that renders the air quality template and CAQI history chart."""

    def __init__(self) -> None:
        api_key = os.environ.get("AIRLY_KEY")
        if not api_key:
            raise ValueError("AIRLY_KEY environment variable not set")
        self._headers = {"apikey": api_key, "Accept": "application/json"}
        self._url = AIRLY_API_URL_TEMPLATE.format(
            lat=AIRLY_LATITUDE, lng=AIRLY_LONGITUDE
        )
        self._data: dict | None = None

    @property
    def data(self) -> dict:
        """Measurement data, fetched on first access and cached afterwards."""
        if self._data is None:
            self._data = self._fetch_data()
        return self._data

    def _fetch_data(self) -> dict:
        """Fetch air quality data from the Airly API."""
        try:
            with httpx.Client() as client:
                response = client.get(self._url, headers=self._headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch air quality data: {e}") from e

    def get_value_by_name(self, name: str) -> float:
        """Find a value by name in the current measurements, or 0.0 if missing."""
        if not self.data or "current" not in self.data:
            return 0.0
        for item in self.data["current"]["values"]:
            if item["name"] == name:
                return item["value"]
        return 0.0

    def plot_caqi_history(self) -> None:
        """Render the hourly CAQI bar chart to CAQI_FILENAME."""
        if not self.data or "history" not in self.data:
            raise ValueError("No air quality data available")

        history = self.data["history"]
        caqis = [entry["indexes"][0].get("value", 0) for entry in history]
        colors = [entry["indexes"][0]["color"] for entry in history]
        hours = [entry["fromDateTime"].split("T")[1][:2] for entry in history]
        x_pos = list(range(len(caqis)))

        fig, ax = plt.subplots(figsize=CHART_FIGSIZE)
        try:
            ax.bar(x_pos, caqis, color=colors, width=CHART_BAR_WIDTH)
            ax.set_xticks(x_pos, hours)
            fig.savefig(HOME_DIR / CAQI_FILENAME, bbox_inches="tight")
        finally:
            plt.close(fig)

    def fill_template(self) -> None:
        """Draw current air quality data onto the template image."""
        if not self.data or "current" not in self.data:
            raise ValueError("No current air quality data available")

        fonts = Fonts.load()
        current = self.data["current"]
        caqi = current["indexes"][0]["value"]
        advice = "\n".join(
            textwrap.wrap(current["indexes"][0]["advice"], width=ADVICE_WRAP_WIDTH)
        )

        pm1 = self.get_value_by_name("PM1")
        pm25 = self.get_value_by_name("PM25")
        pm10 = self.get_value_by_name("PM10")
        temperature = self.get_value_by_name("TEMPERATURE")
        humidity = self.get_value_by_name("HUMIDITY")

        # (position, text, font, fill)
        content = [
            (
                EMOJI_POSITION,
                AIR_QUALITY_EMOJIS[bisect_right(CAQI_BINS, caqi)],
                fonts.emoji,
                "black",
            ),
            (CAQI_POSITION, str(round(caqi)), fonts.extra_bold, "black"),
            (PM25_POSITION, str(round(pm25)), fonts.extra_bold, "black"),
            (PM10_POSITION, str(round(pm10)), fonts.extra_bold, "black"),
            (PM1_POSITION, str(round(pm1)), fonts.extra_bold, "black"),
            (
                PM25_PERCENT_POSITION,
                _percent(pm25, PM25_MAX_THRESHOLD),
                fonts.bold_small,
                "gray",
            ),
            (
                PM10_PERCENT_POSITION,
                _percent(pm10, PM10_MAX_THRESHOLD),
                fonts.bold_small,
                "gray",
            ),
            (TEMP_POSITION, str(round(temperature)), fonts.extra_bold, "black"),
            (HUMIDITY_POSITION, str(round(humidity)), fonts.extra_bold, "black"),
            (ADVICE_POSITION, advice, fonts.regular_small, "black"),
        ]

        with Image.open(HOME_DIR / TEMPLATE_FILENAME) as image:
            draw = ImageDraw.Draw(image)
            for position, text, font, fill in content:
                draw.text(position, text, fill=fill, font=font)
            image.save(HOME_DIR / TEMPLATE_PROCESSED_FILENAME)


def _percent(value: float, threshold: float) -> str:
    return f"{round(100 * value / threshold)}%"
