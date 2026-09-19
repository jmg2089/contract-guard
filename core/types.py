"""모듈 간 계약(contract). 두 사람이 병렬로 작업하려면 이 스키마가 먼저 고정되어야 한다.

이 파일은 금요일 밤에 확정하고, 이후로는 합의 없이 바꾸지 않는다.
"""
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

Severity = Literal["violation", "unfavorable", "ok"]


@dataclass
class Clause:
    """계약서에서 잘라낸 조항 한 개."""
    id: str                  # "c3"
    article_no: Optional[int]  # 3  (제3조). 번호가 없으면 None
    title: str               # "수습기간"
    text: str                # 조항 본문 전체
    start: int = 0           # 원문에서의 문자 오프셋 (하이라이트용)
    end: int = 0

    def to_dict(self):
        return asdict(self)


@dataclass
class LawArticle:
    """법령 조문 한 개. text는 반드시 공식 원문이어야 한다 (인용 게이트의 기준이 됨)."""
    id: str        # "근로기준법-제60조"
    law: str       # "근로기준법"
    article: str   # "제60조"
    title: str     # "연차 유급휴가"
    text: str      # 조문 원문
    verified: bool = False  # 법제처 원문으로 교체했는지 여부

    def to_dict(self):
        return asdict(self)


@dataclass
class Finding:
    """조항 하나에 대한 판정 결과."""
    clause_id: str
    severity: Severity
    law_id: str          # 근거 조문 id. 인용 게이트가 이 값이 검색 결과에 있는지 확인한다
    quote: str           # 근거 조문에서 '그대로' 발췌한 문장
    reason: str          # 왜 문제인지 (계약서 문구와 법 문구를 연결)
    suggestion: str = ""  # 대체 문구 제안
    source: Literal["rule", "model", "llm"] = "llm"
    gate_passed: bool = False  # 인용 검증 통과 여부

    def to_dict(self):
        return asdict(self)


@dataclass
class Report:
    clauses: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    dropped: list = field(default_factory=list)  # 인용 게이트에서 탈락한 판정 (발표 자료용 증거)
    meta: dict = field(default_factory=dict)

    @property
    def violations(self):
        return [f for f in self.findings if f.severity == "violation"]

    @property
    def unfavorable(self):
        return [f for f in self.findings if f.severity == "unfavorable"]
