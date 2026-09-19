"""이 문서가 근로계약서인지 판별한다.

왜 필요한가.

수료증 사진을 올렸더니 조항이 잡히지 않아 "위반 0건"이 나왔다. 글자는 제대로 읽혔는데
문서 종류가 달랐던 것이다. 앞서 만든 validate.py 는 '읽혔는가'만 본다. 읽히기는 잘 읽힌
이력서·견적서·재직증명서는 그 검사를 그냥 통과한다. 계약 용어 세 개만 있으면 되기 때문이다.

더 위험한 쪽은 따로 있다. 완전히 무관한 문서는 사용자도 자기가 뭘 올렸는지 안다.
정작 문제는 **비슷한 문서**다. 용역계약서·프리랜서 계약서는 '계약', '대금', '업무'가
가득해 어떤 어휘 검사든 통과한다. 그런데 근로기준법이 적용되지 않으므로, 여기에
"최저임금 위반입니다"라고 답하면 틀린 법을 들이댄 것이 된다.

그래서 두 층으로 판별한다.

  1) 구조 검사 — 근로기준법 제17조가 명시하도록 정한 항목이 몇 개나 있는가.
     판정 근거를 조문으로 설명할 수 있다. 이 프로젝트의 인용 검증 원칙과 같다.
  2) 학습 분류기 — 문서 전체를 보고 종류를 맞힌다.
     구조는 비슷하지만 성격이 다른 문서(용역계약서)를 여기서 걸러낸다.

둘이 엇갈리면 낮은 쪽을 따른다. 법률 도구에서 과신은 오탐보다 비싸다.
"""
import re

# ── 근로기준법 제17조 명시사항 ──────────────────────────────────────────
# 제17조 제1항: 1.임금 2.소정근로시간 3.제55조 휴일 4.제60조 연차유급휴가
#               5.그 밖에 대통령령으로 정하는 근로조건(시행령 제8조 — 근무장소·업무내용 등)
#
# 실제 계약서는 표현이 제각각이므로 조문 용어만 찾으면 못 잡는다.
# 항목마다 실무에서 쓰이는 표현을 함께 둔다.
REQUIRED_TERMS: dict[str, list[str]] = {
    "임금": ["임금", "급여", "월급", "시급", "연봉", "보수액", "기본급"],
    "소정근로시간": ["근로시간", "근무시간", "소정근로", "시업", "종업", "근무일"],
    "휴일": ["휴일", "주휴", "유급휴일", "휴무일"],
    "연차유급휴가": ["연차", "유급휴가", "연차휴가", "휴가"],
    "근무장소": ["근무장소", "근무지", "취업장소", "근무 장소"],
    "업무내용": ["업무내용", "담당업무", "직무", "업무의 내용", "종사할 업무"],
}

# 근로계약서에만 나타나는 당사자 구조. 용역계약서는 '갑/을'은 써도 '근로자'는 안 쓴다.
PARTY_TERMS = ["근로자", "사용자", "사업주", "피용자"]

# 계약서라면 있어야 할 체결 형식
FORM_TERMS = ["서명", "날인", "인)", "(인", "체결", "당사자", "계약서"]

# 용역·프리랜서 계약서 쪽으로 기우는 표지.
# 이게 있다고 곧바로 배제하지는 않는다 — 근로계약서를 용역계약서로 위장하는 사례가 많아
# 오히려 이 조합이 중요한 신호가 된다.
CONTRACTOR_TERMS = [
    "용역", "수급인", "도급인", "프리랜서", "위탁", "수탁자", "위탁자",
    "납품", "검수", "산출물", "용역비", "대금", "사업소득", "3.3%",
    "개인사업자", "위임", "도급",
]

