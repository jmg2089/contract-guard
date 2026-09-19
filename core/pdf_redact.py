"""PDF 위의 민감정보를 실제로 덮어 가린 미리보기 이미지를 만든다.

왜 필요한가.

지금까지 마스킹은 텍스트에만 있었다. 사용자는 입력창의 글자가 [성명] 으로 바뀐 것을
볼 뿐, 자기 계약서에서 무엇이 가려졌는지는 알 수 없었다. "가렸습니다"라는 문장을
믿으라고 요구한 셈이다.

보호는 보여야 신뢰가 된다. 그래서 문서 모양 그대로, 이름과 주민등록번호 자리에
검은 박스가 덮인 그림을 돌려준다. 사용자는 검사 버튼을 누르기 전에 눈으로 확인한다.
자동 인식이 100%가 아니므로, 빠진 곳이 있으면 사용자가 발견할 수 있어야 한다.


어떻게 찾는가

core/privacy.py 가 "텍스트 몇 번째 글자부터 몇 번째 글자까지"를 준다.
PDF 는 "어느 단어가 어느 좌표에 있는지"를 준다. 이 둘을 이어야 한다.

    페이지의 단어 목록을 좌표 순으로 이어 붙여 한 줄짜리 텍스트를 만들고,
    그 과정에서 '텍스트의 i 번째 글자 = 몇 번째 단어' 라는 대응표를 같이 만든다.
    민감정보 구간이 걸치는 단어들을 모아 사각형으로 합친다.

이렇게 하면 '성 명 : 정 민 규' 처럼 글자가 낱낱이 떨어져 추출돼도,
그 낱글자들의 좌표를 전부 모아 하나의 박스로 덮을 수 있다.


PyMuPDF 를 쓰지 않은 이유

PyMuPDF(fitz)가 이 작업에 가장 흔히 쓰이지만 두 가지 이유로 쓰지 않았다.
첫째, 라이선스가 AGPL-3.0 이다. 대회 제출물과 이후 공개 범위를 생각하면 부담이 된다.
둘째, 이미 쓰고 있는 pdfplumber 가 단어 좌표를 주고, 그 렌더링 백엔드인
pypdfium2(BSD/Apache)가 페이지를 이미지로 그려 준다. 의존성을 늘리지 않고 된다.
"""
import base64
import io

from .privacy import counts as span_counts
from .privacy import find_spans

MAX_PAGES = 3          # 계약서는 보통 1~2쪽. 미리보기를 무한정 만들면 사용자가 기다린다
RENDER_DPI = 110       # 화면에서 읽을 수 있으면 충분하다. 높이면 응답만 무거워진다
PAD = 1.5              # 박스를 글자보다 아주 조금 크게 (글자 가장자리가 비어져 나오지 않게)


def _page_words(page):
    """페이지의 단어와 좌표. 좌표는 PDF 포인트 단위다."""
    return page.extract_words(use_text_flow=False, keep_blank_chars=False)


def _line_text_and_map(words):
    """단어 목록 -> (이어 붙인 텍스트, 글자 위치별 단어 번호).

    단어를 읽기 순서(위에서 아래, 왼쪽에서 오른쪽)로 정렬한 뒤 공백으로 잇는다.
    이때 '완성된 텍스트의 i 번째 글자는 몇 번째 단어에서 왔는가'를 같이 기록한다.
    이 대응표가 있어야 민감정보 구간을 좌표로 되돌릴 수 있다.
    """
    ordered = sorted(words, key=lambda w: (round(w["top"] / 4), w["x0"]))
    parts, owner = [], []
    pos = 0
    prev_row = None
    for i, w in enumerate(ordered):
        row = round(w["top"] / 4)
        if prev_row is not None:
            sep = "\n" if row != prev_row else " "
            parts.append(sep)
            owner.append(-1)  # 구분자는 어느 단어에도 속하지 않는다
            pos += len(sep)
        parts.append(w["text"])
        owner.extend([i] * len(w["text"]))
        pos += len(w["text"])
        prev_row = row
    return "".join(parts), owner, ordered


