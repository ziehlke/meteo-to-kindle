"""Tests for the main pipeline: full offline run and publishing."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from PIL import Image

import meteo_to_kindle.airly as airly
import meteo_to_kindle.cli as get_image
from meteo_to_kindle.cli import publish_to_share
from meteo_to_kindle.config import (
    AIRLY_API_URL_TEMPLATE,
    AIRLY_LATITUDE,
    AIRLY_LONGITUDE,
    METEO_API_BASE,
    METEO_MODEL,
)

AIRLY_URL = AIRLY_API_URL_TEMPLATE.format(lat=AIRLY_LATITUDE, lng=AIRLY_LONGITUDE)
AVAILABLE_URL = f"{METEO_API_BASE}/meteorograms/available"
RUN_URL = f"{METEO_API_BASE}/meteorograms/{METEO_MODEL}"

METEO_POINT: dict[str, Any] = {
    "lat": 50.07,
    "lon": 20.05,
    "grid": "P5",
    "row": 151,
    "col": 236,
}


def _series(values: list[float]) -> dict[str, Any]:
    return {"data": values, "interval": 3600, "unit": "x", "point": METEO_POINT}


METEO_AVAILABLE: dict[str, Any] = {
    "um4_60": [1793059200],
    "um4_120": [1793059200],
    "gfs": [1793059200],
}

METEO_RUN: dict[str, Any] = {
    "fstart": "2026-10-26T12:00:00Z",
    "data": {
        "airtmp_point": _series([10.5, 9.0, 8.0, 7.5, 9.0, 12.0]),
        "airtmp_min": _series([10.0, 8.5, 7.5, 7.0, 8.5, 11.5]),
        "airtmp_max": _series([11.0, 9.5, 8.5, 8.0, 9.5, 12.5]),
        "dwptmp_point": _series([8.0, 7.5, 7.0, 6.5, 7.0, 8.5]),
        "slpres_point": _series([101_000, 101_100, 101_200, 101_300, 101_400, 101_500]),
        "pcpttl_max": _series([0.0, 0.5, 2.0, 0.0, 0.0, 0.0]),
        "pcpttlprob_point": _series([10.0, 50.0, 80.0, 30.0, 10.0, 5.0]),
        "pcpttl_type_max": _series([0.0, 1.0, 2.0, 0.0, 0.0, 0.0]),
        "storm_max": _series([0.0, 0.0, 2.0, 0.0, 0.0, 0.0]),
        "wind10_sd_true_prev_point": _series([3.0, 4.0, 5.0, 4.5, 3.5, 2.5]),
        "wind_gust_max": _series([7.0, 9.0, 11.0, 10.0, 8.0, 6.0]),
        "wind10_dr_deg_true_prev_point": _series(
            [270.0, 280.0, 290.0, 300.0, 310.0, 320.0]
        ),
        "cldvlow_aver": _series([0.0, 0.1, 0.2, 0.1, 0.0, 0.0]),
        "cldlow_aver": _series([0.4, 0.5, 0.8, 0.6, 0.3, 0.1]),
        "cldmed_aver": _series([0.3, 0.4, 0.5, 0.4, 0.2, 0.1]),
        "cldhigh_aver": _series([0.1, 0.2, 0.3, 0.2, 0.1, 0.0]),
    },
}

AIRLY_PAYLOAD: dict[str, Any] = {
    "current": {
        "indexes": [{"value": 42.4, "advice": "Take a walk!"}],
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
        }
    ],
}


def _no_pngcrush(_name: str) -> None:
    return None


def _found_pngcrush(_name: str) -> str:
    return "/usr/bin/pngcrush"


# ------------------------------------------------------------------- main


@respx.mock
def test_main_end_to_end_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIRLY_KEY", "test-key")
    monkeypatch.setattr(get_image.shutil, "which", _no_pngcrush)

    # Redirect all generated files into a temp directory
    monkeypatch.setattr(airly, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(get_image, "OUTPUT_DIR", tmp_path)

    respx.get(AIRLY_URL).mock(return_value=httpx.Response(200, json=AIRLY_PAYLOAD))
    respx.get(AVAILABLE_URL).mock(
        return_value=httpx.Response(200, json=METEO_AVAILABLE)
    )
    respx.post(RUN_URL).mock(return_value=httpx.Response(200, json=METEO_RUN))

    get_image.main()

    assert (tmp_path / "template.png").exists()
    assert (tmp_path / "caqi.png").exists()
    assert (tmp_path / "meteogram.png").exists()
    output = tmp_path / "weather-script-output.png"
    with Image.open(output) as result:
        assert result.size == (600, 800)
        assert result.mode == "L"  # kindle grayscale


# --------------------------------------------------------------- publishing


def test_publish_skipped_without_pngcrush(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_image.shutil, "which", _no_pngcrush)
    run_calls: list[tuple[object, ...]] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        run_calls.append(args)

    monkeypatch.setattr(get_image.subprocess, "run", fake_run)
    publish_to_share(Path("out.png"), Path("/somewhere"))
    assert run_calls == []


def test_publish_crushes_and_moves_to_share(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(get_image.shutil, "which", _found_pngcrush)

    def fake_run(cmd: list[str], check: bool, cwd: Path) -> None:
        Path("pngout.png").write_bytes(b"crushed")  # pngcrush's output file

    monkeypatch.setattr(get_image.subprocess, "run", fake_run)
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.chdir(tmp_path)

    publish_to_share(Path("out.png"), share)

    assert (share / "pngout.png").read_bytes() == b"crushed"
