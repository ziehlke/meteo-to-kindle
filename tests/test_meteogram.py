"""Tests for the meteogram renderer: output size, content and sun geometry."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from PIL import Image

from meteo_to_kindle.meteo import MeteogramData
from meteo_to_kindle.meteogram import (
    _date_labels,
    _is_sunlit,
    _night_segments,
    render_meteogram,
)

START = datetime(2026, 10, 26, 12, tzinfo=UTC)  # 14:00 local (CEST)
WIND_SPEED = "wind10_sd_true_prev_point"
WIND_DIRECTION = "wind10_dr_deg_true_prev_point"
WARSAW = ZoneInfo("Europe/Warsaw")


def _local(data: MeteogramData) -> list[datetime]:
    return [ts.astimezone(WARSAW) for ts in data.timestamps]


def _data(
    hours: int = 24,
    series: dict[str, tuple[float | None, ...]] | None = None,
    start: datetime = START,
) -> MeteogramData:
    """Synthetic meteogram with smooth values and one rainy + one snowy spell."""
    default: dict[str, tuple[float | None, ...]] = {
        "airtmp_point": tuple(10 + 5 * np.sin(i / 6) for i in range(hours)),
        "airtmp_min": tuple(8 + 5 * np.sin(i / 6) for i in range(hours)),
        "airtmp_max": tuple(12 + 5 * np.sin(i / 6) for i in range(hours)),
        "dwptmp_point": tuple(7 + 5 * np.sin(i / 6) for i in range(hours)),
        "wchill_point": tuple(9 + 5 * np.sin(i / 6) for i in range(hours)),
        "slpres_point": tuple(101_000 + 300 * i for i in range(hours)),
        "pcpttl_max": tuple(
            1.5 if 4 <= i < 6 else 1.0 if i == 6 else 0.0 for i in range(hours)
        ),
        "pcpttlprob_point": tuple(40 + 30 * np.sin(i / 4) for i in range(hours)),
        "pcpttl_type_max": tuple(
            2 if 5 <= i < 6 else 3 if i == 6 else 1 if 4 <= i < 5 else 0
            for i in range(hours)
        ),
        "storm_max": tuple(2 if i == 4 else 0 for i in range(hours)),
        WIND_SPEED: tuple(3 + 2 * np.cos(i / 5) for i in range(hours)),
        "wind_gust_max": tuple(6 + 3 * np.cos(i / 5) for i in range(hours)),
        WIND_DIRECTION: tuple(270.0 for _ in range(hours)),
        "cldvlow_aver": tuple(0.2 * (i % 2) for i in range(hours)),
        "cldlow_aver": tuple(0.4 for _ in range(hours)),
        "cldmed_aver": tuple(0.3 for _ in range(hours)),
        "cldhigh_aver": tuple(0.1 for _ in range(hours)),
    }
    return MeteogramData(
        model="um4_60",
        start=start,
        latitude=50.07,
        longitude=20.05,
        timestamps=tuple(start + timedelta(hours=i) for i in range(hours)),
        series=default | (series or {}),
    )


def _rendered(data: MeteogramData, tmp_path: Path) -> np.ndarray:
    output = render_meteogram(data, tmp_path / "meteogram.png")
    assert output == tmp_path / "meteogram.png"
    with Image.open(output) as image:
        return np.array(image.convert("L"))


def test_render_produces_600x640_image(tmp_path: Path) -> None:
    pixels = _rendered(_data(), tmp_path)
    assert pixels.shape == (640, 600)  # (height, width)


def test_render_contains_visible_content(tmp_path: Path) -> None:
    pixels = _rendered(_data(), tmp_path)
    assert float(np.std(pixels)) > 5.0  # not a blank page


def test_render_handles_missing_values(tmp_path: Path) -> None:
    series: dict[str, tuple[float | None, ...]] = {
        "airtmp_point": (None, 5.0, None, 6.0),
        "airtmp_min": (None, None, None, None),
        "airtmp_max": (None, None, None, None),
        "dwptmp_point": (4.0, 4.0, None, None),
        "wind_gust_max": (None, None, None, None),
        WIND_DIRECTION: (None, 90.0, None, None),
    }
    pixels = _rendered(_data(hours=4, series=series), tmp_path)
    assert pixels.shape == (640, 600)


def test_render_without_any_series(tmp_path: Path) -> None:
    data = MeteogramData(
        model="gfs",
        start=START,
        latitude=50.07,
        longitude=20.05,
        timestamps=(START, START + timedelta(hours=1)),
        series={},
    )
    pixels = _rendered(data, tmp_path)
    assert pixels.shape == (640, 600)


def test_render_single_hour(tmp_path: Path) -> None:
    pixels = _rendered(_data(hours=1), tmp_path)
    assert pixels.shape == (640, 600)


def test_render_anchors_last_day_caption_inside_frame(tmp_path: Path) -> None:
    # Run ending one hour after midnight: the last day's caption would be
    # centered at the frame edge, so it must be right-anchored instead
    base = datetime(2026, 10, 26, 22, tzinfo=UTC)  # 23:00 local
    data = MeteogramData(
        model="um4_60",
        start=base,
        latitude=50.07,
        longitude=20.05,
        timestamps=(base, base + timedelta(hours=1)),  # 23:00 Mon, 00:00 Tue
        series={},
    )
    pixels = _rendered(data, tmp_path)
    assert pixels.shape == (640, 600)


@pytest.mark.parametrize(
    ("moment", "latitude", "longitude", "expected"),
    [
        (datetime(2026, 10, 26, 11, 40, tzinfo=UTC), 50.07, 20.05, True),  # local noon
        (datetime(2026, 10, 26, 22, 0, tzinfo=UTC), 50.07, 20.05, False),  # midnight
        # Sydney in spring, 11:00 local (UTC+11): sun above the horizon
        (datetime(2026, 10, 26, 0, 0, tzinfo=UTC), -33.87, 151.21, True),
    ],
)
def test_is_sunlit(
    moment: datetime, latitude: float, longitude: float, expected: bool
) -> None:
    assert _is_sunlit(moment, latitude, longitude) is expected


def test_night_segments_cover_night_and_skip_daylight() -> None:
    nights = _night_segments(_local(_data(hours=48)), 50.07, 20.05)

    assert nights, "October nights must shade some hours"
    assert all(end > start for start, end in nights)

    def covered(hour_index: int) -> bool:
        return any(start <= hour_index < end for start, end in nights)

    # 02:00 and 03:00 local are inside a night span, 12:00 local is not
    assert covered(12) and covered(15)
    assert not covered(22)


def test_night_segments_needs_two_points() -> None:
    assert _night_segments([START], 50.07, 20.05) == []


def test_date_labels_centered_per_day() -> None:
    labels = _date_labels(_local(_data(hours=24)))

    assert labels[0][0] == "Mon 26.10"
    assert labels[1][0] == "Tue 27.10"
    # DST ended Oct 25, so 12:00 UTC is 13:00 local: Oct 26 covers indices
    # 0-10 (13:00-23:00), centered at 5.0; Oct 27 covers indices 11-23, at 17.0
    assert labels[0][1] == pytest.approx(5.0)
    assert labels[1][1] == pytest.approx(17.0)


def test_date_labels_compact_drops_weekday() -> None:
    labels = _date_labels(_local(_data(hours=24)), compact=True)

    assert labels[0][0] == "26.10"
    assert labels[1][0] == "27.10"


def test_render_gfs_horizon_thins_hour_ticks(tmp_path: Path) -> None:
    pixels = _rendered(_data(hours=240), tmp_path)

    assert pixels.shape == (640, 600)


def test_render_evening_run_keeps_date_captions_apart(tmp_path: Path) -> None:
    """Sliver first day on an evening run must not collide with day 2.

    18:00 UTC = 19:00 local: the first day bucket covers just 5 hours, so
    its caption pins to the left rim while day 2 centers over its bucket.
    """
    pixels = _rendered(
        _data(hours=120, start=datetime(2026, 10, 31, 18, tzinfo=UTC)), tmp_path
    )

    # Date-caption row (rows 26-44), left half of the figure: the pinned
    # first caption must end with a >=10px blank gap before the second
    # caption's zone begins (~x=100).
    inked = np.flatnonzero((pixels[26:44, :250] < 100).any(axis=0))
    gaps = inked[1:] - inked[:-1]
    wide = np.flatnonzero(gaps >= 10)
    assert wide.size >= 1, "date captions run together with no separating gap"
    assert 40 <= inked[wide[0]] <= 95
