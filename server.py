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

from flask import Flask, Response, jsonify, render_template, request

from core.pipeline import analyze
from core import classify as clf
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
    from analyzer import analyze_contract

    return analyze_contract(text, use_llm=use_llm) or {}


def _unused_build_payload(text: str, use_llm: bool) -> dict:
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
    """배포 후 상태 확인용. 분류기가 실제로 로드됐는지가 핵심 지표다.

    classifier.loaded 가 false 면 빌드 때 학습이 실패한 것이다.
    그 경우에도 서비스는 살아 있지만 룰 검사 15개만으로 동작한다(재현율 86.7%).
    """
    idx = get_index()
    model = clf.load()
    return jsonify(
        ok=True,
        law_articles=len(idx.articles),
        unverified=len(idx.unverified),
        min_wage={"year": MIN_WAGE_YEAR, "hourly": MIN_WAGE_HOURLY},
        rules=len(__import__("core.rules", fromlist=["RULES"]).RULES),
        classifier={
            "loaded": model is not None,
            "classes": (len(model.classes_) if model is not None else 0),
        },
    )


@app.get("/api/samples")
def api_samples():
    """샘플 계약서 목록. 방문자가 붙여넣을 계약서가 없을 때 쓴다."""
    from data.samples import listing

    return jsonify(listing())


@app.get("/api/samples/<sample_id>")
def api_sample(sample_id):
    from data.samples import get

    s = get(sample_id)
    if s is None:
        return jsonify(error="없는 샘플입니다"), 404
    return jsonify(s)


@app.post("/api/revised")
def api_revised():
    """검토 의견서를 마크다운 파일로 내려준다."""
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify(error="text 가 비어 있습니다"), 400
    payload = build_payload(text, False)
    return Response(
        payload["revised_markdown"],
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="contract-review.md"'},
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


def _samples_listing():
    from data.samples import listing

    return listing()


def _sample_texts():
    from data.samples import SAMPLES

    return {s["id"]: s["text"] for s in SAMPLES}


@app.post("/download")
def download_review():
    """검토 의견서를 마크다운 파일로 내려준다. 사용자가 실제로 들고 갈 결과물."""
    text = (request.form.get("text") or "").strip()
    if not text:
        return jsonify(error="text 가 비어 있습니다"), 400
    md = build_payload(text, False).get("revised_markdown", "")
    return Response(
        md,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="contract-review.md"'},
    )


MAX_UPLOAD_MB = 8
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


@app.post("/api/extract")
def api_extract():
    """업로드된 PDF에서 텍스트만 뽑아 돌려준다. 프론트가 입력창에 채워 넣는 용도."""
    import io

    from core.segment import pdf_diagnosis

    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify(ok=False, message="파일이 없습니다."), 400
    if not f.filename.lower().endswith(".pdf"):
        return jsonify(
            ok=False,
            reason="not_pdf",
            message="PDF 파일만 읽을 수 있습니다. 이미지나 캡처 화면은 글자를 직접 읽을 수 없으니 "
                    "계약서 내용을 복사해서 붙여넣어 주세요.",
        ), 400
    return jsonify(pdf_diagnosis(io.BytesIO(f.read())))


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
        "samples": _samples_listing(),
        "sample_texts": _sample_texts(),
        "upload_message": None,
        "upload_ok": None,
    }
    if request.method == "POST":
        text = (request.form.get("text") or "").strip()
        use_llm = request.form.get("use_llm") == "on"

        # PDF가 올라왔으면 거기서 글자를 뽑아 텍스트 입력을 대신한다
        f = request.files.get("file")
        if f is not None and f.filename:
            import io

            from core.segment import pdf_diagnosis

            if not f.filename.lower().endswith(".pdf"):
                ctx["upload_message"] = (
                    "PDF 파일만 읽을 수 있습니다. 이미지나 캡처 화면은 글자를 직접 읽을 수 없으니 "
                    "계약서 내용을 복사해서 아래 입력창에 붙여넣어 주세요."
                )
            else:
                diag = pdf_diagnosis(io.BytesIO(f.read()))
                ctx["upload_message"] = diag["message"]
                ctx["upload_ok"] = diag["ok"]
                if diag["ok"]:
                    text = diag["text"]

        ctx["text"] = text
        if text:
            ctx["result"] = build_payload(text, use_llm)
    return render_template("index.html", **ctx)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
