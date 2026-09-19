"""결정론적 룰 체크 — LLM 없이 잡을 수 있는 것은 LLM에게 맡기지 않는다.

숫자 비교(최저임금 미달, 수습 4개월, 연차 10일)는 언어 모델이 가장 자주 틀리는
영역이다. 여기서 확정적으로 잡고, LLM은 '문장의 의미를 읽어야 하는' 조항에만 쓴다.

모든 룰은 근거 quote 를 법령 원문에서 그대로 떠오므로 judge.verify_citation() 을
그대로 통과한다. 즉 룰과 LLM이 같은 검증 관문을 지난다.
"""
import re

from .types import Clause, Finding
from .retrieve import get_index
from config import (
    MIN_WAGE_HOURLY,
    MIN_WAGE_MONTHLY,
    MONTHLY_HOURS,
    LEGAL_DAILY_HOURS,
    LEGAL_WEEKLY_HOURS,
    LEGAL_ANNUAL_LEAVE_DAYS,
    LEGAL_DISMISSAL_NOTICE_DAYS,
    LEGAL_SETTLEMENT_DAYS,
    PROBATION_MAX_MONTHS,
)

NUM = r"([0-9][0-9,]*)"


def _num(s: str) -> int:
    return int(s.replace(",", ""))


# "위약금을 청구하지 아니한다" 처럼 근로자에게 유리한 조항을 위반으로 잡는 오탐을 막는다.
# 정규식은 단어만 보기 때문에 부정 표현을 따로 확인해야 한다.
# '아니한다'는 아/니/한/다 이므로 '아니하'로는 매칭되지 않는다. 한국어 활용형을 넓게 받는다.
NEG_RE = re.compile(
    r"(?:하지|되지|받지|물지|지지|시키지)\s*(?:아니|않|못하)"
    r"|없\s*(?:다|으며|고|음)"
    r"|면제(?:한|하며|된)"
    r"|(?:청구|부과|요구|공제)할\s*수\s*없"
)


def _sentence_around(text: str, pos: int) -> str:
    """매칭된 위치가 속한 문장만 잘라낸다. 다른 문장의 부정 표현에 속지 않기 위해서다."""
    start = max(text.rfind(".", 0, pos), text.rfind("\n", 0, pos)) + 1
    end = min(
        (i for i in (text.find(".", pos), text.find("\n", pos)) if i != -1),
        default=len(text),
    )
    return text[start : end + 1]


def _negated(text: str, match) -> bool:
    if match is None:
        return False
    return bool(NEG_RE.search(_sentence_around(text, match.start())))


def _finding(clause, severity, law_id, sentence_idx, reason, suggestion=""):
    """법령 원문에서 문장 하나를 '그대로' 떠서 quote 로 쓴다."""
    art = get_index().get(law_id)
    if art is None:
        return None
    sentences = [s.strip() for s in re.split(r"(?<=다\.)\s*", art.text) if len(s.strip()) > 10]
    quote = sentences[min(sentence_idx, len(sentences) - 1)] if sentences else art.text
    return Finding(
        clause_id=clause.id,
        severity=severity,
        law_id=law_id,
        quote=quote,
        reason=reason,
        suggestion=suggestion,
        source="rule",
        gate_passed=True,
    )


# --- 개별 룰 -----------------------------------------------------------------

def r_penalty(c: Clause):
    m = re.search(r"위약금|손해배상액을?\s*(?:미리|예정)|배상액을\s*예정|위약벌"
                  r"|(?:교육비|연수비|훈련비|지원금)[^.\n]{0,25}?(?:반환|상환)", c.text)
    if m and not _negated(c.text, m):
        return _finding(c, "violation", "근로기준법-제20조", 0,
                        "퇴사·계약 불이행을 이유로 위약금이나 사전에 정한 손해배상액을 물리는 약정입니다. 근로기준법상 체결 자체가 금지됩니다.",
                        "해당 조항을 삭제하고, 실제 발생한 손해가 있을 때 개별적으로 청구하도록 바꾸십시오.")


