"""Render a Kindle-friendly grayscale meteogram from Meteo ICM data.

The output is designed for a 600px-wide e-ink display: black-and-gray
panels stacked like the classic meteo.pl meteogram (temperature, wind,
precipitation, cloud cover by altitude) with a top hour/date axis and
day/night shading computed from the sun's position.
"""

import matplotlib

matplotlib.use("Agg")  # headless backend, must be set before importing pyplot

from datetime import datetime
from math import cos, radians, sin
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.font_manager
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure, SubFigure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator, StrMethodFormatter

from .config import FONT_DIR, METEOGRAM_DPI, METEOGRAM_FIGSIZE, TIMEZONE_NAME
from .meteo import MeteogramData

# Grayscale palette for the e-ink display
INK = "0.0"
DARK = "0.25"
MID = "0.5"
NIGHT_SHADE = "0.88"
GRID = "0.7"

# Wind direction arrows, north = up; the arrow points where the wind blows
_DIRECTION_ARROWS = ("↑", "↗", "→", "↘", "↓", "↙", "←", "↖")

# Panel rectangles in figure fractions: (left, bottom, width, height); the top
# block reserves ~65px so date captions, hour labels and unit captions each
# get their own horizontal band without collisions. The cloud panel needs the
# most height after temperature: its altitude bands are only readable if each
# kilometer gets a few pixels, so wind and precipitation shrink a little.
_TEMP_AX = (0.105, 0.641, 0.84, 0.257)
_PRECIP_AX = (0.105, 0.416, 0.84, 0.185)
_WIND_AX = (0.105, 0.218, 0.84, 0.152)
_CLOUD_AX = (0.105, 0.02, 0.84, 0.152)

_MODEL_TITLES = {"um4_60": "UM4 · 60h", "um4_120": "UM4 · 120h", "gfs": "GFS · 240h"}

# Grey scale steps mimicking meteoblue's cloud legend: (lower coverage bound,
# shade). Coverage below the first step stays transparent, so the night
# shading shows through, and the lightest step stays clear of NIGHT_SHADE so
# thin clouds keep some contrast against night.
_CLOUD_STEPS = (
    (0.10, "0.82"),
    (0.25, "0.70"),
    (0.50, "0.54"),
    (0.75, "0.37"),
    (0.90, "0.18"),
)

# The panel draws coverage as a meteoblue-style contoured field: per hour the
# vertical profile is rebuilt from the model's own summaries and the four
# resulting decks merge densest-first. Meteo ICM provides the pieces only in
# UM runs - GFS ships just the layer coverages, handled by the fallbacks:
# - cldbse01..cldbse79 = base (km) of cloud covering more than 0.1/2.5/4.5/
#   6.5/7.9 oktas: a real coverage-per-altitude ladder for the lowest deck
# - cldtop = top (km) of the tallest cloud in the column
# - cldvlow/low/med/high_aver = total sky coverage of the model layers
_CLOUD_LADDER = (
    ("cldbse01", 0.1 / 8),
    ("cldbse25", 2.5 / 8),
    ("cldbse45", 4.5 / 8),
    ("cldbse65", 6.5 / 8),
    ("cldbse79", 7.9 / 8),
)
_CLOUD_MAX_KM = 14.0  # panel rim; deep-convective tops clip here
_CLOUD_FIELD_ROWS = 281  # altitude steps along the rim, ~50 m apart
_CLOUD_HAZE_BAND = (0.7, 1.2)  # fog strip: held above ground, then faded, km
_CLOUD_LOW_TOP_KM = 2.0  # top of the model's low-cloud layer
_CLOUD_LOW_CAP_KM = 0.4  # ladder columns overshoot their highest rung by this, km
_CLOUD_LOW_EDGE_KM = 0.4  # vertical thickness of deck fades, km
_CLOUD_MED_BAND = (2.4, 3.5, 5.0, 5.5)  # mid deck: edge, full, full, edge, km
_CLOUD_HIGH_BASE_KM = 6.0  # high decks stay clear below this (and the y-tick)
_CLOUD_HIGH_RISE_KM = 1.0  # climb from the high base to full coverage, km
_CLOUD_HIGH_EDGE_KM = 0.25  # thickness of the high deck's clear edge and cap
_CLOUD_SMOOTH_PASSES = 2  # time-axis passes: melt hourly tables into blobs
# Contour levels between the grey steps: every value paints its step's shade,
# below 10% nothing paints and the night shading shows through.
_CLOUD_LEVELS = (0.0, *(bound for bound, _ in _CLOUD_STEPS), 1.0)
_CLOUD_LEVEL_COLORS = ("none", *(shade for _, shade in _CLOUD_STEPS))