# 문서가 스스로 자기 종류를 밝히는 표지. 보통 제목 줄에 나온다.
#
# 이걸 '문서 어디에 나오든 강한 신호'로 다뤘다가 크게 틀렸다. 용역계약서 제4조에
# "세금계산서 수령일로부터 30일 이내" 라는 문구가 있다는 이유로 그 계약서를
# 견적서류로 판정했다. 계약서 본문에 스쳐 지나가는 단어와, 제목 줄에 박힌
# 문서 종류 표기는 무게가 전혀 다르다.
#
# 그래서 위치를 본다. 제목 구역(앞부분)에 있으면 강한 신호, 본문에 있으면 약한 참고.
TITLE_MARKERS = [
    "수료증", "이수증", "재직증명서", "경력증명서", "졸업증명서", "성적증명서",
    "이력서", "자기소개서", "견적서", "거래명세서", "세금계산서", "영수증",
    "임명장", "위촉장", "표창장", "상장", "안내문", "공고", "회의록",
    "보도자료", "취업규칙", "사규", "약관", "개인정보 처리방침", "제안서",
    "보고서", "명세서", "확인서", "신청서", "동의서",
]

# 본문 어디에 있든 '계약서가 아님'을 가리키는 표현. 위 표지보다 약하게 센다.
OTHER_DOC_TERMS = [
    "수료하였", "증서를 수여", "이수하였", "졸업하였", "위촉합니다",
    "재직 중임을 증명", "경력사항은 아래", "위와 같이 견적", "상기와 같이 증명",
    "모집분야", "접수방법", "제출서류", "지원 자격", "문의사항은",
    "이 법은", "이 규칙은", "이 영은", "부칙", "벌칙", "선고", "판결",
]

# 법령·판례 원문 표지. 근로자·사용자가 잔뜩 나오지만 계약서가 아니다.
STATUTE_MARKERS = [
    "이 법은 헌법에 따라", "제1조(목적) 이 법은", "이 법은 공포",
    "부칙 제1조(시행일)", "이하의 벌금에 처한다", "이하의 징역에 처한다",
    "선고", "판결", "원고의 청구를", "대통령령으로 정하는 바에 따라 시행",
]

TITLE_ZONE = 200  # 앞 200자를 제목 구역으로 본다

# 계약서라면 반드시 있는 '체결' 흔적. 서명란이나 체결 문구다.
#
# 이게 없으면 계약서가 아니다. 근로 관련 뉴스 기사나 '근로계약서 작성 안내문'은
# 근로자·임금·근로시간이 다 나오고 계약서 문구를 예시로 인용하기까지 하지만,
# 서명란이 없다. 실제로 이 검사를 넣기 전에 둘 다 근로계약서로 오판했다.
EXECUTION_SIGNALS = [
    "(인)", "(인", "서명", "날인", "체결한다", "체결합니다", "체결하였",
    "각 1부씩", "2부를 작성", "2통을 작성", "위와 같이 계약",
]

# 근로자성(종속성) 지표 — 대법원이 근로자인지 판단할 때 보는 요소들이다.
#
# 계약서 제목이 '프리랜서'여도 이 지표가 강하면 실질은 근로계약일 수 있다.
# 위장도급·가짜 3.3 계약이라 불리는 문제이고, 실무에서 다툼이 가장 많다.
# 제목이 아니라 실질로 판단하는 것이 법원의 태도이므로 여기서도 그렇게 한다.
SUBORDINATION_SIGNALS = [
    "지휘", "감독", "출근", "퇴근", "출퇴근", "취업규칙", "복무규정",
    "사규", "인사규정", "결재", "승인 없이", "겸업", "겸직",
    "지정한 장소", "지정하는 시간", "근태", "연장근로", "휴가를 신청",
]


def _hits(text: str, terms: list[str]) -> list[str]:
    return [t for t in terms if t in text]


