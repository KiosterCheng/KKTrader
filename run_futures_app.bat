@echo off
title KKTrader Futures Ingestor One-Click Startup

echo ============================================================
echo  KKTrader Futures Ingestor One-Click Startup (Local Redis)
echo ============================================================
echo.

:: 1. Check if Redis is already running on port 6379
echo [Step 1/3] Detecting local Redis status...
netstat -ano | findstr 6379 >nul
if %errorlevel% equ 0 (
    echo [ALREADY RUNNING] Local Redis is already active.
    goto start_app
)

echo [NOT RUNNING] Local Redis is offline. Attempting auto-start...

:: 2.1 Try starting as Windows Service (net start redis)
echo.
echo Attempt A: Starting Windows Redis Service...
net start redis >nul 2>&1
if %errorlevel% equ 0 (
    echo [SUCCESS] Redis service started successfully.
    goto wait_and_start
)

:: 2.2 Try starting redis-server from Path environment variable
echo.
echo Attempt B: Searching and starting redis-server from Path...
where redis-server >nul 2>&1
if %errorlevel% equ 0 (
    echo Found redis-server in Path, starting in background...
    start /b redis-server >nul 2>&1
    goto wait_and_start
)

:: 2.3 Try starting from current directory
if exist "redis-server.exe" (
    echo Found redis-server.exe in current directory, starting...
    start /b redis-server.exe >nul 2>&1
    goto wait_and_start
)

:: 2.4 Try starting from common Program Files directory
if exist "C:\Program Files\Redis\redis-server.exe" (
    echo Found redis-server.exe in C:\Program Files\Redis\, starting...
    start /b "" "C:\Program Files\Redis\redis-server.exe" >nul 2>&1
    goto wait_and_start
)

echo.
echo [FAIL] Unable to auto-start Redis. Please make sure:
echo    1. Redis is installed on this Windows PC.
echo    2. Redis folder is added to Path environment variables.
echo    3. Or try running this batch file as Administrator (Right click -> Run as Admin).
echo.
choice /t 5 /d y /n /m "Do you want to run the python app anyway?"
if %errorlevel% equ 2 goto end
goto start_app

:wait_and_start
echo Waiting for Redis to initialize (2 seconds)...
timeout /t 2 /nobreak >nul

:start_app
echo.
echo ============================================================
echo [Step 3/3] Starting FuturesMonitor.py...
echo ============================================================
echo.
python FuturesMonitor.py

:: ============================================================
:: Lifecycle Cleanup: This executes AFTER FuturesMonitor.py stops
:: ============================================================
echo.
echo ============================================================
echo  [Step 4/4] Ingestor stopped. Cleaning up local resources...
echo ============================================================
echo.

:: A. Attempt to stop Windows native Redis service
echo Stopping Windows Redis service...
net stop redis >nul 2>&1

echo.
echo [SUCCESS] All local Windows Redis services stopped safely.
echo ============================================================

:end
pause
