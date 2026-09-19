"""LLM 키가 제대로 연결됐는지 5초 만에 확인한다.

    python scripts/check_llm.py

세 가지를 순서대로 검사한다.
  1. API 호출이 되는가
  2. 모델이 JSON 형식을 지키는가
  3. 인용 게이트가 실제로 작동하는가  ← 이 프로젝트의 핵심

3번이 중요하다. dummy 모드에서는 게이트가 한 번도 일하지 않기 때문에,
실제 키를 붙이기 전까지는 '할루시네이션을 막았다'를 증명할 수 없다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from config import LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL, LLM_API_KEY  # noqa: E402
from core.llm import complete, parse_json  # noqa: E402
from core.retrieve import get_index  # noqa: E402
from core.judge import judge_clause, verify_citation  # noqa: E402
from core.types import Clause, Finding  # noqa: E402

CLAUSE = Clause(
    id="c1", article_no=5, title="손해배상",
    text="제5조(손해배상) 근로자가 계약기간 만료 전에 퇴사하는 경우 위약금으로 금 3,000,000원을 회사에 지급한다.",
)


def main():
    print("=" * 66)
    print(f"  provider : {LLM_PROVIDER}")
    print(f"  model    : {LLM_MODEL}")
    print(f"  base_url : {LLM_BASE_URL or '(기본값)'}")
    print(f"  api_key  : {'설정됨 (' + LLM_API_KEY[:6] + '…)' if LLM_API_KEY else '없음'}")
    print("=" * 66)

    if LLM_PROVIDER == "dummy":
        print("\n[!] dummy 모드입니다. .env 에 키를 넣고 LLM_PROVIDER 를 바꾸세요.")
        print("    이 상태로는 인용 게이트가 한 번도 작동하지 않습니다.")
        return 1

    # 1. 호출
    print("\n[1/3] API 호출...")
    try:
        raw = complete("너는 JSON만 출력한다.", '{"ping":1} 을 그대로 돌려줘.')
    except Exception as e:
        print(f"  실패: {type(e).__name__}: {e}")
        print("\n  흔한 원인: 키 오타 / base_url 오타 / 모델명이 그 공급자에 없음")
        return 1
    print(f"  응답 {len(raw)}자 수신")

    # 2. JSON 준수
    print("\n[2/3] JSON 형식 준수...")
    print("  파싱 성공" if parse_json(raw) else "  파싱 실패 — 프롬프트를 더 강하게 해야 합니다")

    # 3. 실제 판정 + 게이트
    print("\n[3/3] 실제 조항 판정 + 인용 게이트...")
    index = get_index()
    laws = index.search(CLAUSE.text)
    print(f"  검색된 조문 {len(laws)}개: {', '.join(a.id for a in laws)}")

    kept, dropped = judge_clause(CLAUSE, laws)
    if dropped is not None:
        print("  게이트 차단됨 — 모델이 근거를 지어냈거나 인용이 원문과 달랐습니다")
        print(f"    주장한 근거 : {dropped.law_id or '(없음)'}")
        print(f"    주장한 인용 : {dropped.quote[:70] or '(없음)'}")
        print("  이건 실패가 아니라 게이트가 제 일을 한 것입니다.")
    elif kept.severity == "ok":
        print("  판정: 이상 없음 (이 조항은 위반이 나와야 정상이므로 프롬프트 점검 필요)")
    else:
        print(f"  판정: {kept.severity}")
        print(f"    근거 : {kept.law_id}")
        print(f"    인용 : {kept.quote[:70]}")
        print("  게이트 통과 — 인용문이 실제 조문 원문과 일치합니다")

    # 게이트가 가짜 인용을 실제로 막는지 역방향 확인
    fake = Finding(
        clause_id="c1", severity="violation", law_id="근로기준법-제20조",
        quote="사용자는 근로자에게 위약금을 3배로 청구할 수 있다.", reason="지어낸 인용",
    )
    blocked = not verify_citation(fake, {a.id: a for a in laws})
    print(f"\n  지어낸 인용문 차단 확인: {'정상 차단됨' if blocked else '차단 실패 — 게이트 버그'}")

    print("\n" + "=" * 66)
    print("  이제 python -m eval.run_eval -v 로 LLM 포함 숫자를 뽑으세요.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
