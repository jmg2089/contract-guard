"""위험도 점수 + 원문 하이라이트 + 수정본 생성.

판정 결과를 '그래서 어쩌라는 건가'에 답하는 형태로 바꾸는 층이다.
- 위험도 점수: 판정 목록을 한 숫자로 요약한다. 심사위원이 30초 안에 이해할 수 있는 형태
- 하이라이트: 계약서 원문에서 문제 구간의 위치를 돌려준다. 프론트가 색칠할 수 있도록
- 수정본: 대체 문구를 적용한 계약서 초안을 만든다. 사용자가 실제로 쓸 수 있는 결과물

점수 산식은 자의적이지 않아야 한다. 가중치를 코드에 드러내고 화면에도 설명한다.
"""
from .types import Report

# 판정 1건당 가중치. 근거: 위반 소지는 조항 자체가 무효가 될 수 있고,
# 불리 조항은 법 위반은 아니지만 협상으로 고쳐야 하는 수준이다.
WEIGHT = {"violation": 25, "unfavorable": 10}

GRADES = [
    (0, 0, "안전", "법령과 대조해 문제되는 조항을 찾지 못했습니다."),
    (1, 25, "주의", "고칠 여지가 있는 조항이 있습니다. 서명 전에 확인하십시오."),
    (26, 60, "위험", "법 위반 소지가 있는 조항이 포함되어 있습니다. 수정을 요구하십시오."),
    (61, 100, "매우 위험", "무효가 될 수 있는 조항이 여러 건입니다. 전문가 상담을 권합니다."),
]


def risk_score(report: Report) -> dict:
    """0~100 위험도. 가중 합산 후 상한을 둔다.

    조항 수로 나누지 않는다. 조항이 많다고 위험이 희석되는 것이 아니기 때문이다.
    위약금 조항 하나가 있는 계약서는 조항이 5개든 50개든 똑같이 위험하다.
    """
    raw = sum(WEIGHT.get(f.severity, 0) for f in report.findings)
    score = min(100, raw)

    grade, message = "안전", GRADES[0][3]
    for lo, hi, g, msg in GRADES:
        if lo <= score <= hi:
            grade, message = g, msg
            break

    return {
        "score": score,
        "grade": grade,
        "message": message,
        "breakdown": {
            "violation": len(report.violations),
            "unfavorable": len(report.unfavorable),
            "violation_weight": WEIGHT["violation"],
            "unfavorable_weight": WEIGHT["unfavorable"],
        },
        "formula": f"위반 소지 {len(report.violations)}건 × {WEIGHT['violation']}점 "
                   f"+ 불리 조항 {len(report.unfavorable)}건 × {WEIGHT['unfavorable']}점 "
                   f"= {raw}점 (100점 상한)",
    }


def highlights(report: Report) -> list[dict]:
    """계약서 원문에서 문제 구간의 위치. 프론트가 그대로 색칠하면 된다.

    조항 분할 단계에서 이미 오프셋을 들고 있으므로 추가 계산이 없다.
    """
    by_clause = {}
    for f in report.findings:
        cur = by_clause.get(f.clause_id)
        # 한 조항에 여러 판정이 붙으면 더 심각한 쪽을 쓴다
        if cur is None or (cur["severity"] == "unfavorable" and f.severity == "violation"):
            by_clause[f.clause_id] = {"severity": f.severity, "law_id": f.law_id}

    out = []
    for c in report.clauses:
        hit = by_clause.get(c.id)
        if hit is None:
            continue
        out.append({
            "clause_id": c.id,
            "start": c.start,
            "end": c.end,
            "severity": hit["severity"],
            "law_id": hit["law_id"],
        })
    return sorted(out, key=lambda h: h["start"])


def revised_contract(text: str, report: Report) -> str:
    """대체 문구를 반영한 수정본 초안.

    원문을 지우지 않는다. 문제 조항 아래에 수정 제안을 주석으로 덧붙이는 방식이다.
    계약서는 당사자가 합의해서 고치는 문서이므로, 우리가 임의로 바꾼 것처럼
    보이게 만들면 안 된다. 협상 자료로 쓸 수 있는 형태가 맞다.
    """
    by_clause = {}
    for f in report.findings:
        by_clause.setdefault(f.clause_id, []).append(f)

    lines = ["# 근로계약서 검토 의견서", ""]
    lines.append("아래는 원문 조항과, 법령에 저촉될 소지가 있는 부분에 대한 수정 제안입니다.")
    lines.append("원문은 그대로 두었습니다. 협상 자료로 사용하십시오.")
    lines.append("")
    lines.append("---")
    lines.append("")

    for c in report.clauses:
        title = f"제{c.article_no}조 {c.title}" if c.article_no else (c.title or c.id)
        hits = by_clause.get(c.id, [])
        mark = "🔴" if any(f.severity == "violation" for f in hits) else ("🟡" if hits else "")
        lines.append(f"## {mark} {title}".strip())
        lines.append("")
        lines.append("> " + c.text.replace("\n", "\n> "))
        lines.append("")
        for f in hits:
            lines.append(f"**문제** — {f.reason}")
            lines.append("")
            lines.append(f"**근거** — {f.law_id}")
            lines.append(f"> {f.quote}")
            lines.append("")
            if f.suggestion:
                lines.append(f"**수정 제안** — {f.suggestion}")
                lines.append("")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("이 문서는 법률 자문이 아닙니다. 실제 분쟁이나 계약 체결 판단은")
    lines.append("노무사·변호사 또는 고용노동부 상담(☎1350)을 통해 확인하십시오.")
    return "\n".join(lines)
