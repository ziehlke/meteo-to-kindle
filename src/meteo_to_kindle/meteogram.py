"""Render a Kindle-friendly grayscale meteogram from Meteo ICM data.

The output is designed for a 600px-wide e-ink display: black-and-gray
panels stacked like the classic meteo.pl meteogram (temperature, wind,
precipitation, cloud cover) with a top hour/date axis and day/night
shading computed from the sun's position.
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
from matplotlib.lines import Line2D
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
# get their own horizontal band without collisions.
_TEMP_AX = (0.105, 0.641, 0.84, 0.257)
_PRECIP_AX = (0.105, 0.411, 0.84, 0.19)
_WIND_AX = (0.105, 0.192, 0.84, 0.169)
_CLOUD_AX = (0.105, 0.02, 0.84, 0.123)

_MODEL_TITLES = {"um4_60": "UM4 · 60h", "um4_120": "UM4 · 120h", "gfs": "GFS · 240h"}


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
        alignment, position = "center", axes_left + axes_width * fraction
        # Only sliver days at the run edges need pinning to the figure rims;
        # interior days are always full-day buckets, and pinning them too
        # would let two captions share an anchor and overlap.
        if index == 0 and fraction < 0.08:
            alignment, position = "left", 0.01
        elif index == len(labels) - 1 and fraction > 0.92:
            alignment, position = "right", 0.99
        fig.text(position, 0.938, label, fontsize=10.5, ha=alignment)


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


def _draw_clouds(ax: plt.Axes, data: MeteogramData, hours: np.ndarray) -> None:
    """Cloud cover panel: layered very low/low/mid/high fills in grays."""
    layers = [
        (_values(data, "cldhigh_aver"), "0.8"),  # drawn first, lightest
        (_values(data, "cldmed_aver"), "0.55"),
        (_values(data, "cldlow_aver"), "0.35"),
        (_values(data, "cldvlow_aver"), "0.15"),  # drawn last, darkest
    ]
    for coverage, shade in layers:
        ax.fill_between(
            hours, 0, np.nan_to_num(coverage, nan=0.0) * 100, color=shade, lw=0
        )
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 50, 100])
    _unit_label(ax, "%", "left")
