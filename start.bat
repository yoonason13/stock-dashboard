@echo off
chcp 65001 > nul
echo === 주식 AI 대시보드 시작 ===
echo.

cd /d "%~dp0"

REM 가상환경이 없으면 생성
if not exist "venv" (
    echo [1/3] 가상환경 생성 중...
    python -m venv venv
)

REM 패키지 설치
echo [2/3] 패키지 설치 중...
call venv\Scripts\activate
pip install -r requirements.txt -q

REM .env 파일 확인
if not exist ".env" (
    echo.
    echo [!] .env 파일이 없습니다.
    echo     .env.example 을 복사해서 .env 로 만들고
    echo     ANTHROPIC_API_KEY 를 입력해주세요.
    echo.
    pause
    exit /b 1
)

echo [3/3] 서버 시작 중... (http://localhost:5000)
echo.
python app.py
pause
