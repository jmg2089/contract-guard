"""조항 유형 분류기 — LLM 없이 '의미'를 판별하는 층.

정규식(rules.py)은 글자를 본다. 그래서 "위약금"은 잡아도
"교육비를 전액 반환하여야 한다"는 못 잡는다. 같은 뜻인데 단어가 다르기 때문이다.

이 분류기는 우리가 직접 만든 학습 데이터로 학습한 모델이다.
외부 API를 호출하지 않고, 인터넷 연결도 필요 없고, 비용이 0이며,
같은 입력에 항상 같은 출력을 낸다.

그리고 중요한 성질이 하나 있다.
    이 모델은 문장을 '생성'하지 않는다. 유형만 고른다.
    근거 문장은 언제나 data/laws.json 의 법령 원문에서 그대로 떠온다.
    따라서 법 문구를 지어낼 방법이 구조적으로 존재하지 않는다.
"""
from pathlib import Path

from .types import Clause, Finding
from .retrieve import get_index
from config import (CLASSIFIER_MIN_CONF, CLASSIFIER_HIGH_CONF,
                    CLASSIFIER_PATH, CLASSIFIER_DEFER_TO_RULES)

# 유형별 판정 등급과 설명. 분류기는 '어느 조문인가'만 고르고, 문장은 여기서 나온다.
TYPE_INFO = {
    "근로기준법-제20조": ("violation", "퇴사나 계약 불이행을 이유로 금전 부담을 지우는 조항입니다. 명칭이 위약금이든 교육비 반환이든 실질이 같으면 금지됩니다.", "해당 조항을 삭제하고, 실제 발생한 손해가 있을 때 개별적으로 청구하도록 바꾸십시오."),
    "근로기준법-제7조": ("violation", "근로자의 퇴사나 업무 거부를 막아 자유의사에 어긋나는 근로를 강요하는 조항입니다.", "사직의 자유를 보장하고, 인수인계 협조 의무 수준으로 완화하십시오."),
    "근로기준법-제17조": ("violation", "근로조건을 회사가 일방적으로 바꿀 수 있게 한 조항입니다. 근로조건은 명시하고 변경 시에도 다시 명시해야 합니다.", "변경 시 근로자와 서면 합의를 거친다고 수정하십시오."),
    "근로기준법-제43조": ("violation", "임금을 전액·정기 지급하지 않거나 임의로 공제·유예할 수 있게 한 조항입니다.", "임금은 매월 정해진 날에 통화로 전액 지급한다고 명시하십시오."),
    "근로기준법-제23조": ("violation", "정당한 이유 없이 해고할 수 있게 하거나, 부당한 사유를 해고 사유로 삼는 조항입니다.", "해고 사유를 구체적으로 열거하고 정당한 이유를 요건으로 명시하십시오."),
    "근로기준법-제26조": ("violation", "해고 예고 기간을 법정 기준보다 짧게 정한 조항입니다.", "30일 전 예고 또는 30일분 통상임금 지급으로 수정하십시오."),
    "근로기준법-제56조": ("violation", "연장·야간·휴일 근로에 대한 가산수당을 배제하거나 축소하는 조항입니다.", "통상임금의 50% 이상을 가산 지급한다고 명시하십시오."),
    "근로기준법-제60조": ("violation", "연차 유급휴가를 주지 않거나, 일수를 줄이거나, 사용 시기를 회사가 일방적으로 정하는 조항입니다.", "15일 이상을 부여하고 근로자가 청구한 시기에 부여한다고 수정하십시오."),
    "근로기준법-제50조": ("violation", "법정 근로시간 한도를 넘는 소정근로시간을 정한 조항입니다.", "1일 8시간, 1주 40시간으로 정하고 초과분은 연장근로로 구분하십시오."),
    "근로기준법-제54조": ("violation", "법정 휴게시간을 주지 않거나 실질적으로 쉬지 못하게 하는 조항입니다.", "4시간 근로 시 30분, 8시간 근로 시 1시간 이상을 근로시간 도중에 부여하십시오."),
    "근로기준법-제36조": ("violation", "퇴직 후 금품 청산 기한을 법정 14일보다 길게 정한 조항입니다.", "14일 이내 지급으로 수정하십시오."),
    "근로자퇴직급여보장법-제8조": ("violation", "퇴직금을 분할 지급하거나 포기시키는 조항입니다. 이런 약정은 퇴직금 지급으로 인정되지 않습니다.", "퇴직 시 계속근로기간 1년당 30일분 이상의 평균임금을 지급한다고 명시하십시오."),
    "남녀고용평등법-제11조": ("violation", "혼인·임신·출산을 퇴직 사유로 삼는 조항입니다.", "해당 조항을 전면 삭제하십시오."),
    "최저임금법-제6조": ("violation", "최저임금에 미치지 못하는 임금을 정했거나, 수습을 이유로 과도하게 감액하는 조항입니다.", "최저임금액 이상으로 정정하십시오."),
}

_model = None
_loaded = False


def load():
    """모델을 한 번만 읽는다. 파일이 없으면 None — 분류 단계는 조용히 건너뛴다."""
    global _model, _loaded
    if _loaded:
        return _model
    _loaded = True
    path = Path(CLASSIFIER_PATH)
    if not path.exists():
        return None
    try:
        import joblib

        _model = joblib.load(path)
    except Exception:
        _model = None
    return _model


def available() -> bool:
    return load() is not None


def classify(clause: Clause) -> Finding | None:
    model = load()
    if model is None:
        return None

    text = clause.text.strip()
    # 문맥이 없는 짧은 조항("연차 | 근로기준법에 따름")은 단어 하나만 보고 오판한다.
    # 룰은 숫자를 보므로 짧아도 정확하지만, 분류기는 문장 전체를 봐야 한다.
    if len(text) < 25:
        return None

    proba = model.predict_proba([text])[0]
    idx = int(proba.argmax())
    label = model.classes_[idx]
    conf = float(proba[idx])

    if label == "NORMAL" or conf < CLASSIFIER_MIN_CONF:
        return None

    # 숫자로 확정 판단하는 유형은 룰에게 넘긴다. 룰이 못 잡았다면 그 조항엔 그 숫자가 없는 것이다.
    if label in CLASSIFIER_DEFER_TO_RULES:
        return None

    info = TYPE_INFO.get(label)
    article = get_index().get(label)
    if info is None or article is None:
        return None

    severity, reason, suggestion = info

    # 확신도가 낮으면 '위반'이라고 단정하지 않고 '확인 권장'으로 낮춰 말한다.
    # 놓치지 않으면서도 잘못된 단정을 하지 않는 방법이다.
    if conf < CLASSIFIER_HIGH_CONF:
        severity = "unfavorable"
        reason = "이 조항은 아래 조문에 저촉될 소지가 있어 확인이 필요합니다. " + reason

    # 근거 문장은 법령 원문에서 그대로 떠온다. 모델은 여기에 관여하지 않는다.
    import re

    sentences = [s.strip() for s in re.split(r"(?<=다\.)\s*", article.text) if len(s.strip()) > 10]
    quote = sentences[0] if sentences else article.text

    return Finding(
        clause_id=clause.id,
        severity=severity,
        law_id=label,
        quote=quote,
        reason=f"{reason} (분류기 확신도 {conf:.0%})",
        suggestion=suggestion,
        source="model",
        gate_passed=True,
    )
