@echo off
echo Starting EV Charging Station Predictor (Development Mode)

REM 환경변수 파일 로드
set ENV_FILE=.env

REM 개발 환경 설정 확인
if exist %ENV_FILE% (
    echo Loading environment from %ENV_FILE%
) else (
    echo Warning: %ENV_FILE% not found. Using default values.
)

REM 백엔드 및 프론트엔드 시작
echo.
echo Starting backend server...
cd backend
start "Backend Server" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 32375 --reload"

echo.
echo Starting frontend server...
cd ..\frontend
start "Frontend Server" cmd /k "npm run dev"

echo.
echo Servers are starting...
echo - Backend: http://localhost:32375
echo - Frontend: http://localhost:32377 (or next available port)
echo - API Docs: http://localhost:32375/docs

pause