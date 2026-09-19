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
from core.validate import validate as validate_input
from core.doctype import classify_document
from core.mask import mask as mask_sensitive, summary as mask_summary
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

    # 판정에 쓰이지 않는 개인정보를 먼저 가린다.
    # 주민등록번호·계좌번호는 위약금 조항이 위법인지 따지는 데 한 글자도 필요 없다.
    # 브라우저에서 이미 가리고 보내지만(static/js/mask.js), 자바스크립트가 꺼져 있거나
    # API 를 직접 호출하는 경우를 대비해 서버에서 한 번 더 가린다.
    text, masked = mask_sensitive(text)

    check = validate_input(text)

    # 읽히기는 했는데 근로계약서가 아닌 경우를 여기서 가른다.
    # validate_input 은 '읽혔는가'만 본다. 이력서·재직증명서는 계약 용어가 몇 개
    # 들어 있어 그 검사를 그냥 통과하는데, 거기에 근로기준법을 들이대면 틀린 답이 된다.
    doc = classify_document(text) if check["ok"] else None

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

    # 제17조 서면 명시 누락은 조항 단위 룰로는 잡을 수 없다.
    # 없는 조항은 검사 대상이 되지 않기 때문이다. 문서 전체를 봐야만 나오는 판정이라
    # 여기서 별도 항목으로 붙인다. 인용문은 조문 원문에서 가져오므로 인용 검증을 통과한다.
    if doc and doc["kind"] == "employment" and doc.get("missing_articles"):
        m = doc["missing_articles"]
        art = index.get(m["law_id"])
        findings.append({
            "clause_id": None,
            "severity": "violation",
            "severity_label": SEVERITY_LABEL["violation"],
            "source": "rule",
            "source_label": "문서 전체 검사",
            "law_id": m["law_id"],
            "quote": m["quote"],
            "reason": m["message"],
            "suggestion": "빠진 항목을 계약서에 적어 넣고 서면으로 교부받으세요. "
                          "명시하지 않으면 사용자에게 500만원 이하의 벌금이 부과될 수 있습니다.",
            "clause_title": "계약서 전체",
            "clause_text": "",
            "law_label": f"{art.law} {art.article}({art.title})" if art else "",
            "law_text": art.text if art else "",
        })

    meta = dict(report.meta)
    meta["risk"] = risk_score(report)
    meta["input_check"] = check
    meta["doctype"] = doc
    meta["masked"] = masked
    meta["masked_message"] = mask_summary(masked)

    # 근로계약서가 아니면 위험도 점수를 내보내지 않는다.
    # 용역계약서에 "위반 0건 · 0점 · 안전"을 띄우면, 근로기준법이 적용되지 않아
    # 검사조차 하지 않았다는 사실이 '문제 없음'으로 읽힌다. 가장 피해야 할 오해다.
    meta["analyzable"] = doc is not None and doc["kind"] == "employment"

    return {
        # 마스킹을 거친 본문. 화면의 입력창에 이 값을 되돌려 넣어야 한다.
        # 원본을 그대로 다시 뿌리면 가린 의미가 없다 — HTML 응답에 주민번호가 그대로 실린다.
        "text": text,
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