def structure_report(text: str) -> dict:
    """근로기준법 제17조 명시사항이 몇 개나 보이는지 센다.

    이 함수의 값은 점수 자체가 아니라 '무엇이 없는지 말할 수 있다'는 데 있다.
    사용자에게 "근로계약서가 아닙니다"만 던지면 납득시킬 수 없지만,
    "임금·소정근로시간·휴일이 보이지 않습니다"라고 하면 스스로 확인할 수 있다.
    """
    found, missing = [], []
    for name, variants in REQUIRED_TERMS.items():
        if _hits(text, variants):
            found.append(name)
        else:
            missing.append(name)

    head = text[:TITLE_ZONE]
    parties = _hits(text, PARTY_TERMS)
    forms = _hits(text, FORM_TERMS)
    contractor = _hits(text, CONTRACTOR_TERMS)

    # 제목 구역의 종류 표기 — 단, '계약서'라고 적혀 있으면 그쪽을 우선한다.
    # '용역계약서 ... 견적서' 같은 문서를 견적서로 오판하지 않기 위함이다.
    title_says_contract = "계약서" in head or "계약을 체결" in head
    title_markers = [] if title_says_contract else _hits(head, TITLE_MARKERS)

    # 제목 줄이 '근로계약서' 그 자체인가. 문서가 스스로 종류를 밝힌 가장 강한 신호다.
    # 줄 전체가 근로계약서로 끝나야 인정한다 — '표준근로계약서 작성 안내' 같은
    # 설명 문서를 계약서로 착각하지 않기 위해서다.
    titled_employment = any(
        re.fullmatch(r"[가-힣\s]*근로계약서", line.strip())
        for line in head.split("\n")
    )

    return {
        "required_found": found,
        "required_missing": missing,
        "required_ratio": len(found) / len(REQUIRED_TERMS),
        "parties": parties,
        "forms": forms,
        "contractor_signals": contractor,
        "title_markers": title_markers,
        "title_says_contract": title_says_contract,
        "titled_employment": titled_employment,
        "other_doc_signals": _hits(text, OTHER_DOC_TERMS),
        "statute_signals": _hits(text, STATUTE_MARKERS),
        "execution_signals": _hits(text, EXECUTION_SIGNALS),
        "subordination_signals": _hits(text, SUBORDINATION_SIGNALS),
        "articles": len(re.findall(r"제\s*\d+\s*조", text)),
    }