def render_meteogram(data: MeteogramData, output: Path) -> Path:
    """Render the meteogram PNG (600x640 px) and return its path."""
    _register_fonts()
    hours = np.arange(len(data.timestamps))
    local = [ts.astimezone(ZoneInfo(TIMEZONE_NAME)) for ts in data.timestamps]
    nights = _night_segments(local, data.latitude, data.longitude)

    fig = plt.figure(figsize=METEOGRAM_FIGSIZE, dpi=METEOGRAM_DPI)
    fig.patch.set_facecolor("white")
    try:
        temperature_ax = fig.add_axes(_TEMP_AX)
        precip_ax = fig.add_axes(_PRECIP_AX)
        wind_ax = fig.add_axes(_WIND_AX)
        cloud_ax = fig.add_axes(_CLOUD_AX)
        _style_axes(
            [temperature_ax, precip_ax, wind_ax, cloud_ax], hours, local, nights
        )

        _draw_header(fig, data, local)
        _draw_temperature(temperature_ax, data, hours)
        _draw_precipitation(precip_ax, data, hours)
        _draw_wind(wind_ax, data, hours)
        _draw_clouds(cloud_ax, data, hours)

        # Tick numerals use DejaVu Sans: Manrope spaces multi-digit numbers loosely.
        # On panels whose top tick sits exactly at the frame edge (fixed ylims),
        # anchor that label downward so its ink stays clear of the captions.
        for axis in fig.axes:
            yticks = axis.get_yticks()
            labels = axis.get_yticklabels()
            for label in labels:
                label.set_fontfamily("DejaVu Sans")
            if (
                labels
                and yticks.size
                and np.isclose(yticks[-1], axis.get_ylim()[1])
                and labels[-1].get_fontsize() == 16
            ):
                labels[-1].set_verticalalignment("top")

        fig.savefig(output, dpi=METEOGRAM_DPI, facecolor="white")
    finally:
        plt.close(fig)
    return output


def _register_fonts() -> None:
    """Register the bundled Manrope fonts so charts match the template."""
    for font_path in FONT_DIR.glob("Manrope-*.ttf"):
        matplotlib.font_manager.fontManager.addfont(str(font_path))
    plt.rcParams["font.family"] = "Manrope"


def _style_axes(
    axes: list[plt.Axes],
    hours: np.ndarray,
    local: list[datetime],
    nights: list[tuple[float, float]],
) -> None:
    """Shared panel look: frames, hour gridlines, night shading, top ticks."""
    # 6h ticks need ~25px per gap; beyond 120 hours (GFS 240h) they would be
    # closer than the 10.5pt hour labels, so long horizons step to 12h ticks.
    step = 12 if len(local) > 120 else 6
    day_ticks = [i for i, moment in enumerate(local) if moment.hour % step == 0]

    for index, ax in enumerate(axes):
        left, right = (
            (float(hours[0]), float(hours[-1])) if len(hours) > 1 else (-0.5, 0.5)
        )
        ax.set_xlim(left, right)
        ax.set_xticks(day_ticks)
        ax.tick_params(
            axis="x",
            which="both",
            length=2,
            pad=1,
            top=index == 0,
            labeltop=index == 0,
            bottom=False,
            labelbottom=False,
        )
        ax.tick_params(axis="y", labelsize=16, length=2, pad=1)
        ax.grid(axis="x", color=GRID, linestyle=":", linewidth=0.6, which="major")
        for spine in ax.spines.values():
            spine.set_linewidth(0.8)
            spine.set_color(INK)
        for start, end in nights:
            ax.axvspan(start, end, color=NIGHT_SHADE, lw=0, zorder=0)
        ax.set_axisbelow(True)

    if day_ticks:
        axes[0].set_xticklabels([f"{local[i]:%H}" for i in day_ticks], fontsize=10.5)


