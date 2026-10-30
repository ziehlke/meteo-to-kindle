"""Tests for image_processor: composing the template and meteogram."""

from pathlib import Path

from PIL import Image

from meteo_to_kindle.image_processor import WeatherImageProcessor

BLUE = (0, 0, 255)
RED = (255, 0, 0)


def _solid(size: tuple[int, int], color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", size, color)


def test_paste_meteogram_pastes_at_top(tmp_path: Path) -> None:
    template = _solid((600, 800), BLUE)
    template.save(tmp_path / "template.png")
    meteogram = _solid((600, 500), RED)
    meteogram.save(tmp_path / "meteogram.png")

    processor = WeatherImageProcessor(output_dir=tmp_path)
    result = processor.paste_meteogram(tmp_path / "meteogram.png")

    assert result.size == (600, 800)
    assert result.getpixel((10, 10)) == (76, 76, 76)  # red converted to grayscale
    assert result.getpixel((10, 501)) == BLUE  # template below the meteogram


def test_paste_meteogram_resizes_off_target_width(tmp_path: Path) -> None:
    template = _solid((600, 800), BLUE)
    template.save(tmp_path / "template.png")
    meteogram = _solid((525, 425), RED)
    meteogram.save(tmp_path / "meteogram.png")

    processor = WeatherImageProcessor(output_dir=tmp_path)
    result = processor.paste_meteogram(tmp_path / "meteogram.png")

    assert result.size == (600, 800)
    assert result.getpixel((10, 10)) == (76, 76, 76)
    # Resized meteogram ends at int(425 * 600 / 525) == 485
    assert result.getpixel((10, 486)) == BLUE
    assert meteogram.size == (525, 425)  # source file untouched
