# VS Code에서 5분 안에 돌리기

## 0. 준비

압축을 풀고 VS Code에서 **`contract-guard` 폴더 자체를 연다.** (`File → Open Folder`)

상위 폴더를 열면 import가 깨진다. VS Code 왼쪽 탐색기에 `app.py`, `core`, `data`가 바로 보여야 맞다.

**파이썬 3.11 또는 3.12를 쓴다.** 터미널(`Ctrl + ~`)에서 확인:

```
python --version
```

3.13 이상이면 `pip install`이 실패한다. `pdfplumber`가 의존하는 `pillow`, `openai`가 의존하는 `pydantic-core`는 아직 최신 파이썬용 윈도우 빌드본이 없어서 pip이 소스 컴파일로 넘어가다 죽는다. 버전을 낮추는 쪽이 컴파일 환경을 갖추는 것보다 압도적으로 빠르다.

python.org에서 3.12를 설치하고(`Add python.exe to PATH` 체크), 가상환경을 그 버전으로 만든다.

```powershell
py -3.12 -m venv .venv
```

당장 급하면 3.13+에서도 `requirements-min.txt`로 돌릴 수 있다. PDF 업로드와 LLM 판정만 빠지고 나머지는 전부 동작한다.

## 1. 가상환경 만들기 (한 번만)

터미널에서 — **윈도우 PowerShell**:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

`실행 정책` 오류가 나면 한 번만:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**macOS / Linux**:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

프롬프트 앞에 `(.venv)`가 붙으면 성공이다.

VS Code 오른쪽 아래 Python 버전을 클릭해 `.venv`를 인터프리터로 선택해두면 자동완성이 잡힌다.

## 2. 설치

```
pip install -r requirements.txt
```

## 3. 실행 — 세 가지

### (1) 평가 스크립트 — 여기부터 시작한다. API 키 필요 없음

```
python -m eval.run_eval --no-llm -v
```

정상이면 재현율·정밀도 표가 뜬다. **이게 뜨면 환경 설정은 끝난 것이다.**

> **왜 `python eval/run_eval.py`가 아니라 `python -m eval.run_eval`인가**
> 앞의 방식은 `eval` 폴더 안에서 파이썬이 시작돼 `core`, `config`를 못 찾는다. `-m`은 **현재 폴더를 기준으로** 모듈을 찾아 실행한다. 그래서 VS Code 오른쪽 위 ▶ 버튼도 쓰면 안 된다. 터미널에 직접 친다.

### (2) Flask 서버 — 화면과 API가 같이 뜬다

```
python server.py
```

브라우저에서 `http://localhost:5000` 을 연다. 계약서를 붙여넣고 `검사하기`를 누르면 결과가 나온다.

이 화면(`templates/index.html`)은 **팀원 프론트가 늦어질 때를 대비한 보험**이다. 팀원이 자기 템플릿을 올리면 그걸로 교체된다. 그때까지는 이게 데모 가능한 상태를 유지해준다.

같은 서버가 JSON API도 연다. 팀원이 JS로 호출할 때 쓴다.

```
GET  /health        상태 확인
GET  /api/laws      탑재된 법조문 전체
POST /api/analyze   { "text": "...", "use_llm": true }
```

터미널에서 바로 찔러보려면 (윈도우 PowerShell):

```powershell
curl.exe -X POST http://localhost:5000/api/analyze -H "Content-Type: application/json" -d '{\"text\":\"제5조(손해배상) 근로자가 계약기간 만료 전에 퇴사하는 경우 위약금으로 금 3,000,000원을 지급한다.\",\"use_llm\":false}'
```

## 4. LLM 붙이기 (키가 생겼을 때)

키가 없어도 위 세 개는 전부 돌아간다(`dummy` 모드). 키가 생기면:

**윈도우 PowerShell** (그 터미널 세션에서만 유효)

```powershell
$env:LLM_PROVIDER="openai_compatible"
$env:LLM_MODEL="gpt-4o-mini"
$env:LLM_API_KEY="sk-..."
```

**macOS / Linux**

```bash
export LLM_PROVIDER=openai_compatible
export LLM_MODEL=gpt-4o-mini
export LLM_API_KEY=sk-...
```