def structure_verdict(text: str) -> dict:
    """구조 검사만으로 내리는 1차 판정.

    설계에서 한 번 크게 틀렸고, 그걸 바로잡은 자리라 남겨 둔다.

    처음에는 '제17조 명시사항이 몇 개나 있는가'로 근로계약서 여부를 판정했다.
    그랬더니 자체 샘플 중 **위반이 가장 많은 계약서 두 건이 근로계약서가 아니라고
    걸러졌다.** 당연한 결과였다. 나쁜 근로계약서란 바로 그 명시사항을 빠뜨린 계약서다.
    완비도를 문턱으로 쓰면 가장 보호가 필요한 사용자를 문 앞에서 돌려보내게 된다.

    그래서 역할을 나눴다.
      - 문서 종류 판정   : 당사자 구조('근로자'·'사용자')와 다른 문서 표지로 본다.
                          이건 계약 내용이 나쁘든 좋든 변하지 않는다.
      - 명시사항 완비도  : 판정에서 빼고, 제17조 위반 여부를 따지는 근거로 쓴다.
                          missing_articles() 가 그 일을 한다.
    """
    r = structure_report(text)

    # 1) 제목 구역이 자기 종류를 밝히면 거기서 끝낸다. 가장 강한 신호다.
    #    수료증은 '교육기간'이 적혀 있어도 수료증이고, 취업규칙은 '근로자'가
    #    수십 번 나와도 계약서가 아니다.
    if r["title_markers"]:
        return {"kind": "other", "confidence": 0.9, "report": r,
                "why": f"문서 제목에 '{r['title_markers'][0]}'가 있습니다. "
                       f"근로계약서가 아닙니다."}

    # 2) 법령·판례 원문. 근로자·사용자가 가장 많이 나오는 문서이면서
    #    계약서가 아닌, 이 도구에서 가장 헷갈리기 쉬운 입력이다.
    if len(r["statute_signals"]) >= 2:
        return {"kind": "other", "confidence": 0.85, "report": r,
                "why": "법령 또는 판례 원문으로 보입니다. 검토 대상은 계약서입니다."}

    # 3) 계약 문서의 꼴을 갖췄는가.
    #
    #    처음에는 '서명란이나 체결 문구가 없으면 계약서가 아니다'로 잘랐다.
    #    그랬더니 자체 샘플 세 건이 전부 걸렸다. 조항 부분만 잘라 놓은 발췌였기 때문이다.
    #    실제 사용자도 계약서 전체가 아니라 문제되는 조항만 복사해 붙여넣는 경우가 많다.
    #    서명란을 요구하면 그 사람들을 전부 돌려보내게 된다.
    #
    #    그래서 두 갈래 중 하나만 만족하면 통과시킨다.
    #      (a) 체결 흔적이 있다 — 계약서 전문을 올린 경우
    #      (b) 조항 구조와 근로조건 항목이 있다 — 조항만 발췌한 경우
    #    근로 관련 기사와 '계약서 작성 안내문'은 둘 다 만족하지 못한다.
    #    계약서를 설명하는 글이지 계약 조항 자체가 아니기 때문이다.
    looks_like_clauses = r["articles"] >= 2 and len(r["required_found"]) >= 2
    if not r["execution_signals"] and not looks_like_clauses and not r["titled_employment"]:
        return {"kind": "other", "confidence": 0.75, "report": r,
                "why": "서명란도 계약 조항 구조도 확인되지 않습니다. "
                       "계약서가 아니라 설명·안내 문서로 보입니다."}

    strong_contractor = len(r["contractor_signals"]) >= 3

    # 4) 위장도급 판정. 용역·프리랜서로 이름 붙였더라도 종속성 지표가 강하면
    #    실질은 근로계약일 수 있다. 법원이 제목이 아니라 실질로 판단하기 때문이다.
    #    여기서 근로계약서로 돌리되, 화면에서 반드시 근거를 함께 보여준다.
    if strong_contractor and len(r["subordination_signals"]) >= 4:
        return {"kind": "employment", "confidence": 0.6, "report": r,
                "why": f"계약서 이름은 용역·프리랜서지만 사용자에게 종속된 정황이 "
                       f"{len(r['subordination_signals'])}가지 보입니다 "
                       f"({', '.join(r['subordination_signals'][:4])}). "
                       f"실질이 근로계약일 수 있습니다."}

    # 5) 본문에만 있는 약한 표지. 단독으로 결론내지 않고 확신만 낮춘다.
    weak_other = len(r["other_doc_signals"]) >= 2 and not r["title_says_contract"]

    if weak_other and not r["parties"]:
        return {"kind": "other", "confidence": 0.7, "report": r,
                "why": f"계약서가 아닌 문서에서 쓰이는 표현이 여럿 보입니다 "
                       f"({', '.join(r['other_doc_signals'][:3])})."}

    if r["parties"]:
        # 당사자 구조가 근로계약이다. 용역 표현이 섞여 있으면 위장 가능성을 따로 알린다.
        if strong_contractor:
            return {"kind": "contractor", "confidence": 0.55, "report": r,
                    "why": f"'{r['parties'][0]}' 표기와 용역·위탁 표현"
                           f"({', '.join(r['contractor_signals'][:3])})이 함께 보입니다."}
        conf = 0.7 if weak_other else 0.85
        return {"kind": "employment", "confidence": conf, "report": r,
                "why": f"근로계약 당사자 표기를 확인했습니다 ({', '.join(r['parties'][:2])})."}

    if strong_contractor:
        return {"kind": "contractor", "confidence": 0.7, "report": r,
                "why": f"용역·위탁 계약에서 쓰이는 표현이 보입니다 "
                       f"({', '.join(r['contractor_signals'][:3])})."}

    # 당사자 표기는 없지만 근로조건이 여럿 적혀 있으면 서식형 계약서일 수 있다.
    # 여기서 단정하지 않고 학습 분류기 쪽에 판단을 넘긴다.
    if r["required_ratio"] >= 0.5:
        return {"kind": "employment", "confidence": 0.45, "report": r,
                "why": f"당사자 표기는 없으나 근로조건 항목 "
                       f"{len(r['required_found'])}개가 확인됩니다."}

    # 6) 계약서이긴 한데 근로계약서가 아닌 경우.
    #    임대차·매매·비밀유지·가맹계약서가 여기로 온다. 용역 어휘로만 걸러내면
    #    이런 계약서가 '문서 아님'으로 떨어지는데, 사용자에게는 "계약서는 맞지만
    #    이 서비스가 보는 계약서가 아닙니다"라고 말해 주는 편이 정확하다.
    if r["title_says_contract"] and r["execution_signals"]:
        return {"kind": "contractor", "confidence": 0.65, "report": r,
                "why": "계약서로 보이지만 근로계약의 당사자 표기와 근로조건이 "
                       "확인되지 않습니다. 근로계약서가 아닌 다른 계약서로 보입니다."}

    return {"kind": "other", "confidence": 0.6, "report": r,
            "why": "근로계약 당사자 표기도, 근로조건 항목도 충분히 보이지 않습니다."}