def r_min_wage(c: Clause):
    m = re.search(r"시급\s*(?:금)?\s*" + NUM, c.text)
    if m and _num(m.group(1)) < MIN_WAGE_HOURLY:
        return _finding(c, "violation", "최저임금법-제6조", 0,
                        f"명시된 시급 {_num(m.group(1)):,}원은 {MIN_WAGE_HOURLY:,}원 미만입니다. 미달 부분은 무효이며 최저임금액으로 지급한 것으로 봅니다.",
                        f"시급을 {MIN_WAGE_HOURLY:,}원 이상으로 정정하십시오.")


def r_min_wage_monthly(c: Clause):
    """월급제 최저임금 미달. 시급만 보면 놓치는 가장 흔한 패턴이다."""
    m = re.search(r"(?:월|월급|월\s*급여|임금)\s*(?:금)?\s*" + NUM + r"\s*원", c.text)
    if not m:
        return None
    amount = _num(m.group(1))
    if amount < 500_000 or amount >= MIN_WAGE_MONTHLY:  # 500만 미만 = 월급으로 보기 어려움
        return None
    hourly = round(amount / MONTHLY_HOURS)
    return _finding(c, "violation", "최저임금법-제6조", 0,
                    f"월 급여 {amount:,}원은 월 소정근로시간 {MONTHLY_HOURS}시간 기준 시급 약 {hourly:,}원으로, "
                    f"최저임금 {MIN_WAGE_HOURLY:,}원에 미달합니다.",
                    f"월 급여를 {MIN_WAGE_MONTHLY:,}원 이상으로 정정하십시오.")


def r_forced_labor(c: Clause):
    """퇴사 자체를 막는 조항. '위약금'이 없어도 강제근로에 해당할 수 있다.

    '퇴직 후 ~할 수 없다'(경업금지)는 재직 중 구속이 아니므로 제외한다.
    제외하지 않으면 경업금지 조항을 강제근로로 오판한다.
    """
    if re.search(r"(?:퇴사|사직|퇴직)\s*(?:한\s*)?후", c.text):
        return None
    if re.search(r"(?:퇴사|사직|퇴직)[^.\n]{0,40}?(?:할\s*수\s*없|하지\s*못한다|금지|불가)"
                 r"|(?:동의|승인|허가)\s*(?:없이|없으면)[^.\n]{0,20}?(?:퇴사|사직|퇴직)", c.text):
        return _finding(c, "violation", "근로기준법-제7조", 0,
                        "근로자의 퇴사 자체를 금지하거나 회사 승인에 종속시키는 조항입니다. 자유의사에 어긋나는 근로 강요에 해당할 수 있습니다.",
                        "사직 의사표시 후 일정 기간(통상 30일) 인수인계 협조 의무로 바꾸십시오.")


def r_leave_timing(c: Clause):
    """연차 일수는 맞지만 시기지정권을 빼앗는 조항."""
    if re.search(r"(?:연차|유급휴가)[^.\n]{0,50}?(?:회사|사용자)[^.\n]{0,20}?(?:지정|정하는)[^.\n]{0,15}?(?:날|시기|기간)"
                 r"|(?:연차|유급휴가)[^.\n]{0,40}?(?:회사|사용자)가\s*일방", c.text):
        return _finding(c, "unfavorable", "근로기준법-제60조", 0,
                        "연차 일수는 충족하지만 사용 시기를 회사가 일방적으로 지정하는 조항입니다. 연차는 근로자가 청구한 시기에 주는 것이 원칙입니다.",
                        "근로자가 청구한 시기에 부여하되, 사업 운영에 막대한 지장이 있는 경우에만 시기를 변경할 수 있다고 수정하십시오.")


def r_probation(c: Clause):
    m = re.search(r"수습[^.\n]{0,20}?" + NUM + r"\s*개월", c.text)
    if m and _num(m.group(1)) > PROBATION_MAX_MONTHS:
        # 근거는 최저임금법 제5조 제2항 — 수습 감액이 허용되는 범위를 3개월로 정한 조문이다.
        return _finding(c, "unfavorable", "최저임금법-제5조", 2,
                        f"수습기간을 {_num(m.group(1))}개월로 정하고 있습니다. 최저임금 감액이 허용되는 범위는 {PROBATION_MAX_MONTHS}개월 이내이므로 그 이후 감액 지급은 최저임금 위반이 됩니다.",
                        f"수습기간을 {PROBATION_MAX_MONTHS}개월 이내로 줄이거나, 이후 기간은 감액 없이 전액 지급으로 명시하십시오.")


