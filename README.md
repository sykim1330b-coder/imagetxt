# imagetxt

이미지 속 **영어 텍스트를 보이는 그대로** 옮겨 적어 주는 개인용 웹앱입니다.
번역도 요약도 하지 않고, 이미지에 적힌 문장을 줄바꿈까지 그대로 텍스트로 돌려줍니다.

인식은 로컬 [Tesseract](https://github.com/tesseract-ocr/tesseract) OCR로 처리하므로
업로드한 이미지가 외부 서버로 전송되지 않고 전부 내 컴퓨터 안에서 끝납니다.

## 기능

- png, jpg, webp, bmp, tiff, gif 업로드 (드래그앤드롭 · 클립보드 붙여넣기, 최대 20MB)
- 인식 모드: 문서(자동, 기본) · 텍스트 한 덩어리 · 한 줄 · 흩어진 텍스트
- 줄바꿈: **보이는 그대로**(기본) 또는 줄바꿈으로 끊긴 문장을 문단으로 합치기
- 자동 보정(사진 회전 보정 · 흑백 변환 · 대비 조정 · 작은 이미지 확대)
- 평균 신뢰도 표시, 흐릿하게 읽힌 단어가 있으면 경고
- 결과 미리보기, TXT 다운로드, 클립보드 복사

## 설치

Python 3.10 이상과 Tesseract 엔진(영어 데이터 포함)이 필요합니다.

```bash
# 1) OCR 엔진
brew install tesseract          # macOS
sudo apt install tesseract-ocr  # Ubuntu/Debian

# 2) 앱
pip install -e .
```

Windows는 [UB Mannheim 설치 파일](https://github.com/UB-Mannheim/tesseract/wiki)을 사용하고
설치 경로를 PATH에 추가하세요.

## 실행

```bash
imagetxt
```

또는:

```bash
uvicorn imagetxt.main:app --port 8000
```

브라우저에서 <http://127.0.0.1:8000> 을 열면 됩니다. 모델을 내려받지 않으므로
첫 실행부터 몇 초 안에 결과가 나옵니다.

## 사용 팁

- **이미지 품질이 정확도를 좌우합니다**: 글자가 클수록, 초점이 맞을수록,
  기울어지지 않을수록 잘 읽힙니다. 화면을 찍은 사진보다 스크린샷이 훨씬 정확합니다.
- **인식 모드**: 기본값(문서)으로 결과가 어긋나면, 문단이 하나뿐인 이미지는
  "텍스트 한 덩어리", 캡션 한 줄은 "한 줄", 표지판이나 UI 화면은
  "흩어진 텍스트"를 선택해 보세요.
- **줄바꿈**: 원본 모양 그대로 남기려면 기본값을, 문서에 붙여 넣고 이어서
  쓸 문장이 필요하면 "문단으로 합치기"를 고르세요(줄 끝 하이픈도 이어 붙입니다).
- **신뢰도**: 결과에 평균 신뢰도가 표시됩니다. 낮게 나오거나 흐릿하게 읽힌
  단어 경고가 뜨면 원본과 대조해 보세요.
- 영어 전용입니다. 한국어가 섞인 이미지는 그 부분이 빠지거나 깨져 나옵니다.

## API

웹 UI 없이 직접 호출할 수도 있습니다.

```bash
curl -X POST http://127.0.0.1:8000/api/ocr \
  -F "file=@page.png" \
  -F "page_mode=auto" \
  -F "layout=lines" \
  -F "enhance=true"
```

```json
{
  "filename": "page.png",
  "text": "Meeting Notes - March 14\n\nShip the OCR feature by Friday.",
  "confidence": 95.5,
  "word_count": 25,
  "low_confidence_words": 0,
  "width": 1000,
  "height": 420
}
```

업로드한 이미지는 응답 직후 서버에서 삭제되고, 결과는 따로 저장하지 않습니다.

## 프로젝트 구조

```
src/imagetxt/
├── main.py      # FastAPI 앱: POST /api/ocr, 정적 파일 서빙
├── ocr.py       # Tesseract 래퍼 (이미지 전처리, 줄·문단 조립, 신뢰도)
└── static/      # 웹 UI (index.html, app.js, style.css)
```

`ocr.py`는 웹 계층과 독립적이라 라이브러리처럼 바로 쓸 수 있습니다.

```python
from imagetxt.ocr import read_image

result = read_image("page.png", layout="paragraph")
print(result.text, result.confidence)
```

## 테스트

```bash
pip install -e ".[dev]"
python -m pytest
```

텍스트 조립 로직은 엔진 없이 검증하고, 실제 인식 테스트는 Tesseract가 설치된
환경에서만 실행됩니다(없으면 자동으로 건너뜁니다).
