"""Tests for image_processor: geometry, color replacement and non-mutation."""

from pathlib import Path

import pytest
from PIL import Image

from image_processor import Box, WeatherImageProcessor

BLUE = (0, 0, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)

# The real meteogram is 600x757; crop/final-crop constants are tuned for it
METEOGRAM_SIZE = (600, 757)


def _solid(size: tuple[int, int], color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", size, color)


@pytest.mark.parametrize(
    ("box", "expected"),
    [
        ((0, 646, None, 757), (0, 646, 600, 757)),  # None -> image edge
        ((10, 20, 30, 40), (10, 20, 30, 40)),  # plain values pass through
        ((35, 122, -40, -10), (35, 122, 560, 747)),  # negatives count from edge
    ],
)
def test_resolve_box(box: Box, expected: tuple[int, int, int, int]) -> None:
    assert WeatherImageProcessor._resolve_box(box, METEOGRAM_SIZE) == expected


def test_crop_image_moves_sections_and_crops(tmp_path: Path) -> None:
    # Red band exactly covering the first crop source region
    img = _solid(METEOGRAM_SIZE, BLUE)
    img.paste(_solid((600, 757 - 646), RED), (0, 646))

    processor = WeatherImageProcessor(home_dir=tmp_path)
    result = processor.crop_image(img)

    # Final crop (35, 122, -40, 547) of 600x757
    assert result.size == (525, 425)
    # Row moved by first paste: source (35, 646) -> target (35, 522)
    assert result.getpixel((0, 522 - 122)) == RED
    # Second paste pulls its bottom part from the just-moved red band:
    # source row 434 + (436 - 348) = 522 -> red
    assert result.getpixel((0, 436 - 122)) == RED
    # ...while its top part still comes from the original blue area
    assert result.getpixel((0, 400 - 122)) == BLUE


def test_remove_logo_replaces_exact_colors_only(tmp_path: Path) -> None:
    img = Image.new("RGB", (3, 2))
    pixels = [
        (255, 251, 240),  # white-ish -> pure white
        (215, 216, 215),  # gray-ish  -> target gray
        (1, 2, 3),  # untouched
        (244, 244, 244),  # white-ish -> pure white
        (216, 216, 216),  # gray-ish  -> target gray
        (255, 252, 240),  # near miss -> untouched
    ]
    img.putdata(pixels)

    processor = WeatherImageProcessor(home_dir=tmp_path)
    result = processor.remove_logo(img)

    expected = [
        (255, 255, 255),
        (226, 226, 226),
        (1, 2, 3),
        (255, 255, 255),
        (226, 226, 226),
        (255, 252, 240),
    ]
    assert [result.getpixel((x, y)) for y in range(2) for x in range(3)] == expected


def test_adjust_size_resizes_and_pastes_onto_template(tmp_path: Path) -> None:
    template = _solid((600, 800), BLUE)
    template.save(tmp_path / "template.png")
    weather = _solid((525, 425), RED)

    processor = WeatherImageProcessor(home_dir=tmp_path)
    result = processor.adjust_size(weather)

    assert result.size == (600, 800)
    assert result.getpixel((10, 10)) == RED  # pasted weather at the top
    # Resized weather ends at int(425 * 600 / 525) == 485
    assert result.getpixel((10, 500)) == BLUE  # template below it
    assert weather.size == (525, 425)  # input untouched


def test_paste_caqi_draws_chart_without_mutating_input(tmp_path: Path) -> None:
    caqi = _solid((100, 50), GREEN)
    caqi.save(tmp_path / "caqi.png")
    base = _solid((600, 800), BLUE)

    processor = WeatherImageProcessor(home_dir=tmp_path)
    result = processor.paste_caqi(base)

    assert result.getpixel((10, 510)) == GREEN  # chart pasted at (0, 500)
    assert result.getpixel((10, 499)) == BLUE  # above the chart unchanged
    assert base.getpixel((10, 510)) == BLUE  # input not mutated
