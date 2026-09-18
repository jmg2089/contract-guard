# 근로계약서 독소조항 검사기

계약서를 넣으면 조항별로 근로기준법 위반·불리 조항을 찾아내고, **근거 법조문을 원문 그대로 인용**한다.

## 이 프로젝트의 한 문장

> **LLM은 법을 기억해서 답하지 않는다.** 검색된 조문만 보고 판정하고, 인용문이 원문과 글자 단위로 일치하지 않으면 그 판정을 버린다.

이게 마케팅 문구가 아니라 `core/judge.py:verify_citation()` 함수로 강제된다. 게이트를 통과 못 한 판정은 사용자 화면에 도달하지 못하고 `report.dropped`로 격리되며, **격리된 건수가 UI에 그대로 표시된다.** "우리가 할루시네이션을 N번 막았다"가 데모 중에 눈에 보인다.

---

## 아키텍처

```
계약서 원문 (PDF / 붙여넣기)
      │
      ├─ segment()        제N조 단위 분할              정규식      LLM 안 씀
      │
      ├─ run_rules()      숫자·금지문구 결정론적 탐지     정규식+계산  LLM 안 씀
      │                   (최저임금 미달, 수습 6개월,
      │                    연차 10일, 위약금 예정 …)
      │
      ├─ search()         조항 → 관련 법조문 top-4      BM25       LLM 안 씀
      │
      ├─ judge_clause()   검색된 조문만 보고 판정        ← LLM은 여기 한 칸뿐
      │
      └─ verify_citation()  ┌ 인용 조문이 검색 결과 안에 있는가?
                            ├ quote 가 조문 원문의 실제 부분문자열인가?
                            └ quote 가 12자 이상인가?
                              하나라도 실패 → 판정 폐기
```

숫자 비교는 언어 모델이 가장 자주 틀리는 영역이라 룰에서 확정적으로 잡고, LLM은 "문장의 의미를 읽어야 하는" 조항에만 쓴다. 룰이 이미 잡은 조항은 LLM을 태우지 않으므로 비용과 지연도 같이 줄어든다.

룰과 LLM이 **같은 인용 게이트를 통과한다.** 룰도 근거 문장을 법령 원문에서 그대로 떠온다.

---

## 실행

```bash
pip install -r requirements.txt

# 1) 키 없이 — 룰만으로 전체 파이프라인 확인
python -m eval.run_eval --no-llm -v

# 2) LLM 붙여서
cp .env.example .env     # LLM_API_KEY 채우기
export $(cat .env | xargs)
python -m eval.run_eval -v

# 3) 앱 띄우기
streamlit run app.py
```

### LLM 공급자 전환

`core/judge.py`는 한 줄도 안 바뀐다. 환경변수만 바꾼다.

| 공급자 | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` |
|---|---|---|---|
| 키 없음 (개발용) | `dummy` | — | — |
| OpenAI | `openai_compatible` | (비움) | `gpt-4o-mini` |
| Upstage Solar | `openai_compatible` | `https://api.upstage.ai/v1` | `solar-pro` |
| Groq | `openai_compatible` | `https://api.groq.com/openai/v1` | 모델명 |
| Anthropic | `anthropic` | — | 모델명 |

---

## 배포 — Render (무료, Flask 기준)

1. GitHub에 리포지토리로 push (`.env`는 `.gitignore`에 이미 들어있다)
2. https://render.com 가입 → `New` → `Web Service` → 리포 연결
3. 설정값
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn server:app --bind 0.0.0.0:$PORT --timeout 120`
   - Instance Type: `Free`
4. `Environment` 탭에서 키 등록 (키가 없으면 이 단계는 건너뛴다 — `dummy` 모드로 룰만 돌아간다)
   ```
   LLM_PROVIDER = openai_compatible
   LLM_MODEL    = gpt-4o-mini
   LLM_API_KEY  = sk-...
   ```
5. Deploy. 첫 빌드 3~5분.

`render.yaml`이 리포에 들어있으므로 `New` → `Blueprint`로 연결하면 3~4단계가 자동으로 잡힌다.

주의:
- 무료 인스턴스 메모리는 512MB다. **임베딩 모델을 런타임에 로딩하지 마라.** BM25만 쓰는 현재 구조는 100MB 미만이다.
- 무료 티어는 15분 무요청 시 잠들고, 다음 접속에 30~50초가 걸린다. **심사 기간(9/21~10/5) 중 하루 한 번은 직접 접속해 깨워두고, 데모 영상은 미리 녹화해둔다.**
- Railway, Fly.io, PythonAnywhere도 같은 `Procfile`로 동작한다. Render가 막히면 갈아타면 된다.

---

## 법령 데이터 — 가장 중요한 경고

`data/laws.json`의 조문은 현재 **`verified: false`** 상태다. 인용 게이트는 quote가 이 텍스트의 부분문자열인지로 판정하므로, **원문이 부정확하면 게이트 전체가 무의미해진다.**

토요일 오전 안에 반드시 처리한다.

```bash
LAW_OC=<법제처 등록 ID> python scripts/fetch_laws.py
```

OC는 https://open.law.go.kr 가입 후 즉시 발급된다(심사 없음). 막히면 법제처 웹에서 조문을 복사해 손으로 채우고 `verified`를 `true`로 바꿔도 된다. 중요한 건 **원문과 글자가 같은지**다.

---

## 평가

```bash
python -m eval.run_eval -v
```

TP 판정 기준: **(조 번호, 근거 법조문 id)가 둘 다 일치할 때만** 정답. 결론이 맞아도 근거 조문이 틀리면 오답으로 센다. 이 프로젝트의 주장과 일관되게 채점한다.

현재 시드 3건 기준 숫자는 **의미 없다.** 케이스가 3개뿐이고 룰이 그 3개에 맞춰 짜였기 때문이다. 평가셋의 목적은 점수를 잘 받는 게 아니라 **실패를 드러내는 것**이다. 다음 조건을 채우기 전까지는 발표에 숫자를 쓰지 마라.

- 계약서 10건 이상
- 라벨 30개 이상
- 그중 **정상 조항만 있는 대조군 2건 이상** (없으면 정밀도가 거짓말을 한다)
- 룰이 못 잡고 LLM만 잡는 케이스 5건 이상 (아니면 "LLM 왜 쓰냐" 질문에 답할 수 없다)

---

## 파일 지도

| 경로 | 역할 | 담당 |
|---|---|---|
| `core/types.py` | **모듈 간 계약.** 금요일 밤 확정 후 합의 없이 변경 금지 | 둘이 같이 |
| `core/segment.py` | 계약서 → 조항 분할 | 팀원 |
| `core/retrieve.py` | BM25 법조문 검색 + 동의어 확장 | 팀원 |
| `core/judge.py` | LLM 판정 + **인용 게이트** | 팀원 |
| `core/llm.py` | 공급자 추상화 | 팀원 |
| `core/pipeline.py` | 오케스트레이션 | 팀원 |
| `server.py` | Flask 서버 — 두 사람의 경계선 | 합의 후 변경 |
| `templates/index.html` | 화면 (현재는 보험용 최소 구현) | 팀원 |
| `core/rules.py` | 결정론적 룰 12개 | 정민규 |
| `data/laws.json` | 법령 원문 | 정민규 |
| `eval/dataset.json` | 평가셋 + 정답 라벨 | 정민규 |
| `eval/run_eval.py` | 지표 산출 | 정민규 |

---

## 면책

이 도구는 법률 자문이 아니다. UI 하단과 제출 문서 양쪽에 반드시 명시한다. 이 문구가 없으면 심사에서 감점 요인이 된다.
