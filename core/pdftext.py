"""PDF에서 글자를 뽑는 층. 엔진을 하나만 믿지 않는다.

왜 이 파일이 따로 있는가.

같은 PDF라도 추출 엔진마다 결과가 크게 다르다. 특히 한국 계약서는 두 가지 이유로
기본 추출이 자주 무너진다.

  1) 표 형식. 근로계약서는 '항목 | 내용' 표가 많다. 기본 추출기는 글자를 좌표 순서로
     이어 붙이므로 표를 만나면 칸을 가로질러 읽어 문장이 뒤섞인다.
     "임금 근로시간 월 200만원 09:00~18:00" 처럼 나온다. 사람도 못 읽는다.

  2) 한글(HWP)에서 만든 PDF. 폰트를 서브셋으로 심으면서 글리프-유니코드 대응표
     (ToUnicode)를 빠뜨리는 경우가 많다. 화면에는 멀쩡히 보이지만 뽑으면
     (cid:123) 같은 코드나 엉뚱한 글자가 나온다.

그래서 엔진 여러 개로 뽑아 보고, 결과를 점수 매겨 제일 나은 것을 고른다.
비용은 PDF 한 장에 수십 밀리초다. 실패한 추출을 사용자에게 던지는 비용보다 훨씬 싸다.

점수는 '그럴듯해 보이는가'가 아니라 다음 세 가지로 매긴다.
  - 한글 비율      : 깨진 추출은 이 값이 먼저 무너진다
  - 계약 용어 적중 : 근로계약서라면 반드시 나오는 단어들
  - cid 오염도     : (cid:NNN) 가 보이면 그 엔진은 실패한 것이다
"""
import re

# 근로계약서라면 반드시 몇 개는 나온다. 추출이 성공했는지 보는 가장 싼 신호다.
_TERMS = [
    "근로", "임금", "급여", "계약", "근무", "사용자", "근로자", "회사",
    "퇴직", "휴가", "휴일", "연차", "시간", "지급", "업무", "수당",
]

_CID_RE = re.compile(r"\(cid:\d+\)")
_ARTICLE_RE = re.compile(r"제\s*(\d{1,3})\s*조")


def order_score(text: str) -> float:
    """읽은 순서가 맞는지 본다. 이게 없으면 뒤섞인 추출을 걸러낼 수 없다.

    글자만 세면 2단 편집 계약서의 뒤섞인 추출과 올바른 추출이 똑같은 점수를 받는다.
    같은 글자가 순서만 다르게 나오기 때문이다.

    근로계약서에는 공짜로 쓸 수 있는 순서 표지가 있다. 조 번호다.
    제대로 읽었으면 1, 2, 3, ... 으로 올라간다. 2단을 가로질러 읽으면
    1, 4, 2, 5, 3, 6 처럼 들쭉날쭉해진다. 그 비율을 그대로 점수로 쓴다.
    """
    nums = [int(n) for n in _ARTICLE_RE.findall(text or "")]
    if len(nums) < 3:
        return 1.0  # 조 번호가 없는 표 형식 계약서는 이 신호로 판단하지 않는다
    rising = sum(1 for a, b in zip(nums, nums[1:]) if b >= a)
    return rising / (len(nums) - 1)


def score(text: str) -> dict:
    """추출 결과의 품질 점수. 0.0 ~ 1.0."""
    text = text or ""
    letters = re.findall(r"[가-힣a-zA-Z一-鿿]", text)
    if not letters:
        return {"score": 0.0, "hangul": 0.0, "terms": 0, "cid": 0,
                "order": 0.0, "chars": len(text)}

    hangul = sum(1 for c in letters if "가" <= c <= "힣") / len(letters)
    terms = sum(1 for t in _TERMS if t in text)
    cid = len(_CID_RE.findall(text))
    order = order_score(text)

    # 한글 비율이 제일 중요하다. 이게 무너지면 나머지는 의미가 없다.
    s = hangul * 0.45
    s += min(terms / 8, 1.0) * 0.25
    s += order * 0.30
    if cid:
        # cid 가 하나라도 보이면 그 엔진은 폰트 대응표를 못 읽은 것이다. 크게 깎는다.
        s *= max(0.0, 1.0 - cid / max(len(text), 1) * 20)
    if len(letters) < 50:
        s *= 0.3  # 글자가 거의 안 나온 결과를 1등으로 뽑는 것을 막는다

    return {"score": round(s, 4), "hangul": round(hangul, 3), "terms": terms,
            "cid": cid, "order": round(order, 3), "chars": len(text)}


def _normalize(text: str) -> str:
    """layout=True 로 뽑으면 칸을 맞추느라 공백이 길게 들어간다. 그걸 정리한다."""
    text = (text or "").replace("\r\n", "\n").replace("　", " ")
    # 표의 칸 구분으로 쓰인 긴 공백은 구분자로 살린다. 그냥 지우면 두 칸이 붙어버린다.
    text = re.sub(r"[ \t]{3,}", " | ", text)
    text = re.sub(r"[ \t]{2}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip(" |") for line in text.split("\n"))
    return text.strip()


# ---------------------------------------------------------------- 엔진들
# 각 엔진은 (이름, 함수) 이고, 함수는 bytes 를 받아 str 을 돌려준다.
# 하나가 터져도 전체가 멈추면 안 되므로 호출부에서 개별로 감싼다.


def _plumber_plain(data: bytes) -> str:
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages).strip()


