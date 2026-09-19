"""조항 유형 분류기를 학습해 data/clause_clf.joblib 로 저장한다.

    python scripts/train_classifier.py

학습 데이터는 두 곳에서 온다.
  1. data/train_clauses.py  — 사람이 직접 쓴 독소조항/정상조항 문장
  2. data/laws.json         — 법령 원문 문장을 NORMAL 로 자동 편입

2번이 중요하다. 법을 그대로 베낀 계약서 조항은 적법하므로 NORMAL 이 맞고,
이걸 넣기 전에는 '휴게시간은 근로자가 자유롭게 이용할 수 있다'(제54조 원문)를
휴게시간 위반으로 오판했다. 넣은 뒤 그 오탐이 사라졌다.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.svm import LinearSVC  # noqa: E402

from data.train_clauses import rows  # noqa: E402
from config import CLASSIFIER_PATH  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def law_normals() -> list[str]:
    laws = json.loads((ROOT / "data" / "laws.json").read_text(encoding="utf-8"))
    out = []
    for a in laws:
        for s in re.split(r"(?<=다\.)\s*", a["text"]):
            s = s.strip()
            if 15 <= len(s) <= 120 and not s.startswith("다만"):
                out.append(s)
    return out


def build():
    # char_wb n-gram: 한국어는 형태소 분석기 없이도 문자 n-gram 이 잘 통한다.
    # 배포 환경마다 깨지는 형태소 분석기 의존성을 피할 수 있다.
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1, sublinear_tf=True),
        CalibratedClassifierCV(LinearSVC(C=1.0, class_weight="balanced"), cv=3),
    )


def main():
    data = [(r["text"], r["label"]) for r in rows()]
    extra = law_normals()
    data += [(s, "NORMAL") for s in extra]

    X = [t for t, _ in data]
    y = [l for _, l in data]

    from collections import Counter

    c = Counter(y)
    ver = "최신 (426문장)" if len(X) - len(extra) >= 400 else f"구버전 ({len(X) - len(extra)}문장) — 최신 zip 으로 덮어쓰세요"
    print(f"학습 데이터 {len(X)}문장 / {len(c)}개 클래스 (법령 원문 NORMAL {len(extra)}문장 포함)")
    print(f"데이터 버전: {ver}")
    for k, v in c.most_common():
        print(f"  {k:<28} {v}")

    n_splits = min(3, min(c.values()))
    if n_splits >= 2:
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
        s = cross_val_score(build(), X, y, cv=cv, scoring="accuracy")
        print(f"\n{n_splits}-fold 교차검증 정확도: {s.mean():.1%} (±{s.std():.1%})")
        if s.mean() < 0.70:
            print("  [!] 70% 미만입니다. 클래스당 문장 수를 늘리세요. 가장 효과 큰 작업입니다.")

    model = build().fit(X, y)
    out = ROOT / CLASSIFIER_PATH
    out.parent.mkdir(parents=True, exist_ok=True)

    import joblib

    joblib.dump(model, out, compress=3)
    print(f"\n저장: {out}  ({out.stat().st_size / 1024:.0f} KB)")
    print("확인: python -m eval.run_eval --no-llm -v")


if __name__ == "__main__":
    main()
