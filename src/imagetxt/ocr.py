"""Tesseract OCR 래퍼.

웹 계층과 독립적인 순수 인식 로직. 이미지 안의 영어 텍스트를 그대로
읽어서(번역·요약 없이) 문자열로 돌려준다. 인식은 image_to_data 한 번으로
끝내고, 그 결과에서 줄/문단 구조와 평균 신뢰도를 함께 계산한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Tesseract의 페이지 분할 모드(PSM). 사진·스크린샷 대부분은 "auto"로 충분하고,
# 인식이 어긋날 때 사용자가 이미지 모양에 맞는 모드를 고를 수 있게 한다.
PAGE_MODES: dict[str, int] = {
    "auto": 3,  # 일반 문서: 여러 단락·열을 자동 분할
    "block": 6,  # 하나의 균일한 텍스트 덩어리
    "line": 7,  # 한 줄짜리 이미지
    "sparse": 11,  # 표지판·UI처럼 텍스트가 흩어져 있는 이미지
}

# 줄바꿈 처리 방식.
LAYOUTS = {"lines", "paragraph"}

OCR_LANGUAGE = "eng"

# 이 값보다 낮은 신뢰도의 단어는 "흐릿하게 읽힌 단어"로 세어 사용자에게 알린다.
LOW_CONFIDENCE = 60.0

# Tesseract는 300dpi 정도의 큰 글자에서 정확도가 가장 좋다. 작은 이미지는
# 확대해서 넘기고, 원래 큰 이미지는 그대로 둔다.
_TARGET_WIDTH = 1200
_MAX_SCALE = 3.0


@dataclass
class OcrResult:
    text: str
    confidence: Optional[float]  # 0~100, 인식된 단어가 없으면 None
    word_count: int
    low_confidence_words: int
    width: int
    height: int


def read_image(
    image_path: str,
    page_mode: str = "auto",
    layout: str = "lines",
    enhance: bool = True,
) -> OcrResult:
    """이미지에서 영어 텍스트를 읽어 그대로 반환한다.

    page_mode는 PAGE_MODES의 키, layout은 "lines"(줄바꿈 유지) 또는
    "paragraph"(줄바꿈으로 끊긴 문장을 문단으로 합치기)다.
    """
    if page_mode not in PAGE_MODES:
        raise ValueError(f"지원하지 않는 인식 모드입니다: {page_mode}")
    if layout not in LAYOUTS:
        raise ValueError(f"지원하지 않는 줄바꿈 방식입니다: {layout}")

    import pytesseract
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(image_path) as opened:
            opened.load()
            prepared = _prepare(opened, enhance=enhance)
            size = opened.size
    except UnidentifiedImageError as exc:
        raise ValueError("이미지 파일을 열 수 없습니다. 손상된 파일인지 확인해 주세요.") from exc

    try:
        data = pytesseract.image_to_data(
            prepared,
            lang=OCR_LANGUAGE,
            config=f"--psm {PAGE_MODES[page_mode]}",
            output_type=pytesseract.Output.DICT,
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR 엔진을 찾을 수 없습니다. "
            "macOS: brew install tesseract / Ubuntu: sudo apt install tesseract-ocr "
            "로 설치한 뒤 다시 시도해 주세요."
        ) from exc
    except pytesseract.TesseractError as exc:
        # 영어 학습 데이터(eng.traineddata)가 없을 때 주로 발생한다.
        raise RuntimeError(f"OCR 실행에 실패했습니다: {exc}") from exc

    words = _collect_words(data)
    text = _build_text(words, layout)
    confidences = [w.confidence for w in words]

    return OcrResult(
        text=text,
        confidence=sum(confidences) / len(confidences) if confidences else None,
        word_count=len(words),
        low_confidence_words=sum(1 for c in confidences if c < LOW_CONFIDENCE),
        width=size[0],
        height=size[1],
    )


def _prepare(image, enhance: bool):
    """OCR에 넘기기 좋게 이미지를 다듬는다(회전 보정·흑백·대비·확대)."""
    from PIL import Image, ImageOps

    # 휴대폰 사진은 회전 정보가 EXIF에만 있어서 그대로 넘기면 옆으로 누운 채 인식된다.
    prepared = ImageOps.exif_transpose(image)
    # 투명 PNG는 배경이 검게 깔려 글자가 묻히므로 흰 배경 위에 합성한다.
    if prepared.mode in ("RGBA", "LA", "P"):
        prepared = prepared.convert("RGBA")
        background = Image.new("RGBA", prepared.size, (255, 255, 255, 255))
        prepared = Image.alpha_composite(background, prepared)
    prepared = prepared.convert("L")

    if not enhance:
        return prepared

    prepared = ImageOps.autocontrast(prepared)
    width, height = prepared.size
    if width > 0 and width < _TARGET_WIDTH:
        scale = min(_TARGET_WIDTH / width, _MAX_SCALE)
        prepared = prepared.resize(
            (round(width * scale), round(height * scale)), Image.LANCZOS
        )
    return prepared


@dataclass
class _Word:
    block: int
    paragraph: int
    line: int
    text: str
    confidence: float


def _collect_words(data: dict) -> list[_Word]:
    """image_to_data의 열 단위 결과를 단어 목록으로 바꾼다."""
    words: list[_Word] = []
    for i, raw_text in enumerate(data.get("text", [])):
        text = (raw_text or "").strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][i])
        except (KeyError, IndexError, TypeError, ValueError):
            confidence = -1.0
        if confidence < 0:  # 인식되지 않은 자리 표시자
            continue
        words.append(
            _Word(
                block=int(data["block_num"][i]),
                paragraph=int(data["par_num"][i]),
                line=int(data["line_num"][i]),
                text=text,
                confidence=confidence,
            )
        )
    return words


def _build_text(words: list[_Word], layout: str) -> str:
    """단어 목록을 이미지에 보이는 순서 그대로 문자열로 조립한다."""
    if not words:
        return ""

    # (블록, 문단) 단위로 묶고 그 안에서 줄 단위로 다시 묶는다.
    paragraphs: list[list[str]] = []
    current_key: Optional[tuple[int, int]] = None
    current_line: Optional[int] = None

    for word in words:
        key = (word.block, word.paragraph)
        if key != current_key:
            paragraphs.append([word.text])
            current_key, current_line = key, word.line
        elif word.line != current_line:
            paragraphs[-1].append(word.text)
            current_line = word.line
        else:
            paragraphs[-1][-1] += f" {word.text}"

    if layout == "lines":
        blocks = ["\n".join(lines) for lines in paragraphs]
    else:
        blocks = [_join_lines(lines) for lines in paragraphs]
    return "\n\n".join(blocks)


def _join_lines(lines: list[str]) -> str:
    """줄바꿈으로 끊긴 문장을 한 문단으로 잇는다(줄 끝 하이픈은 이어붙임)."""
    joined = ""
    for line in lines:
        if not joined:
            joined = line
        elif joined.endswith("-"):
            joined = joined[:-1] + line
        else:
            joined += " " + line
    return joined
