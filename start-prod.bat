@echo off
echo Starting EV Charging Station Predictor (Production Mode)

REM 프로덕션 환경변수 파일 로드
set ENV_FILE=.env.production

REM 프로덕션 환경 설정 확인
if exist %ENV_FILE% (
    echo Loading production environment from %ENV_FILE%
    REM 환경변수 설정을 위해 .env.production 파일을 복사
    copy %ENV_FILE% .env.temp
    for /f "delims=" %%i in (.env.temp) do set %%i
    del .env.temp
) else (
    echo Error: %ENV_FILE% not found. Please create production environment file.
    pause
    exit /b 1
)

REM 프로덕션 서버 시작
echo.
echo Starting backend server in production mode...
cd backend
start "Backend Server (Production)" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 32375 --workers 4"

echo.
echo Starting frontend build...
cd ..\frontend
call npm run build
if %errorlevel% neq 0 (
    echo Frontend build failed!
    pause
    exit /b 1
)

echo.
echo Starting frontend server in production mode...
call npm run preview

echo.
echo Production servers are running...
echo - Backend: http://220.69.200.55:32375
echo - Frontend: http://220.69.200.55:32376
echo - API Docs: http://220.69.200.55:32375/docs

pause