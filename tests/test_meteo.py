"""Tests for the Meteo ICM API client: parsing, retries and error paths."""

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

import meteo_to_kindle.meteo as meteo
from meteo_to_kindle.config import AIRLY_LATITUDE, AIRLY_LONGITUDE, METEO_API_BASE
from meteo_to_kindle.meteo import MeteoClient, MeteogramData, _clean, _parse

BASE_URL = METEO_API_BASE
AVAILABLE_URL = f"{BASE_URL}/meteorograms/available"
RUN_URL = f"{BASE_URL}/meteorograms/um4_60"

POINT: dict[str, Any] = {
    "lat": 50.07,
    "lon": 20.05,
    "grid": "P5",
    "row": 151,
    "col": 236,
}

AVAILABLE = {
    "um4_60": [1793016000, 1793037600, 1793059200],
    "um4_120": [1793059200],
    "gfs": [1792994400],
}


def _series(values: list[Any]) -> dict[str, Any]:
    return {"data": values, "interval": 3600, "unit": "x", "point": POINT}


def _run_payload(
    values: list[Any], fstart: str = "2026-10-26T12:00:00Z"
) -> dict[str, Any]:
    return {
        "fstart": fstart,
        "data": {
            "airtmp_point": _series(values),
            "pcpttl_max": _series([0.0] * len(values)),
        },
    }


@pytest.fixture
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the real sleep with a recorder so tests don't wait."""
    calls: list[float] = []
    monkeypatch.setattr(meteo, "sleep", calls.append)
    return calls


@respx.mock
def test_fetch_returns_latest_run_as_series() -> None:
    respx.get(AVAILABLE_URL).mock(return_value=httpx.Response(200, json=AVAILABLE))
    route = respx.post(RUN_URL).mock(
        return_value=httpx.Response(
            200, json=_run_payload([10.5, None, -327276480.0, 8.1])
        )
    )

    data = MeteoClient().fetch()

    assert route.called
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "point": {"lat": AIRLY_LATITUDE, "lon": AIRLY_LONGITUDE},
        "date": 1793059200,
    }
    assert data.model == "um4_60"
    assert data.latitude == 50.07
    assert data.longitude == 20.05
    assert data.start == datetime(2026, 10, 26, 12, tzinfo=UTC)
    assert data.timestamps[0] == data.start
    assert len(data.timestamps) == 4
    assert data.series["airtmp_point"] == (10.5, None, None, 8.1)
    assert data.values("pcpttl_max") == (0.0, 0.0, 0.0, 0.0)


def test_values_falls_back_to_all_missing() -> None:
    data = MeteogramData(
        model="um4_60",
        start=datetime(2026, 10, 26, 12, tzinfo=UTC),
        latitude=50.07,
        longitude=20.05,
        timestamps=(datetime(2026, 10, 26, 12, tzinfo=UTC),),
        series={},
    )
    assert data.values("airtmp_point") == (None,)


@respx.mock
def test_fetch_raises_when_model_has_no_runs() -> None:
    respx.get(AVAILABLE_URL).mock(return_value=httpx.Response(200, json=AVAILABLE))
    with pytest.raises(RuntimeError, match="No runs available for model 'nope'"):
        MeteoClient(model="nope").fetch()


@respx.mock
def test_fetch_retries_then_succeeds(fast_sleep: list[float]) -> None:
    respx.get(AVAILABLE_URL).mock(return_value=httpx.Response(200, json=AVAILABLE))
    respx.post(RUN_URL).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json=_run_payload([1.0])),
        ]
    )

    data = MeteoClient().fetch()

    assert data.values("airtmp_point") == (1.0,)
    assert fast_sleep == [meteo.RETRY_DELAY_SECONDS]