def _night_segments(
    local: list[datetime], latitude: float, longitude: float
) -> list[tuple[float, float]]:
    """Hours where the sun is below the horizon, as (start, end) hour spans."""
    if len(local) < 2:
        return []
    steps = np.linspace(0.0, len(local) - 1.0, (len(local) - 1) * 4 + 1)
    sunlit = [_is_sunlit(_at(local, step), latitude, longitude) for step in steps]

    segments: list[tuple[float, float]] = []
    begin: float | None = None
    for step, lit in zip(steps, sunlit, strict=True):
        if not lit and begin is None:
            begin = float(step)
        if lit and begin is not None:
            segments.append((begin, float(step)))
            begin = None
    if begin is not None:
        segments.append((begin, float(steps[-1])))
    return segments


def _at(local: list[datetime], step: float) -> datetime:
    """Interpolate a timestamp at a fractional hour index."""
    low = int(step)
    high = min(low + 1, len(local) - 1)
    return local[low] + (local[high] - local[low]) * (step - low)


def _is_sunlit(moment: datetime, latitude: float, longitude: float) -> bool:
    """Whether the sun is above the horizon at a moment (NOAA approximation)."""
    utc = moment.astimezone(ZoneInfo("UTC"))
    day_of_year = utc.timetuple().tm_yday
    year_fraction = 2 * np.pi / 365 * (day_of_year - 1 + (utc.hour - 12) / 24)

    equation = 229.18 * (
        0.000075
        + 0.001868 * cos(year_fraction)
        - 0.032077 * sin(year_fraction)
        - 0.014615 * cos(2 * year_fraction)
        - 0.040849 * sin(2 * year_fraction)
    )
    declination = (
        0.006918
        - 0.399912 * cos(year_fraction)
        + 0.070257 * sin(year_fraction)
        - 0.006758 * cos(2 * year_fraction)
        + 0.000907 * sin(2 * year_fraction)
        - 0.002697 * cos(3 * year_fraction)
    )
    solar_minutes = utc.hour * 60 + utc.minute + equation + 4 * longitude
    hour_angle = radians(solar_minutes / 4 - 180)
    zenith_cos = sin(radians(latitude)) * sin(declination) + cos(
        radians(latitude)
    ) * cos(declination) * cos(hour_angle)
    return zenith_cos > 0


