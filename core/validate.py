"""입력이 근로계약서로 볼 수 있는지 먼저 판정한다.

이 층이 없으면 치명적인 오류가 난다.

    OCR이 깨진 글자를 뱉었다 -> 조항이 안 잡힌다 -> 위반 0건 -> "안전합니다 0점"

사용자는 안심하고 서명한다. 분석이 실패한 것을 성공으로 오해한 것이다.
법률 도구에서 "문제를 못 찾았다"와 "읽지 못했다"는 절대 같은 말이 아니다.

그래서 판정 전에 세 가지를 본다.
  1) 분석할 만한 길이인가
  2) 한국어 문서인가 (OCR이 깨지면 한글 비율이 무너진다)
  3) 계약 문서의 어휘가 보이는가

셋 중 하나라도 안 되면 결과를 "안전"이라고 말하지 않는다.
"""
import re

# 근로계약서라면 이 중 몇 개는 반드시 나온다. 없으면 다른 문서이거나 판독 실패다.
CONTRACT_TERMS = [
    "근로", "임금", "급여", "계약", "근무", "사용자", "근로자", "회사", "고용",
    "채용", "수습", "퇴직", "해고", "휴가", "휴일", "연차", "시간", "지급",
    "업무", "직무", "보험", "상여", "수당", "위약", "배상", "갑", "을",
]

MIN_LENGTH = 50
MIN_HANGUL_RATIO = 0.30
MIN_TERM_HITS = 3


def _hangul_ratio(text: str) -> float:
    """공백·숫자·기호를 뺀 글자 중 한글 비율.

    OCR이 실패하면 자모가 깨지거나 엉뚱한 한자·기호가 섞여 이 값이 무너진다.
    """
    letters = re.findall(r"[가-힣a-zA-Z一-鿿]", text)
    if not letters:
        return 0.0
    hangul = sum(1 for c in letters if "가" <= c <= "힣")
    return hangul / len(letters)


def _term_hits(text: str) -> list[str]:
    return [t for t in CONTRACT_TERMS if t in text]


def validate(text: str) -> dict:
    """입력 판정 결과.

    ok=False 면 화면에서 위험도 점수를 보여주면 안 된다.
    '문제 없음'과 '판독 실패'가 같은 화면으로 보이는 순간 이 서비스는 위험해진다.
    """
    text = (text or "").strip()
    stripped = re.sub(r"\s+", "", text)

    if len(stripped) < MIN_LENGTH:
        return {
            "ok": False,
            "reason": "too_short",
            "title": "분석하기에 내용이 너무 짧습니다",
            "message": f"글자 수가 {len(stripped)}자입니다. 계약서 전문을 붙여넣어 주세요.",
            "detail": {"length": len(stripped)},
        }

    ratio = _hangul_ratio(text)
    hits = _term_hits(text)

    if ratio < MIN_HANGUL_RATIO:
        # 영문이 멀쩡하게 쓰인 문서와, 글자가 깨진 문서는 다르게 안내해야 한다
        latin_words = re.findall(r"[a-zA-Z]{3,}", text)
        if len(latin_words) >= 15:
            return {
                "ok": False,
                "reason": "not_korean",
                "title": "영문 계약서는 아직 지원하지 않습니다",
                "message": "이 서비스는 한국 근로기준법 조문과 대조하는 방식이라 한국어 계약서만 검토할 수 있습니다. "
                           "한글 계약서가 따로 있다면 그쪽을 올려주세요.",
                "detail": {"hangul_ratio": round(ratio, 2), "terms": len(hits)},
            }
        return {
            "ok": False,
            "reason": "garbled",
            "title": "글자를 제대로 읽지 못했습니다",
            "message": "한글 비율이 너무 낮습니다. 사진이나 스캔본에서 글자를 잘못 읽었을 수 있습니다. "
                       "계약서 내용을 직접 복사해서 붙여넣어 주세요.",
            "detail": {"hangul_ratio": round(ratio, 2), "terms": len(hits)},
        }

    if len(hits) < MIN_TERM_HITS:
        return {
            "ok": False,
            "reason": "not_contract",
            "title": "근로계약서로 보이지 않습니다",
            "message": "근로계약서에서 흔히 쓰이는 표현(임금, 근로시간, 계약기간 등)을 찾지 못했습니다. "
                       "다른 문서를 올리셨거나 글자가 잘못 읽혔을 수 있습니다.",
            "detail": {"hangul_ratio": round(ratio, 2), "terms": len(hits)},
        }

    # 통과했지만 어휘가 빈약하면 결과를 단정하지 않도록 표시해 둔다
    weak = len(hits) < 6 or len(stripped) < 200
    return {
        "ok": True,
        "reason": "ok",
        "weak": weak,
        "title": "",
        "message": (
            "계약서 분량이 적어 일부 조항만 검토되었을 수 있습니다."
            if weak else ""
        ),
        "detail": {"hangul_ratio": round(ratio, 2), "terms": len(hits), "length": len(stripped)},
    }
