# 강수현 님 프론트와 합치기 — 30분

**프론트가 기준입니다.** 강수현 님이 만든 Flask 앱을 그대로 두고, 판정 엔진만 그 안으로 옮깁니다. 라우트도 템플릿도 건드리지 않습니다.

붙는 지점은 **함수 하나**입니다.

```python
from analyzer import analyze_contract
result = analyze_contract(request.form.get("text", ""))
```

---

## 1단계 — 파일 복사 (5분)

강수현 님 프로젝트 루트에 이것만 복사합니다.

```
core/                 판정 로직 (26개 룰 + 분류기 + 검색)
data/                 법령 원문 37개 + 학습 데이터 431문장
scripts/              분류기 학습 스크립트
config.py             상수 (최저임금, 법정 기준, 임계값)
analyzer.py           ← 붙는 지점. 이 파일만 import 하면 된다
```

**복사하지 않는 것** — 충돌하기 때문입니다.

```
server.py             강수현 님 앱이 이미 있음
templates/            강수현 님 것을 씀
Procfile, render.yaml 배포 설정은 하나만 있어야 함
```

`eval/` 은 선택입니다. 성능 숫자를 다시 뽑을 거면 같이 복사하세요.

### 이름이 겹치면

강수현 님 프로젝트에 이미 `config.py` 나 `data/` 폴더가 있다면 덮어쓰지 말고 알려주세요. `core/` 안의 import 경로를 바꿔서 넣으면 됩니다.

---

## 2단계 — 의존성 추가 (2분)

강수현 님 `requirements.txt` 에 두 줄만 추가합니다.

```
scikit-learn>=1.3
joblib>=1.3
rank-bm25>=0.2.2
```

버전을 고정하지 마세요. 특정 버전으로 핀하면 그 버전의 윈도우 빌드본이 없는 파이썬에서 소스 컴파일로 넘어가 실패합니다.

```bash
pip install -r requirements.txt
python scripts/train_classifier.py
```

마지막 줄에 `3-fold 교차검증 정확도: 77.1%` 가 나오면 준비 완료입니다.

---

## 3단계 — 라우트에 한 줄 (5분)

강수현 님 Flask 앱의 기존 라우트를 그대로 두고 호출만 추가합니다.

```python
from analyzer import analyze_contract, system_info

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    if request.method == "POST":
        result = analyze_contract(request.form.get("text", ""))
    return render_template("index.html", result=result, info=system_info())
```

JS로 비동기 호출하는 구조라면 엔드포인트만 하나 추가하면 됩니다.

```python
@app.post("/api/analyze")
def api_analyze():
    body = request.get_json(silent=True) or {}
    result = analyze_contract(body.get("text", ""))
    if result is None:
        return jsonify(error="text 가 비어 있습니다"), 400
    return jsonify(result)
```

---

## 4단계 — 템플릿 변수 연결 (15분)

`analyze_contract()` 가 돌려주는 값입니다. 필드 이름만 맞춰주면 됩니다.

```jsonc
{
  "meta": {
    "clause_count": 4,        // 검토한 조항 수
    "violation_count": 2,     // 위반 소지
    "unfavorable_count": 2,   // 불리 조항 / 확인 권장
    "rule_findings": 0,       // 룰 검사가 잡은 건수
    "model_findings": 4,      // 학습 모델이 잡은 건수
    "llm_findings": 0,
    "blocked_by_gate": 0      // ★ 반드시 화면에 노출
  },
  "findings": [               // severity 순 정렬됨
    {
      "severity": "violation",          // violation | unfavorable  (CSS 클래스로 바로 사용 가능)
      "severity_label": "위반 소지",      // 그대로 출력해도 되는 한글
      "clause_title": "제5조 교육비",
      "clause_text": "제5조(교육비) 근로자가 입사 후 2년 이내 퇴사하면...",
      "law_label": "근로기준법 제20조(위약 예정의 금지)",
      "quote": "사용자는 근로계약 불이행에 대한 위약금 또는 손해배상액을 예정하는 계약을 체결하지 못한다.",
      "law_text": "…조문 전문 (모달용)",
      "reason": "퇴사나 계약 불이행을 이유로 금전 부담을 지우는 조항입니다...",
      "suggestion": "해당 조항을 삭제하고, 실제 발생한 손해가 있을 때...",
      "source": "model",                // rule | model | llm
      "source_label": "학습 모델"
    }
  ],
  "clauses": [ ... ],         // 분할된 조항 전체 (문제없는 것 포함)
  "dropped": [ ... ]          // 인용 검증에서 걸러진 판정
}
```

`system_info()` 는 화면 상단·하단 표시용입니다.

```jsonc
{
  "law_count": 37, "unverified": 0, "rule_count": 26,
  "classifier_loaded": true, "classifier_classes": 15,
  "min_wage": 10320, "min_wage_year": 2026
}
```

### Jinja 예시

