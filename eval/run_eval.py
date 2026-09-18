"""평가 스크립트 — 발표에 박을 숫자를 만드는 파일.

    python -m eval.run_eval              # 룰 + LLM
    python -m eval.run_eval --no-llm     # 룰만 (키 없이 실행 가능)

출력 지표:
    재현율(recall)   심어둔 독소조항 중 몇 개를 잡았는가
    정밀도(precision) 잡았다고 한 것 중 몇 개가 진짜인가
    오탐(false positive) 정상 조항을 문제라고 한 건수
    게이트 차단        모델이 근거를 지어내 걸러진 건수

TP 기준: (조 번호, 근거 법조문 id)가 둘 다 일치할 때만 정답 처리한다.
근거 조문이 틀리면 결론이 맞아도 오답이다 — 이 프로젝트의 주장과 일관되게.
"""
import argparse
import json
from pathlib import Path

from core.pipeline import analyze

DATA = Path(__file__).resolve().parent / "dataset.json"


def run(use_llm: bool, verbose: bool, use_classifier: bool = True):
    cases = json.loads(DATA.read_text(encoding="utf-8"))["cases"]
    tp = fp = fn = gate_blocked = 0
    rows = []

    for case in cases:
        report = analyze(case["text"], use_llm=use_llm, use_classifier=use_classifier)
        gate_blocked += len(report.dropped)
        clause_no = {c.id: c.article_no for c in report.clauses}

        predicted = {(clause_no.get(f.clause_id), f.law_id) for f in report.findings if f.severity != "ok"}
        expected = {(l["article_no"], l["law_id"]) for l in case["labels"]}

        hit = predicted & expected
        miss = expected - predicted
        extra = predicted - expected

        tp += len(hit)
        fn += len(miss)
        fp += len(extra)

        rows.append((case["id"], case["name"], len(hit), len(miss), len(extra)))
        if verbose:
            print(f"\n[{case['id']}] {case['name']}")
            for a, l in sorted(hit, key=lambda x: (x[0] or 0)):
                print(f"  잡음   제{a}조 · {l}")
            for a, l in sorted(miss, key=lambda x: (x[0] or 0)):
                print(f"  놓침   제{a}조 · {l}")
            for a, l in sorted(extra, key=lambda x: (x[0] or 0)):
                print(f"  오탐   제{a}조 · {l}")

    recall = tp / (tp + fn) if tp + fn else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0

    print("\n" + "=" * 64)
    print(f"{'케이스':<10}{'이름':<34}{'잡음':>5}{'놓침':>6}{'오탐':>6}")
    print("-" * 64)
    for cid, name, h, m, e in rows:
        print(f"{cid:<10}{name[:32]:<34}{h:>5}{m:>6}{e:>6}")
    print("=" * 64)
    print(f"구성          : 룰{' + 분류기' if use_classifier else ''}{' + LLM' if use_llm else ''}")
    print(f"재현율 recall : {recall:.1%}   ({tp}/{tp + fn})")
    print(f"정밀도 prec.  : {precision:.1%}   ({tp}/{tp + fp})")
    print(f"F1            : {f1:.1%}")
    print(f"게이트 차단   : {gate_blocked}건")
    print("=" * 64)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--no-classifier", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()
    run(use_llm=not a.no_llm, verbose=a.verbose, use_classifier=not a.no_classifier)