def r_annual_leave(c: Clause):
    if "연차" not in c.text and "유급휴가" not in c.text:
        return None
    if re.search(r"연차[^.\n]{0,20}?(없|미지급|부여하지)", c.text):
        return _finding(c, "violation", "근로기준법-제60조", 0,
                        "연차 유급휴가를 주지 않는다는 취지의 조항입니다.",
                        "연차 유급휴가 규정을 근로기준법 기준으로 명시하십시오.")
    m = re.search(NUM + r"\s*일[^.\n]{0,10}?(?:유급|연차)", c.text) or re.search(r"연차[^.\n]{0,15}?" + NUM + r"\s*일", c.text)
    if m and _num(m.group(1)) < LEGAL_ANNUAL_LEAVE_DAYS:
        return _finding(c, "violation", "근로기준법-제60조", 0,
                        f"연차를 {_num(m.group(1))}일로 정하고 있습니다. 1년간 80% 이상 출근 시 {LEGAL_ANNUAL_LEAVE_DAYS}일이 법정 기준입니다.",
                        f"연차 유급휴가를 {LEGAL_ANNUAL_LEAVE_DAYS}일 이상으로 수정하십시오.")


def r_working_hours(c: Clause):
    m = re.search(r"1\s*일\s*" + NUM + r"\s*시간", c.text)
    if m and _num(m.group(1)) > LEGAL_DAILY_HOURS:
        return _finding(c, "violation", "근로기준법-제50조", 1,
                        f"1일 소정근로시간을 {_num(m.group(1))}시간으로 정하고 있습니다. 휴게시간을 제외한 1일 근로시간은 {LEGAL_DAILY_HOURS}시간을 넘길 수 없습니다.",
                        f"소정근로시간을 1일 {LEGAL_DAILY_HOURS}시간으로 하고 초과분은 연장근로로 구분해 가산수당을 명시하십시오.")
    w = re.search(r"(?:1\s*주|주\s*간)[^.\n]{0,10}?" + NUM + r"\s*시간", c.text)
    if w and _num(w.group(1)) > LEGAL_WEEKLY_HOURS:
        return _finding(c, "violation", "근로기준법-제50조", 0,
                        f"1주 소정근로시간을 {_num(w.group(1))}시간으로 정하고 있습니다. 법정 한도는 {LEGAL_WEEKLY_HOURS}시간입니다.",
                        f"1주 {LEGAL_WEEKLY_HOURS}시간으로 정정하십시오.")


def r_unpaid_overtime(c: Clause):
    if re.search(r"(연장|야간|휴일|초과)\s*근로[^.\n]{0,30}?(수당|가산)[^.\n]{0,20}?(없|미지급|포함된 것으로|지급하지)", c.text) or \
       re.search(r"(포괄|고정)\s*연장", c.text) and re.search(r"추가\s*지급하지", c.text):
        return _finding(c, "violation", "근로기준법-제56조", 0,
                        "연장·야간·휴일 근로에 대한 가산수당을 지급하지 않는다는 취지입니다. 가산수당은 당사자 합의로 배제할 수 없습니다.",
                        "연장·야간·휴일 근로 시 통상임금의 50% 이상을 가산 지급한다고 명시하십시오.")


def r_dismissal_notice(c: Clause):
    m = re.search(r"해고[^.\n]{0,30}?" + NUM + r"\s*일\s*전", c.text)
    if m and _num(m.group(1)) < LEGAL_DISMISSAL_NOTICE_DAYS:
        return _finding(c, "violation", "근로기준법-제26조", 0,
                        f"해고 예고기간을 {_num(m.group(1))}일로 정하고 있습니다. 법정 기준은 {LEGAL_DISMISSAL_NOTICE_DAYS}일 전 예고 또는 그에 상당하는 통상임금 지급입니다.",
                        f"{LEGAL_DISMISSAL_NOTICE_DAYS}일 전 예고 또는 {LEGAL_DISMISSAL_NOTICE_DAYS}일분 통상임금 지급으로 수정하십시오.")
    if re.search(r"(즉시|언제든지)\s*해고|사유\s*없이[^.\n]{0,10}해고", c.text):
        return _finding(c, "violation", "근로기준법-제23조", 0,
                        "정당한 이유 없이 해고할 수 있다는 취지의 조항입니다.",
                        "해고 사유와 절차를 구체적으로 열거하고 정당한 이유를 요건으로 명시하십시오.")