def _plumber_layout(data: bytes) -> str:
    """칸 위치를 유지하며 뽑는다. 표 형식 계약서에서 기본 추출보다 훨씬 낫다."""
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = []
        for p in pdf.pages:
            try:
                pages.append(p.extract_text(layout=True) or "")
            except Exception:
                pages.append(p.extract_text() or "")
        return _normalize("\n".join(pages))


def _plumber_words(data: bytes) -> str:
    """단어 좌표를 직접 읽어 줄을 재구성한다.

    기본 추출이 줄을 잘못 묶을 때의 마지막 수단이다. y 좌표로 줄을 만들고
    x 간격이 크게 벌어지면 칸 구분으로 본다.
    """
    import io

    import pdfplumber

    out = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            rows: dict[int, list] = {}
            for w in words:
                key = round(w["top"] / 4)  # 4pt 안쪽이면 같은 줄로 본다
                rows.setdefault(key, []).append(w)
            for key in sorted(rows):
                line, prev_x1 = [], None
                for w in sorted(rows[key], key=lambda x: x["x0"]):
                    if prev_x1 is not None and w["x0"] - prev_x1 > 18:
                        line.append("|")  # 칸이 바뀐 것으로 본다
                    line.append(w["text"])
                    prev_x1 = w["x1"]
                out.append(" ".join(line))
            out.append("")
    return _normalize("\n".join(out))


def _plumber_columns(data: bytes) -> str:
    """단(column)을 찾아 각 단을 따로, 위에서 아래로 읽는다.

    2단으로 편집한 계약서에서 다른 엔진은 전부 실패한다. 글자를 좌표 순서로 이어
    붙이므로 왼쪽 단 한 줄, 오른쪽 단 한 줄을 번갈아 읽어 문장이 반씩 섞인다.
    "제1조 ... 제4조 ..." 처럼 조가 뒤엉켜 룰도 분류기도 제대로 걸리지 않는다.

    해법은 단순하다. 페이지 세로 전체에 걸쳐 글자가 하나도 지나가지 않는 세로 빈 띠
    (거터)를 찾아 그 자리에서 자르고, 왼쪽을 다 읽은 뒤 오른쪽을 읽는다.
    거터가 없으면(=1단 문서면) 빈 문자열을 돌려주고 다른 엔진에 맡긴다.
    """
    import io

    import pdfplumber

    out, found_any = [], False
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False)
            if len(words) < 20:
                continue

            width = page.width
            # 페이지 가로를 2pt 칸으로 나눠 글자가 덮는 칸을 표시한다
            step = 2
            cells = int(width / step) + 1
            covered = [False] * cells
            for w in words:
                for i in range(int(w["x0"] / step), min(int(w["x1"] / step) + 1, cells)):
                    covered[i] = True

            # 페이지 가운데 30~70% 구간에서 가장 넓은 빈 띠를 찾는다.
            # 가장자리 여백은 단 구분이 아니므로 제외한다.
            lo, hi = int(cells * 0.3), int(cells * 0.7)
            best_len, best_mid, run_start = 0, None, None
            for i in range(lo, hi):
                if not covered[i]:
                    if run_start is None:
                        run_start = i
                elif run_start is not None:
                    if i - run_start > best_len:
                        best_len, best_mid = i - run_start, (run_start + i) / 2
                    run_start = None
            if run_start is not None and hi - run_start > best_len:
                best_len, best_mid = hi - run_start, (run_start + hi) / 2

            # 빈 띠가 페이지 가로의 4% 이상이어야 단 구분으로 인정한다
            if best_mid is None or best_len * step < width * 0.04:
                continue

            found_any = True
            split_x = best_mid * step
            for side in (0, 1):
                col = [w for w in words
                       if (w["x0"] < split_x) == (side == 0)]
                rows: dict[int, list] = {}
                for w in col:
                    rows.setdefault(round(w["top"] / 4), []).append(w)
                for key in sorted(rows):
                    line = sorted(rows[key], key=lambda x: x["x0"])
                    out.append(" ".join(w["text"] for w in line))
                out.append("")

    return _normalize("\n".join(out)) if found_any else ""


def _pypdf(data: bytes) -> str:
    """pdfplumber(pdfminer) 와 구현이 다르다. 한쪽이 실패해도 다른 쪽이 읽는 PDF가 있다."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages).strip()


ENGINES = [
    ("plumber", _plumber_plain),
    ("layout", _plumber_layout),
    ("words", _plumber_words),
    ("columns", _plumber_columns),
    ("pypdf", _pypdf),
]


def extract_best(data: bytes) -> dict:
    """엔진을 모두 돌려 제일 나은 결과를 고른다.

    돌려주는 것:
      text     제일 점수가 높은 추출 결과
      engine   그걸 만든 엔진 이름
      score    그 결과의 품질 점수
      attempts 전 엔진의 점수 (화면에 보여주지는 않지만 디버깅과 신뢰 설명에 쓴다)
    """
    attempts, best = [], None
    for name, fn in ENGINES:
        try:
            text = fn(data)
        except Exception as e:
            attempts.append({"engine": name, "error": type(e).__name__, "score": 0.0})
            continue
        m = score(text)
        attempts.append({"engine": name, **m})
        if best is None or m["score"] > best[1]["score"]:
            best = (name, m, text)

    if best is None:
        return {"text": "", "engine": None, "score": 0.0, "attempts": attempts}

    name, m, text = best
    return {"text": text, "engine": name, "score": m["score"],
            "metrics": m, "attempts": attempts}