def _draw_header(fig: plt.Figure, data: MeteogramData, local: list[datetime]) -> None:
    """Model label and curve legend on top, day captions below."""
    fig.text(
        0.012, 0.99, _model_title(data.model), fontsize=13, weight="bold", va="top"
    )
    fig.text(
        0.988,
        0.99,
        f"{_point_label(data)} • run {data.start:%d.%m %H:%M} UTC",
        fontsize=10,
        ha="right",
        va="top",
        color=DARK,
    )
    # Curve legend for the temperature panel, in the gap between the title
    # and the run info; styles mirror the plotted lines exactly.
    fig.legend(
        handles=[
            Line2D([], [], color=DARK, linewidth=1.0),  # air temperature
            Line2D([], [], color=INK, linewidth=1.8),  # apparent temperature
            Line2D([], [], color=MID, linewidth=0.9, linestyle="--"),  # dew point
            Line2D([], [], color=DARK, linewidth=0.7, linestyle=":"),  # pressure
        ],
        labels=["Air", "Feels", "Dew", "hPa"],
        ncols=4,
        fontsize=8.5,
        frameon=False,
        handlelength=1.3,
        columnspacing=0.8,
        handletextpad=0.4,
        loc="upper center",
        bbox_to_anchor=(0.4, 0.993),
    )
    span = max(len(local) - 1, 1)
    # Captions describe buckets inside the shared panel span (every panel
    # has the same left edge and width), so map day centers into the axes
    # region instead of raw figure fractions - otherwise captions drift
    # left of the days they describe and the leftmost ones collide with
    # their neighbours on runs starting late in the day.
    axes_left, axes_width = _TEMP_AX[0], _TEMP_AX[2]
    labels = _date_labels(local, compact=len(local) > 120)
    for index, (label, center) in enumerate(labels):
        fraction = center / span
        position = axes_left + axes_width * fraction
        caption = fig.text(position, 0.938, label, fontsize=10.5, ha="center")
        # Pin only edge captions whose centered text would cross the image.
        bounds = caption.get_window_extent()
        if index == 0 and bounds.x0 < fig.bbox.x0:
            caption.set_horizontalalignment("left")
            caption.set_x(0.01)
        elif index == len(labels) - 1 and bounds.x1 > fig.bbox.x1:
            caption.set_horizontalalignment("right")
            caption.set_x(0.99)


def _point_label(data: MeteogramData) -> str:
    """Compact location label, e.g. '50.07°N 20.05°E'."""
    lat_hem = "N" if data.latitude >= 0 else "S"
    lon_hem = "E" if data.longitude >= 0 else "W"
    return f"{abs(data.latitude):.2f}°{lat_hem} {abs(data.longitude):.2f}°{lon_hem}"


def _model_title(model: str) -> str:
    """Human-readable model name for the header."""
    return _MODEL_TITLES.get(model, model)


def _date_labels(
    local: list[datetime], compact: bool = False
) -> list[tuple[str, float]]:
    """Date captions centered over each day's hours, as (label, hour index).

    Long horizons (GFS 240h) squeeze day buckets to ~50px, too narrow for
    the full weekday caption; compact mode drops the weekday.
    """
    pattern = "%d.%m" if compact else "%a %d.%m"
    # Dict insertion order keeps the buckets chronological - sorting by
    # label string would scramble the day order ("Mon" < "Sat" < "Sun").
    indices: dict[str, list[int]] = {}
    for index, moment in enumerate(local):
        indices.setdefault(f"{moment:{pattern}}", []).append(index)
    return [(label, (min(day) + max(day)) / 2) for label, day in indices.items()]


def _values(data: MeteogramData, name: str) -> np.ndarray:
    """Series values as a float array with NaN for missing points."""
    return np.array(
        [np.nan if value is None else value for value in data.values(name)], dtype=float
    )


def _bounds(*arrays: np.ndarray, pad: float = 2.0) -> tuple[float, float]:
    """Finite min/max over several arrays, with a fallback for all-missing."""
    finite = np.concatenate([array[np.isfinite(array)] for array in arrays])
    if finite.size == 0:
        return (0.0, 1.0)
    return (float(finite.min()) - pad, float(finite.max()) + pad)


def _finite_max(*arrays: np.ndarray) -> float | None:
    """Largest finite value across arrays, or None when everything is missing."""
    finite = np.concatenate([array[np.isfinite(array)] for array in arrays])
    return float(finite.max()) if finite.size else None


