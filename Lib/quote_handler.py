"""
報價回呼模組 — 處理 Shioaji tick 回呼並寫入 Redis

選擇權 volume 為觸發時間後的增量（非交易所當日累計量）。
清除 Redis 後會自動重新計算價平、重新訂閱、重建 baseline。
"""
import json
import time
from datetime import datetime
from Lib import config
from Lib.contracts import get_option_contracts
from Lib.logger import log


class QuoteHandler:
    """封裝報價回呼的狀態與邏輯"""

    def __init__(self, api, r, trigger_time: str, option_mode: str):
        self.api = api
        self.r = r
        self.trigger_time = trigger_time
        self.option_mode = option_mode
        self.is_options_active = False
        self.active_contracts = []      # 當前訂閱的合約物件清單
        self.volume_baseline = {}       # {code: 首次 total_volume} 用於計算增量
        self.last_index_price = None    # 記錄最新加權指數，供 ATM 計算使用

    def _calculate_atm(self, futures_price: float) -> int:
        """根據設定決定使用加權指數或期貨價格計算價平 (四捨五入)"""
        if config.ATM_SOURCE == "index" and self.last_index_price is not None:
            price_to_use = self.last_index_price
            log(f"使用加權指數計算價平，參考價格: {price_to_use}")
        else:
            price_to_use = futures_price
            if config.ATM_SOURCE == "index":
                log(f"大盤資料尚未收齊，退回使用期貨價格計算價平: {price_to_use}")
            else:
                log(f"使用期貨價格計算價平: {price_to_use}")

        atm = round(price_to_use / config.STRIKE_STEP) * config.STRIKE_STEP
        return atm

    def _subscribe_options(self, atm: int):
        """訂閱選擇權：取消舊訂閱 → 清除 baseline → 訂閱新合約"""
        # 1. 取消舊訂閱
        for con in self.active_contracts:
            try:
                self.api.quote.unsubscribe(con)
            except Exception:
                pass

        # 2. 清除舊的 baseline
        self.volume_baseline.clear()

        # 3. 篩選並訂閱新合約
        contracts = get_option_contracts(self.api, atm, mode=self.option_mode)
        for con in contracts:
            if config.SUBSCRIBE_DELAY > 0:
                time.sleep(config.SUBSCRIBE_DELAY)
            self.api.quote.subscribe(con)

        self.active_contracts = contracts
        self.is_options_active = True
        log(f"成功訂閱 {len(contracts)} 檔選擇權 (ATM={atm})")

    def on_quote(self, topic, quote):
        """指數/股票報價回呼 — 由 set_quote_callback 觸發

        參數:
            topic: str, 如 "I/TSE/001"
            quote: dict, 欄位值可能是 float 或 list
        """
        now_str = datetime.now().strftime("%H:%M:%S")

        code = quote.get("Code", "")

        # 大盤指數: topic="I/TSE/001", Code="001" → 映射為 "TSE001"
        if isinstance(topic, str) and topic.startswith("I/"):
            code = "TSE001"
        elif not code and isinstance(topic, str) and "/" in topic:
            code = topic.rsplit("/", 1)[-1]

        if not code:
            return

        # Close 和 VolSum 可能是 list 或 float
        close_raw = quote.get("Close", [0])
        close = close_raw[0] if isinstance(close_raw, list) else close_raw
        vol_raw = quote.get("VolSum", [0])
        total_vol = vol_raw[0] if isinstance(vol_raw, list) else vol_raw

        try:
            price = float(close)
            volume = int(total_vol)

            if code == "TSE001":
                self.last_index_price = price
                data = {"p": price, "v": volume, "t": now_str}
                print(f"[DEBUG] 大盤 Callback 值: {data}")
                self.r.hset(config.REDIS_SNAPSHOT_KEY, code, json.dumps(data))
                log(f"大盤: {price}")

        except Exception as e:
            log(f"指數回呼處理錯誤 ({code}): {e}")

    def on_tick_fop(self, exchange, tick):
        """期貨/選擇權 Tick 回呼 — 由 set_on_tick_fop_v1_callback 觸發

        參數:
            exchange: Exchange enum (如 Exchange.TAIFEX)
            tick: TickFOPv1 物件, 有 .code, .close, .total_volume 等屬性
        """
        now_str = datetime.now().strftime("%H:%M:%S")

        code = tick.code
        close = tick.close
        total_vol = tick.total_volume if hasattr(tick, "total_volume") else 0

        if not code:
            return

        try:
            price = float(close)
            volume = int(total_vol)

            # A. 期貨 tick — 只寫入 TX00
            if "TXF" in code or (code.startswith("TX") and len(code) == 5):
                data = {"p": price, "v": volume, "t": now_str}
                print(f"[DEBUG] 近月期貨 Callback 值: {data}")
                self.r.hset(config.REDIS_SNAPSHOT_KEY, "TX00", json.dumps(data))
                log(f"期貨({code}): {price}")

                # 到達觸發時間 → 訂閱選擇權
                if now_str >= self.trigger_time and not self.is_options_active:
                    atm = self._calculate_atm(price)
                    log(f"觸發！最終決定價平: {atm}")
                    self._subscribe_options(atm)

                # 偵測 Redis 被清除 → 重新計算價平並重新訂閱
                elif self.is_options_active and not self.r.hexists(config.REDIS_SNAPSHOT_KEY, "TX00"):
                    atm = self._calculate_atm(price)
                    log(f"偵測到 Redis 已清除，重新訂閱！最終決定價平: {atm}")
                    self._subscribe_options(atm)

            # B. 選擇權 — volume 用增量（扣除 baseline）
            else:
                if code not in self.volume_baseline:
                    self.volume_baseline[code] = volume
                    log(f"建立 baseline: {code}, total_volume={volume}")

                delta_volume = volume - self.volume_baseline[code]
                data = {"p": price, "v": delta_volume, "t": now_str}
                self.r.hset(config.REDIS_SNAPSHOT_KEY, code, json.dumps(data))

        except Exception as e:
            log(f"期貨/選擇權回呼處理錯誤 ({code}): {e}")

    def register(self):
        """將回呼註冊到 Shioaji

        需要註冊兩個 callback:
        - set_quote_callback: 處理指數/股票 (topic: str, quote: dict)
        - set_on_tick_fop_v1_callback: 處理期貨/選擇權 (exchange, tick)
        """
        self.api.quote.set_quote_callback(self.on_quote)
        self.api.quote.set_on_tick_fop_v1_callback(self.on_tick_fop)
        log("報價回呼已註冊 (指數 + 期貨/選擇權)")
