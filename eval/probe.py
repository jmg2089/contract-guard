"""적대적 테스트 — 시스템이 뚫리는 지점을 일부러 찾는다.

dataset.json 이 '잡아야 할 것을 잡는가'를 보는 시험지라면,
probe.py 는 '속일 수 있는가'를 보는 시험지다. 둘은 목적이 다르다.

    python -m eval.probe            # 룰 + LLM
    python -m eval.probe --no-llm   # 룰만

새 실패 사례를 발견하면 여기에 추가한다. 케이스가 늘어날수록 숫자가 정직해진다.

경고: 여기 있는 케이스에 맞춰 룰을 고치면 다시 과적합이다.
     고친 뒤에는 반드시 '새로운' 케이스를 추가해서 다시 깨보라.
"""
import argparse

from core.pipeline import analyze

PROBES = [
    # (이름, 계약서 텍스트, 잡아야 하는가, 메모)
    ("교육비 반환 약정",
     "제5조(교육비) 근로자가 입사일로부터 2년 이내에 퇴사하는 경우 회사가 지출한 교육비 5,000,000원을 전액 반환하여야 한다.",
     True, "'위약금'이라는 단어 없이 같은 효과를 내는 실무 표현"),

    ("월급제 최저임금 미달",
     "제3조(임금) 근로자의 임금은 월 1,800,000원으로 하며, 소정근로시간은 1주 40시간으로 한다.",
     True, "시급 표기가 없어 단순 숫자 비교로는 안 잡힌다"),

    ("연차 시기지정권 박탈",
     "제6조(연차) 연차 유급휴가 15일을 부여하되, 사용 시기는 전적으로 회사가 지정하는 날로 한다.",
     True, "일수는 합법인데 실질이 불리한 경우"),

    ("퇴사 제한 (사실상 강제근로)",
     "제9조(퇴직) 근로자는 회사의 사전 서면 동의 없이 퇴사할 수 없다.",
     True, "금전 조항이 아니라 자유 제한"),

    ("부정 표현 — 근로자에게 유리한 조항",
     "제5조(손해배상) 회사는 근로자의 단순 과실에 대하여 위약금을 청구하지 아니한다.",
     False, "'위약금' 단어만 보면 오탐한다. 한국어 부정 활용형 처리 시험"),

    ("면제 표현",
     "제7조(교육비) 회사는 근로자에게 교육비 반환을 요구할 수 없다.",
     False, "위와 같은 유형의 다른 활용형"),

    ("번호 항목형 계약서",
     "1. 임금: 시급 9,000원\n2. 근로시간: 1일 10시간\n3. 퇴사 시 위약금 200만원을 배상한다",
     True, "'제N조' 형식이 아닐 때 조항 분할이 되는가"),

    ("표 형식 계약서",
     "임 금 | 시급 9,000원\n근로시간 | 1일 10시간\n위약금 | 중도퇴사 시 200만원",
     True, "실제 표준계약서 PDF에서 흔한 형태"),

    ("정상 계약서 (대조군)",
     "제2조(임금) 근로자의 임금은 월 2,800,000원으로 하며 매월 25일에 통화로 전액 지급한다.\n\n"
     "제3조(근로시간) 소정근로시간은 1일 8시간, 1주 40시간으로 하며 휴게시간 1시간을 부여한다.",
     False, "아무 문제 없는 계약서에 빨간 줄을 긋지 않는가"),
]


def run(use_llm: bool):
    miss = false_alarm = ok = 0
    print("=" * 76)
    for name, text, should_catch, memo in PROBES:
        report = analyze(text, use_llm=use_llm)
        found = [f for f in report.findings if f.severity != "ok"]
        verdict = "통과"
        if should_catch and not found:
            verdict, miss = "놓침", miss + 1
        elif not should_catch and found:
            verdict, false_alarm = "오탐", false_alarm + 1
        else:
            ok += 1

        mark = {"통과": " ", "놓침": "!", "오탐": "!"}[verdict]
        print(f"\n{mark} [{verdict}] {name}   ({report.meta['clause_count']}개 조항으로 분할)")
        print(f"      {memo}")
        for f in found:
            print(f"      -> [{f.severity}] {f.law_id}  ({f.source})")
        if not found:
            print("      -> (탐지 없음)")

    print("\n" + "=" * 76)
    print(f"통과 {ok} / 놓침 {miss} / 오탐 {false_alarm}   (전체 {len(PROBES)}건)")
    print("=" * 76)
    if miss == 0 and false_alarm == 0:
        print("전부 통과했다면 케이스가 너무 쉬운 것이다. 새 케이스를 추가하라.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--no-llm", action="store_true")
    a = p.parse_args()
    run(use_llm=not a.no_llm)
