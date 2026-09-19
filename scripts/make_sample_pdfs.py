"""샘플 계약서를 PDF로 만든다 -> static/samples/*.pdf

왜 필요한가: 실제 사용자는 계약서를 PDF로 들고 있다. 붙여넣기만 지원하면
'우리 서비스는 텍스트만 받는다'는 인상을 준다. 샘플 PDF가 있으면
심사위원이 다운로드 -> 업로드 순서로 PDF 경로까지 직접 확인할 수 있다.

만들어지는 PDF는 텍스트 레이어를 가진다(스캔 이미지가 아니다).
pdfplumber 가 그대로 읽어내므로 업로드 경로 시연에 그대로 쓸 수 있다.

    python scripts/make_sample_pdfs.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from data.samples import SAMPLES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "samples"

# 한글이 들어간 PDF는 CJK 폰트를 등록하지 않으면 네모(tofu)로 깨진다.
# reportlab 에 한국어 CID 폰트가 내장돼 있어 외부 폰트 파일 없이 동작한다.
# 시스템에 TTF 가 있으면 그쪽이 더 예쁘므로 먼저 시도한다.
TTF_CANDIDATES = [
    ("NanumGothic", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    ("MalgunGothic", "C:/Windows/Fonts/malgun.ttf"),
    ("AppleGothic", "/System/Library/Fonts/AppleSDGothicNeo.ttc"),
]
CID_FONT = "HYSMyeongJo-Medium"  # reportlab 내장 한국어 폰트


def register_font() -> str:
    for name, path in TTF_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            return name
        except Exception:
            continue
    pdfmetrics.registerFont(UnicodeCIDFont(CID_FONT))
    return CID_FONT


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """글자 단위 줄바꿈. 한국어는 어절이 길어 단어 단위로만 자르면 넘친다."""
    out = []
    for para in text.split("\n"):
        if not para:
            out.append("")
            continue
        line = ""
        for ch in para:
            if pdfmetrics.stringWidth(line + ch, font, size) > width:
                out.append(line)
                line = ch
            else:
                line += ch
        out.append(line)
    return out


def make_pdf(sample: dict, font: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{sample['id']}.pdf"

    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(sample["name"])
    w, h = A4
    margin = 22 * mm
    size, leading = 10.5, 17
    usable = w - margin * 2

    y = h - margin
    c.setFont(font, size)
    for line in wrap(sample["text"], font, size, usable):
        if y < margin + leading:
            c.showPage()
            c.setFont(font, size)
            y = h - margin
        c.drawString(margin, y, line)
        y -= leading

    c.save()
    return path


def main():
    font = register_font()
    print(f"폰트: {font}\n")
    for s in SAMPLES:
        p = make_pdf(s, font)
        print(f"  {p.relative_to(ROOT)}  ({p.stat().st_size / 1024:.0f} KB)  {s['name']}")

    # 만든 PDF 를 그대로 다시 읽어서 텍스트 레이어가 살아 있는지 확인한다.
    print("\n텍스트 추출 검증")
    try:
        from core.segment import extract_pdf_text

        for s in SAMPLES:
            t = extract_pdf_text(str(OUT / f"{s['id']}.pdf"))
            print(f"  {s['id']:<10} {len(t):>5}자 추출  {'OK' if len(t) > 100 else '실패'}")
    except ImportError:
        print("  pdfplumber 가 없어 건너뜁니다 (pip install pdfplumber)")


if __name__ == "__main__":
    main()
