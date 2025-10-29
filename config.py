"""Configuration constants for the meteo-to-kindle application."""

from pathlib import Path
from typing import List, Tuple

# Directory configuration
HOME_DIR = Path(__file__).parent

# Weather service configuration
KRAKOW_COORDS: Tuple[int, int] = (466, 232)
WEATHER_URL_TEMPLATE = (
    "http://www.meteo.pl/um/metco/mgram_pict.php?ntype=0u&"
    "row={row}&col={col}&lang=pl"
)

# File paths
OUTPUT_FILENAME = "weather-script-output.png"
TEMPLATE_FILENAME = "master_template.png"
CAQI_FILENAME = "caqi.png"
TEMPLATE_PROCESSED_FILENAME = "template.png"

# Font paths
FONT_DIR = HOME_DIR / "Manrope"
EMOJI_FONT_PATH = FONT_DIR / "OpenMoji-Black.ttf"
EXTRA_BOLD_FONT_PATH = FONT_DIR / "Manrope-ExtraBold.ttf"
BOLD_FONT_PATH = FONT_DIR / "Manrope-Bold.ttf"
REGULAR_FONT_PATH = FONT_DIR / "Manrope-Regular.ttf"

# Output configuration
SMB_SHARE_PATH = Path("/home/dietpi/").resolve()

# Retry configuration
RETRY_DELAY_SECONDS = 15

# Image processing configuration
TARGET_IMAGE_WIDTH = 600
IMAGE_BITS = 8

# Airly API configuration
AIRLY_LATITUDE = 50.0739491148
AIRLY_LONGITUDE = 20.0485859686
AIRLY_API_URL_TEMPLATE = (
    "https://airapi.airly.eu/v2/measurements/point?lat={lat}6&lng={lng}"
)

# Air quality configuration
CAQI_BINS: List[int] = [20, 35, 50, 75, 100, 125]
PM25_MAX_THRESHOLD = 50.0
PM10_MAX_THRESHOLD = 25.0

# Emoji mapping for air quality
AIR_QUALITY_EMOJIS = "😍😀🙂😐😟🤬💩"

# Chart configuration
CHART_FIGSIZE = (7, 1)
CHART_BAR_WIDTH = 0.94

# Text positioning on template
EMOJI_POSITION = (9, 653)
CAQI_POSITION = (70, 650)
PM25_POSITION = (195, 650)
PM10_POSITION = (350, 650)
TEMP_POSITION = (505, 650)
PM25_PERCENT_POSITION = (195, 688)
PM10_PERCENT_POSITION = (350, 688)
PRESSURE_POSITION = (350, 720)
HUMIDITY_POSITION = (505, 720)
ADVICE_POSITION = (9, 740)

# Font sizes
EMOJI_FONT_SIZE = 60
EXTRA_BOLD_FONT_SIZE = 40
BOLD_SMALL_FONT_SIZE = 30
REGULAR_SMALL_FONT_SIZE = 15

# Text formatting
ADVICE_WRAP_WIDTH = 45

# Image crop coordinates
CROP_OPERATIONS = [
    ((0, 524, None, 635), (0, 400, None, 511)),
    ((0, 312, None, 511), (0, 226, None, 425)),
]
FINAL_CROP_COORDS = (35, 0, -40, 425)

# CAQI chart position
CAQI_CHART_POSITION = (0, 500)

# Color replacement for logo removal
WHITE_COLORS_TO_REPLACE = [(255, 251, 240), (244, 244, 244)]
GRAY_COLORS_TO_REPLACE = [(216, 216, 216), (215, 216, 215)]
WHITE_TARGET_COLOR = (255, 255, 255)
GRAY_TARGET_COLOR = (226, 226, 226)
