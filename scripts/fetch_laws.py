"""법제처 국가법령정보 오픈API로 조문 원문을 받아 data/laws.json 을 덮어쓴다.

인용 게이트는 quote 가 조문 원문의 부분문자열인지를 검사한다.
따라서 data/laws.json 의 text 가 공식 원문이 아니면 게이트 전체가 무의미해진다.
토요일 오전 안에 반드시 한 번 실행해서 verified=true 로 만들 것.

사용:
    LAW_OC=<법제처에 등록한 이메일 ID> python scripts/fetch_laws.py

OC 발급: https://open.law.go.kr 회원가입 후 즉시 발급(별도 심사 없음).
발급이 막히면 법제처 웹에서 조문을 복사해 data/laws.json 을 손으로 채우고
verified 를 true 로 바꾸는 것도 허용한다 — 중요한 건 '원문과 글자가 같은지'다.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OC = os.getenv("LAW_OC", "")
OUT = Path(__file__).resolve().parent.parent / "data" / "laws.json"
BASE = "http://www.law.go.kr/DRF/lawService.do"

TARGETS = {
    "근로기준법": ["제7조", "제17조", "제19조", "제20조", "제21조", "제23조", "제26조",
                "제36조", "제43조", "제50조", "제53조", "제54조", "제55조", "제56조", "제60조"],
    "최저임금법": ["제6조"],
    "근로자퇴직급여 보장법": ["제8조"],
    "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률": ["제11조"],
}


def fetch(law_name: str) -> dict:
    q = urllib.parse.urlencode({"OC": OC, "target": "law", "type": "JSON", "LM": law_name})
    with urllib.request.urlopen(f"{BASE}?{q}", timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    s = s.replace("　", " ")
    return re.sub(r"\s+", " ", s).strip()


def main():
    if not OC:
        sys.exit("LAW_OC 환경변수가 필요합니다. https://open.law.go.kr 에서 발급하세요.")

    articles = []
    for law_name, wanted in TARGETS.items():
        data = fetch(law_name)
        units = data.get("법령", {}).get("조문", {}).get("조문단위", [])
        if isinstance(units, dict):
            units = [units]
        for u in units:
            no = clean(u.get("조문번호", ""))
            key = f"제{no}조"
            if key not in wanted:
                continue
            body = clean(u.get("조문내용", ""))
            for h in (u.get("항") or []):
                if isinstance(h, dict):
                    body += " " + clean(h.get("항내용", ""))
            body = re.sub(rf"^{re.escape(key)}\s*\([^)]*\)\s*", "", body)
            articles.append({
                "id": f"{law_name.split()[0]}-{key}",
                "law": law_name,
                "article": key,
                "title": clean(u.get("조문제목", "")),
                "text": body,
                "verified": True,
            })
        print(f"{law_name}: {sum(1 for a in articles if a['law'] == law_name)}개")

    OUT.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(articles)}개 조문을 {OUT} 에 저장했습니다.")


if __name__ == "__main__":
    main()
