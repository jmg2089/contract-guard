"""문서 종류 분류기를 학습해 data/doctype_clf.joblib 로 저장한다.

    python scripts/train_doctype.py

조항 분류기와 같은 파이프라인을 쓴다(char_wb n-gram + LinearSVC + 확률 보정).
이미 검증된 구성이고, 한국어에서 형태소 분석기 없이 동작한다는 장점이 그대로 온다.
배포 환경마다 깨지는 형태소 분석기 의존성을 피할 수 있다.

학습은 문장 단위, 판정은 문서 단위다. 자세한 이유는 data/train_doctype.py 참고.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter  # noqa: E402

from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.svm import LinearSVC  # noqa: E402

from data.train_doctype import DATASET  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "doctype_clf.joblib"


def build():
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1, sublinear_tf=True),
        CalibratedClassifierCV(LinearSVC(C=1.0, class_weight="balanced"), cv=3),
    )


def main():
    X = [t for t, _ in DATASET]
    y = [l for _, l in DATASET]
    c = Counter(y)

    print(f"학습 데이터 {len(X)}문장 / {len(c)}개 클래스")
    for k, v in c.most_common():
        print(f"  {k:<12} {v}")

    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=0)
    s = cross_val_score(build(), X, y, cv=cv, scoring="accuracy")
    print(f"\n3-fold 교차검증 정확도: {s.mean():.1%} (±{s.std():.1%})")

    model = build().fit(X, y)

    import joblib

    OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, OUT, compress=3)
    print(f"저장: {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
    print("확인: python -m eval.doctype_eval")


if __name__ == "__main__":
    main()