# 근로기준법 제17조 제2항: 임금의 구성항목·계산방법·지급방법과 소정근로시간,
# 휴일, 연차유급휴가는 '서면으로' 명시해 교부해야 한다. 위반 시 과태료 대상이다.
# 근무장소·업무내용은 시행령 사항이라 같은 무게로 다루지 않는다.
WRITTEN_REQUIRED = ["임금", "소정근로시간", "휴일", "연차유급휴가"]


def missing_articles(text: str) -> dict | None:
    """제17조가 서면 명시하도록 정한 항목 중 빠진 것을 찾는다.

    문서 종류 판정에서 빼낸 완비도 검사가 여기로 왔다.
    이건 '근로계약서가 아니다'라는 신호가 아니라 그 자체로 위반 소지다.
    조항 단위 룰로는 잡을 수 없다 — 없는 조항은 검사 대상이 되지 않기 때문이다.
    문서 전체를 봐야만 나오는 판정이라 따로 둔다.
    """
    r = structure_report(text)
    missing = [k for k in WRITTEN_REQUIRED if k in r["required_missing"]]
    if not missing:
        return None
    return {
        "missing": missing,
        "law_id": "근로기준법-제17조",
        "quote": "사용자는 제1항제1호와 관련한 임금의 구성항목ㆍ계산방법ㆍ지급방법 및 "
                 "제2호부터 제4호까지의 사항이 명시된 서면을 근로자에게 교부하여야 한다.",
        "message": f"근로기준법 제17조가 서면 명시를 요구하는 항목 중 "
                   f"{', '.join(missing)}에 관한 내용을 찾지 못했습니다.",
    }


# ── 학습 분류기 층 ──────────────────────────────────────────────────────

_MODEL = None
_MODEL_TRIED = False
DOCTYPE_PATH = "data/doctype_clf.joblib"


def _model():
    """분류기를 한 번만 읽어 재사용한다. 없으면 None — 구조 검사만으로 돈다."""
    global _MODEL, _MODEL_TRIED
    if _MODEL_TRIED:
        return _MODEL
    _MODEL_TRIED = True
    try:
        from pathlib import Path

        import joblib

        p = Path(__file__).resolve().parent.parent / DOCTYPE_PATH
        if p.exists():
            _MODEL = joblib.load(p)
    except Exception:
        _MODEL = None
    return _MODEL


def _sentences(text: str) -> list[str]:
    """문서를 문장/줄 단위로 쪼갠다. 표 형식 계약서는 줄이 곧 항목이다."""
    parts: list[str] = []
    for line in re.split(r"[\n]+", text):
        for s in re.split(r"(?<=다\.)\s+|(?<=함\.)\s+", line):
            s = s.strip()
            if len(s) >= 6:
                parts.append(s)
    return parts


