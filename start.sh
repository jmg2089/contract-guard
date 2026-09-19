#!/usr/bin/env bash
# 맥·리눅스용. 윈도우는 start.bat 을 쓴다.
cd "$(dirname "$0")" || exit 1

echo "실행 위치: $(pwd)"
[ -f server.py ] || { echo "[문제] 이 폴더에 server.py 가 없습니다."; exit 1; }

python3 -m pip install -q -r requirements.txt || exit 1
[ -f data/clause_clf.joblib ]  || python3 scripts/train_classifier.py > /dev/null
[ -f data/doctype_clf.joblib ] || python3 scripts/train_doctype.py  > /dev/null

echo
echo "http://127.0.0.1:5000 으로 접속하세요. 끄려면 Ctrl+C."
echo
python3 server.py
