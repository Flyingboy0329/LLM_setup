@echo off
chcp 65001 >nul
title LLM_SetUp Studio v1.0
cd /d "%~dp0"

echo ========================================================
echo   🟣 LLM_SetUp Studio - 賽博工控 AI 調度工作站
echo   Developed by Pan Bo-Han (潘柏翰)
echo ========================================================
echo.
echo [系統] 正在喚醒硬體遙測與推論中樞...

python gui\app_window.py

if %errorlevel% neq 0 (
    echo.
    echo [錯誤] 啟動失敗，請確認 Python 環境與依賴套件是否已安裝。
    pause
)