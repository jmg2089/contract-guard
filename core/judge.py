"""조항 판정 + 인용 검증 게이트.

이 프로젝트의 핵심 주장:
    "LLM은 법을 기억해서 답하지 않는다. 검색된 조문만 보고 판정하고,
     인용이 원문과 일치하지 않으면 그 판정은 버린다."

게이트는 verify_citation() 하나다. 이게 통과 못 한 판정은 사용자에게
도달하지 못하고 report.dropped 로 격리된다. 격리된 개수 자체가
'우리가 할루시네이션을 몇 번 막았는지'를 보여주는 발표 자료가 된다.
"""
import re

from .types import Clause, Finding, LawArticle
from .llm import complete, parse_json
from config import MIN_QUOTE_LEN

SYSTEM = """너는 한국 근로계약서를 검토하는 보조 도구다.

절대 규칙:
1. 아래 [참고 조문]에 실제로 주어진 문장만 근거로 쓴다. 기억하고 있는 법 지식은 쓰지 않는다.
2. quote 는 [참고 조문] 본문에서 글자 하나 바꾸지 말고 그대로 복사한다. 요약하거나 다듬지 않는다.
3. 참고 조문 중 어느 것도 해당 조항과 관련이 없으면 verdict 를 "ok" 로 하고 law_id 와 quote 를 빈 문자열로 둔다.
4. 추측하지 않는다. 근거를 못 대면 "ok" 다.

출력은 JSON 객체 하나만. 설명 문장 금지.
{
  "verdict": "violation" | "unfavorable" | "ok",
  "law_id": "참고 조문의 id 를 그대로",
  "quote": "참고 조문 본문에서 그대로 복사한 한 문장",
  "reason": "계약서 문구 어느 부분이 왜 문제인지 2문장 이내",
  "suggestion": "대체 문구 제안 1문장"
}

verdict 기준:
- violation  : 법 규정에 정면으로 어긋나 무효이거나 처벌 대상이 될 수 있는 경우
- unfavorable: 위법은 아니지만 근로자에게 일방적으로 불리한 경우
- ok         : 문제없음"""

USER_TMPL = """[계약서 조항]
{clause}

[참고 조문]
{laws}

위 조항을 판정하라."""


def _norm(s: str) -> str:
    """공백/구두점 차이를 무시한 비교용 정규화. 문자 자체는 바꾸지 않는다."""
    return re.sub(r"[\s·,.\"'()]+", "", s)


def verify_citation(finding: Finding, retrieved: dict[str, LawArticle]) -> bool:
    """인용 검증 게이트 — 이 프로젝트의 심장.

    1) 인용한 조문이 '이번에 검색된' 조문 안에 있어야 한다 (기억해낸 법 차단)
    2) quote 가 그 조문 원문의 실제 부분문자열이어야 한다 (문구 날조 차단)
    3) quote 가 너무 짧으면 근거로 인정하지 않는다 (의미 없는 조각 차단)
    """
    if finding.severity == "ok":
        return True
    article = retrieved.get(finding.law_id)
    if article is None:
        return False
    q = _norm(finding.quote)
    if len(q) < MIN_QUOTE_LEN:
        return False
    return q in _norm(article.text)


def judge_clause(clause: Clause, laws: list[LawArticle]) -> tuple[Finding, Finding | None]:
    """반환: (사용자에게 보여줄 판정, 게이트 탈락으로 격리된 판정 또는 None)"""
    if not laws:
        return _ok(clause), None

    laws_block = "\n\n".join(
        f"id: {a.id}\n{a.law} {a.article}({a.title})\n{a.text}" for a in laws
    )
    raw = complete(SYSTEM, USER_TMPL.format(clause=clause.text, laws=laws_block))
    data = parse_json(raw)

    verdict = data.get("verdict", "ok")
    if verdict not in ("violation", "unfavorable", "ok"):
        verdict = "ok"

    finding = Finding(
        clause_id=clause.id,
        severity=verdict,
        law_id=(data.get("law_id") or "").strip(),
        quote=(data.get("quote") or "").strip(),
        reason=(data.get("reason") or "").strip(),
        suggestion=(data.get("suggestion") or "").strip(),
        source="llm",
    )

    retrieved = {a.id: a for a in laws}
    if verify_citation(finding, retrieved):
        finding.gate_passed = True
        return finding, None

    # 게이트 탈락: 사용자에게는 'ok' 로 내려보내고, 원본은 증거로 격리
    finding.gate_passed = False
    return _ok(clause), finding


def _ok(clause: Clause) -> Finding:
    return Finding(
        clause_id=clause.id,
        severity="ok",
        law_id="",
        quote="",
        reason="",
        source="llm",
        gate_passed=True,
    )
