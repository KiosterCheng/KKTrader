# -*- coding: utf-8 -*-
"""
sqlite_logger.py — 獨立的 SQLite K 線歷史資料記錄器 (完全解耦，可移植)

使用方法:
  python sqlite_logger.py
"""

import os
import json
import time
import sqlite3
import threading
import configparser
from datetime import datetime

# 檢查必要套件
try:
    import redis
except ImportError:
    print("\n[ERROR] 缺少 redis 套件，請執行: pip install redis\n")
    import sys
    sys.exit(1)

# ----------------------------------------------------
# 1. 讀取設定檔 (支援尋找目前目錄或上層目錄的 settings.ini)
# ----------------------------------------------------
config_parser = configparser.ConfigParser()
ini_name = "settings.ini"
ini_path = ini_name

# 如果當前目錄找不到，往上一層目錄找 (方便放在獨立資料夾中執行)
if not os.path.exists(ini_path):
    ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ini_name)
    
if not os.path.exists(ini_path):
    raise FileNotFoundError(f"找不到設定檔 settings.ini (搜尋路徑: {os.path.abspath(ini_name)} 或 {os.path.abspath(ini_path)})")

config_parser.read(ini_path, encoding="utf-8")

# Redis 連線設定組裝
use_cloud = config_parser.getboolean("Redis", "use_cloud_redis", fallback=False)
password = config_parser.get("Redis", "password", fallback="")
if use_cloud:
    host = config_parser.get("Redis", "cloud_host")
    port = config_parser.getint("Redis", "cloud_port")
else:
    host = config_parser.get("Redis", "local_host", fallback="localhost")
    port = config_parser.getint("Redis", "local_port", fallback=6379)

if password and password.strip():
    REDIS_URL = f"redis://default:{password}@{host}:{port}"
else:
    REDIS_URL = f"redis://{host}:{port}"

# 讀取期貨訂閱標的
FT_TARGETS = [t.strip() for t in config_parser.get("Futures", "targets", fallback="TXFR1,TXFR2").split(",") if t.strip()]

# SQLite 資料庫儲存路徑 (預設放在 settings.ini 相同目錄下，方便統一管理)
_DB_PATH = os.path.join(os.path.dirname(ini_path), "history.db")

# ----------------------------------------------------
# 2. SQLite 資料庫初始化與寫入
# ----------------------------------------------------
def init_db():
    """初始化 SQLite 資料庫與建立 Table"""
    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS klines (
            code TEXT,
            interval INTEGER,
            datetime TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY (code, interval, datetime)
        )
    """)
    conn.commit()
    conn.close()


def save_to_sqlite(code: str, interval: int, bar_data: dict):
    """將單根 K 線存入 SQLite"""
    try:
        init_db()
        today_str = datetime.today().strftime("%Y-%m-%d")
        datetime_str = f"{today_str} {bar_data['time']}"
        
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO klines (code, interval, datetime, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            code,
            interval,
            datetime_str,
            float(bar_data['open']),
            float(bar_data['high']),
            float(bar_data['low']),
            float(bar_data['close']),
            int(bar_data['volume'])
        ))
        conn.commit()
        conn.close()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [SQLite] 已寫入 {code} {interval}M K棒: {datetime_str} | C={bar_data['close']} V={bar_data['volume']}")
    except Exception as e:
        print(f"[SQLite 寫入錯誤] {e}")


# ----------------------------------------------------
# 3. 背景心跳與主程式
# ----------------------------------------------------
def heartbeat_task(r):
    """向 Redis 註冊心跳 (status:sqlite_logger:heartbeat)"""
    while True:
        try:
            r.set("status:sqlite_logger:heartbeat", "running", ex=10)
        except Exception:
            pass
        time.sleep(5)


def main():
    print("=" * 60)
    print(" KKTrader 獨立 SQLite K 線資料記錄器 (SQLiteLogger) 啟動")
    print("=" * 60)
    print(f"Redis 連線目標: {REDIS_URL.split('@')[-1]}")
    print(f"SQLite 儲存路徑: {os.path.abspath(_DB_PATH)}")
    
    # 建立 Redis 連線
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        print("Redis 連線成功！")
    except Exception as e:
        print(f"無法連線至 Redis: {e}")
        return

    # 啟動心跳執行緒
    t_hb = threading.Thread(target=heartbeat_task, args=(r,), daemon=True)
    t_hb.start()
    print("心跳服務已啟動 (status:sqlite_logger:heartbeat)")

    # 訂閱模式：監聽所有來源 (如 FT/Crypto/ST) 的 1分K 與 5分K 定稿廣播
    pubsub = r.pubsub()
    pubsub.psubscribe("*:K1:Final:*")
    pubsub.psubscribe("*:K5:Final:*")
    print("訂閱 K 線定稿通知中 (*:K1:Final:* 與 *:K5:Final:*)...")
    print("開始監聽事件... (按 Ctrl+C 結束)")

    try:
        for message in pubsub.listen():
            # 模式訂閱傳回的訊息類型為 'pmessage'
            if message['type'] != 'pmessage':
                continue
            
            channel = message['channel']
            # 解析頻道取得商品代碼與週期, 例: "FT:K5:Final:TXFR1" -> "TXFR1" & 5
            parts = channel.split(":")
            
            try:
                interval = int(parts[1][1:]) # "K5" -> 5
                code = parts[-1]             # "TXFR1"
                bar_data = json.loads(message['data'])
                save_to_sqlite(code, interval, bar_data)
            except Exception as e:
                print(f"解析或儲存廣播資料錯誤: {e}")
                
    except KeyboardInterrupt:
        print("\n中斷訊號觸發，記錄器安全退出。")
    finally:
        pubsub.close()
        r.close()


if __name__ == "__main__":
    main()
