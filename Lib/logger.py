"""
日誌模組 — 統一的 console 輸出格式
"""
from datetime import datetime


def log(msg: str):
    """帶時間戳記的日誌輸出"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