@respx.mock
def test_fetch_gives_up_after_max_retries(fast_sleep: list[float]) -> None:
    respx.get(AVAILABLE_URL).mock(return_value=httpx.Response(200, json=AVAILABLE))
    respx.post(RUN_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(RuntimeError, match="Failed to fetch forecast after 3 attempts"):
        MeteoClient().fetch()
    assert fast_sleep == [meteo.RETRY_DELAY_SECONDS, meteo.RETRY_DELAY_SECONDS]


@respx.mock
def test_fetch_retries_invalid_json(fast_sleep: list[float]) -> None:
    respx.get(AVAILABLE_URL).mock(
        side_effect=[
            httpx.Response(200, content=b"not json"),
            httpx.Response(200, json=AVAILABLE),
        ]
    )

    client = MeteoClient()
    assert client._fetch_available() == 1793059200
    assert fast_sleep == [meteo.RETRY_DELAY_SECONDS]


def test_clean_accepts_finite_and_drops_missing() -> None:
    assert _clean(None) is None
    assert _clean(7.25) == 7.25
    assert _clean("n/a") is None
    assert _clean("3.5") == 3.5
    assert _clean(float("nan")) is None
    assert _clean(float("inf")) is None
    assert _clean(-3.27e8) is None


@respx.mock
def test_fetch_raises_on_malformed_available_response() -> None:
    respx.get(AVAILABLE_URL).mock(
        side_effect=[
            httpx.Response(200, json=[1, 2, 3]),
            httpx.Response(200, json={"um4_60": "soon"}),
            httpx.Response(200, json={"um4_60": []}),
        ]
    )

    client = MeteoClient()
    for _ in range(3):
        with pytest.raises(RuntimeError, match="No runs available for model 'um4_60'"):
            client.fetch()


def test_parse_raises_without_series_data() -> None:
    with pytest.raises(RuntimeError, match="no series data"):
        _parse("um4_60", {"fstart": "2026-10-26T12:00:00Z"})
    with pytest.raises(RuntimeError, match="no series data"):
        _parse("um4_60", {"fstart": "2026-10-26T12:00:00Z", "data": {"a": "junk"}})


def test_parse_raises_on_malformed_payload() -> None:
    with pytest.raises(RuntimeError, match="no series data"):
        _parse("um4_60", ["not", "a", "dict"])


def test_parse_raises_for_invalid_interval() -> None:
    for interval in (None, 0, -3600, "soon", 0.5, float("nan")):
        series = _series([1.0])
        if interval is None:
            del series["interval"]
        else:
            series["interval"] = interval
        payload = {"fstart": "2026-10-26T12:00:00Z", "data": {"a": series}}
        with pytest.raises(RuntimeError, match="no valid series interval"):
            _parse("um4_60", payload)


def test_parse_accepts_whole_float_interval() -> None:
    series = _series([1.0, 2.0])
    series["interval"] = 3600.0
    data = _parse("um4_60", {"fstart": "2026-10-26T12:00:00Z", "data": {"a": series}})
    assert data.timestamps == (
        datetime(2026, 10, 26, 12, tzinfo=UTC),
        datetime(2026, 10, 26, 13, tzinfo=UTC),
    )


def test_parse_raises_when_series_has_no_data() -> None:
    with pytest.raises(RuntimeError, match="series 'a' has no data"):
        _parse(
            "um4_60",
            {"fstart": "2026-10-26T12:00:00Z", "data": {"a": {"interval": 3600}}},
        )


def test_parse_raises_for_missing_fstart() -> None:
    with pytest.raises(RuntimeError, match="no run start timestamp"):
        _parse("um4_60", {"data": {"a": _series([1.0])}})


def test_parse_raises_for_invalid_fstart() -> None:
    with pytest.raises(RuntimeError, match="Invalid run start timestamp"):
        _parse("um4_60", {"fstart": "yesterday", "data": {"a": _series([1.0])}})


def test_parse_raises_for_naive_fstart() -> None:
    with pytest.raises(RuntimeError, match="has no timezone"):
        _parse(
            "um4_60",
            {"fstart": "2026-10-26T12:00:00", "data": {"a": _series([1.0])}},
        )


def test_parse_raises_for_missing_point() -> None:
    with pytest.raises(RuntimeError, match="no resolved point"):
        _parse(
            "um4_60",
            {
                "fstart": "2026-10-26T12:00:00Z",
                "data": {"a": {"data": [1.0], "interval": 3600}},
            },
        )


def test_parse_raises_for_invalid_point_values() -> None:
    series = _series([1.0])
    series["point"] = {"lat": "n/a", "lon": 20.05}
    payload = {"fstart": "2026-10-26T12:00:00Z", "data": {"a": series}}
    with pytest.raises(RuntimeError, match="invalid point coordinates"):
        _parse("um4_60", payload)


def test_parse_pads_uneven_series_to_reference_length() -> None:
    payload = {
        "fstart": "2026-10-26T12:00:00Z",
        "data": {
            "airtmp_point": _series([1.0, 2.0, 3.0]),
            "short_series": _series([9.0]),
        },
    }
    data = _parse("um4_60", payload)
    assert data.series["short_series"] == (9.0, None, None)


def test_parse_drops_nan_and_fill_values() -> None:
    payload = {
        "fstart": "2026-10-26T12:00:00Z",
        "data": {"airtmp_point": _series([float("nan"), float("inf"), -3.27e8, 1.0])},
    }
    data = _parse("um4_60", payload)
    assert data.series["airtmp_point"] == (None, None, None, 1.0)
