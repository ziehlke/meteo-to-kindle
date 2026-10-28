"""Client for the Meteo ICM meteorogram API that powers app.meteo.pl.

The legacy meteo.pl meteogram image endpoint now serves an advertisement,
while the app fetches raw hourly forecast series as JSON and renders them
itself. This client mirrors those two requests:

1. ``GET /meteorograms/available`` to discover model run timestamps.
2. ``POST /meteorograms/{model}`` with the point to get the hourly series.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import sleep
from typing import Any

import httpx

from .config import (
    AIRLY_LATITUDE,
    AIRLY_LONGITUDE,
    METEO_API_BASE,
    METEO_MODEL,
    RETRY_DELAY_SECONDS,
)

# The API marks missing data with a Fortran-style fill value (~-3.27e8);
# anything beyond this threshold is treated as missing as well.
_FILL_THRESHOLD = 1e6


def _clean(value: Any) -> float | None:
    """Normalize one data point: keep finite numbers, drop everything else."""
    if value is None:
        return None
    try:
        number = float(value)
    except TypeError, ValueError:
        return None  # junk like "n/a" counts as missing
    if math.isnan(number) or math.isinf(number) or abs(number) > _FILL_THRESHOLD:
        return None
    return number


@dataclass(frozen=True)
class MeteogramData:
    """Hourly forecast series for one model run at one point."""

    model: str
    start: datetime  # model run start, UTC
    latitude: float
    longitude: float
    timestamps: tuple[datetime, ...]
    series: dict[str, tuple[float | None, ...]]

    def values(self, name: str) -> tuple[float | None, ...]:
        """Values for a series name, or all-missing when it is not provided."""
        return self.series.get(name, (None,) * len(self.timestamps))


class MeteoClient:
    """Fetches meteorogram data from the Meteo ICM API with retries."""

    def __init__(
        self,
        base_url: str = METEO_API_BASE,
        model: str = METEO_MODEL,
        latitude: float = AIRLY_LATITUDE,
        longitude: float = AIRLY_LONGITUDE,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._point = {"lat": latitude, "lon": longitude}
        self._max_retries = max_retries

    def fetch(self) -> MeteogramData:
        """Fetch the latest available model run for the configured point."""
        run = self._fetch_available()
        payload = self._fetch_run(run)
        return _parse(self._model, payload)

    def _fetch_available(self) -> int:
        """Return the newest model run timestamp currently available."""
        data = self._request("GET", "/meteorograms/available", None, "timestamps")
        runs = data.get(self._model) if isinstance(data, dict) else None
        if not isinstance(runs, list) or not runs:
            raise RuntimeError(f"No runs available for model '{self._model}'")
        return max(runs)

    def _fetch_run(self, run: int) -> dict[str, Any]:
        """Fetch the forecast series for one model run."""
        body = {"point": self._point, "date": run}
        return self._request("POST", f"/meteorograms/{self._model}", body, "forecast")

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None, label: str
    ) -> Any:
        """Perform one request with retries, returning the decoded JSON."""
        url = self._base_url + path
        error: ValueError | httpx.HTTPError | None = None
        with httpx.Client(follow_redirects=True) as client:
            for attempt in range(1, self._max_retries + 1):
                try:
                    response = client.request(method, url, json=body)
                    response.raise_for_status()
                    return response.json()
                except (ValueError, httpx.HTTPError) as e:
                    error = e
                    if attempt < self._max_retries:
                        print(
                            f"\n{label.capitalize()} request failed "
                            f"(attempt {attempt}/{self._max_retries}), "
                            f"retrying in {RETRY_DELAY_SECONDS} seconds...\n"
                        )
                        sleep(RETRY_DELAY_SECONDS)
        raise RuntimeError(
            f"Failed to fetch {label} after {self._max_retries} attempts: {error}"
        ) from error


def _parse(model: str, payload: Any) -> MeteogramData:
    """Turn one API run payload into a MeteogramData object."""
    raw = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise RuntimeError("Meteo API returned no series data")

    names = [name for name in raw if isinstance(raw[name], dict)]
    if not names:
        raise RuntimeError("Meteo API returned no series data")
    reference = _series_spec(raw, names[0])
    interval = reference.get("interval")
    if not isinstance(interval, (int, float)) or interval <= 0:
        raise RuntimeError("Meteo API returned no valid series interval")
    step = int(interval)
    start = _parse_start(payload.get("fstart"))
    latitude, longitude = _parse_point(reference.get("point"))

    # Series may be slightly uneven; pad to the length of the first one.
    count = len(reference["data"])
    series = {
        name: _cleaned_values(_series_spec(raw, name)["data"], count) for name in names
    }
    timestamps = tuple(start + timedelta(seconds=step * i) for i in range(count))
    return MeteogramData(
        model=model,
        start=start,
        latitude=latitude,
        longitude=longitude,
        timestamps=timestamps,
        series=series,
    )


def _parse_point(point: Any) -> tuple[float, float]:
    """Extract the model grid point the forecast was resolved to."""
    if not isinstance(point, dict) or "lat" not in point or "lon" not in point:
        raise RuntimeError("Meteo API returned no resolved point")
    try:
        return float(point["lat"]), float(point["lon"])
    except (TypeError, ValueError) as e:
        raise RuntimeError(
            f"Meteo API returned invalid point coordinates: {point!r}"
        ) from e


def _series_spec(raw: dict[str, Any], name: str) -> dict[str, Any]:
    spec = raw[name]
    if not isinstance(spec, dict) or not isinstance(spec.get("data"), list):
        raise RuntimeError(f"Meteo API series '{name}' has no data")
    return spec


def _cleaned_values(values: list[Any], count: int) -> tuple[float | None, ...]:
    """Clean one series and pad/truncate it to the expected length."""
    cleaned = [_clean(value) for value in values]
    return tuple(cleaned[:count]) + (None,) * max(0, count - len(cleaned))


def _parse_start(value: Any) -> datetime:
    """Parse the model run start timestamp (ISO-8601, UTC)."""
    if not isinstance(value, str):
        raise RuntimeError("Meteo API returned no run start timestamp")
    try:
        start = datetime.fromisoformat(value)
    except ValueError as e:
        raise RuntimeError(f"Invalid run start timestamp: {value!r}") from e
    if start.tzinfo is None:
        raise RuntimeError(f"Run start timestamp has no timezone: {value!r}")
    return start.astimezone(UTC)