def _unit_label(ax: plt.Axes, text: str, side: str) -> None:
    """Draw a unit caption at a panel's top corner.

    Left captions sit above the frame rim, high enough to stay clear of
    the 16pt tick labels that hang below their tick position; right
    captions sit just below the rim, inside the panel, so they never
    collide with the hour labels sharing the band above the frame, and
    get an opaque patch so data lines cannot show through the glyphs.
    """
    anchor = {
        "left": (-0.04, 1.06, "right", "bottom"),
        "right": (0.988, 0.97, "right", "top"),
    }[side]
    ax.text(
        anchor[0],
        anchor[1],
        text,
        transform=ax.transAxes,
        ha=anchor[2],
        va=anchor[3],
        fontsize=9.5,
        color=INK,
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 1}
        if side == "right"
        else None,
    )


def _draw_temperature(ax: plt.Axes, data: MeteogramData, hours: np.ndarray) -> None:
    """Temperature panel: apparent temperature by wind, min/max, dew point."""
    temp = _values(data, "airtmp_point")
    temp_min = _values(data, "airtmp_min")
    temp_max = _values(data, "airtmp_max")
    chill = _values(data, "wchill_point")
    dew = _values(data, "dwptmp_point")
    pressure = _values(data, "slpres_point") / 100

    whisker = np.isfinite(temp_min) & np.isfinite(temp_max)
    ax.vlines(hours[whisker], temp_min[whisker], temp_max[whisker], color=MID, lw=0.7)
    ax.plot(hours, temp, color=DARK, linewidth=1.0)
    ax.plot(hours, dew, color=MID, linewidth=0.9, linestyle="--")
    # Drawn last so the apparent-temperature line is the most distinct
    ax.plot(hours, chill, color=INK, linewidth=1.8)

    ax.set_ylim(*_bounds(temp_min, temp, temp_max, dew, chill))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
    _unit_label(ax, "°C", "left")

    pressure_ax = ax.twinx()
    pressure_ax.plot(hours, pressure, color=DARK, linewidth=0.7, linestyle=":")
    pressure_ax.set_ylim(*_bounds(pressure))
    pressure_ax.yaxis.set_major_locator(MaxNLocator(nbins=3, integer=True))
    pressure_ax.yaxis.set_major_formatter(StrMethodFormatter("{x:.0f}"))
    pressure_ax.tick_params(axis="y", labelsize=9, pad=1)
    _unit_label(pressure_ax, "hPa", "right")
    pressure_ax.spines["top"].set_visible(False)


def _draw_precipitation(ax: plt.Axes, data: MeteogramData, hours: np.ndarray) -> None:
    """Precipitation panel: hourly mm bars, type hatching, probability line."""
    amount = np.nan_to_num(_values(data, "pcpttl_max"), nan=0.0)
    kind = np.nan_to_num(_values(data, "pcpttl_type_max"), nan=0.0)
    probability = _values(data, "pcpttlprob_point")

    faces: list[str] = []
    hatches: list[str] = []
    edges: list[str] = []
    for code in kind:
        if code == 2:  # snow
            faces.append("white")
            hatches.append("///")
            edges.append(INK)
        elif code == 3:  # sleet
            faces.append("white")
            hatches.append("...")
            edges.append(INK)
        else:  # rain, unknown and zero amounts
            faces.append(DARK)
            hatches.append("")
            edges.append("none")
    ax.bar(
        hours,
        amount,
        width=0.9,
        color=faces,
        hatch=hatches,
        edgecolor=edges,
        linewidth=0.4,
    )

    maximum = _finite_max(amount)
    top = max(1.0, np.ceil((maximum or 0.0) * 1.2 * 2) / 2)
    ax.set_ylim(0, top)
    ax.set_yticks([0, top])
    _unit_label(ax, "mm/h", "left")

    for hour in [
        i for i, storm in enumerate(_values(data, "storm_max")) if storm and storm >= 1
    ]:
        ax.text(
            hour,
            top * 0.92,
            "▼",
            fontsize=8,
            ha="center",
            va="top",
            family="DejaVu Sans",
            color=INK,
        )

    probability_ax = ax.twinx()
    probability_ax.plot(hours, probability, color=MID, linewidth=0.7, linestyle=":")
    probability_ax.set_ylim(0, 100)
    probability_ax.set_yticks([0, 50, 100])
    probability_ax.tick_params(axis="y", labelsize=9, pad=1)
    _unit_label(probability_ax, "%", "right")
    probability_ax.spines["top"].set_visible(False)


