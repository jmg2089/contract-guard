"""환경 점검. 서버를 띄우기 전에 무엇이 빠졌는지 알려준다.

    python scripts/doctor.py

실행이 안 될 때 원인은 대개 셋 중 하나다.
  1) 엉뚱한 폴더에서 돌리고 있다
  2) 파이썬이 두 개라 패키지를 깐 쪽과 실행하는 쪽이 다르다
  3) 분류기 모델을 아직 학습시키지 않았다
이 셋을 한 번에 확인한다.
"""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK, BAD = "  [정상]", "  [문제]"
problems: list[str] = []


def head(t):
    print("\n" + "=" * 62)
    print(t)
    print("-" * 62)


head("1. 실행 위치와 파이썬")
print(f"  프로젝트 폴더 : {ROOT}")
print(f"  현재 작업폴더 : {Path.cwd()}")
print(f"  파이썬        : {sys.executable}")
print(f"  버전          : {sys.version.split()[0]}")
if sys.version_info < (3, 10):
    problems.append("파이썬 3.10 이상이 필요합니다.")
    print(BAD, "파이썬이 너무 낮습니다.")
else:
    print(OK, "파이썬 버전 문제 없음")

head("2. 필요한 파일")
need = [
    "server.py", "analyzer.py",
    "core/privacy.py", "core/pdf_redact.py", "core/mask.py", "core/doctype.py",
    "static/js/mask.js", "static/js/ocr.js",
    "templates/index.html", "templates/privacy.html",
    "data/laws.json",
]
for rel in need:
    p = ROOT / rel
    if p.exists():
        print(OK, rel)
    else:
        print(BAD, rel, "<- 없습니다")
        problems.append(f"{rel} 가 없습니다. 압축을 덜 푼 것입니다.")

head("3. 패키지")
pkgs = [
    ("flask", "웹 서버"),
    ("sklearn", "학습 분류기"),
    ("joblib", "모델 저장"),
    ("rank_bm25", "법령 검색"),
    ("pdfplumber", "PDF 글자·좌표 추출"),
    ("pypdf", "두 번째 PDF 추출 엔진"),
    ("pypdfium2", "PDF 페이지 렌더 (미리보기)"),
    ("PIL", "이미지에 박스 그리기 (미리보기)"),
]
for mod, why in pkgs:
    try:
        importlib.import_module(mod)
        print(OK, f"{mod:12} {why}")
    except Exception:
        print(BAD, f"{mod:12} {why} <- 없습니다")
        problems.append(f"{mod} 가 없습니다. pip install -r requirements.txt")

head("4. 분류기 모델")
for rel, script in [("data/clause_clf.joblib", "scripts/train_classifier.py"),
                    ("data/doctype_clf.joblib", "scripts/train_doctype.py")]:
    p = ROOT / rel
    if p.exists():
        print(OK, f"{rel} ({p.stat().st_size // 1024} KB)")
    else:
        print(BAD, f"{rel} 없음 -> python {script} 를 실행하세요")
        problems.append(f"python {script}")

head("5. 실제로 돌려보기")
try:
    from analyzer import analyze_contract, system_info

    info = system_info()
    print(OK, f"법조문 {info['law_count']}개 · 룰 {info['rule_count']}개 "
              f"· 분류기 {'로드됨' if info['classifier_loaded'] else '없음'}")
    r = analyze_contract(
        "근로계약서\n사용자와 근로자는 근로계약을 체결한다.\n"
        "성명 : 홍길동\n연락처 : 010-1234-5678\n"
        "제1조(임금) 임금은 시급 9,000원으로 한다.\n"
        "제2조(손해배상) 중도 퇴사 시 위약금 300만원을 지급한다.\n"
        "사용자 (인) 근로자 (인)"
    )
    v = sum(1 for f in r["findings"] if f["severity"] == "violation")
    print(OK, f"판정 동작 확인 — 위반 {v}건 탐지")
    print(OK, f"마스킹 동작 확인 — {r['meta']['masked_message'] or '가릴 것 없음'}")
except Exception as e:
    print(BAD, f"판정 중 오류: {type(e).__name__}: {e}")
    problems.append(f"판정 오류: {type(e).__name__}")

try:
    from core.pdf_redact import redact_preview

    sample = ROOT / "static" / "samples" / "official.pdf"
    if sample.exists():
        out = redact_preview(sample.read_bytes())
        if out["ok"]:
            print(OK, f"PDF 미리보기 동작 확인 — {len(out['pages'])}쪽 생성")
        else:
            print(BAD, f"PDF 미리보기 실패: {out.get('message', out.get('reason'))}")
            problems.append("PDF 미리보기가 동작하지 않습니다.")
except Exception as e:
    print(BAD, f"PDF 미리보기 오류: {type(e).__name__}: {e}")
    problems.append(f"미리보기 오류: {type(e).__name__}")

print("\n" + "=" * 62)
if problems:
    print("해결해야 할 것")
    print("-" * 62)
    for p in dict.fromkeys(problems):
        print("  -", p)
    print("=" * 62)
    sys.exit(1)

print("  전부 정상입니다. 아래로 서버를 띄우세요.")
print()
print("    python server.py")
print()
print("  그다음 브라우저에서 http://127.0.0.1:5000 으로 접속하세요.")
print("=" * 62)