def _boxes_for_spans(text: str, owner: list[int], ordered: list[dict], spans) -> list[tuple]:
    """민감정보 구간 -> 덮을 사각형 목록.

    한 구간이 여러 단어에 걸치고, 그 단어들이 여러 줄에 걸칠 수도 있다.
    줄이 다르면 사각형을 나눠야 한다. 한 덩어리로 합치면 줄 사이의
    멀쩡한 글자까지 덮어 버린다.
    """
    boxes = []
    for s in spans:
        idxs = sorted({owner[i] for i in range(s.start, min(s.end, len(owner))) if owner[i] >= 0})
        if not idxs:
            continue
        # 같은 줄(top 이 비슷한)끼리 묶는다
        groups: dict[int, list[dict]] = {}
        for i in idxs:
            w = ordered[i]
            groups.setdefault(round(w["top"] / 4), []).append(w)
        for row in groups.values():
            boxes.append((
                min(w["x0"] for w in row) - PAD,
                min(w["top"] for w in row) - PAD,
                max(w["x1"] for w in row) + PAD,
                max(w["bottom"] for w in row) + PAD,
            ))
    return boxes


def _render(page, boxes) -> bytes:
    """페이지를 이미지로 그리고 그 위에 검은 박스를 덮어 PNG 로 돌려준다.

    주의: 원본 PDF 는 건드리지 않는다. 그린 그림 위에만 덮는다.
    사용자에게 돌려주는 것은 이미지이므로, 그림 위에 덮은 것이 곧 최종 결과다.
    글자를 지운 PDF 를 만드는 것이 아니라 보여줄 그림을 만드는 것이 목적이다.
    """
    from PIL import ImageDraw

    im = page.to_image(resolution=RENDER_DPI)
    pil = im.original.convert("RGB")

    # PDF 좌표(포인트) -> 이미지 픽셀
    scale = RENDER_DPI / 72.0
    draw = ImageDraw.Draw(pil)
    for x0, top, x1, bottom in boxes:
        draw.rectangle(
            [x0 * scale, top * scale, x1 * scale, bottom * scale],
            fill=(17, 17, 17),
        )

    buf = io.BytesIO()
    pil.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def redact_preview(data: bytes) -> dict:
    """PDF 바이트 -> 마스킹 미리보기.

    돌려주는 것:
      ok       미리보기를 만들었는가
      pages    [{page, image (data URL)}]
      counts   종류별 가린 건수
      reason   못 만든 경우 그 이유 (스캔본 등)
    """
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            total = len(pdf.pages)
            pages, all_counts = [], {}
            any_text = False

            for idx, page in enumerate(pdf.pages[:MAX_PAGES]):
                words = _page_words(page)
                if not words:
                    # 글자가 이미지로 들어 있는 쪽. 좌표를 알 수 없으므로 덮을 수 없다.
                    continue
                any_text = True
                text, owner, ordered = _line_text_and_map(words)
                spans = find_spans(text)
                boxes = _boxes_for_spans(text, owner, ordered, spans)

                png = _render(page, boxes)
                pages.append({
                    "page": idx + 1,
                    "image": "data:image/png;base64," + base64.b64encode(png).decode(),
                    "boxes": len(boxes),
                })
                for k, v in span_counts(spans).items():
                    all_counts[k] = all_counts.get(k, 0) + v

            if not any_text:
                return {"ok": False, "reason": "scanned", "pages": [], "counts": {},
                        "message": "글자가 이미지로 들어 있어 위치를 찾을 수 없습니다. "
                                   "브라우저에서 글자를 읽은 뒤 가립니다."}

            return {"ok": True, "reason": "ok", "pages": pages, "counts": all_counts,
                    "total_pages": total,
                    "truncated": total > MAX_PAGES}
    except Exception as e:
        return {"ok": False, "reason": "error", "pages": [], "counts": {},
                "message": f"미리보기를 만들지 못했습니다. ({type(e).__name__})"}
