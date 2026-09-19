import re
from core.pipeline import analyze
from core.scoring import risk_score, highlights, revised_contract
from core.retrieve import get_index
from core import classify as _clf
from config import (
    SEVERITY_LABEL,
    MIN_WAGE_HOURLY,
    MIN_WAGE_YEAR,
)

SOURCE_LABEL = {"rule": "룰 검사", "model": "학습 모델", "llm": "LLM 판정"}

def validate_contract_input(text: str) -> dict:
    """입력값이 근로계약서로 분석할 만한 내용인지 검사한다."""

    text = (text or "").strip()

    # 1. 너무 짧은 입력 차단
    if len(text) < 30:
        return {
            "valid": False,
            "message": "입력 내용이 너무 짧습니다. 근로계약서 내용을 입력해주세요.",
        }

    # 2. 의미 없는 자음/모음 반복 입력 차단
    korean_syllables = len(re.findall(r"[가-힣]", text))
    korean_jamo = len(re.findall(r"[ㄱ-ㅎㅏ-ㅣ]", text))

    if korean_jamo > korean_syllables:
        return {
            "valid": False,
            "message": "의미 있는 문장으로 확인되지 않습니다. 근로계약서 내용을 입력해주세요.",
        }

    # 3. 근로계약서에서 일반적으로 나타나는 핵심 표현
    contract_keywords = [
        "근로",
        "근로자",
        "사용자",
        "회사",
        "사업주",
        "임금",
        "급여",
        "월급",
        "시급",
        "근무",
        "근로시간",
        "근무시간",
        "휴게",
        "휴일",
        "연차",
        "퇴직",
        "계약기간",
        "근로계약",
    ]

    keyword_count = sum(1 for keyword in contract_keywords if keyword in text)

    if keyword_count < 2:
        return {
            "valid": False,
            "message": "근로계약서로 확인할 수 없는 내용입니다. 근로조건, 임금, 근로시간 등이 포함된 계약서 내용을 입력해주세요.",
        }

    # 4. 어느 정도 문장 구조가 있는지 검사
    meaningful_chars = len(re.findall(r"[가-힣A-Za-z0-9]", text))

    if meaningful_chars < 20:
        return {
            "valid": False,
            "message": "분석할 수 있는 계약서 내용이 부족합니다.",
        }

    return {
        "valid": True,
        "message": "",
    }

def analyze_contract(text: str, use_llm: bool = False) -> dict | None:
    text = (text or "").strip()

    print("===== ANALYZE_CONTRACT 실행 =====")
    print("입력:", repr(text))

    if not text:
        return None

    validation = validate_contract_input(text)

    print("VALIDATION 결과:", validation)

    if not validation["valid"]:
        print("===== 입력 검증 차단 =====")

        return {
            "error": "invalid_contract",
            "message": validation["message"],
        }

    print("===== 입력 검증 통과 =====")

    report = analyze(text, use_llm=use_llm)

    index = get_index()
    clause_by_id = {c.id: c for c in report.clauses}
    index = get_index()
    clause_by_id = {c.id: c for c in report.clauses}

    findings = []
    for f in report.findings:
        c = clause_by_id.get(f.clause_id)
        art = index.get(f.law_id)
        d = f.to_dict()
        d["severity_label"] = SEVERITY_LABEL[f.severity]
        d["source_label"] = SOURCE_LABEL.get(f.source, f.source)
        d["clause_title"] = (
            f"제{c.article_no}조 {c.title}" if c and c.article_no else (c.title if c else "")
        )
        d["clause_text"] = c.text if c else ""
        d["law_label"] = f"{art.law} {art.article}({art.title})" if art else ""
        d["law_text"] = art.text if art else ""
        findings.append(d)

    meta = dict(report.meta)
    meta["risk"] = risk_score(report)

    return {
        "meta": meta,
        "highlights": highlights(report),
        "clauses": [c.to_dict() for c in report.clauses],
        "findings": findings,
        "dropped": [
            {"clause_id": d.clause_id, "claimed_law_id": d.law_id, "claimed_quote": d.quote}
            for d in report.dropped
        ],
        "revised_markdown": revised_contract(text, report),
    }


def system_info() -> dict:
    """화면 상단/하단에 표시할 시스템 정보. 상태 점검용으로도 쓴다."""
    index = get_index()
    model = _clf.load()
    from core.rules import RULES

    return {
        "law_count": len(index.articles),
        "unverified": len(index.unverified),
        "rule_count": len(RULES),
        "classifier_loaded": model is not None,
        "classifier_classes": len(model.classes_) if model is not None else 0,
        "min_wage": MIN_WAGE_HOURLY,
        "min_wage_year": MIN_WAGE_YEAR,
    }


def samples() -> list[dict]:
    """샘플 계약서 목록(본문 제외). 버튼 렌더링용."""
    from data.samples import listing

    return listing()


def sample_text(sample_id: str) -> str | None:
    """샘플 계약서 본문."""
    from data.samples import get

    s = get(sample_id)
    return s["text"] if s else None


def law_articles() -> list[dict]:
    """탑재된 법령 조문 전체. 근거 조문 전문을 모달로 띄울 때 쓴다."""
    return [a.to_dict() for a in get_index().articles]


if __name__ == "__main__":
    import json

    print(json.dumps(system_info(), ensure_ascii=False, indent=2))
    demo = (
        "제1조(근로조건) 회사는 근로자의 동의 없이 임금 및 근로조건을 변경할 수 있다.\n\n"
        "제2조(임금) 임금은 시급 9,500원으로 한다.\n\n"
        "제3조(손해배상) 중도 퇴사 시 위약금 300만원을 지급한다."
    )
    r = analyze_contract(demo)
    print("\n", json.dumps(r["meta"], ensure_ascii=False))
    for f in r["findings"]:
        print(f"  [{f['severity_label']}] {f['clause_title']} / {f['law_label']} / {f['source_label']}")