def _draw_wind(ax: plt.Axes, data: MeteogramData, hours: np.ndarray) -> None:
    """Wind panel: speed and gust curves with a direction arrow row on top."""
    speed = _values(data, "wind10_sd_true_prev_point")
    gust = _values(data, "wind_gust_max")
    direction = _values(data, "wind10_dr_deg_true_prev_point")

    ax.plot(hours, gust, color=MID, linewidth=0.8, linestyle="--")
    ax.plot(hours, speed, color=INK, linewidth=1.1)

    top = (_finite_max(gust) or 1.0) * 1.3 + 1
    ax.set_ylim(0, top)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=3, integer=True))
    _unit_label(ax, "m/s", "left")

    every = max(1, len(hours) // 20)
    # Start one hour in so edge arrows aren't clipped by the panel border
    for hour in hours[1::every] if len(hours) > 2 else ():
        bearing = direction[hour]
        if np.isnan(bearing):
            continue
        heading = float(bearing)
        arrow = _DIRECTION_ARROWS[round(((heading + 180) % 360) / 45) % 8]
        ax.text(
            hour,
            top * 0.97,
            arrow,
            fontsize=9.5,
            ha="center",
            va="top",
            family="DejaVu Sans",
            color=INK,
        )


def _cloud_haze_band(vlow: float) -> list[tuple[float, float]]:
    """Deck anchors for the near-surface fog strip at the very-low coverage."""
    hold, fade = _CLOUD_HAZE_BAND
    return [(0.0, vlow), (hold, vlow), (fade, 0.0)]


def _cloud_low_deck(
    bases: tuple[float, ...], low: float, high: float, top: float
) -> list[tuple[float, float]]:
    """Deck anchors for the lowest clouds, from the okta-coverage base ladder.

    Every ladder base sits at the altitude where this hour's coverage
    crosses its okta threshold, so interpolating between the anchors shades
    the deck light-to-dense the way meteoblue's panels do. The deck holds
    its density to the low-cloud layer top when a separate high deck owns
    the sky above, else to the reported cloud top when that towers above
    the ladder, else just past the highest reported base, and a wide skirt
    fades it into the sky above, so neighbouring hours merge into
    meteoblue's lens shapes; the sky-owning case never fades below the
    ladder's highest base, which can tower over the layer. Runs without a
    ladder (GFS) fall back to a plain deck held at the layer top with the
    same skirt.
    """
    anchors: list[tuple[float, float]] = [
        (float(base), threshold)
        for (_, threshold), base in zip(_CLOUD_LADDER, bases, strict=True)
        if np.isfinite(base)
    ]
    if not anchors:
        if low <= 0.0:
            return []
        return [
            (0.0, low),
            (_CLOUD_LOW_TOP_KM, low),
            (_CLOUD_LOW_TOP_KM + _CLOUD_LOW_EDGE_KM, 0.0),
        ]
    low = max(anchors[-1][1], low)
    peak = anchors[-1][0]
    if high > 0.0 and not (np.isfinite(top) and top <= 4.0):
        # the reported top belongs to the high deck, not to this column
        deck_top = max(_CLOUD_LOW_TOP_KM, peak)
    elif np.isfinite(top) and top > peak + _CLOUD_LOW_CAP_KM:
        # the ladder column is the whole deck: it tops out at the cloud top
        deck_top = min(top, _CLOUD_MAX_KM)
    else:
        deck_top = peak + _CLOUD_LOW_CAP_KM
    anchors += [(deck_top, low), (deck_top + _CLOUD_LOW_EDGE_KM, 0.0)]
    return anchors


def _cloud_mid_deck(med: float) -> list[tuple[float, float]]:
    """Deck anchors for the middle deck: a bump fading on both shoulders."""
    if med <= 0.0:
        return []
    edge, filled, until, top = _CLOUD_MED_BAND
    return [(edge, 0.0), (filled, med), (until, med), (top, 0.0)]


def _cloud_high_deck(high: float, top: float) -> list[tuple[float, float]]:
    """Deck anchors for the high deck, rising to the reported cloud top.

    The deck stays clear below the high base, climbs to full coverage by
    the rise and tops out at the reported cloud top with a quick fade.
    Runs without a cloud top (GFS) hold the deck to the panel rim like the
    fixed bands they replace; tops that never climb past the rise read as
    low-deck weather instead of a deck high in the column.
    """
    if high <= 0.0:
        return []
    start = _CLOUD_HIGH_BASE_KM + _CLOUD_HIGH_EDGE_KM
    full = start + _CLOUD_HIGH_RISE_KM
    if not np.isfinite(top):
        return [(start, 0.0), (full, high), (_CLOUD_MAX_KM, high)]
    if top <= full:
        return []
    ceiling = min(top, _CLOUD_MAX_KM)
    if ceiling >= _CLOUD_MAX_KM:
        return [(start, 0.0), (full, high), (ceiling, high)]
    return [
        (start, 0.0),
        (full, high),
        (ceiling, high),
        (min(ceiling + _CLOUD_HIGH_EDGE_KM, _CLOUD_MAX_KM), 0.0),
    ]


def _cloud_surface(
    anchors: list[tuple[float, float]], altitudes: np.ndarray
) -> np.ndarray:
    """Interpolate one deck's anchors onto the altitude grid, sorted first."""
    if not anchors:
        return np.zeros_like(altitudes)
    heights, coverages = zip(*sorted(anchors), strict=True)
    return np.interp(altitudes, heights, coverages, left=0.0, right=0.0)


def _cloud_column(
    vlow: float,
    low: float,
    med: float,
    high: float,
    top: float,
    bases: tuple[float, ...],
    altitudes: np.ndarray,
) -> np.ndarray:
    """Coverage (0-1) by altitude for one hour: the densest deck wins."""
    surfaces = [
        _cloud_surface(anchors, altitudes)
        for anchors in (
            _cloud_haze_band(vlow),
            _cloud_low_deck(bases, low, high, top),
            _cloud_mid_deck(med),
            _cloud_high_deck(high, top),
        )
    ]
    return np.clip(np.maximum.reduce(surfaces), 0.0, 1.0)


def _smooth_time(coverage: np.ndarray, passes: int) -> np.ndarray:
    """Blend the coverage field along time only with a short binomial kernel.

    Hour-by-hour profiles compiled into columns read as stacked tables; a
    couple of light passes soften those steps so decks drift as blobs the
    way meteoblue's contoured fields do. The kernel mirrors at the panel
    edges so the end hours keep their coverage.
    """
    for _ in range(passes):
        padded = np.pad(coverage, ((0, 0), (1, 1)), mode="edge")
        coverage = 0.25 * padded[:, :-2] + 0.5 * padded[:, 1:-1] + 0.25 * padded[:, 2:]
    return coverage


def _cloud_field(data: MeteogramData) -> tuple[np.ndarray, np.ndarray]:
    """Rebuild the coverage field, shape (altitude, hour), plus its grid.

    Meteo ICM provides the vertical structure only as summaries, so each
    hour merges the densest of the rebuilt decks: the near-surface haze,
    the base-ladder column, the middle deck band and the high deck up to
    the reported cloud top. The columns blend along time through
    _smooth_time, melting the hourly steps into drifting decks; the grid
    returned for contouring is the true altitude axis. What the model
    layers leave open between them shows as clear-air gaps, exactly like
    meteoblue's panels.
    """
    vlow, low, med, high = (
        np.nan_to_num(_values(data, name), nan=0.0)
        for name in ("cldvlow_aver", "cldlow_aver", "cldmed_aver", "cldhigh_aver")
    )
    bases = tuple(_values(data, f"cldbse{suffix}") for suffix, _ in _CLOUD_LADDER)
    cloud_tops = _values(data, "cldtop")
    altitudes = np.linspace(0.0, _CLOUD_MAX_KM, _CLOUD_FIELD_ROWS)
    columns = [
        _cloud_column(
            float(vlow[index]),
            float(low[index]),
            float(med[index]),
            float(high[index]),
            float(cloud_tops[index]),
            tuple(float(base[index]) for base in bases),
            altitudes,
        )
        for index in range(len(data.timestamps))
    ]
    field = _smooth_time(np.column_stack(columns), _CLOUD_SMOOTH_PASSES)
    return altitudes, field


def _cloud_legend(fig: Figure | SubFigure) -> None:
    """Meteoblue-style grey step legend above the cloud panel's right corner.

    One swatch per grey step, framed like meteoblue's bar, with labels on the
    swatch boundaries: every label is the lower coverage bound of its cell
    ("100" closes the last one), so a shade can never read as a different
    step than the one it renders for.
    """
    labels = ("10", "25", "50", "75", "90", "100")
    width, height = 0.03, 0.0085
    left = _CLOUD_AX[0] + _CLOUD_AX[2] - len(_CLOUD_STEPS) * width
    row = _CLOUD_AX[1] + _CLOUD_AX[3] + 0.026
    for index, (_, shade) in enumerate(_CLOUD_STEPS):
        fig.add_artist(
            Rectangle(
                (left + index * width, row),
                width,
                height,
                transform=fig.transFigure,
                facecolor=shade,
                edgecolor="none",
            )
        )
    fig.add_artist(
        Rectangle(
            (left, row),
            len(_CLOUD_STEPS) * width,
            height,
            transform=fig.transFigure,
            facecolor="none",
            edgecolor=INK,
            linewidth=0.5,
        )
    )
    for index, label in enumerate(labels):
        fig.text(
            left + index * width,
            row - 0.0025,
            label,
            fontsize=7,
            family="DejaVu Sans",
            ha="center",
            va="top",
        )
    fig.text(
        left - 0.012,
        row + height / 2,
        "Cloud cover (%)",
        fontsize=7.5,
        ha="right",
        va="center",
    )


def _draw_clouds(ax: plt.Axes, data: MeteogramData, hours: np.ndarray) -> None:
    """Cloud panel: coverage contoured over altitude, meteoblue-style.

    The rebuilt profile (see _cloud_field) is contoured through the grey
    steps over the true-km altitude axis, so where the grey sits reads as
    the cloud's altitude, the tone as its density, and the floating deck
    islands, gradations and clear-air gaps between decks come from the
    data instead of fixed altitude bands.
    """
    altitudes, field = _cloud_field(data)
    if len(hours) > 1:
        positions, coverage = hours, field
    else:
        # contouring needs a 2x2 grid: repeat the lone hour's column so it
        # paints the whole panel width, like the bands did
        positions, coverage = (-0.5, 0.5), np.repeat(field, 2, axis=1)
    ax.contourf(
        positions,
        altitudes,
        coverage,
        levels=_CLOUD_LEVELS,
        colors=_CLOUD_LEVEL_COLORS,
    )

    # meteoblue keeps this panel free of hour gridlines: they would bleed
    # through the clear-sky cells and break up the altitude bands.
    ax.grid(visible=False, axis="x")

    ax.set_ylim(0, _CLOUD_MAX_KM)
    ax.set_yticks([0, _CLOUD_LOW_TOP_KM, _CLOUD_HIGH_BASE_KM, _CLOUD_MAX_KM])
    ax.tick_params(axis="y", labelsize=11)  # thinner panel: keep ticks clear
    _unit_label(ax, "km", "left")
    _cloud_legend(ax.figure)