```html
{% if result %}
  <div class="stats">
    <div>{{ result.meta.clause_count }}<span>검토한 조항</span></div>
    <div>{{ result.meta.violation_count }}<span>위반 소지</span></div>
    <div>{{ result.meta.blocked_by_gate }}<span>인용 검증에서 차단</span></div>
  </div>

  {% for f in result.findings %}
    <article class="card {{ f.severity }}">
      <span class="badge">{{ f.severity_label }}</span>
      <strong>{{ f.clause_title }}</strong>
      <span class="src">{{ f.source_label }}</span>
      <blockquote class="clause">{{ f.clause_text }}</blockquote>
      <p>{{ f.reason }}</p>
      <p><code>{{ f.law_label }}</code></p>
      <blockquote class="law">{{ f.quote }}</blockquote>
      {% if f.suggestion %}<p>{{ f.suggestion }}</p>{% endif %}
    </article>
  {% endfor %}

  {% if not result.findings %}
    <p>법조문과 대조해 문제되는 조항을 찾지 못했습니다.</p>
  {% endif %}
{% endif %}
```

---

## 5단계 — 검증 (3분)

세 계약서를 차례로 넣어보세요. 결과가 확연히 달라야 합니다.

### A. 룰이 잡아야 함 (rule 4건 / model 0건)

```
제2조(수습기간) 수습기간은 6개월로 하며 수습기간 중 임금은 80%를 지급한다.
제3조(임금) 임금은 시급 9,500원으로 한다.
제5조(손해배상) 근로자가 계약기간 만료 전 퇴사하는 경우 위약금으로 금 3,000,000원을 지급한다.
제9조(퇴직) 근로자는 회사의 사전 서면 동의 없이 퇴사할 수 없다.
```

### B. 분류기가 잡아야 함 (rule 0건 / model 4건)

```
제1조(근로조건) 회사는 근로자의 동의 없이 임금 및 근로조건을 변경할 수 있다.

제2조(임금 유예) 회사의 경영 사정이 악화된 경우 임금 지급을 무기한 유예할 수 있다.

제5조(교육비) 근로자가 입사 후 2년 이내 퇴사하면 회사가 지원한 어학연수 비용을 전액 돌려주어야 한다.

제6조(업무지시) 근로자는 회사가 지시하는 어떠한 업무도 거부할 수 없으며 거부 시 계약 위반으로 본다.
```

### C. 아무것도 안 잡혀야 함

```
제1조(계약기간) 본 계약은 2026년 10월 1일부터 기간의 정함이 없는 것으로 한다.
제2조(임금) 임금은 월 2,800,000원으로 하며 매월 25일에 통화로 전액 지급한다.
제3조(근로시간) 소정근로시간은 1일 8시간, 1주 40시간으로 하며 휴게시간 1시간을 부여한다.
제4조(연차) 연차 유급휴가는 근로자가 청구한 시기에 부여한다.
```

C에서 뭔가 잡히면 오탐입니다. 그 조항 원문을 알려주세요.

---

## 6단계 — 배포 (5분)

Render 빌드 명령에 분류기 학습을 넣어야 합니다. **로컬에서 만든 `.joblib` 를 올리면 안 됩니다** — sklearn 버전이 달라 로드에 실패할 수 있습니다. 서버에서 직접 학습시키면 버전이 항상 일치하고, 10초면 끝납니다.

Render 대시보드 → Settings → Build Command:

```
pip install -r requirements.txt && python scripts/train_classifier.py
```

`.gitignore` 에 한 줄 추가:

```
data/clause_clf.joblib
```

push하면 자동 재배포됩니다.

---

## 화면에 반드시 남길 것 3가지

디자인은 전적으로 강수현 님 것입니다. 다만 이 셋은 심사 점수와 직결됩니다.

**① `meta.blocked_by_gate`** — "인용 검증에서 차단 N건"

이 시스템은 법 문장을 생성하지 않습니다. 근거는 언제나 법령 원문에서 그대로 인용되고, 원문과 일치하지 않는 판정은 사용자에게 도달하기 전에 폐기됩니다. 이 숫자가 그 장치가 작동한 횟수입니다.

**② `quote`** — 근거 법조문 원문

한 글자도 가공하지 말고 그대로 출력해주세요. "왜 위반인가"를 우리가 설명하는 게 아니라 **법이 말하게 하는 것**이 이 서비스의 핵심입니다.

**③ `source_label`** — 룰 검사 / 학습 모델 구분

숫자 판단은 결정론적 룰 26개가, 의미 판별은 학습 분류기가 담당합니다. 이 구분이 보여야 "왜 두 층을 만들었는가"에 답이 됩니다.

---

## 막히면

- `ModuleNotFoundError: No module named 'core'` → `analyzer.py` 가 프로젝트 **루트**에 있어야 합니다. 하위 폴더에 두면 안 됩니다
- `classifier_loaded: false` → `python scripts/train_classifier.py` 를 안 돌린 겁니다. 룰 26개만으로도 동작하지만 의미 판별이 빠집니다
- `500` 에러 → 조항 원문과 함께 알려주세요
- 파일 이름이 겹친다 → 덮어쓰지 말고 먼저 알려주세요
