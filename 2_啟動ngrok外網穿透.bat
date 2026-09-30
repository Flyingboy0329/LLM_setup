@echo off
title ngrok Tunnel - LLM Setup
cd /d "%~dp0"

echo ======================================================================
echo   [ngrok Tunnel Service] Connecting to fixed domain...
echo   - Local Port: http://localhost:8080
echo   - Public URL: https://consumer-herbicide-clergyman.ngrok-free.dev
echo ======================================================================

where ngrok >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] ngrok.exe not found in PATH or current folder!
    echo Please make sure ngrok is installed.
    echo ======================================================================
    pause
    exit /b
)

ngrok http 8080 --url https://consumer-herbicide-clergyman.ngrok-free.dev

pause
