"""테스트용 근로계약서 PDF를 만든다. 개인정보는 전부 가상이다.

    python scripts/make_test_pdf.py

마스킹 미리보기를 확인하려면 개인정보가 들어 있는 계약서가 필요한데,
실제 계약서를 쓸 수는 없다. 그래서 가짜 인물로 한 장 만든다.
이름·주소·전화·주민번호·계좌·이메일이 모두 들어 있고, 임금과 근로시간에는
일부러 위반 소지를 넣어 두었다. 마스킹과 판정을 한 번에 확인할 수 있다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "samples" / "test_with_privacy.pdf"

LINES = [
    ("title", "표 준 근 로 계 약 서"),
    ("", ""),
    ("", '주식회사 한빛테크(이하 "사업주")와 김현수(이하 "근로자")는 다음과 같이'),
    ("", "근로계약을 체결한다."),
    ("", ""),
    ("", "1. 근로개시일 : 2026년 10월 1일부터"),
    ("", "2. 근 무 장 소 : 부산광역시 해운대구 센텀중앙로 55, 12층"),
    ("", "3. 업무의 내용 : 데이터 분석 및 관련 지원 업무"),
    ("", "4. 소정근로시간 : 09시 00분부터 21시 00분까지 (휴게시간 12:00~13:00)"),
    ("", "5. 근무일/휴일 : 매주 6일(월~토) 근무"),
    ("", "6. 임 금 : 월 1,600,000원,  임금지급일 : 매월 25일"),
    ("", "   연장근로수당은 별도로 지급하지 아니한다."),
    ("", "7. 수습기간 : 6개월로 하며 이 기간 중 임금의 80%를 지급한다."),
    ("", "8. 퇴직금 : 매월 임금에 포함하여 지급한 것으로 본다."),
    ("", "9. 손해배상 : 근로자가 계약기간 중 퇴사하는 경우 위약금 300만원을"),
    ("", "   회사에 배상하여야 한다."),
    ("", ""),
    ("", "                          2026년 9월 19일"),
    ("", ""),
    ("", "(사업주)  사업체명 : 주식회사 한빛테크      전화 : 051-747-0000"),
    ("", "          주   소 : 부산광역시 해운대구 센텀중앙로 55"),
    ("", "          대 표 자 : 박정호                (서명)"),
    ("", ""),
    ("", "(근로자)  주   소 : 부산광역시 수영구 광안로 12, 301호"),
    ("", "          연 락 처 : 010-1234-5678"),
    ("", "          생 년 월 일 : 1997. 06. 17"),
    ("", "          주민등록번호 : 970617-1234567"),
    ("", "          이 메 일 : hyunsoo@example.com"),
    ("", "          급여계좌 : 국민은행 123456-01-234567"),
    ("", "          성   명 : 김 현 수               (서명)"),
]


def main():
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    W, H = A4
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=A4)

    y = H - 70
    for kind, text in LINES:
        if kind == "title":
            c.setFont("HYSMyeongJo-Medium", 14)
            c.drawString(190, y, text)
            c.setFont("HYSMyeongJo-Medium", 10)
        elif text:
            c.drawString(55, y, text)
        y -= 21
    c.save()
    print(f"만들었습니다: {OUT}")
    print("이 파일을 화면에서 업로드하면 다음을 한 번에 확인할 수 있습니다.")
    print("  - 이름·주소·전화·주민번호·계좌·이메일이 검은 박스로 덮이는가")
    print("  - 임금 1,600,000원과 근로시간 09:00~21:00 은 그대로 남는가")
    print("  - 최저임금 미달, 연장근로수당 배제, 퇴직금 분할, 위약금 조항이 잡히는가")


if __name__ == "__main__":
    sys.exit(main())
