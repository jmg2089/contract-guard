"""전체 파이프라인 오케스트레이션.

계약서 원문
  -> segment()      조항 분할            (LLM 안 씀)
  -> run_rules()    결정론적 위반 탐지    (LLM 안 씀)
  -> search()       조항별 법조문 검색    (LLM 안 씀)
  -> judge_clause() 검색된 조문만 보고 판정 (LLM 씀)
  -> verify_citation() 인용 게이트        (LLM 안 씀)
  -> Report

LLM이 관여하는 구간은 딱 한 칸이고, 그 앞뒤가 전부 검증 가능한 코드다.
"""
from concurrent.futures import ThreadPoolExecutor

from .types import Report
from .segment import segment
from .retrieve import get_index
from .rules import run_rules
from .judge import judge_clause
from . import classify as clf
from config import SEVERITY_ORDER


def analyze(text: str, use_llm: bool = True, use_classifier: bool = True, max_workers: int = 6) -> Report:
    clauses = segment(text)
    index = get_index()
    report = Report(clauses=clauses)

    rule_hits: dict[str, list] = {}
    for c in clauses:
        hits = run_rules(c)
        if hits:
            rule_hits[c.id] = hits
            report.findings.extend(hits)

    # 2단계: 분류기 — 룰이 못 잡은 조항의 '의미'를 본다. 외부 API 없음.
    if use_classifier and clf.available():
        for c in clauses:
            if c.id in rule_hits:
                continue
            f = clf.classify(c)
            if f is not None:
                report.findings.append(f)
                rule_hits.setdefault(c.id, []).append(f)

    if not use_llm:
        report.findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
        report.meta = _meta(report, clauses, llm=False)
        return report

    # 룰이 이미 위반을 잡은 조항은 LLM을 태우지 않는다 (비용/지연 절감)
    targets = [c for c in clauses if c.id not in rule_hits]

    def work(c):
        laws = index.search(c.text)
        return judge_clause(c, laws)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for kept, dropped in pool.map(work, targets):
            if kept.severity != "ok":
                report.findings.append(kept)
            if dropped is not None:
                report.dropped.append(dropped)

    report.findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
    report.meta = _meta(report, clauses, llm=True)
    return report


def _meta(report, clauses, llm: bool) -> dict:
    return {
        "clause_count": len(clauses),
        "violation_count": len(report.violations),
        "unfavorable_count": len(report.unfavorable),
        "rule_findings": sum(1 for f in report.findings if f.source == "rule"),
        "model_findings": sum(1 for f in report.findings if f.source == "model"),
        "llm_findings": sum(1 for f in report.findings if f.source == "llm"),
        "blocked_by_gate": len(report.dropped),
        "llm_enabled": llm,
    }
