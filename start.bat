@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================================
echo  근로계약서 점검 서비스
echo ============================================================
echo  실행 위치 : %CD%
echo.

if not exist "server.py" (
    echo  [문제] 이 폴더에 server.py 가 없습니다.
    echo         이 파일은 프로젝트 폴더 안에 있어야 합니다.
    echo.
    pause
    exit /b 1
)

where python > nul 2>&1
if errorlevel 1 (
    echo  [문제] python 을 찾을 수 없습니다.
    echo         파이썬을 설치하거나 PATH 에 추가한 뒤 다시 실행하세요.
    echo.
    pause
    exit /b 1
)

echo  [1/3] 필요한 패키지를 확인합니다...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo  [문제] 패키지 설치에 실패했습니다.
    pause
    exit /b 1
)

echo  [2/3] 판정 모델을 확인합니다...
if not exist "data\clause_clf.joblib" (
    echo        조항 분류기를 학습합니다. 10초쯤 걸립니다...
    python scripts\train_classifier.py > nul
)
if not exist "data\doctype_clf.joblib" (
    echo        문서 종류 분류기를 학습합니다...
    python scripts\train_doctype.py > nul
)

echo  [3/3] 서버를 시작합니다.
echo.
echo ============================================================
echo  브라우저에서 아래 주소로 접속하세요.
echo.
echo      http://127.0.0.1:5000
echo.
echo  끄려면 이 창에서 Ctrl + C 를 누르세요.
echo ============================================================
echo.

start "" http://127.0.0.1:5000
python server.py

pause
