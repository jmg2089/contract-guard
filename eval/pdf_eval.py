"""PDF 추출 계층 평가.

계약서 검토 도구에서 PDF 추출은 '부가 기능'이 아니다. 여기서 글자가 뒤섞이면
뒤에 붙은 룰과 분류기가 아무리 정확해도 결과가 틀린다. 그래서 따로 평가한다.

시험 대상은 실제로 자주 들어오는 세 가지 편집 형태다.

  1) 1단 줄글      — 가장 흔하다. 어떤 엔진이든 읽는다.
  2) 표 형식       — '항목 | 내용' 표. 기본 추출기가 칸을 가로질러 읽기 쉽다.
  3) 2단 편집      — 기본 추출기가 전부 실패한다. 왼쪽 한 줄, 오른쪽 한 줄을
                     번갈아 읽어 제1조와 제4조가 한 문장으로 붙는다.

각 PDF를 엔진별로 뽑아, 조 번호가 오름차순으로 나오는지(order)와
최종 탐지 건수를 비교한다. 자동 선택이 제일 나은 엔진을 골랐는지 확인한다.

    python -m eval.pdf_eval
"""
import io
import sys

from analyzer import analyze_contract
from core.pdftext import ENGINES, extract_best, order_score

# 세 형태 모두 같은 위반 3건을 담는다. 편집 형태만 다르다.
VIOLATIONS = [
    ("제1조(근로계약기간)", "2026년 3월 1일부터 1년간으로 한다."),
    ("제2조(임금)", "월 급여는 1,600,000원으로 하며 수습 3개월간은 80%를 지급한다."),
    ("제3조(근로시간)", "09:00부터 20:00까지 근무하며 연장근로수당은 지급하지 아니한다."),
    ("제4조(연차휴가)", "입사 1년 미만인 자에게는 연차유급휴가를 부여하지 아니한다."),
    ("제5조(퇴직금)", "퇴직금은 월 급여에 포함하여 매월 분할 지급한다."),
    ("제6조(손해배상)", "근로자가 계약기간 중 퇴사할 경우 위약금 300만원을 회사에 지급한다."),
]


def _canvas(path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("HYSMyeongJo-Medium", 10)
    return c, A4


def make_plain(path):
    c, (W, H) = _canvas(path)
    y = H - 70
    c.drawString(60, H - 45, "근 로 계 약 서")
    for head, body in VIOLATIONS:
        c.drawString(60, y, f"{head} {body}")
        y -= 26
    c.save()


def make_table(path):
    c, (W, H) = _canvas(path)
    y = H - 70
    c.drawString(60, H - 45, "근 로 계 약 서")
    for head, body in VIOLATIONS:
        label = head.split("(")[1].rstrip(")")
        c.drawString(60, y, label)
        c.drawString(190, y, body)
        y -= 28
    c.save()


def make_two_column(path):
    """왼쪽 단에 제1~3조, 오른쪽 단에 제4~6조. 기본 추출이 무너지는 형태."""
    c, (W, H) = _canvas(path)

    def wrap(text, n=22):
        out, line = [], ""
        for w in text.split():
            if len(line) + len(w) > n:
                out.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        if line:
            out.append(line)
        return out

    left, right = [], []
    for i, (head, body) in enumerate(VIOLATIONS):
        target = left if i < 3 else right
        target.extend([head] + wrap(body) + [""])

    # 줄 단위로 좌·우를 번갈아 그린다. 워드프로세서가 2단을 출력하는 방식이고,
    # 그리는 순서만 보고 읽는 추출기까지 제대로 시험하려면 이렇게 해야 한다.
    y = H - 70
    for i in range(max(len(left), len(right))):
        if i < len(left) and left[i]:
            c.drawString(50, y, left[i])
        if i < len(right) and right[i]:
            c.drawString(320, y, right[i])
        y -= 18
    c.save()


FIXTURES = [
    ("1단 줄글", make_plain),
    ("표 형식", make_table),
    ("2단 편집", make_two_column),
]


def main() -> int:
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    failures = []

    print("=" * 76)
    print(f"{'편집 형태':10} {'엔진':10} {'조 순서':>7} {'글자':>6} {'조항':>5} {'위반':>5}  선택")
    print("-" * 76)

    for label, maker in FIXTURES:
        path = tmp / f"{label}.pdf"
        maker(str(path))
        data = path.read_bytes()
        picked = extract_best(data)

        best_hits = 0
        for name, fn in ENGINES:
            try:
                text = fn(data)
            except Exception as e:
                print(f"{label:10} {name:10}    오류 {type(e).__name__}")
                continue
            if not text:
                print(f"{label:10} {name:10} {'-':>7} {'-':>6} {'-':>5} {'-':>5}   (해당 없음)")
                continue
            r = analyze_contract(text)
            hits = sum(1 for f in r["findings"] if f["severity"] == "violation")
            best_hits = max(best_hits, hits)
            mark = "  <= 자동 선택" if name == picked["engine"] else ""
            print(f"{label:10} {name:10} {order_score(text):>7.2f} {len(text):>6} "
                  f"{len(r['clauses']):>5} {hits:>5}{mark}")

        chosen = analyze_contract(picked["text"])
        got = sum(1 for f in chosen["findings"] if f["severity"] == "violation")
        if got < best_hits:
            failures.append(f"{label}: 자동 선택({picked['engine']}) {got}건 < 최선 {best_hits}건")
        print("-" * 76)

    print("=" * 76)
    if failures:
        for f in failures:
            print("  [실패]", f)
        print("=" * 76)
        return 1
    print("  자동 선택이 모든 편집 형태에서 최선의 엔진을 골랐다.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