설정 후 다시:

```
python -m eval.run_eval -v
```

키를 코드에 절대 적지 않는다. `.env`는 `.gitignore`에 이미 들어있다.

---

# 구조 — 계약서 한 조항이 겪는 일

이렇게 생긴 조항 하나가 들어왔다고 하자.

```
제5조(손해배상) 근로자가 계약기간 만료 전에 퇴사하는 경우
위약금으로 금 3,000,000원을 회사에 지급한다.
```

### 1단계 `core/segment.py` — 자른다

계약서 전문에서 `제N조` 패턴을 찾아 조항 단위로 쪼갠다. 정규식만 쓴다. LLM을 쓰면 느리고, 비싸고, 매번 결과가 달라진다.

결과: `Clause(id="c5", article_no=5, title="손해배상", text="...")`

### 2단계 `core/rules.py` — 확실한 건 코드로 먼저 잡는다

12개 규칙이 이 조항을 훑는다. `r_penalty`가 `위약금` 문구를 잡아낸다.

이 단계가 존재하는 이유: **숫자와 금지 문구는 LLM이 제일 자주 틀린다.** "시급 9,500원이 최저임금 10,320원보다 작은가"를 언어 모델에게 물어볼 이유가 없다. 파이썬이 `<` 하나로 끝낸다.

여기서 잡히면 LLM을 아예 호출하지 않는다. 비용과 시간이 같이 줄어든다.

### 3단계 `core/retrieve.py` — 관련 법조문을 찾는다 (룰이 못 잡은 조항만)

조항 텍스트를 질의어로 써서 `data/laws.json`의 18개 조문 중 관련도 높은 **4개**를 BM25로 뽑는다.

`위약금` 같은 계약서 용어를 `손해배상액 예정` 같은 법령 용어로 넓혀주는 동의어 사전(`SYNONYMS`)이 들어있다. **검색이 실패하는 주된 원인은 계약서와 법령이 다른 단어를 쓰기 때문이다.** 정확도를 올리고 싶으면 여기를 제일 먼저 손대라.

### 4단계 `core/judge.py` — LLM은 여기 한 칸만 관여한다

LLM에게 주는 것: **[이 조항]** + **[방금 검색한 조문 4개]** 뿐이다.

시스템 프롬프트가 못박는다.

- 주어진 조문에 실제로 있는 문장만 근거로 써라
- `quote`는 조문 본문에서 **글자 하나 바꾸지 말고** 복사해라
- 관련 조문이 없으면 `ok`라고 해라. 추측하지 마라

### 5단계 `core/judge.py:verify_citation()` — 게이트

LLM이 뭐라고 하든 여기서 세 가지를 검사한다.

| 검사 | 막는 것 |
|---|---|
| 인용한 조문 id가 **방금 검색된 4개 안에** 있는가 | 모델이 학습 때 외운 법을 꺼내 쓰는 것 |
| `quote`가 그 조문 원문의 **실제 부분문자열**인가 | 모델이 그럴듯한 법 문장을 지어내는 것 |
| `quote`가 12자 이상인가 | "…한다." 같은 무의미한 조각으로 통과하는 것 |

하나라도 실패하면 그 판정은 **사용자 화면에 도달하지 못하고** `report.dropped`로 격리된다. 격리된 개수는 화면에 "인용 검증에서 차단 N건"으로 표시된다.

**이 게이트가 이 프로젝트가 심사에서 팔아야 할 유일한 물건이다.**

### 6단계 `core/pipeline.py` — 위 전부를 순서대로 돌린다

조항이 20개면 4단계를 스레드 6개로 동시에 돌린다. 순차 실행하면 40초, 병렬이면 8초다.

---

## 파일별 한 줄 요약

