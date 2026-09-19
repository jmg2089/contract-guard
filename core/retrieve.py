"""조항 -> 관련 법조문 검색.

형태소 분석기(kiwi, mecab)는 배포 환경에서 설치가 깨지는 일이 잦다.
어절 + 문자 2-gram 혼합 토크나이저 + BM25 만으로 법령처럼 어휘가 고정된
도메인에서는 충분한 성능이 나온다. 의존성 1개, 모델 다운로드 0.
"""
import json
import re
from pathlib import Path
from rank_bm25 import BM25Okapi

from .types import LawArticle
from config import RETRIEVE_TOP_K

_LAW_PATH = Path(__file__).resolve().parent.parent / "data" / "laws.json"

# 계약서에서 쓰는 말 -> 법령에서 쓰는 말. 어휘 불일치가 검색 실패의 주범이다.
SYNONYMS = {
    "위약금": "위약금 손해배상액 예정",
    "손해배상": "위약금 손해배상액 예정",
    "수습": "수습 최저임금 감액",
    "시급": "최저임금 임금 지급",
    "연봉": "임금 지급 통화 전액",
    "월급": "임금 지급 통화 전액 매월",
    "연차": "연차 유급휴가 출근",
    "휴가": "연차 유급휴가",
    "퇴사": "퇴직 금품 청산",
    "퇴직금": "퇴직금 계속근로기간 평균임금",
    "해고": "해고 정당한 이유 예고 통상임금",
    "야근": "연장근로 가산 통상임금",
    "잔업": "연장근로 가산 통상임금",
    "특근": "휴일근로 가산 통상임금",
    "주말근무": "휴일근로 유급휴일 가산",
    "근무시간": "근로시간 휴게시간 소정근로시간",
    "점심시간": "휴게시간",
    "결혼": "혼인 임신 출산 퇴직 사유",
    "임신": "혼인 임신 출산 퇴직 사유",
    "경업": "근로계약 불이행 위약금",
}


def tokenize(text: str) -> list[str]:
    text = re.sub(r"[^가-힣a-zA-Z0-9]+", " ", text)
    words = [w for w in text.split() if w]
    grams = []
    for w in words:
        if len(w) >= 2:
            grams.extend(w[i : i + 2] for i in range(len(w) - 1))
    return words + grams


def expand(text: str) -> str:
    extra = [v for k, v in SYNONYMS.items() if k in text]
    return text + " " + " ".join(extra)


class LawIndex:
    def __init__(self, path: Path = _LAW_PATH):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.articles = [LawArticle(**a) for a in raw]
        self.by_id = {a.id: a for a in self.articles}
        corpus = [tokenize(f"{a.law} {a.article} {a.title} {a.text}") for a in self.articles]
        self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, k: int = RETRIEVE_TOP_K) -> list[LawArticle]:
        scores = self.bm25.get_scores(tokenize(expand(query)))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self.articles[i] for i in ranked[:k] if scores[i] > 0]

    def get(self, law_id: str) -> LawArticle | None:
        return self.by_id.get(law_id)

    @property
    def unverified(self) -> list[str]:
        return [a.id for a in self.articles if not a.verified]


_index: LawIndex | None = None


def get_index() -> LawIndex:
    global _index
    if _index is None:
        _index = LawIndex()
    return _index
