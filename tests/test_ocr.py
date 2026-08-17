"""OCR 로직 테스트.

텍스트 조립·전처리는 Tesseract 없이 검증하고, 실제 인식은 엔진이 설치된
환경에서만 실행한다(없으면 skip).
"""

import shutil

import pytest
from PIL import Image, ImageDraw

from imagetxt import ocr
from imagetxt.ocr import _Word

pytest.importorskip("pytesseract")

TESSERACT_MISSING = shutil.which("tesseract") is None


def words(*specs):
    """(블록, 문단, 줄, 텍스트) 튜플들을 _Word 목록으로 만든다."""
    return [
        _Word(block=b, paragraph=p, line=ln, text=t, confidence=95.0)
        for b, p, ln, t in specs
    ]


def test_build_text_keeps_lines_as_they_appear():
    text = ocr._build_text(
        words(
            (1, 1, 1, "Hello"),
            (1, 1, 1, "world"),
            (1, 1, 2, "second"),
            (1, 1, 2, "line"),
        ),
        "lines",
    )
    assert text == "Hello world\nsecond line"


def test_build_text_separates_paragraphs_with_blank_line():
    text = ocr._build_text(
        words((1, 1, 1, "First"), (1, 2, 1, "Second"), (2, 1, 1, "Third")),
        "lines",
    )
    assert text == "First\n\nSecond\n\nThird"


def test_build_text_paragraph_layout_joins_wrapped_lines():
    text = ocr._build_text(
        words((1, 1, 1, "wrapped"), (1, 1, 2, "sentence"), (1, 2, 1, "next")),
        "paragraph",
    )
    assert text == "wrapped sentence\n\nnext"


def test_build_text_paragraph_layout_reattaches_hyphenated_word():
    text = ocr._build_text(words((1, 1, 1, "exam-"), (1, 1, 2, "ple")), "paragraph")
    assert text == "example"


def test_build_text_empty():
    assert ocr._build_text([], "lines") == ""


def test_collect_words_skips_blanks_and_unrecognized():
    data = {
        "text": ["", "Hello", "  ", "world"],
        "conf": ["-1", "91.5", "-1", "88"],
        "block_num": [1, 1, 1, 1],
        "par_num": [1, 1, 1, 1],
        "line_num": [1, 1, 1, 1],
    }
    collected = ocr._collect_words(data)
    assert [w.text for w in collected] == ["Hello", "world"]
    assert collected[0].confidence == pytest.approx(91.5)


def test_read_image_rejects_unknown_options(tmp_path):
    path = tmp_path / "x.png"
    Image.new("RGB", (10, 10), "white").save(path)

    with pytest.raises(ValueError):
        ocr.read_image(str(path), page_mode="magic")
    with pytest.raises(ValueError):
        ocr.read_image(str(path), layout="magic")


def test_prepare_upscales_small_images_and_flattens_transparency():
    small = Image.new("RGBA", (200, 60), (255, 255, 255, 0))
    prepared = ocr._prepare(small, enhance=True)
    assert prepared.mode == "L"
    assert prepared.size[0] > 200  # 작은 이미지는 확대해서 넘긴다

    prepared_raw = ocr._prepare(small, enhance=False)
    assert prepared_raw.size == (200, 60)


def test_prepare_upscales_toward_target_width():
    prepared = ocr._prepare(Image.new("L", (600, 200), "white"), enhance=True)

    assert prepared.size[0] == ocr._TARGET_WIDTH


def test_prepare_does_not_shrink_large_images():
    large = Image.new("L", (ocr._TARGET_WIDTH + 500, 400), "white")

    assert ocr._prepare(large, enhance=True).size == large.size


def test_prepare_caps_total_pixels_on_tall_images():
    """세로로 긴 이미지를 배율대로 늘리면 메모리를 다 먹는다."""
    tall = Image.new("L", (400, 9000), "white")

    prepared = ocr._prepare(tall, enhance=True)

    assert prepared.size[0] * prepared.size[1] <= ocr._MAX_PIXELS
    assert prepared.size[0] > 400  # 그래도 확대는 된다


def make_text_image(path, lines):
    # 줄 간격을 글자 크기에 맞춰 좁게 둔다. 너무 벌리면 Tesseract가 줄마다
    # 다른 문단으로 인식해서 "문단으로 합치기"가 동작하지 않는다.
    image = Image.new("RGB", (900, 70 * len(lines) + 80), "white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((40, 40 + i * 70), line, fill="black", font_size=44)
    image.save(path)


@pytest.mark.skipif(TESSERACT_MISSING, reason="Tesseract가 설치되어 있지 않습니다")
def test_read_image_transcribes_english_text(tmp_path):
    path = tmp_path / "sample.png"
    make_text_image(path, ["The quick brown fox", "jumps over the lazy dog"])

    result = ocr.read_image(str(path))

    assert "quick brown fox" in result.text
    assert "lazy dog" in result.text
    assert result.text.count("\n") >= 1  # 두 줄이 그대로 유지된다
    assert result.word_count >= 8
    assert result.confidence > 50
    assert (result.width, result.height) == Image.open(path).size


@pytest.mark.skipif(TESSERACT_MISSING, reason="Tesseract가 설치되어 있지 않습니다")
def test_read_image_paragraph_layout_merges_lines(tmp_path):
    path = tmp_path / "sample.png"
    make_text_image(path, ["The quick brown fox", "jumps over the lazy dog"])

    result = ocr.read_image(str(path), layout="paragraph")

    assert "fox jumps" in result.text


@pytest.mark.skipif(TESSERACT_MISSING, reason="Tesseract가 설치되어 있지 않습니다")
def test_read_image_without_text_returns_empty(tmp_path):
    path = tmp_path / "blank.png"
    Image.new("RGB", (400, 200), "white").save(path)

    result = ocr.read_image(str(path))

    assert result.text == ""
    assert result.word_count == 0
    assert result.confidence is None
