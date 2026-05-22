@echo off
echo ===========================================
echo DailyStockV2 Environment Launcher
echo ===========================================

REM 使用使用者提供的位置
set CONDA_PATH=C:\ProgramData\Anaconda3\Scripts\activate.bat

if not exist "%CONDA_PATH%" (
    echo [ERROR] Could not find activate.bat at %CONDA_PATH%
    echo Please check the path and try again.
    pause
    exit /b 1
)

echo Found Conda at: %CONDA_PATH%
echo Activating 'base' environment...
call "%CONDA_PATH%" base

echo.
echo Environment activated!
echo Current Python:
where python
echo.

REM 切換到專案目錄
cd /d "%~dp0"

echo You can now run 'python main.py'
echo.

REM 保持視窗開啟
cmd /k
