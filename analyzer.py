"""통합용 단일 진입점 — 프론트엔드 프로젝트에 붙일 때 이 파일 하나만 보면 된다.

강수현 님이 만든 Flask 앱에 붙이는 방법:

    1) 이 프로젝트의 다음을 프론트 프로젝트 루트로 복사한다
         core/          판정 로직
         data/          법령 원문 + 학습 데이터
         scripts/       분류기 학습 스크립트
         config.py      상수
         analyzer.py    이 파일
         requirements.txt

    2) 분류기를 한 번 학습시킨다 (10초)
         python scripts/train_classifier.py

    3) 기존 Flask 라우트에서 함수 하나만 호출한다

         from analyzer import analyze_contract

         @app.route("/", methods=["GET", "POST"])
         def index():
             result = None
             if request.method == "POST":
                 result = analyze_contract(request.form.get("text", ""))
             return render_template("index.html", result=result)

기존 라우트 구조를 바꿀 필요가 없다. 반환값 스키마는 FRONTEND.md 4번에 있다.
"""
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


def analyze_contract(text: str, use_llm: bool = False) -> dict | None:
    """계약서 원문 -> 판정 결과 딕셔너리. 입력이 비어 있으면 None.

    use_llm 은 기본 False. 외부 API 없이 룰 + 학습 분류기만으로 동작한다.
    """
    text = (text or "").strip()
    if not text:
        return None

    report = analyze(text, use_llm=use_llm)
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
