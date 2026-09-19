"""계약서 원문 -> 조항 리스트.

LLM을 쓰지 않는다. 한국 근로계약서는 '제N조(제목)' 패턴이 지배적이라
정규식으로 90% 이상 잡힌다. 비용 0, 지연 0, 결과 재현 가능.
패턴이 전혀 안 맞을 때만 문단 단위 폴백으로 내려간다.
"""
import re
from .types import Clause

ARTICLE_RE = re.compile(
    r"제\s*(\d+)\s*조(?:\s*의\s*\d+)?\s*(?:[(\[【]\s*([^)\]】\n]{1,40}?)\s*[)\]】])?",
)

# 번호 없는 항목형 계약서 폴백: "1. ...", "가. ...", "① ..."
ITEM_RE = re.compile(r"^(?:\d{1,2}[.)]|[가-힣][.)]|[①-⑳])\s+", re.MULTILINE)


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("　", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def segment(text: str) -> list[Clause]:
    text = _clean(text)
    matches = list(ARTICLE_RE.finditer(text))

    if len(matches) >= 2:
        return _from_matches(text, matches)
    return _fallback(text)


def _from_matches(text: str, matches) -> list[Clause]:
    clauses = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if len(body) < 8:
            continue
        clauses.append(
            Clause(
                id=f"c{len(clauses) + 1}",
                article_no=int(m.group(1)),
                title=(m.group(2) or "").strip() or f"제{m.group(1)}조",
                text=body,
                start=start,
                end=end,
            )
        )
    return clauses


MIN_CLAUSE_LEN = 8  # "임금: 시급 9,000원"(14자) 같은 짧은 조항이 통째로 버려지는 것을 막는다


def _fallback(text: str) -> list[Clause]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= MIN_CLAUSE_LEN]
    if len(parts) < 2:
        parts = [p.strip() for p in ITEM_RE.split(text) if len(p.strip()) >= MIN_CLAUSE_LEN]
    if len(parts) < 2:  # 줄바꿈만 있는 표 형식 계약서
        parts = [p.strip() for p in text.split("\n") if len(p.strip()) >= MIN_CLAUSE_LEN]
    clauses, cursor = [], 0
    for p in parts:
        idx = text.find(p, cursor)
        cursor = idx + len(p) if idx >= 0 else cursor
        head = p.split("\n")[0][:30]
        clauses.append(
            Clause(
                id=f"c{len(clauses) + 1}",
                article_no=None,
                title=head,
                text=p,
                start=max(idx, 0),
                end=max(idx, 0) + len(p),
            )
        )
    return clauses


def extract_pdf_text(file_obj) -> str:
    """PDF에서 텍스트를 뽑는다. 경로 문자열도, 파일 객체도 받는다.

    텍스트 레이어가 있는 PDF만 읽힌다. 스캔본이나 사진을 PDF로 만든 것은
    글자가 이미지이므로 빈 문자열이 나온다. 그 경우 호출부가 안내해야 한다.
    """
    import pdfplumber

    pages = []
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def pdf_diagnosis(file_obj) -> dict:
    """PDF를 읽고 무엇이 문제인지까지 판별한다.

    사용자에게 '실패했습니다'만 던지면 무엇을 해야 할지 알 수 없다.
    스캔본인지, 암호가 걸렸는지, 그냥 빈 파일인지를 구분해서 알려준다.
    """
    import pdfplumber

    try:
        with pdfplumber.open(file_obj) as pdf:
            pages = len(pdf.pages)
            text = "\n".join((p.extract_text() or "") for p in pdf.pages).strip()
            images = sum(len(p.images) for p in pdf.pages)
    except Exception as e:
        msg = str(e).lower()
        if "password" in msg or "encrypt" in msg:
            return {"ok": False, "text": "", "reason": "encrypted",
                    "message": "암호가 걸린 PDF입니다. 암호를 푼 뒤 다시 올려주세요."}
        return {"ok": False, "text": "", "reason": "unreadable",
                "message": f"PDF를 읽지 못했습니다. ({type(e).__name__})"}

    if len(text) >= 50:
        return {"ok": True, "text": text, "reason": "ok", "pages": pages,
                "message": f"{pages}쪽에서 {len(text):,}자를 읽었습니다."}

    if images > 0:
        return {"ok": False, "text": text, "reason": "scanned", "pages": pages,
                "message": "글자가 이미지로 들어 있는 스캔본입니다. "
                           "이 서비스는 문서에서 글자를 직접 읽으므로 스캔본은 인식하지 못합니다. "
                           "계약서 내용을 복사해서 아래 입력창에 붙여넣어 주세요."}

    return {"ok": False, "text": text, "reason": "empty", "pages": pages,
            "message": "PDF에서 글자를 찾지 못했습니다. 내용을 복사해서 붙여넣어 주세요."}
