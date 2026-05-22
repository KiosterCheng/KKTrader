"""
BarGenerator 模組 — 負責將期貨即時 Tick 資料聚合成 1分K 與 5分K
並將實時進度與定稿結果寫入 Redis。
"""
import json
from datetime import datetime
from Lib import config
from Lib.logger import log


class Bar:
    """單一 K 線的資料結構"""
    def __init__(self, time_str: str, price: float, volume: int = 0):
        self.time = time_str      # 對齊後的時間 "HH:MM:00"
        self.open = price
        self.high = price
        self.low = price
        self.close = price
        self.volume = volume

    def update(self, price: float, volume: int):
        """用新的成交更新 K 線"""
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class BarGenerator:
    """處理單一商品 (Code) 的 1分K 與 5分K 聚合器"""
    def __init__(self, code: str, r):
        self.code = code
        self.r = r
        
        # 記憶體中當前進行中的 Bar (real-time bar)
        self.current_k1 = None  # type: Bar
        self.current_k5 = None  # type: Bar

    @staticmethod
    def _align_time(time_str: str, interval: int) -> str:
        """向下捨去對齊時間字串（標示為 K 線開盤/開始時間，與股票軟體一致）
        支援 1 或 5 分鐘
        輸入格式: "HH:MM:SS" 或 "HH:MM:SS.mmm"
        輸出格式: "HH:MM:00"
        """
        parts = time_str.split(":")
        if len(parts) < 2:
            now = datetime.now()
            hh = now.hour
            mm = now.minute
        else:
            try:
                # 去除前後空格，並強制轉型為整數，保證格式一致
                hh = int(parts[0].strip())
                mm = int(parts[1].strip())
            except ValueError:
                now = datetime.now()
                hh = now.hour
                mm = now.minute
        
        # 向下捨去對齊 (K 線開始時間對齊)
        if interval == 5:
            mm = (mm // 5) * 5
            
        return f"{hh:02d}:{mm:02d}:00"

    def handle_tick(self, price: float, volume: int, time_str: str):
        """核心進入點：處理一筆新 Tick
        
        參數:
            price: 最新成交價 (float)
            volume: 單筆成交量 (int)
            time_str: Tick 時間，如 "09:01:23"
        """
        # A. 處理 1分K
        self._process_bar_interval(price, volume, time_str, interval=1)
        
        # B. 處理 5分K
        self._process_bar_interval(price, volume, time_str, interval=5)

    def _process_bar_interval(self, price: float, volume: int, time_str: str, interval: int):
        """通用區間 K 線更新邏輯"""
        aligned_time = self._align_time(time_str, interval)
        current_bar = self.current_k1 if interval == 1 else self.current_k5
        
        limit = config.FT_K1_LIMIT if interval == 1 else config.FT_K5_LIMIT
        latest_key = config.REDIS_FT_K1_LATEST if interval == 1 else config.REDIS_FT_K5_LATEST
        list_key = f"FT:K1:List:{self.code}" if interval == 1 else f"FT:K5:List:{self.code}"
        pub_channel = f"FT:K1:Final:{self.code}" if interval == 1 else f"FT:K5:Final:{self.code}"

        # 1. 首次初始化
        if current_bar is None:
            new_bar = Bar(aligned_time, price, volume)
            if interval == 1:
                self.current_k1 = new_bar
            else:
                self.current_k5 = new_bar
            
            # 更新 Redis「即時進行中 K 線」快照
            self.r.hset(latest_key, self.code, new_bar.to_json())
            return

        # 2. 邊界檢查：跨越至下一根 K 線 (對齊後時間大於記憶體中的 K 線時間)
        # 用字串比較大小是安全的，因為 "09:02:00" > "09:01:00"
        if aligned_time > current_bar.time:
            # 2.1 定稿上一根 K 線並寫入 Redis 歷史清單
            bar_data = current_bar.to_dict()
            json_data = json.dumps(bar_data)
            
            self.r.rpush(list_key, json_data)
            self.r.ltrim(list_key, -limit, -1)  # 保留最近 N 根
            
            # 2.2 發布定稿廣播
            self.r.publish(pub_channel, json_data)
            log(f"[{self.code}] 定稿 {interval}分K: {bar_data['time']} | O={bar_data['open']}, H={bar_data['high']}, L={bar_data['low']}, C={bar_data['close']}, V={bar_data['volume']}")

            # 2.3 初始化新一根 K 線
            new_bar = Bar(aligned_time, price, volume)
            if interval == 1:
                self.current_k1 = new_bar
            else:
                self.current_k5 = new_bar

            # 更新 Redis 最新一根快照
            self.r.hset(latest_key, self.code, new_bar.to_json())

        # 3. 在同一區間內：更新現有 K 線
        elif aligned_time == current_bar.time:
            current_bar.update(price, volume)
            
            # 即時寫回 Redis 最新一根快照
            self.r.hset(latest_key, self.code, current_bar.to_json())
            
        # 4. 極端情況：收到歷史 Tick (例如網路延遲嚴重的 Tick)
        else:
            # 略過或僅作為 log，不影響當前即時 K 線
            pass
