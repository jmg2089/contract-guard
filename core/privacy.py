"""민감정보가 '어디에' 있는지 찾는다. 가리는 방법은 여기서 정하지 않는다.

왜 파일을 나눴는가.

처음에는 core/mask.py 하나가 탐지와 치환을 같이 했다. 문자열을 받아 별표로 바꾸는
구조였다. 그런데 PDF 위에 검은 박스를 그리려면 "무엇을 가릴지"가 아니라
"몇 번째 글자부터 몇 번째 글자까지인지"가 필요하다. 치환 함수는 그 정보를 버린다.

그래서 탐지를 여기로 떼어냈다. 기준은 하나, 출력은 둘이다.

    core/privacy.py     어디가 민감정보인지 (start, end, 종류)
        |
        +-- core/mask.py        그 구간을 별표로 치환   -> 분석에 넘길 텍스트
        +-- core/pdf_redact.py  그 구간의 좌표를 찾아   -> PDF 위에 검은 박스
        +-- static/js/mask.js   같은 규칙을 브라우저에서 (OCR 좌표용)

규칙이 한 곳에 있어야 텍스트에서 가린 것과 그림에서 가린 것이 어긋나지 않는다.


탐지를 두 갈래로 나눈 이유

  1) 패턴 기반 — 주민등록번호, 계좌번호, 전화번호, 이메일.
     형태 자체가 특이해서 그것만 보고 찾을 수 있다.

  2) 라벨 기반 — 이름, 주소, 생년월일, 사업체명.
     이쪽은 형태로 못 찾는다. '정민규'라는 글자만 보고 이름인지 알 수 없고,
     정규식으로 사람 이름을 찾으려 들면 본문의 평범한 단어까지 먹는다.
     대신 계약서에는 라벨이 붙어 있다. '성명 :', '주소 :' 뒤의 값만 가린다.
     라벨은 남기고 값만 가리므로 '성명 : [가림]'이 되어, 문서 구조는 그대로 읽힌다.


절대 가리면 안 되는 것

이게 이 파일에서 제일 중요하다. 임금과 근로시간을 가리면 판정이 통째로 죽는다.
최저임금 위반을 찾는 도구가 임금 액수를 지워 버리면 아무것도 못 찾는다.
그래서 분석에 쓰이는 라벨은 KEEP_LABELS 에 넣고 값을 건드리지 않는다.

라벨 자체를 남기는 설계도 여기에 걸려 있다. core/doctype.py 는 근로기준법 제17조
명시사항(임금·소정근로시간·휴일·연차·근무장소·업무내용)이 있는지로 문서를 판별하는데,
라벨까지 지우면 근로계약서가 근로계약서로 안 보이게 된다.
"""
import re
from dataclasses import dataclass


@dataclass
class Span:
    """민감정보 한 건. text[start:end] 가 가려야 할 값이다."""
    start: int
    end: int
    kind: str          # 화면에 보여줄 종류 이름 ("성명", "생년월일" ...)
    value: str         # 가려질 원본 값. 로그에 남기지 않는다.


# ── 라벨 기반 ────────────────────────────────────────────────────────────
#
# 고용노동부 표준근로계약서, 외국인근로자 표준근로계약서(별지 제6호서식),
# 그리고 실무에서 흔한 변형 표기를 함께 넣었다.
#
# 다만 솔직히 적어 둔다. 고용노동부가 배포하는 원본 양식은 HWP 첨부라
# 본문 라벨을 글자 단위로 대조하지는 못했다. 아래 목록은 널리 쓰이는 양식 구조와
# 실무 표기를 모은 것이며, 새로운 표기를 만나면 추가해야 한다.
# 그래서 '못 찾을 수 있다'를 전제로 화면에 확인 요청 문구를 띄운다.

MASK_LABELS: list[tuple[str, list[str]]] = [
    ("성명", ["성명", "이름", "근로자명", "근로자 성명", "사용자 성명", "대표자",
             "대표이사", "사업주명", "대표자명", "수급인", "Name", "Full name"]),
    ("사업체명", ["사업체명", "업체명", "사업장명", "회사명", "상호", "법인명",
                "Name of the enterprise"]),
    ("생년월일", ["생년월일", "생 년 월 일", "출생연도", "출생일", "생일", "Birthdate",
                "Date of birth"]),
    ("주소", ["주소", "현주소", "본국주소", "자택주소", "소재지", "사업장 소재지",
             "본사 소재지", "Address", "Location of the enterprise"]),
    ("연락처", ["연락처", "전화번호", "전화", "휴대전화", "휴대폰", "핸드폰",
               "Phone", "Phone number", "Tel"]),
    ("이메일", ["이메일", "메일", "전자우편", "E-mail", "Email"]),
    ("소속", ["소속", "부서", "소속부서", "Department"]),
    ("식별번호", ["주민등록번호", "주민번호", "외국인등록번호", "여권번호",
                "사업자등록번호", "법인등록번호", "Passport No", "Identification number"]),
    ("계좌번호", ["계좌번호", "급여계좌", "입금계좌", "예금주", "카드번호"]),
]