def r_settlement(c: Clause):
    m = re.search(r"퇴직[^.\n]{0,25}?(?:임금|급여|금품)[^.\n]{0,25}?" + NUM + r"\s*일\s*이내", c.text)
    if m and _num(m.group(1)) > LEGAL_SETTLEMENT_DAYS:
        return _finding(c, "violation", "근로기준법-제36조", 0,
                        f"퇴직 후 금품 청산 기한을 {_num(m.group(1))}일로 정하고 있습니다. 법정 기한은 {LEGAL_SETTLEMENT_DAYS}일 이내입니다.",
                        f"{LEGAL_SETTLEMENT_DAYS}일 이내 지급으로 수정하십시오.")


def r_severance_waiver(c: Clause):
    if re.search(r"퇴직금[^.\n]{0,40}?(포기|청구하지|(?:임금|급여|월급)에\s*포함|분할\s*(?:하여\s*)?지급|매월\s*지급|중간\s*정산)", c.text):
        return _finding(c, "violation", "근로자퇴직급여보장법-제8조", 0,
                        "퇴직금을 미리 나누어 지급하거나 포기하게 하는 조항입니다. 이런 약정은 퇴직금 지급으로 인정되지 않습니다.",
                        "퇴직 시 계속근로기간 1년당 30일분 이상의 평균임금을 지급한다고 명시하십시오.")


def r_marriage_pregnancy(c: Clause):
    if re.search(r"(혼인|결혼|임신|출산)[^.\n]{0,25}?(퇴직|사직|퇴사)", c.text):
        return _finding(c, "violation", "남녀고용평등법-제11조", 1,
                        "혼인·임신·출산을 퇴직 사유로 예정하는 조항입니다.",
                        "해당 조항을 전면 삭제하십시오.")


def r_wage_offset(c: Clause):
    if re.search(r"(임금|급여)[^.\n]{0,30}?(상계|공제)[^.\n]{0,20}?(대여금|가불|전차금)", c.text):
        return _finding(c, "unfavorable", "근로기준법-제43조", 0,
                        "임금에서 대여금 등을 임의로 공제하는 조항입니다. 임금은 전액 지급이 원칙입니다.",
                        "공제 항목은 법령에 근거가 있는 경우로 한정한다고 명시하십시오.")


def r_break_time(c: Clause):
    if re.search(r"휴게[^.\n]{0,20}?(없|부여하지|미부여)", c.text):
        return _finding(c, "violation", "근로기준법-제54조", 0,
                        "휴게시간을 주지 않는다는 취지의 조항입니다.",
                        "4시간 근로 시 30분 이상, 8시간 근로 시 1시간 이상의 휴게시간을 명시하십시오.")



# --- 추가 룰 (조문 확장분을 실제로 사용하는 규칙) ---------------------------------

def r_dismissal_written(c: Clause):
    """해고 서면통지 의무 배제. 서면통지 없는 해고는 효력 자체가 없다."""
    if re.search(r"해고[^.\n]{0,40}?(?:구두|유선|전화|문자)(?:로만|로|만)?\s*(?:통보|통지|고지)"
                 r"|해고[^.\n]{0,30}?서면[^.\n]{0,20}?(?:하지\s*아니|않는다|생략|없이)", c.text):
        return _finding(c, "violation", "근로기준법-제27조", 0,
                        "해고 사유와 시기를 서면으로 통지하지 않겠다는 취지의 조항입니다. 서면통지 없는 해고는 효력이 없습니다.",
                        "해고 시 사유와 시기를 서면으로 통지한다고 명시하십시오.")


def r_pay_cut_limit(c: Clause):
    """감급 제재 한도 초과. 1회 평균임금 1일분의 1/2, 총액 임금총액의 1/10 이내."""
    m = re.search(r"(?:감봉|감급)[^.\n]{0,30}?" + NUM + r"\s*(?:퍼센트|%)", c.text)
    if m and _num(m.group(1)) > 10:
        return _finding(c, "violation", "근로기준법-제95조", 0,
                        f"감급 제재를 임금의 {_num(m.group(1))}퍼센트로 정하고 있습니다. 감급 총액은 1임금지급기 임금 총액의 10분의 1을 넘을 수 없습니다.",
                        "감급 한도를 임금 총액의 10분의 1 이내로 수정하십시오.")
    if re.search(r"(?:감봉|감급)[^.\n]{0,30}?(?:제한\s*없|한도\s*없|회사가\s*정하는)", c.text):
        return _finding(c, "violation", "근로기준법-제95조", 0,
                        "감급 제재의 한도를 두지 않은 조항입니다. 법정 한도를 넘는 감급은 무효입니다.",
                        "1회 평균임금 1일분의 2분의 1, 총액은 임금 총액의 10분의 1 이내로 명시하십시오.")


