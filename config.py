"""전역 설정. 숫자 상수는 전부 여기 모아둔다 (법 개정 시 한 곳만 고치면 되도록)."""
import os


def _env(key: str, default: str = "") -> str:
    """Streamlit Community Cloud 의 Secrets 와 로컬 .env 를 동시에 지원한다.

    Cloud 는 Secrets 를 환경변수로도 주입하지만 버전에 따라 누락되는 경우가 있어
    st.secrets 를 폴백으로 둔다. streamlit 이 없는 환경(평가 스크립트)에서도 동작해야 하므로
    import 는 함수 안에서 한다.
    """
    v = os.getenv(key)
    if v:
        return v
    try:
        import streamlit as st

        return str(st.secrets.get(key, default))
    except Exception:
        return default


# 고용노동부 고시 기준 2026년 적용 최저임금 시간급
MIN_WAGE_HOURLY = 10_320
MIN_WAGE_YEAR = 2026
# 주 40시간 + 주휴시간 포함 월 소정근로시간 관행값. 월급제 최저임금 환산에 쓴다.
MONTHLY_HOURS = 209
MIN_WAGE_MONTHLY = MIN_WAGE_HOURLY * MONTHLY_HOURS  # 2,156,880원

# 근로기준법 기준선
LEGAL_DAILY_HOURS = 8
LEGAL_WEEKLY_HOURS = 40
LEGAL_OT_WEEKLY_CAP = 12          # 제53조: 합의 시 1주 12시간 한도
LEGAL_ANNUAL_LEAVE_DAYS = 15      # 제60조: 1년 80% 이상 출근 시 15일
LEGAL_DISMISSAL_NOTICE_DAYS = 30  # 제26조
LEGAL_SETTLEMENT_DAYS = 14        # 제36조
PROBATION_MAX_MONTHS = 3          # 최저임금 감액 적용 가능한 수습 기간 상한

# 분류기 설정 — LLM 없이 '의미'를 판별하는 층
CLASSIFIER_PATH = "data/clause_clf.joblib"
CLASSIFIER_MIN_CONF = 0.50   # 이 미만이면 아무 말도 하지 않는다
CLASSIFIER_HIGH_CONF = 0.60  # 이 이상만 '위반 소지', 그 사이는 '확인 권장'으로 낮춰 말한다
# 실측 트레이드오프 (평가셋 11건/라벨 30개 기준)
#   0.45 → 재현율 96.7% / 정밀도 90.6%
#   0.50 → 재현율 96.7% / 정밀도 93.5%   ← 채택
#   0.60 → 재현율 90.0% / 정밀도 100.0%
# 법률 도구에서 오탐은 신뢰를 깎는다. 그래서 놓치지는 않되, 확신이 낮으면 단정하지 않는다.

# 숫자로 확정 판단되는 유형은 룰이 이미 정확하다. 분류기가 끼어들면 오탐만 는다.
# 역할 분리: 숫자는 룰, 의미는 분류기.
CLASSIFIER_DEFER_TO_RULES = {
    "최저임금법-제6조",      # 금액 비교
    "근로기준법-제50조",     # 시간 비교
    "근로기준법-제26조",     # 일수 비교
    "근로기준법-제36조",     # 일수 비교
}

# 검색 설정
RETRIEVE_TOP_K = 4
MIN_QUOTE_LEN = 12  # 인용 게이트: 이보다 짧은 인용은 근거로 인정하지 않는다

# LLM 설정 — 키가 하나도 없어도 dummy 모드로 파이프라인 전체가 돌아간다
LLM_PROVIDER = _env("LLM_PROVIDER", "dummy")  # dummy | openai_compatible | anthropic
LLM_MODEL = _env("LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = _env("LLM_BASE_URL", "")  # Upstage: https://api.upstage.ai/v1
LLM_API_KEY = _env("LLM_API_KEY", "")
LLM_TIMEOUT = 40

SEVERITY_ORDER = {"violation": 0, "unfavorable": 1, "ok": 2}
SEVERITY_LABEL = {
    "violation": "위반 소지",
    "unfavorable": "불리 조항",
    "ok": "특이사항 없음",
}