```
config.py          숫자 상수 전부 (최저임금 10,320원 등). 법 바뀌면 여기만 고친다
core/types.py      Clause / LawArticle / Finding — 두 사람 사이의 계약. 합의 없이 바꾸지 않는다
core/segment.py    계약서 → 조항 리스트          LLM 안 씀
core/rules.py      결정론적 규칙 12개             LLM 안 씀   ← 정민규 담당
core/retrieve.py   조항 → 관련 법조문 BM25 검색   LLM 안 씀   ← 정민규 담당
core/llm.py        공급자 전환 (OpenAI/Upstage/Claude)
core/judge.py      LLM 판정 + 인용 게이트
core/pipeline.py   전체 오케스트레이션
server.py          Flask 서버 (화면 + JSON API)     ← 두 사람의 경계선. 합의해야 고친다
templates/         HTML 화면                       ← 팀원 담당
data/laws.json     법령 원문                      ← 정민규 담당, 최우선
eval/dataset.json  평가셋 + 정답 라벨              ← 정민규 담당
eval/run_eval.py   재현율/정밀도 산출
```

---

## 정확도를 올리는 순서

"API로 정확도를 높인다"는 건 사실 네 갈래인데, 효과 순서가 정해져 있다.

**1. `data/laws.json`을 공식 원문으로 교체 (효과 최대, 지금 당장)**

지금은 `verified: false`다. 인용 게이트가 "quote가 이 텍스트의 부분문자열인가"로 판정하므로, 원문에 글자 하나라도 다르면 **맞는 판정까지 전부 차단된다.** 법제처 오픈API(`scripts/fetch_laws.py`)로 받거나 손으로 복사해 채운다. 이게 안 되면 나머지는 의미 없다.

**2. 조문 수를 18개 → 40개로 늘린다**

없는 조문은 검색될 수 없다. 데모에 쓸 계약서에 나올 만한 조항 종류를 먼저 세고, 그걸 덮는 조문을 채운다. 법 전체를 넣을 필요는 없다.

**3. `SYNONYMS` 사전을 키운다 (가성비 최고)**

실패 사례를 볼 때마다 한 줄씩 추가한다. `eval/run_eval.py -v`에서 "놓침"으로 찍힌 케이스가 곧 작업 목록이다.

**4. 프롬프트와 `RETRIEVE_TOP_K` 조정 (효과 제일 작음, 제일 마지막)**

여기부터 손대는 팀이 많은데, 1~3번을 안 한 상태에서 프롬프트를 아무리 만져도 숫자가 안 움직인다.

---

## 두 사람 작업 경계

경계선은 `server.py`다.

```
팀원   →  templates/ , static/       화면
정민규 →  core/ , data/ , eval/      판정 로직과 데이터
둘이   →  server.py                  합의 없이 고치지 않는다
```

팀원이 화면만 만들면 되므로, 팀원 쪽에서는 `build_payload()`가 돌려주는 딕셔너리 구조만 알면 된다. 아래 스키마다.

팀원에게 넘길 계약은 이 한 덩어리면 충분하다.

```jsonc
// POST /api/analyze  요청
{ "text": "근로계약서 전문...", "use_llm": true }

// 응답
{
  "meta": {
    "clause_count": 6,
    "violation_count": 2,
    "unfavorable_count": 1,
    "blocked_by_gate": 1      // ← 이 숫자를 화면에 꼭 띄워달라고 할 것
  },
  "findings": [
    {
      "clause_id": "c5",
      "severity": "violation",          // violation | unfavorable | ok
      "severity_label": "위반 소지",
      "clause_title": "제5조 손해배상",
      "clause_text": "근로자가 계약기간 만료 전에...",
      "law_id": "근로기준법-제20조",
      "law_label": "근로기준법 제20조(위약 예정의 금지)",
      "quote": "사용자는 근로계약 불이행에 대한 위약금 또는 손해배상액을 예정하는 계약을 체결하지 못한다.",
      "reason": "퇴사를 이유로 위약금을 물리는 약정입니다...",
      "suggestion": "해당 조항을 삭제하고...",
      "source": "rule"                  // rule | llm
    }
  ],
  "dropped": [
    { "clause_id": "c3", "claimed_law_id": "", "claimed_quote": "" }
  ]
}
```

**이 스키마를 지금 팀원에게 보내고 고정해라.** 그러면 팀원은 백엔드가 완성되기를 기다리지 않고 이 JSON을 하드코딩한 채로 화면을 다 만들 수 있다. 내일 오후에 서버 주소만 바꿔 끼우면 끝난다. 이틀짜리 협업에서 이게 가장 큰 시간 절약이다.
