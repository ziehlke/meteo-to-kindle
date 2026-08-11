"""Tests for get_image: downloading with retries, publishing, full pipeline."""

import shutil
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from PIL import Image

import airly
import get_image
from config import (
    AIRLY_API_URL_TEMPLATE,
    AIRLY_LATITUDE,
    AIRLY_LONGITUDE,
    KRAKOW_COORDS,
    RETRY_DELAY_SECONDS,
    WEATHER_URL_TEMPLATE,
)
from get_image import fetch_weather_image, publish_to_share

METEO_URL = WEATHER_URL_TEMPLATE.format(row=KRAKOW_COORDS[0], col=KRAKOW_COORDS[1])
AIRLY_URL = AIRLY_API_URL_TEMPLATE.format(lat=AIRLY_LATITUDE, lng=AIRLY_LONGITUDE)

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


def _png_bytes(
    size: tuple[int, int], color: tuple[int, int, int] = (255, 255, 255)
) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _no_pngcrush(_name: str) -> None:
    return None


def _found_pngcrush(_name: str) -> str:
    return "/usr/bin/pngcrush"


@pytest.fixture
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the real sleep with a recorder so tests don't wait."""
    calls: list[float] = []
    monkeypatch.setattr(get_image, "sleep", calls.append)
    return calls


@respx.mock
def test_fetch_weather_image_success() -> None:
    respx.get(METEO_URL).mock(
        return_value=httpx.Response(200, content=_png_bytes((8, 8)))
    )
    image = fetch_weather_image(METEO_URL)
    assert image.mode == "RGB"
    assert image.size == (8, 8)


@respx.mock
def test_fetch_weather_image_retries_then_succeeds(fast_sleep: list[float]) -> None:
    respx.get(METEO_URL).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, content=_png_bytes((8, 8))),
        ]
    )
    image = fetch_weather_image(METEO_URL)
    assert image.size == (8, 8)
    assert fast_sleep == [RETRY_DELAY_SECONDS]


@respx.mock
def test_fetch_weather_image_gives_up_after_max_retries(
    fast_sleep: list[float],
) -> None:
    respx.get(METEO_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        fetch_weather_image(METEO_URL)
    assert fast_sleep == [RETRY_DELAY_SECONDS, RETRY_DELAY_SECONDS]


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

    def fake_run(cmd: list[str], check: bool) -> None:
        Path("pngout.png").write_bytes(b"crushed")  # pngcrush's output file

    monkeypatch.setattr(get_image.subprocess, "run", fake_run)
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.chdir(tmp_path)

    publish_to_share(Path("out.png"), share)

    assert (share / "pngout.png").read_bytes() == b"crushed"


# ------------------------------------------------------------------- main


@respx.mock
def test_main_end_to_end_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIRLY_KEY", "test-key")
    monkeypatch.setattr(get_image.shutil, "which", _no_pngcrush)

    # Redirect all generated files into a temp directory
    shutil.copy(airly.HOME_DIR / "master_template.png", tmp_path)
    monkeypatch.setattr(airly, "HOME_DIR", tmp_path)
    monkeypatch.setattr(get_image, "HOME_DIR", tmp_path)

    respx.get(AIRLY_URL).mock(return_value=httpx.Response(200, json=AIRLY_PAYLOAD))
    respx.get(METEO_URL).mock(
        return_value=httpx.Response(200, content=_png_bytes((600, 757)))
    )

    get_image.main()

    assert (tmp_path / "template.png").exists()
    assert (tmp_path / "caqi.png").exists()
    output = tmp_path / "weather-script-output.png"
    with Image.open(output) as result:
        assert result.size == (600, 800)
        assert result.mode == "L"  # kindle grayscale
