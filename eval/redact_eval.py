"""PDF 마스킹 미리보기 평가.

확인해야 할 것이 두 가지인데, 무게가 다르다.

  1) 개인정보가 실제로 덮였는가
  2) 판정에 쓰이는 값이 살아남았는가   <- 이쪽이 더 중요하다

2번이 더 중요한 이유는 분명하다. 개인정보를 하나 놓치면 그 한 건이 문제지만,
임금이나 근로시간을 덮어 버리면 서비스 전체가 죽는다. 최저임금 위반을 찾는 도구가
임금 액수를 지워 놓고 "위반 없음"을 돌려주면, 개인정보를 지키려다 사용자를 더
위험하게 만든 것이 된다.

그래서 이 평가는 렌더링된 그림이 아니라 **좌표**를 본다. 그림을 눈으로 보는 것은
사람이 할 일이고, 기계는 '어느 글자가 박스 안에 들어갔는가'를 정확히 셀 수 있다.

    python -m eval.redact_eval
"""
import io
import sys
import tempfile
from pathlib import Path

import pdfplumber

from core.pdf_redact import _boxes_for_spans, _line_text_and_map, _page_words
from core.privacy import find_spans

# 이 값들은 반드시 가려져야 한다
MUST_HIDE = [
    "주식회사 한빛테크", "박정호", "김현수",
    "부산광역시 해운대구 센텀중앙로 55", "부산광역시 수영구 광안로 12",
    "010-1234-5678", "051-747-0000", "1997. 06. 17",
    "970617-1234567", "hyunsoo@example.com",
]

# 이 값들은 절대 가려지면 안 된다. 하나라도 덮이면 판정이 죽는다.
MUST_KEEP = [
    "2,800,000", "09시 00분", "18시 00분", "2026년 10월 1일",
    "매월 25일", "데이터 분석", "근로기준법", "12:00", "13:00",
]


def build_pdf(path: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    W, H = A4
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("HYSMyeongJo-Medium", 13)
    c.drawString(200, H - 60, "표 준 근 로 계 약 서")
    c.setFont("HYSMyeongJo-Medium", 10)
    lines = [
        '주식회사 한빛테크(이하 "사업주")와 김현수(이하 "근로자")는 다음과 같이 근로계약을 체결한다.',
        "",
        "1. 근로개시일 : 2026년 10월 1일부터",
        "2. 근 무 장 소 : 부산광역시 해운대구 센텀중앙로 55, 12층",
        "3. 업무의 내용 : 데이터 분석 및 관련 지원 업무",
        "4. 소정근로시간 : 09시 00분부터 18시 00분까지 (휴게시간 12:00~13:00)",
        "5. 근무일/휴일 : 매주 5일(월~금) 근무, 주휴일 매주 일요일",
        "6. 임 금 : 월 2,800,000원,  임금지급일 : 매월 25일",
        "7. 연차유급휴가 : 근로기준법에서 정하는 바에 따라 부여함",
        "",
        "(사업주)  사업체명 : 주식회사 한빛테크      전화 : 051-747-0000",
        "          주   소 : 부산광역시 해운대구 센텀중앙로 55",
        "          대 표 자 : 박정호                (서명)",
        "",
        "(근로자)  주   소 : 부산광역시 수영구 광안로 12, 301호",
        "          연 락 처 : 010-1234-5678",
        "          생 년 월 일 : 1997. 06. 17",
        "          주민등록번호 : 970617-1234567",
        "          이메일 : hyunsoo@example.com",
        "          성   명 : 김 현 수               (서명)",
    ]
    y = H - 100
    for line in lines:
        if line:
            c.drawString(55, y, line)
        y -= 22
    c.save()


def _covered_words(path: str) -> tuple[str, str]:
    """박스에 덮인 글자와 살아남은 글자를 읽기 순서 그대로 나눠 돌려준다.

    단어의 중심점이 어느 박스 안에 들어가면 덮인 것으로 본다.
    가장자리만 스친 경우를 덮였다고 세면 실제보다 후하게 나온다.

    순서를 지키는 것이 중요하다. 단어를 집합으로 모아 놓고 '09시 00분'을 찾으면
    글자는 다 남아 있는데도 못 찾는다. 실제로 이 평가를 처음 돌렸을 때 그 이유로
    멀쩡한 줄 다섯 개가 '덮였다'고 나왔다. 도구가 아니라 시험이 틀린 경우였다.
    """
    hidden, visible = [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = _page_words(page)
            text, owner, ordered = _line_text_and_map(words)
            boxes = _boxes_for_spans(text, owner, ordered, find_spans(text))
            for w in ordered:
                cx = (w["x0"] + w["x1"]) / 2
                cy = (w["top"] + w["bottom"]) / 2
                inside = any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in boxes)
                (hidden if inside else visible).append(w["text"])
    return " ".join(hidden), " ".join(visible)


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / "contract.pdf"
    build_pdf(str(tmp))
    hidden_join, visible_join = _covered_words(str(tmp))
    fail = []

    def present(needle: str, haystack: str) -> bool:
        """공백을 무시하고 포함 여부를 본다.

        PDF 추출은 '09시 00분'을 '09시'+'00분부터' 처럼 쪼개 놓으므로
        공백을 그대로 두고 비교하면 멀쩡한 글자도 못 찾는다."""
        return needle.replace(" ", "") in haystack.replace(" ", "")

    print("=" * 72)
    print("가려져야 하는 개인정보")
    print("-" * 72)
    for target in MUST_HIDE:
        ok = present(target, hidden_join)
        print(f"  [{'가림' if ok else '노출'}] {target}")
        if not ok:
            fail.append(f"안 가려짐: {target}")

    print()
    print("=" * 72)
    print("살아남아야 하는 판정 정보 — 여기가 더 중요하다")
    print("-" * 72)
    for target in MUST_KEEP:
        in_visible = present(target, visible_join)
        print(f"  [{'유지' if in_visible else '삭제됨'}] {target}")
        if not in_visible:
            fail.append(f"덮이면 안 되는데 덮임: {target}")

    print("=" * 72)
    if fail:
        for f in fail:
            print("  [실패]", f)
        return 1
    print(f"  전부 통과. (가린 글자 {len(hidden_join)}자 / 남긴 글자 {len(visible_join)}자)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
