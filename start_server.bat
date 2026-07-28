@echo off
title Dashboard Fertilizantes - Servidor Local
echo.
echo ============================================================
echo   Dashboard Fertilizantes para el Bienestar 2026
echo   Servidor Local con Actualizacion Automatica SURI
echo ============================================================
echo.

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python no esta instalado o no esta en PATH.
    echo Instale Python 3.10+ desde https://python.org
    pause
    exit /b 1
)

REM Install dependencies if needed
echo [INFO] Verificando dependencias...
pip install -r requirements.txt -q 2>nul

REM Install Playwright browsers if needed
echo [INFO] Verificando navegador Playwright...
python -m playwright install chromium --with-deps 2>nul

echo.
echo [OK] Iniciando servidor en http://localhost:8080
echo [OK] Presione Ctrl+C para detener el servidor.
echo.

python server.py

pause
