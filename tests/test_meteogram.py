"""Tests for the meteogram renderer: output size, content and sun geometry."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from matplotlib import pyplot as plt
from PIL import Image

from meteo_to_kindle.config import METEOGRAM_DPI, METEOGRAM_FIGSIZE
from meteo_to_kindle.meteo import MeteogramData
from meteo_to_kindle.meteogram import (
    _CLOUD_AX,
    _CLOUD_MAX_KM,
    _CLOUD_Y_POWER,
    _cloud_column,
    _cloud_field,
    _cloud_haze_band,
    _cloud_high_deck,
    _cloud_low_deck,
    _cloud_mid_deck,
    _cloud_surface,
    _date_labels,
    _draw_header,
    _is_sunlit,
    _night_segments,
    _register_fonts,
    _smooth_time,
    render_meteogram,
)

START = datetime(2026, 10, 26, 12, tzinfo=UTC)  # 14:00 local (CEST)
WIND_SPEED = "wind10_sd_true_prev_point"
WIND_DIRECTION = "wind10_dr_deg_true_prev_point"
WARSAW = ZoneInfo("Europe/Warsaw")

_CLOUD_SERIES = ("cldvlow_aver", "cldlow_aver", "cldmed_aver", "cldhigh_aver")


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
        "cldbse01": tuple(0.95 for _ in range(hours)),
        "cldbse25": tuple(1.05 for _ in range(hours)),
        "cldbse45": tuple(1.15 for _ in range(hours)),
        "cldbse65": tuple(1.25 for _ in range(hours)),
        "cldbse79": tuple(1.35 for _ in range(hours)),
        "cldtop": tuple(11.5 for _ in range(hours)),
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


def _cloud_row(altitude: float) -> int:
    """Pixel row where an altitude plots in the cloud panel, per the stretch."""
    bottom = (1 - _CLOUD_AX[1]) * METEOGRAM_FIGSIZE[1] * METEOGRAM_DPI
    span = _CLOUD_AX[3] * METEOGRAM_FIGSIZE[1] * METEOGRAM_DPI
    display = _CLOUD_MAX_KM * (altitude / _CLOUD_MAX_KM) ** _CLOUD_Y_POWER
    return round(bottom - display / _CLOUD_MAX_KM * span)


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


@pytest.mark.parametrize(
    ("start", "width", "first_alignment", "last_alignment"),
    [
        (datetime(2026, 10, 26, 22, tzinfo=UTC), 6, "center", "center"),
        (datetime(2026, 10, 25, 22, tzinfo=UTC), 6, "center", "right"),
        (datetime(2026, 10, 26, 22, tzinfo=UTC), 2, "left", "right"),
    ],
)
def test_date_caption_edges_follow_rendered_bounds(
    start: datetime, width: int, first_alignment: str, last_alignment: str
) -> None:
    data = _data(hours=2, start=start)  # 23:00 and midnight in Warsaw
    _register_fonts()
    fig = plt.figure(figsize=(width, 6.4), dpi=100)
    try:
        _draw_header(fig, data, _local(data))
        first, last = fig.texts[2:]
        assert first.get_horizontalalignment() == first_alignment
        assert last.get_horizontalalignment() == last_alignment
        assert first.get_position()[0] == pytest.approx(
            0.01 if first_alignment == "left" else 0.105
        )
        assert last.get_position()[0] == pytest.approx(
            0.99 if last_alignment == "right" else 0.945
        )
        assert first.get_window_extent().x0 >= fig.bbox.x0
        assert last.get_window_extent().x1 <= fig.bbox.x1
    finally:
        plt.close(fig)


def test_evening_run_date_captions_remain_separate() -> None:
    data = _data(hours=120, start=datetime(2026, 10, 31, 18, tzinfo=UTC))
    _register_fonts()
    fig = plt.figure(figsize=(6, 6.4), dpi=100)
    try:
        _draw_header(fig, data, _local(data))
        first, second = fig.texts[2:4]
        assert first.get_horizontalalignment() == "center"
        assert first.get_window_extent().x1 < second.get_window_extent().x0
    finally:
        plt.close(fig)


def test_cloud_haze_band_fades_with_very_low_coverage() -> None:
    assert _cloud_haze_band(0.6) == pytest.approx([(0.0, 0.6), (0.7, 0.6), (1.2, 0.0)])


def test_cloud_ladder_shades_coverage_by_altitude() -> None:
    # The ladder interpolates coverage between the okta-threshold bases and
    # holds its density to the low-cloud layer's top when a high deck owns
    # the sky; the wide skirt has faded by the middle band's altitude
    altitudes = np.array([0.5, 2.0, 4.0, 6.0, 8.0])
    column = _cloud_column(
        vlow=0.0,
        low=0.4,
        med=0.3,
        high=0.5,
        top=9.5,
        bases=(np.nan, 1.0, np.nan, np.nan, np.nan),
        altitudes=altitudes,
    )
    # clear under the lone weather rung, the deck dense at the layer top,
    # the mid deck inside its bump, a clear gap between the decks, and the
    # high deck full above its rise
    assert column.tolist() == pytest.approx([0.0, 0.4, 0.3, 0.0, 0.5])


def test_cloud_column_tops_at_the_real_cloud_top() -> None:
    # Without a high layer the ladder column holds dense to the reported
    # cloud top, melts through the skirt just above it and clears past that
    altitudes = np.array([1.3, 1.5, 3.0, 3.4, 4.8])
    column = _cloud_column(
        vlow=0.0,
        low=1.0,
        med=0.0,
        high=0.0,
        top=3.0,
        bases=(0.5, 0.8, 1.3, 1.4, 1.5),
        altitudes=altitudes,
    )
    # the 4.5-okta rung sits at 1.3 km and the 7.9-okta rung at 1.5 km
    assert column.tolist() == pytest.approx([0.5625, 0.9875, 1.0, 0.75, 0.0])


def test_cloud_ladder_melts_above_its_highest_base() -> None:
    # No high layer and a top barely above the highest rung: the column
    # caps just past the rung and melts through the wide skirt instead
    anchors = _cloud_low_deck(
        bases=(np.nan, 1.0, np.nan, np.nan, np.nan), low=0.4, high=0.0, top=1.1
    )
    assert anchors == pytest.approx([(1.0, 0.3125), (1.4, 0.4), (3.0, 0.0)])


def test_cloud_low_deck_without_a_ladder_holds_the_layer_top() -> None:
    # GFS runs ship no base ladder: a plain deck held to the model's
    # low-cloud layer top, melting into the sky above; no low cloud, no deck
    anchors = _cloud_low_deck(bases=(np.nan,) * 5, low=0.6, high=0.0, top=float("nan"))
    assert anchors == pytest.approx([(0.0, 0.6), (2.0, 0.6), (3.6, 0.0)])
    assert _cloud_low_deck(bases=(np.nan,) * 5, low=0.0, high=0.0, top=3.0) == []


def test_cloud_mid_deck_fills_its_band() -> None:
    assert _cloud_mid_deck(0.0) == []
    assert _cloud_mid_deck(0.3) == pytest.approx(
        [(2.4, 0.0), (3.5, 0.3), (4.4, 0.3), (5.5, 0.0)]
    )


def test_cloud_high_deck_rises_to_the_cloud_top() -> None:
    # Full from the climb through the reported top, then a skirt melts the
    # deck into the sky above; tops at or past the rim clip instead, and
    # tops that never get past the rise read as low-deck sky
    assert _cloud_high_deck(0.5, 9.5) == pytest.approx(
        [(6.0, 0.0), (7.0, 0.5), (9.5, 0.5), (10.5, 0.0)]
    )
    assert _cloud_high_deck(0.5, 13.2) == pytest.approx(
        [(6.0, 0.0), (7.0, 0.5), (13.2, 0.5), (14.0, 0.0)]
    )
    assert _cloud_high_deck(0.5, 14.0) == pytest.approx(
        [(6.0, 0.0), (7.0, 0.5), (14.0, 0.5)]
    )
    assert _cloud_high_deck(0.0, 9.5) == []  # no high layer, no deck
    assert _cloud_high_deck(0.5, 7.0) == []  # top below the rise: low-deck sky


def test_cloud_high_deck_without_a_top_holds_the_rim() -> None:
    # GFS runs report no cloud top: the deck holds to the panel rim
    assert _cloud_high_deck(0.5, float("nan")) == pytest.approx(
        [(6.0, 0.0), (7.0, 0.5), (14.0, 0.5)]
    )


def test_cloud_surface_sorts_unordered_anchors() -> None:
    # Real data can report a base above the layer cap; sorting the anchors
    # keeps the interpolation ordered where that happens
    grid = np.array([1.0, 2.1])
    anchors = [(0.0, 0.5), (2.4, 0.0), (2.0, 0.5)]
    # the deck holds through 2.0 km and fades by 2.4 km
    assert _cloud_surface(anchors, grid).tolist() == pytest.approx([0.5, 0.375])


def test_cloud_time_smoothing_blends_neighbouring_hours() -> None:
    # One binomial pass softens an hour-to-hour spike; the edges mirror so
    # the end hours keep their coverage
    field = np.array([[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    assert _smooth_time(field, 1).ravel().tolist() == pytest.approx(
        [0.25, 0.5, 0.25, 0.25, 0.5, 0.25]
    )


def test_cloud_field_stretches_the_altitude_axis() -> None:
    # Contouring plots altitudes on meteoblue's stretched axis, spreading
    # the low sky: midway up the true column plots above its true share
    data = _data(hours=2)
    heights, _ = _cloud_field(data)
    altitudes = np.linspace(0.0, _CLOUD_MAX_KM, len(heights))
    mid = len(heights) // 2
    assert heights[mid] == pytest.approx(
        _CLOUD_MAX_KM * (float(altitudes[mid]) / _CLOUD_MAX_KM) ** _CLOUD_Y_POWER
    )
    assert heights[mid] > float(altitudes[mid])


def test_cloud_shades_mean_dense_columns(tmp_path: Path) -> None:
    # Fully overcast in every deck must paint each deck's dense core dark
    pixels = _rendered(
        _data(hours=24, series=dict.fromkeys(_CLOUD_SERIES, (1.0,) * 24)),
        tmp_path,
    )
    # Rows centred on the fog strip, the ladder deck before its skirt, the
    # middle bump and the high deck, at a mid-panel hour clear of tick
    # labels and the axis frame
    for altitude in (0.3, 1.7, 3.9, 9.5):
        row = _cloud_row(altitude)
        assert float(np.mean(pixels[row - 2 : row + 3, 315:335])) < 80.0
