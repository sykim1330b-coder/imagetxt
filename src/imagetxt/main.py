"""FastAPI 앱: 이미지 업로드 → OCR → 텍스트 응답.

OCR은 보통 몇 초면 끝나므로 작업 큐 없이 요청 하나로 결과까지 돌려준다.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import ocr

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024

app = FastAPI(title="imagetxt")

_upload_dir = Path(tempfile.mkdtemp(prefix="imagetxt-uploads-"))


@app.post("/api/ocr")
async def read_image_text(
    file: UploadFile = File(...),
    page_mode: str = Form("auto"),
    layout: str = Form("lines"),
    enhance: str = Form("true"),
):
    """이미지 한 장을 받아 그 안의 영어 텍스트를 그대로 읽어 돌려준다."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(
            400,
            f"지원하지 않는 이미지 형식입니다: {suffix or '(확장자 없음)'}. "
            f"지원 형식: {', '.join(sorted(IMAGE_EXTENSIONS))}",
        )
    if page_mode not in ocr.PAGE_MODES:
        raise HTTPException(400, f"지원하지 않는 인식 모드입니다: {page_mode}")
    if layout not in ocr.LAYOUTS:
        raise HTTPException(400, f"지원하지 않는 줄바꿈 방식입니다: {layout}")

    dest = await _save_upload(file, suffix)
    try:
        # 인식은 CPU를 몇 초 점유하므로 이벤트 루프 밖에서 실행한다.
        result = await run_in_threadpool(
            ocr.read_image,
            str(dest),
            page_mode=page_mode,
            layout=layout,
            enhance=enhance.lower() not in ("false", "0", "off"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    finally:
        dest.unlink(missing_ok=True)

    return {
        "filename": file.filename or dest.name,
        "text": result.text,
        "confidence": round(result.confidence, 1)
        if result.confidence is not None
        else None,
        "word_count": result.word_count,
        "low_confidence_words": result.low_confidence_words,
        "width": result.width,
        "height": result.height,
    }


async def _save_upload(file: UploadFile, suffix: str) -> Path:
    """업로드를 임시 파일로 스트리밍 저장한다(크기 초과 시 즉시 중단)."""
    dest = _upload_dir / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_IMAGE_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "파일이 너무 큽니다 (최대 20MB).")
            out.write(chunk)
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "빈 파일입니다.")
    return dest


_static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