def classifier_vote(text: str) -> dict:
    """문서 안의 모든 문장을 분류기에 태워 종류별 지분을 낸다.

    문장 하나로 문서를 판정하지 않는 이유는 분명하다. 근로계약서에도
    '본 계약서 2부를 작성한다' 처럼 어느 계약서에나 나오는 문장이 섞여 있다.
    문서 전체의 분포를 봐야 한다.

    확신이 낮은 문장은 빼고 센다. 애매한 문장을 억지로 한 쪽에 넣으면
    지분이 흐려진다.
    """
    model = _model()
    if model is None:
        return {"available": False, "share": {}, "votes": 0}

    sents = _sentences(text)
    if not sents:
        return {"available": True, "share": {}, "votes": 0}

    probs = model.predict_proba(sents)
    labels = list(model.classes_)
    counts: dict[str, int] = {}
    used = 0
    for row in probs:
        top = int(row.argmax())
        if row[top] < 0.45:  # 확신 없는 문장은 기권 처리
            continue
        counts[labels[top]] = counts.get(labels[top], 0) + 1
        used += 1

    share = {k: v / used for k, v in counts.items()} if used else {}
    return {"available": True, "share": share, "votes": used,
            "counts": counts, "sentences": len(sents)}


def classify_document(text: str) -> dict:
    """구조 검사와 학습 분류기를 합쳐 최종 판정한다.

    합치는 규칙은 하나다. **둘이 엇갈리면 확신을 낮춘다.**
    법률 도구에서 과신은 오탐보다 비싸다. 확신이 낮으면 화면에서 단정하지 않고
    사용자에게 확인을 요청한다.
    """
    sv = structure_verdict(text)
    vote = classifier_vote(text)
    share = vote.get("share", {})

    kind = sv["kind"]
    conf = sv["confidence"]
    reasons = [sv["why"]]

    if share:
        top = max(share, key=share.get)
        top_share = share[top]
        pct = {k: f"{v:.0%}" for k, v in sorted(share.items(), key=lambda x: -x[1])}
        reasons.append(f"문장 {vote['votes']}개 분류 결과 {pct}.")

        if top == kind:
            conf = min(0.95, conf + 0.10)
        elif top_share >= 0.55 and sv["confidence"] <= 0.5:
            # 분류기가 뚜렷하게 다른 답을 냈다. 구조 검사를 뒤집되 확신은 낮춘다.
            kind = top
            conf = min(conf, 0.55)
            reasons.append("구조 검사와 분류기 판단이 달라 확정하지 않았습니다.")
        else:
            # 구조 검사가 근거를 들고 판정한 경우에는 분류기가 뒤집지 못한다.
            # 문턱을 0.8 로 뒀다가 적대적 케이스에서 세 건이 뒤집혔다.
            # 재직증명서는 근로조건을 잔뜩 적어 두고, 근로 관련 기사와 계약서 작성
            # 안내문은 계약서 문구를 그대로 인용하므로 문장만 보면 근로계약서로 기운다.
            # 구조 검사 쪽은 '서명란이 없다', '제목이 재직증명서다' 처럼 근거를 댈 수 있고
            # 분류기는 176문장으로 학습한 80% 모델이다. 근거 있는 쪽을 우선한다.
            conf = max(0.40, conf - 0.10)
            if top != kind:
                reasons.append(
                    f"분류기는 {top} 쪽으로 기울었으나 문서 종류 표기를 우선했습니다.")

    # 위장도급 경고. 두 갈래로 잡는다.
    #   (a) 계약서 이름은 용역·프리랜서인데 종속성 지표가 강한 경우 — 구조 검사가 잡는다
    #   (b) 근로계약 당사자 구조인데 용역 쪽 문장 지분이 높은 경우 — 분류기가 잡는다
    # 실무에서 가장 다툼이 많은 지점이라 종류 판정과 별개로 알린다.
    rep = sv["report"]
    disguise = (
        len(rep["contractor_signals"]) >= 3 and len(rep["subordination_signals"]) >= 4
    ) or (
        bool(rep["parties"])
        and share.get("contractor", 0) >= 0.30
        and kind in ("employment", "contractor")
    )

    return {
        "kind": kind,
        "confidence": round(conf, 2),
        "reasons": reasons,
        "structure": sv["report"],
        "vote": share,
        "disguise_warning": disguise,
        "missing_articles": missing_articles(text) if kind == "employment" else None,
    }