def r_fixed_term(c: Clause):
    """기간제 2년 초과 사용. 2년을 넘기면 무기계약으로 전환된 것으로 본다.

    주의: "2026년 10월 1일부터" 같은 날짜의 연도를 계약 연수로 오인하면 안 된다.
    계약기간은 현실적으로 한 자리 숫자이므로 1~9년만 받는다.
    """
    if re.search(r"기간의?\s*정함이?\s*없", c.text):
        return None
    m = re.search(r"(?:계약|근로)\s*기간[^.\n]{0,25}?(?<![0-9])([1-9])\s*년(?!\s*\d)", c.text)
    if m and _num(m.group(1)) > 2:
        return _finding(c, "unfavorable", "기간제법-제4조", 0,
                        f"기간제 계약기간을 {_num(m.group(1))}년으로 정하고 있습니다. 총 2년을 초과해 사용하면 기간의 정함이 없는 근로계약으로 전환된 것으로 봅니다.",
                        "계약기간을 2년 이내로 하거나, 2년 초과 시 무기계약 전환을 명시하십시오.")
    if re.search(r"(?:갱신|연장)[^.\n]{0,30}?(?:2년\s*초과|무기계약[^.\n]{0,15}?(?:아니|않)|전환되지)", c.text):
        return _finding(c, "violation", "기간제법-제4조", 1,
                        "반복 갱신으로 2년을 넘겨도 무기계약으로 전환되지 않는다는 취지의 조항입니다. 법정 전환 효과는 약정으로 배제할 수 없습니다.",
                        "해당 조항을 삭제하십시오.")


def r_retaliation(c: Clause):
    """노동청 진정·신고를 이유로 한 불이익. 보복 조치는 별도 금지 규정이 있다."""
    if re.search(r"(?:노동청|노동위원회|고용노동부|근로감독관|진정|신고|고발)[^.\n]{0,40}?"
                 r"(?:해고|징계|불이익|계약\s*해지|퇴사)", c.text):
        return _finding(c, "violation", "근로기준법-제104조", 1,
                        "법 위반 사실을 감독기관에 신고한 것을 이유로 불이익을 주는 조항입니다. 보복 조치는 금지되어 있습니다.",
                        "해당 조항을 삭제하십시오.")


def r_parental_leave(c: Clause):
    """육아휴직 거부 또는 불이익."""
    if re.search(r"육아휴직[^.\n]{0,40}?(?:허용하지|불가|제외|거부|인정하지|해고|불이익)"
                 r"|육아휴직[^.\n]{0,30}?(?:복직|복귀)[^.\n]{0,20}?(?:보장하지|아니)", c.text):
        return _finding(c, "violation", "남녀고용평등법-제19조", 2,
                        "육아휴직을 허용하지 않거나 이를 이유로 불이익을 주는 조항입니다.",
                        "육아휴직을 법령에 따라 허용하고, 복귀 시 같은 업무 또는 같은 수준의 임금 직무로 복직시킨다고 명시하십시오.")


def r_rules_change(c: Clause):
    """취업규칙을 근로자 동의 없이 불리하게 변경."""
    if re.search(r"취업규칙[^.\n]{0,40}?(?:동의\s*없이|일방적|회사가\s*단독|의견\s*청취[^.\n]{0,10}?(?:없|생략))", c.text):
        return _finding(c, "violation", "근로기준법-제94조", 0,
                        "취업규칙을 근로자 동의 없이 변경할 수 있게 한 조항입니다. 불리한 변경에는 근로자 과반수의 동의가 필요합니다.",
                        "불리한 변경 시 근로자 과반수의 동의를 받는다고 명시하십시오.")


