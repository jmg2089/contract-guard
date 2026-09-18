# 배포 — 오늘 밤 안에 끝낸다

대회 규칙상 **작동하지 않는 링크는 실격**이다. 못생겨도 좋으니 링크부터 살려놓고, 다듬는 건 내일 한다.

소요 시간: GitHub 10분 + Render 10분 + 빌드 대기 5분.

---

## 1단계 — GitHub에 올린다 (10분)

### git이 있는지 확인

```powershell
git --version
```

없으면 https://git-scm.com/download/win 에서 설치(기본값으로 다음만 누르면 된다). 설치 후 **새 터미널**을 연다.

### 최초 1회 설정

```powershell
git config --global user.name "정민규"
git config --global user.email "jmg20899@gmail.com"
```

### 리포 만들기

1. https://github.com/new 접속
2. Repository name: `contract-guard`
3. **Public** 선택 (Render 무료 플랜은 public 리포가 편하다)
4. README/gitignore/license는 **전부 체크 해제** — 이미 로컬에 있다
5. `Create repository`

### 올리기

```powershell
cd C:\dev\contract-guard
git init
git add .
git status
```

`git status` 결과에 **`.env` 와 `data/clause_clf.joblib` 이 없어야 한다.** 있으면 `.gitignore`가 적용 안 된 것이니 알려달라.

```powershell
git commit -m "근로계약서 독소조항 검사기"
git branch -M main
git remote add origin https://github.com/<your-id>/contract-guard.git
git push -u origin main
```

`<your-id>`를 실제 GitHub 아이디로 바꾼다. 브라우저 로그인 창이 뜨면 승인한다.

---

## 2단계 — Render에 배포한다 (10분)

1. https://render.com → `Get Started` → **GitHub 계정으로 가입**
2. 대시보드에서 `New +` → `Blueprint`
3. `contract-guard` 리포 선택 → `Connect`
4. Render가 `render.yaml`을 읽어 설정을 자동으로 잡는다. `Apply` 클릭

`Blueprint`가 안 보이면 `New +` → `Web Service`로 하고 직접 입력한다.

| 항목 | 값 |
|---|---|
| Language | `Python 3` |
| Branch | `main` |
| Build Command | `pip install -r requirements.txt && python scripts/train_classifier.py` |
| Start Command | `gunicorn server:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1` |
| Instance Type | `Free` |

Environment 탭에 `PYTHON_VERSION = 3.11.9` 하나만 추가한다. API 키는 필요 없다.

---

## 3단계 — 빌드 로그를 지켜본다 (5분)

빌드 로그에 이 두 줄이 반드시 나와야 한다.

```
데이터 버전: 최신 (426문장)
3-fold 교차검증 정확도: 71.9%
```

**분류기를 배포 서버에서 직접 학습시키는 이유**: joblib 모델은 학습한 sklearn 버전과 로드하는 버전이 다르면 깨질 수 있다. 로컬에서 만든 파일을 올리는 대신 그 서버에서 만들면 버전이 항상 일치한다. 학습은 10초면 끝난다.

빌드가 끝나면 `https://contract-guard-xxxx.onrender.com` 형태의 주소가 나온다.

### 확인

```
https://<주소>/health
```

이렇게 나오면 성공이다.

```json
{"ok": true, "law_articles": 18, "unverified": 0, ...}
```

그다음 메인 페이지에서 아래를 붙여넣고 `검사하기`.

```
제2조(수습기간) 수습기간은 6개월로 하며 수습기간 중 임금은 80%를 지급한다.
제3조(임금) 임금은 시급 9,500원으로 한다.
제5조(손해배상) 근로자가 계약기간 만료 전 퇴사하는 경우 위약금으로 금 3,000,000원을 지급한다.
제9조(퇴직) 근로자는 회사의 사전 서면 동의 없이 퇴사할 수 없다.
```

카드 4장이 근거 조문과 함께 뜨면 **배포 완료**다. 넷째 조항은 정규식으로 못 잡는 것이라, 학습 모델이 작동한다는 증거가 된다.

---

## 알아둘 것

**무료 플랜은 15분 무요청 시 잠든다.** 다음 접속에 30~50초가 걸린다.

- 심사 기간(9/21~10/5) 중 **하루 한 번은 직접 접속해서 깨워둔다**
- **데모 영상은 미리 녹화해둔다.** 심사위원이 접속했을 때 로딩 중이어도 영상은 남는다
- 제출 문서에 "첫 접속 시 서버 기동에 30초가 소요될 수 있습니다"라고 한 줄 적어둔다

**모델 파일이 없어도 서버는 뜬다.** 그 경우 룰 검사 15개만으로 동작하고(재현율 86.7%), 분류기 층만 조용히 빠진다. 빌드 중 학습이 실패해도 서비스가 죽지는 않는다.

**수정 후 재배포**는 push만 하면 된다.

```powershell
git add .
git commit -m "무엇을 고쳤는지"
git push
```

Render가 자동으로 다시 빌드한다.

---

## 배포 후 남은 일

배포가 끝나야 나머지를 마음 놓고 할 수 있다. 순서대로.

1. **데모 영상 60초 녹화** — 윈도우는 `Win + G`로 화면 녹화가 된다
2. **제출 문서 작성** — `PLAN.md`에 "AI 활용 방식" 초안이 있다
3. **학습 데이터 추가** — 클래스당 28개 → 40개면 정확도 80% 근처. 남는 시간에 한다
4. **`eval/probe.py`에 새 케이스 추가** — 지금 9건은 전부 통과해서 변별력이 없다
