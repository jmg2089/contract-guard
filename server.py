"""Flask 서버 — 팀원이 Flask로 프론트를 만들 때 이 파일이 두 사람의 경계선이 된다.

정민규는 core/, data/, eval/ 만 건드린다.
팀원은 templates/, static/ 만 건드린다.
이 파일(server.py)은 둘이 합의해서만 고친다.

실행:
    python server.py
    -> http://localhost:5000

엔드포인트:
    GET  /             화면 (templates/index.html)
    POST /             폼 제출 -> 같은 화면에 결과 렌더링
    POST /api/analyze  JSON API (팀원이 JS로 호출할 때)
    GET  /api/laws     탑재된 법조문 전체
    GET  /health       상태 확인
"""
import os

from flask import Flask, jsonify, render_template, request

from core.pipeline import analyze
from core.retrieve import get_index
from config import MIN_WAGE_HOURLY, MIN_WAGE_YEAR, SEVERITY_LABEL

app = Flask(__name__)

try:  # 팀원이 다른 포트/도메인에서 프론트를 띄울 경우에만 필요
    from flask_cors import CORS

    CORS(app)
except ImportError:
    pass


def build_payload(text: str, use_llm: bool) -> dict:
    """화면 렌더링과 JSON API가 같은 데이터를 쓴다. 형태가 갈라지면 버그가 생긴다."""
    report = analyze(text, use_llm=use_llm)
    index = get_index()
    clause_by_id = {c.id: c for c in report.clauses}

    findings = []
    for f in report.findings:
        c = clause_by_id.get(f.clause_id)
        art = index.get(f.law_id)
        d = f.to_dict()
        d["severity_label"] = SEVERITY_LABEL[f.severity]
        d["source_label"] = {"rule": "룰 검사", "model": "학습 모델", "llm": "LLM 판정"}.get(f.source, f.source)
        d["clause_title"] = (
            f"제{c.article_no}조 {c.title}" if c and c.article_no else (c.title if c else "")
        )
        d["clause_text"] = c.text if c else ""
        d["law_label"] = f"{art.law} {art.article}({art.title})" if art else ""
        findings.append(d)

    return {
        "meta": report.meta,
        "clauses": [c.to_dict() for c in report.clauses],
        "findings": findings,
        "dropped": [
            {"clause_id": d.clause_id, "claimed_law_id": d.law_id, "claimed_quote": d.quote}
            for d in report.dropped
        ],
    }


@app.get("/health")
def health():
    idx = get_index()
    return jsonify(
        ok=True,
        law_articles=len(idx.articles),
        unverified=len(idx.unverified),
        min_wage={"year": MIN_WAGE_YEAR, "hourly": MIN_WAGE_HOURLY},
    )


@app.get("/api/laws")
def api_laws():
    return jsonify([a.to_dict() for a in get_index().articles])


@app.post("/api/analyze")
def api_analyze():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify(error="text 가 비어 있습니다"), 400
    use_llm = bool(body.get("use_llm", False))
    return jsonify(build_payload(text, use_llm))


@app.route("/", methods=["GET", "POST"])
def index():
    idx = get_index()
    ctx = {
        "min_wage": MIN_WAGE_HOURLY,
        "min_wage_year": MIN_WAGE_YEAR,
        "law_count": len(idx.articles),
        "unverified": len(idx.unverified),
        "text": "",
        "result": None,
    }
    if request.method == "POST":
        text = (request.form.get("text") or "").strip()
        use_llm = request.form.get("use_llm") == "on"
        ctx["text"] = text
        if text:
            ctx["result"] = build_payload(text, use_llm)
    return render_template("index.html", **ctx)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
