# -*- coding: utf-8 -*-
"""
base_monitor.py — 數據接收基類 (BaseMonitor)

將「資料來源 -> Redis Snapshot -> Redis PubSub -> BarGenerator 聚合」的資料處理管線 (Pipeline) 抽象化，
讓系統不只支援台灣期貨，還能以相同模式支援加密貨幣交易所 (如 Binance) 或美股報價。
"""

import json
import time
import threading
from datetime import datetime
from Lib import config
from Lib.bar_generator import BarGenerator
from Lib.logger import log


class BaseMonitor:
    """資料監控接收器基類"""
    def __init__(self, source_name: str, r):
        """
        參數:
            source_name: 資料源識別名稱，例如 "FT" (期貨) 或 "Crypto" (加密貨幣)
            r: 已連線的 Redis client 實例
        """
        self.source_name = source_name.upper()
        self.r = r
        self.targets = []
        self.generators = {}
        
        # 依資料源名稱動態產生 Redis Key 名稱，保持結構一致
        self.snapshot_key = f"{self.source_name}:Snapshot"
        self.heartbeat_key = f"status:{self.source_name.lower()}_ingestor:heartbeat"
        
        # 預設 Tick 歷史保留長度
        self.tick_limit = 500

    def init_generators(self, targets: list):
        """為訂閱的商品初始化 BarGenerator"""
        self.targets = targets
        for code in targets:
            # 初始化時傳入對應的資料源名稱，BarGenerator 會自動動態計算對應的 Redis Key
            self.generators[code] = BarGenerator(code, self.r, source_name=self.source_name)
            log(f"[{self.source_name}] 已為 {code} 初始化 BarGenerator")

    def process_tick(self, code: str, price: float, volume: int, total_volume: int = 0):
        """
        標準化 Tick 處理管線 (Pipeline)：
          1. 寫入該資料源的最新價 Snapshot 哈希表 (Redis Hash)
          2. 發布即時 Tick 廣播 (Redis Pub/Sub)
          3. 寫入 Tick 歷史清單並限長 (Redis List)
          4. 餵入 BarGenerator 進行 1分K / 5分K 的即時更新
        """
        now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # 含毫秒的本機時間

        try:
            price = float(price)
            volume = int(volume)
            total_volume = int(total_volume)

            # 1. 寫入 Snapshot 最新價快照
            snapshot_data = {
                "p": price,
                "v": volume,
                "t": now_str[:8],  # HH:MM:SS
                "tv": total_volume
            }
            self.r.hset(self.snapshot_key, code, json.dumps(snapshot_data))

            # 2. Redis Pub/Sub 即時廣播 Tick
            pub_data = {
                "code": code,
                "price": price,
                "volume": volume,
                "time": now_str,
                "total_vol": total_volume
            }
            self.r.publish(f"{self.source_name}:Tick:{code}", json.dumps(pub_data))

            # 3. 寫入 Tick 明細 List 並限長
            tick_list_key = f"{self.source_name}:Ticks:{code}"
            self.r.rpush(tick_list_key, json.dumps(pub_data))
            self.r.ltrim(tick_list_key, -self.tick_limit, -1)

            # 4. 餵入 BarGenerator 計算 1分K / 5分K
            if code in self.generators:
                self.generators[code].handle_tick(price, volume, now_str[:8])

        except Exception as e:
            log(f"[{self.source_name}] 處理 Tick 錯誤 ({code}): {e}")

    def start_heartbeat(self):
        """啟動背景存活心跳執行緒 (預設 TTL 10 秒，每 5 秒更新)"""
        def heartbeat_task():
            while True:
                try:
                    self.r.set(self.heartbeat_key, "running", ex=10)
                except Exception:
                    pass
                time.sleep(5)
                
        t = threading.Thread(target=heartbeat_task, daemon=True)
        t.start()
        log(f"[{self.source_name}] 存活心跳執行緒已啟動 -> {self.heartbeat_key}")

    def start_active_emitter(self):
        """啟動主動定時定稿與補零 K 線引擎 (Active Emitter)"""
        def emitter_task():
            while True:
                try:
                    now_str = datetime.now().strftime("%H:%M:%S")
                    for generator in self.generators.values():
                        generator.check_and_finalize(now_str)
                except Exception as e:
                    log(f"[{self.source_name}] Active Emitter 遭遇錯誤: {e}")
                time.sleep(1)
                
        t = threading.Thread(target=emitter_task, daemon=True)
        t.start()
        log(f"[{self.source_name}] 主動定時定稿與補零 K 線引擎已啟動 (Active Emitter)")
