@echo off
title KKTrader Futures Real-time Console Monitor
echo ============================================================
echo  KKTrader 期貨即時戰情室 — 一鍵啟動監控
echo ============================================================
echo.
echo [Step 1/1] Starting check_futures.py in live mode...
echo.
python check_futures.py --live
echo.
pause