# 분석에 쓰이는 값들. 라벨이 걸려도 값을 건드리지 않는다.
#
# 이 목록이 비면 서비스가 죽는다. 임금을 가린 계약서에서 최저임금 위반을 찾을 수는 없다.
KEEP_LABELS = [
    "임금", "급여", "월급", "시급", "일급", "연봉", "기본급", "상여금", "수당",
    "임금지급일", "지급방법", "지급일", "통상임금", "평균임금", "퇴직금",
    "근로시간", "소정근로시간", "근무시간", "시업", "종업", "휴게시간",
    "근무일", "휴일", "주휴일", "연차", "연차유급휴가", "유급휴가",
    "계약기간", "근로계약기간", "근로개시일", "계약일", "수습기간", "교육기간",
    "업무내용", "업무의 내용", "담당업무", "직무", "종사할 업무",
    "근무장소", "근 무 장 소", "취업장소", "사회보험", "위약금", "손해배상",
]


def _spaced(label: str) -> str:
    """'성명' -> '성\\s*명'.

    PDF에서 글자를 뽑으면 '성 명 : 정 민 규' 처럼 글자 사이에 공백이 들어간다.
    양식이 칸을 맞추려고 자간을 벌려 놓기 때문이다. 공백을 허용하지 않으면
    실제 계약서에서 라벨이 하나도 안 잡힌다.
    """
    parts = [re.escape(c) for c in label if not c.isspace()]
    return r"\s*".join(parts)


def _build_label_re(labels: list[str]) -> re.Pattern:
    body = "|".join(_spaced(l) for l in sorted(labels, key=len, reverse=True))
    # 라벨 앞은 줄머리이거나 공백/괄호/구분자여야 한다.
    # 그래야 '회사명'의 '명'이 '성명'으로 잡히는 식의 겹침을 줄인다.
    return re.compile(rf"(?:(?<=^)|(?<=[\s(\[|·,]))({body})\s*[:：]\s*", re.MULTILINE)


_MASK_RE = [(kind, _build_label_re(variants)) for kind, variants in MASK_LABELS]
_KEEP_RE = _build_label_re(KEEP_LABELS)


# ── 패턴 기반 ────────────────────────────────────────────────────────────
# 순서가 중요하다. 계좌번호 패턴은 'N-N-N' 을 넓게 잡아 카드번호와 휴대전화까지 먹는다.
# 좁은 것을 먼저 돌려야 각자 제 이름으로 잡힌다.

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("주민등록번호", re.compile(r"(?<![0-9])\d{6}\s*[-–]\s*[1-8]\d{6}(?![0-9])")),
    ("카드번호", re.compile(r"(?<![0-9])\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}(?![0-9])")),
    ("연락처", re.compile(r"(?<![0-9])01[016-9][-. ]?\d{3,4}[-. ]?\d{4}(?![0-9])")),
    # 유선전화. 계좌번호 패턴이 'N-N-N' 을 넓게 잡아 '051-000-0000' 까지 먹으므로
    # 먼저 돌려서 제 이름으로 잡는다. 0 으로 시작하는 지역번호만 본다.
    ("연락처", re.compile(r"(?<![0-9])0\d{1,2}[-]\d{3,4}[-]\d{4}(?![0-9])")),
    ("계좌번호", re.compile(r"(?<![0-9-])\d{2,6}-\d{2,6}-\d{2,7}(?![0-9-])")),
    ("이메일", re.compile(r"(?<![\w.])[\w.+-]+@[\w-]+\.[\w.]+")),
]


def _value_end(text: str, start: int, stops: list[int]) -> int:
    """라벨 뒤 값이 어디서 끝나는지 정한다.

    줄 끝까지가 기본이다. 다만 '사업체명 : 한빛테크 (전화 : 02-000-0000)' 처럼
    한 줄에 항목이 여러 개 있으면, 다음 라벨이 시작되기 전에서 끊어야 한다.
    안 그러면 사업체명 하나를 가리면서 줄 전체를 먹는다.
    """
    nl = text.find("\n", start)
    end = len(text) if nl < 0 else nl
    for s in stops:
        if start < s < end:
            end = s
    return end


MAX_VALUE_LEN = 60  # 이보다 길면 라벨 뒤 값이 아니라 문단을 먹은 것으로 본다


