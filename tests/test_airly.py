"""Tests for airly: API fetching, value parsing and template rendering."""

import shutil

import httpx
import pytest
import respx

import airly
from airly import Airly, _percent
from config import (
    ADVICE_POSITION,
    AIRLY_API_URL_TEMPLATE,
    AIRLY_LATITUDE,
    AIRLY_LONGITUDE,
    CAQI_POSITION,
)

AIRLY_URL = AIRLY_API_URL_TEMPLATE.format(lat=AIRLY_LATITUDE, lng=AIRLY_LONGITUDE)

PAYLOAD = {
    "current": {
        "indexes": [{"value": 42.4, "advice": "Take a walk!", "color": "#60BC46"}],
        "values": [
            {"name": "PM1", "value": 3.6},
            {"name": "PM25", "value": 5.2},
            {"name": "PM10", "value": 7.4},
            {"name": "TEMPERATURE", "value": 23.5},
            {"name": "HUMIDITY", "value": 58.2},
        ],
    },
    "history": [
        {
            "fromDateTime": "2026-08-11T14:00:00.000Z",
            "indexes": [{"value": 30, "color": "#60BC46"}],
        },
        {
            "fromDateTime": "2026-08-11T15:00:00.000Z",
            "indexes": [{"value": 40, "color": "#F9A825"}],
        },
    ],
}


@pytest.fixture
def airly_client(monkeypatch) -> Airly:
    """An Airly instance with a fake API key and no network access."""
    monkeypatch.setenv("AIRLY_KEY", "test-key")
    return Airly()


class RecordingDraw:
    """Stand-in for ImageDraw.Draw that records every draw.text call."""

    def __init__(self):
        self.calls = []

    def text(self, position, text, fill=None, font=None):
        self.calls.append({"position": position, "text": text, "fill": fill})


# --------------------------------------------------------------------- API


def test_init_requires_api_key(monkeypatch):
    monkeypatch.delenv("AIRLY_KEY", raising=False)
    with pytest.raises(ValueError, match="AIRLY_KEY"):
        Airly()


@respx.mock
def test_data_is_fetched_once_with_api_key(airly_client):
    route = respx.get(AIRLY_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))

    assert airly_client.data == PAYLOAD
    assert airly_client.data == PAYLOAD  # cached, no second request
    assert route.call_count == 1
    assert route.calls.last.request.headers["apikey"] == "test-key"


@respx.mock
def test_fetch_failure_raises_runtime_error(airly_client):
    respx.get(AIRLY_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(RuntimeError, match="Failed to fetch air quality data"):
        _ = airly_client.data  # property access triggers the fetch


# ----------------------------------------------------------------- values


def test_get_value_by_name(airly_client):
    airly_client._data = PAYLOAD
    assert airly_client.get_value_by_name("PM25") == 5.2


def test_get_value_by_name_returns_zero_for_missing_data(airly_client):
    airly_client._data = PAYLOAD
    assert airly_client.get_value_by_name("NOPE") == 0.0
    airly_client._data = {}
    assert airly_client.get_value_by_name("PM25") == 0.0


@pytest.mark.parametrize(
    ("value", "threshold", "expected"),
    [(5.2, 25.0, "21%"), (7.4, 50.0, "15%"), (25.0, 25.0, "100%")],
)
def test_percent(value, threshold, expected):
    assert _percent(value, threshold) == expected


# ----------------------------------------------------------------- render


@pytest.fixture
def rendered_template(monkeypatch, tmp_path):
    """Run fill_template with a recording draw object and return its calls."""

    def render(payload):
        shutil.copy(airly.HOME_DIR / "master_template.png", tmp_path)
        monkeypatch.setattr(airly, "HOME_DIR", tmp_path)
        recorder = RecordingDraw()
        monkeypatch.setattr(airly.ImageDraw, "Draw", lambda image: recorder)
        client = Airly()
        client._data = payload
        client.fill_template()
        return recorder.calls

    return render


def test_fill_template_draws_all_values(rendered_template):
    calls = rendered_template(PAYLOAD)
    drawn = {(c["position"], c["text"]): c["fill"] for c in calls}

    assert drawn[(CAQI_POSITION, "42")] == "black"
    assert drawn[(ADVICE_POSITION, "Take a walk!")] == "black"


def test_fill_template_requires_current_data(rendered_template):
    with pytest.raises(ValueError, match="No current air quality data"):
        rendered_template({})


@pytest.mark.parametrize(
    ("caqi", "emoji"),
    [(15, "😍"), (42.4, "🙂"), (200, "💩")],
)
def test_fill_template_picks_emoji_by_caqi(rendered_template, caqi, emoji):
    payload = {"current": {"indexes": [{"value": caqi, "advice": "..."}], "values": []}}
    calls = rendered_template(payload)
    emoji_call = next(c for c in calls if c["text"] in "😍😀🙂😐😟🤬💩")
    assert emoji_call["text"] == emoji


# ------------------------------------------------------------------ chart


def test_plot_caqi_history_saves_chart(airly_client, monkeypatch, tmp_path):
    monkeypatch.setattr(airly, "HOME_DIR", tmp_path)
    airly_client._data = PAYLOAD
    airly_client.plot_caqi_history()
    assert (tmp_path / "caqi.png").exists()


def test_plot_caqi_history_requires_history(airly_client):
    airly_client._data = {"current": PAYLOAD["current"]}
    with pytest.raises(ValueError, match="No air quality data"):
        airly_client.plot_caqi_history()
