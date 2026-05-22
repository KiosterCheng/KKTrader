"""
心跳模組 — 定時寫入 Redis 存活燈號維持連線
"""
import threading
import time
from Lib import config
from Lib.logger import log


def start_heartbeat(r):
    """啟動背景心跳執行緒"""
    def _beat():
        while True:
            try:
                r.set(config.REDIS_HEARTBEAT_KEY, "running", ex=config.HEARTBEAT_TTL)
            except Exception:
                pass
            time.sleep(config.HEARTBEAT_INTERVAL)

    t = threading.Thread(target=_beat, daemon=True)
    t.start()
    log("心跳執行緒已啟動")
