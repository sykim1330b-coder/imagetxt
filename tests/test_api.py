"""API 엔드포인트 테스트. 실제 인식은 test_ocr.py에서 다루고 여기서는 mock한다."""

import re
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from imagetxt.main import app
from imagetxt.ocr import OcrResult

client = TestClient(app)

FAKE_OCR = OcrResult(
    text="Hello world\nsecond line",
    confidence=93.25,
    word_count=4,
    low_confidence_words=1,
    width=800,
    height=200,
)


def post_image(filename="page.png", content=b"fake-image-bytes", **form_overrides):
    form = {"page_mode": "auto", "layout": "lines", "enhance": "true"}
    form.update(form_overrides)
    return client.post(
        "/api/ocr",
        files={"file": (filename, content, "image/png")},
        data=form,
    )


@patch("imagetxt.main.ocr.read_image", return_value=FAKE_OCR)
def test_ocr_returns_text(mock_read):
    res = post_image()

    assert res.status_code == 200
    body = res.json()
    assert body["text"] == "Hello world\nsecond line"
    assert body["confidence"] == 93.2  # 소수점 한 자리로 반올림
    assert body["word_count"] == 4
    assert body["low_confidence_words"] == 1
    assert (body["width"], body["height"]) == (800, 200)
    assert body["filename"] == "page.png"


@patch("imagetxt.main.ocr.read_image", return_value=FAKE_OCR)
def test_ocr_passes_options_through(mock_read):
    post_image(page_mode="sparse", layout="paragraph", enhance="false")

    _, kwargs = mock_read.call_args
    assert kwargs["page_mode"] == "sparse"
    assert kwargs["layout"] == "paragraph"
    assert kwargs["enhance"] is False


@patch("imagetxt.main.ocr.read_image", return_value=FAKE_OCR)
def test_ocr_deletes_uploaded_image(mock_read):
    post_image()

    (image_path,) = mock_read.call_args[0]
    assert not Path(image_path).exists()


@patch(
    "imagetxt.main.ocr.read_image",
    side_effect=RuntimeError("Tesseract OCR 엔진을 찾을 수 없습니다."),
)
def test_ocr_engine_missing_reported(mock_read):
    res = post_image()

    assert res.status_code == 500
    assert "Tesseract" in res.json()["detail"]


@patch("imagetxt.main.ocr.read_image", side_effect=ValueError("이미지 파일을 열 수 없습니다."))
def test_ocr_broken_image_is_client_error(mock_read):
    assert post_image().status_code == 400


def test_ocr_rejects_non_image_extension():
    assert post_image(filename="notes.mp3").status_code == 400


def test_ocr_rejects_bad_options():
    assert post_image(page_mode="magic").status_code == 400
    assert post_image(layout="magic").status_code == 400


def test_ocr_rejects_empty_file():
    assert post_image(content=b"").status_code == 400


def test_serves_web_ui():
    res = client.get("/")

    assert res.status_code == 200
    assert "이미지 → 영어 텍스트" in res.text


def test_web_ui_assets_all_resolve():
    """index.html이 참조하는 정적 파일이 실제로 서빙되는지 확인한다.

    파일 이름만 바뀌고 참조가 남으면 페이지는 200인데 화면만 죽으므로,
    링크를 따라가며 확인한다.
    """
    html = client.get("/").text
    assets = re.findall(r'(?:src|href)="(?!https?:|#)([^"]+)"', html)

    assert assets, "index.html에서 정적 파일 참조를 찾지 못했습니다"
    for asset in assets:
        assert client.get(f"/{asset}").status_code == 200, f"{asset} 를 찾을 수 없습니다"