def find_spans(text: str) -> list[Span]:
    """가려야 할 구간을 모두 찾아 위치 순으로 돌려준다. 겹치는 구간은 합친다."""
    text = text or ""
    spans: list[Span] = []

    # 1) 패턴 기반
    for kind, pat in _PATTERNS:
        for m in pat.finditer(text):
            spans.append(Span(m.start(), m.end(), kind, m.group(0)))

    # 2) 라벨 기반
    #    값의 끝을 정하려면 '다음 라벨이 어디서 시작하는지'를 알아야 하므로
    #    가리는 라벨과 남기는 라벨의 위치를 모두 모아 둔다.
    label_starts: list[int] = [m.start() for m in _KEEP_RE.finditer(text)]
    for _, pat in _MASK_RE:
        label_starts.extend(m.start() for m in pat.finditer(text))
    label_starts.sort()

    for kind, pat in _MASK_RE:
        for m in pat.finditer(text):
            vs = m.end()
            ve = _value_end(text, vs, label_starts)
            value = text[vs:ve]
            stripped = value.strip()
            if not stripped or len(stripped) > MAX_VALUE_LEN:
                continue
            # 값의 꼬리를 다듬는다.
            #   '박정호 (서명)'        -> '박정호'      서명·날인 표시는 값이 아니다
            #   '주식회사 한빛테크   (' -> '주식회사 한빛테크'
            #                          다음 항목의 여는 괄호까지 먹은 경우
            #   '051-000-0000)'       -> '051-000-0000'
            #                          괄호 안에 들어 있던 항목의 닫는 괄호
            trimmed = re.sub(r"\s*[(（]\s*(?:서명|인|signature)\s*[)）]?\s*$", "", value)
            trimmed = trimmed.rstrip().rstrip("(（[")
            trimmed = trimmed.rstrip().rstrip(")）]")
            trimmed = trimmed.rstrip()
            if not trimmed:
                continue
            ve = vs + len(trimmed)
            spans.append(Span(vs, ve, kind, text[vs:ve]))

    spans += _propagate(text, spans)
    return _merge(spans)


# 라벨에서 찾아낸 이름을 문서 전체에서 다시 찾을 때, 너무 짧으면 본문 단어와 겹친다.
PROPAGATE_KINDS = {"성명", "사업체명"}
PROPAGATE_MIN_LEN = 2


def _propagate(text: str, spans: list[Span]) -> list[Span]:
    """라벨에서 찾은 이름을 문서의 다른 곳에서도 찾아 가린다.

    라벨 기반 탐지만으로는 구멍이 남는다. 계약서 첫 문장은 보통 이렇게 시작한다.

        주식회사 한빛테크(이하 "사업주")와 김현수(이하 "근로자")는 ...

    여기 '김현수'에는 라벨이 없다. 서명란의 '성명 : 김현수'는 가려지는데 첫 문장은
    그대로 남으면, 가렸다고 말하면서 실제로는 이름이 문서에 남아 있게 된다.

    해법은 단순하다. 서명란에서 이름을 이미 알아냈으므로, 그 이름을 문서 전체에서
    다시 찾으면 된다. 정규식으로 사람 이름을 찾는 것과 다르다. 여기서는 찾을 대상이
    이미 정해져 있으므로 본문의 엉뚱한 단어를 먹을 위험이 없다.

    PDF 추출은 '김 현 수'처럼 글자를 띄워 놓는 경우가 많아, 글자 사이 공백을 허용해
    찾는다.
    """
    known: set[tuple[str, str]] = set()
    for s in spans:
        if s.kind not in PROPAGATE_KINDS:
            continue
        compact = re.sub(r"\s+", "", s.value)
        if len(compact) >= PROPAGATE_MIN_LEN:
            known.add((compact, s.kind))

    extra: list[Span] = []
    for compact, kind in known:
        pattern = re.compile(r"\s*".join(re.escape(c) for c in compact))
        for m in pattern.finditer(text):
            extra.append(Span(m.start(), m.end(), kind, m.group(0)))
    return extra


def _merge(spans: list[Span]) -> list[Span]:
    """겹치거나 맞닿은 구간을 합친다.

    '연락처 : 010-1234-5678' 은 라벨 기반과 패턴 기반에 모두 걸린다.
    합치지 않으면 같은 곳을 두 번 세어 '민감정보 2건'이라고 잘못 안내하게 된다.
    """
    if not spans:
        return []
    spans.sort(key=lambda s: (s.start, -s.end))
    out = [spans[0]]
    for s in spans[1:]:
        last = out[-1]
        if s.start <= last.end:
            if s.end > last.end:
                out[-1] = Span(last.start, s.end, last.kind, "")
        else:
            out.append(s)
    return out


def counts(spans: list[Span]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in spans:
        out[s.kind] = out.get(s.kind, 0) + 1
    return out


def summary(c: dict[str, int]) -> str:
    """화면에 띄울 한 줄. 몇 건을 가렸는지 보여줘야 사용자가 확인할 수 있다."""
    if not c:
        return ""
    total = sum(c.values())
    parts = [f"{k} {v}건" for k, v in sorted(c.items(), key=lambda x: -x[1])]
    return f"민감정보 {total}건을 가렸습니다 ({', '.join(parts)})."
