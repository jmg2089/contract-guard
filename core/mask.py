"""찾아낸 민감정보 구간을 가린 텍스트로 바꾼다.

탐지는 하지 않는다. core/privacy.py 가 어디를 가릴지 정하고, 이 파일은 그 구간을
읽을 수 있는 표시로 바꾸기만 한다. 같은 기준을 core/pdf_redact.py 는 좌표로 받아
PDF 위에 검은 박스를 그린다. 기준이 한 곳에 있어야 텍스트에서 가린 것과
그림에서 가린 것이 어긋나지 않는다.

왜 가리는가.

근로계약서에는 판정에 전혀 쓰이지 않는 개인정보가 들어 있다. 위약금 조항이
위법인지 따지는 데 주민등록번호는 한 글자도 필요 없다. 암호화나 접근통제는
'가지고 있되 지키는' 방식이라 언젠가 뚫릴 수 있지만, 애초에 받지 않으면
유출될 것이 없다. 특히 주민등록번호는 고유식별정보라 법령 근거 없이는
처리 자체가 원칙적으로 금지되고, 이 서비스에는 그 근거가 없다.

별표가 아니라 [성명] 처럼 종류를 적는 이유는, 사용자가 화면에서 무엇이 가려졌는지
바로 알아보게 하기 위해서다. 조용히 지우면 글자가 깨진 것으로 오해한다.
"""
from .privacy import counts as _counts
from .privacy import find_spans
from .privacy import summary as _summary


def mask(text: str) -> tuple[str, dict[str, int]]:
    """민감정보를 가린 텍스트와, 항목별로 몇 건을 가렸는지를 돌려준다."""
    text = text or ""
    spans = find_spans(text)
    if not spans:
        return text, {}

    out, cursor = [], 0
    for s in spans:
        out.append(text[cursor:s.start])
        out.append(f"[{s.kind}]")
        cursor = s.end
    out.append(text[cursor:])
    return "".join(out), _counts(spans)


def summary(counts: dict[str, int]) -> str:
    """화면에 띄울 한 줄 요약.

    조용히 처리하면 사용자는 무슨 일이 있었는지 모른다. 보호는 보여야 신뢰가 된다.
    """
    return _summary(counts)