def r_discrimination(c: Clause):
    """국적·신앙·사회적 신분에 따른 차별."""
    if re.search(r"(?:국적|출신|신앙|종교|혼인\s*여부|학벌|출신지)[^.\n]{0,30}?"
                 r"(?:따라|이유로)[^.\n]{0,25}?(?:차등|차별|달리|제한)", c.text):
        return _finding(c, "violation", "근로기준법-제6조", 0,
                        "국적·신앙 또는 사회적 신분을 이유로 근로조건을 달리 정하는 조항입니다.",
                        "해당 차별 기준을 삭제하고 직무 기준으로 대체하십시오.")



def r_harassment(c: Clause):
    """직장 내 괴롭힘을 용인하거나 신고를 막는 조항."""
    if re.search(r"(?:괴롭힘|폭언|따돌림|갑질)[^.\n]{0,40}?(?:문제\s*삼지|이의|책임지지|해당하지)"
                 r"|(?:괴롭힘|고충)[^.\n]{0,30}?(?:신고|제기)[^.\n]{0,25}?(?:금지|할\s*수\s*없|불이익)", c.text):
        return _finding(c, "violation", "근로기준법-제76조의2", 0,
                        "직장 내 괴롭힘을 문제 삼지 못하게 하거나 신고를 막는 조항입니다. 괴롭힘 금지는 법으로 정해져 있어 약정으로 배제할 수 없습니다.",
                        "해당 조항을 삭제하고, 괴롭힘 발생 시 조사·조치 절차를 명시하십시오.")


def r_maternity_leave(c: Clause):
    """출산전후휴가 미부여 또는 축소."""
    if re.search(r"출산(?:전후)?\s*휴가[^.\n]{0,35}?(?:부여하지|없|무급|제외|허용하지)"
                 r"|출산[^.\n]{0,20}?휴가[^.\n]{0,20}?" + NUM + r"\s*일", c.text):
        m = re.search(r"출산[^.\n]{0,20}?휴가[^.\n]{0,20}?" + NUM + r"\s*일", c.text)
        if m and _num(m.group(1)) >= 90:
            return None
        return _finding(c, "violation", "근로기준법-제74조", 0,
                        "출산전후휴가를 주지 않거나 법정 기준(90일)보다 짧게 정한 조항입니다.",
                        "출산 전후를 통하여 90일 이상의 출산전후휴가를 부여한다고 명시하십시오.")


def r_spouse_leave(c: Clause):
    """배우자 출산휴가 미부여 또는 불이익."""
    if re.search(r"배우자[^.\n]{0,20}?출산[^.\n]{0,25}?(?:휴가[^.\n]{0,15}?(?:없|부여하지|무급)|불이익|해고)", c.text):
        return _finding(c, "violation", "남녀고용평등법-제18조의2", 0,
                        "배우자 출산전후휴가를 주지 않거나 이를 이유로 불이익을 주는 조항입니다. 법정 휴가는 20일 유급입니다.",
                        "배우자 출산전후휴가 20일을 유급으로 부여한다고 명시하십시오.")


def r_job_interference(c: Clause):
    """재취업 방해 목적의 명단 작성·통보."""
    if re.search(r"(?:재취업|이직|취업)[^.\n]{0,30}?(?:방해|명단|블랙리스트|통보하여)"
                 r"|(?:퇴사자|퇴직자)[^.\n]{0,25}?명단[^.\n]{0,25}?(?:공유|통보|제공)", c.text):
        return _finding(c, "violation", "근로기준법-제40조", 0,
                        "퇴직자의 재취업을 방해할 목적으로 명단을 작성하거나 통보하는 조항입니다.",
                        "해당 조항을 전면 삭제하십시오.")


RULES = [
    r_penalty, r_min_wage, r_min_wage_monthly, r_forced_labor, r_leave_timing, r_probation, r_annual_leave, r_working_hours,
    r_unpaid_overtime, r_dismissal_notice, r_settlement, r_severance_waiver,
    r_marriage_pregnancy, r_wage_offset, r_break_time,
    r_dismissal_written, r_pay_cut_limit, r_fixed_term, r_retaliation,
    r_parental_leave, r_rules_change, r_discrimination,
    r_harassment, r_maternity_leave, r_spouse_leave, r_job_interference,
]


def run_rules(clause: Clause) -> list[Finding]:
    out = []
    for rule in RULES:
        try:
            f = rule(clause)
        except Exception:
            f = None
        if f is not None:
            out.append(f)
    return out
