"""
FuturesMonitor.py — 期貨即時 Tick 接收與 K 線轉換程式 (Pipeline 架構)

Pipeline 流程:
  1. Init     → 載入設定、解析期貨訂閱標的
  2. Connect  → 建立 Redis + Shioaji 連線
  3. Cleanup  → 清除前一交易日期貨相關資料
  4. Register → 註冊期權 Tick 回呼，綁定 K 線生成器
  5. Subscribe→ 動態尋找期貨合約並訂閱 (TXFR1 & TXFR2)
  6. Heartbeat→ 啟動背景心跳執行緒 (status:ft_ingestor:heartbeat)
  7. Run      → 主迴圈等待 Tick 跳動

用法:
  python FuturesMonitor.py
"""

import argparse
import json
import signal
import threading
import time
from datetime import datetime

import pandas as pd
from Lib import config
from Lib.base_monitor import BaseMonitor
from Lib.connection import connect_redis, connect_shioaji, disconnect
from Lib.logger import log


class FuturesQuoteHandler(BaseMonitor):
    """處理期貨 Tick 回呼並發送至 BarGenerator 的 Handler"""
    def __init__(self, api, r):
        # 呼叫基類初始化，將資料源設為 "FT" (Futures)
        super().__init__(source_name="FT", r=r)
        self.api = api
        self.subscribed_codes = []  # 已成功訂閱的真實合約代碼清單 (如 ["TXFF6", "TXFG6"])
        self.code_map = {}          # 對照字典 {"TXFF6": "TXFR1"}
        self.tick_limit = config.FT_TICK_LIMIT

    def set_subscribed_codes(self, codes: list, code_map: dict):
        self.subscribed_codes = codes
        self.code_map = code_map
        # 將別名 (如 TXFR1, TXFR2) 傳送給基類的產生器初始化
        aliases = [code_map.get(c, c) for c in codes]
        self.init_generators(aliases)

    def _process_raw_tick(self, code, price, volume, total_vol):
        """核心 Tick 業務邏輯處理，將回呼介面與處理邏輯解耦"""
        log(f"[DEBUG TICK] 收到報價 -> 原始代碼: {code} | 價格: {price} | 單量: {volume} | 總量: {total_vol} | 訂閱列表: {self.subscribed_codes}")
        
        if not code or code not in self.subscribed_codes:
            return

        alias = self.code_map.get(code, code)
        
        # 呼叫基類的標準化處理流程
        self.process_tick(alias, price, volume, total_vol)

    def on_tick_fop(self, exchange, tick):
        """1. 新版期權 v1 Tick 回呼"""
        self._process_raw_tick(
            getattr(tick, "code", ""),
            getattr(tick, "close", 0.0),
            getattr(tick, "volume", 1),
            getattr(tick, "total_volume", 0)
        )

    def on_quote(self, topic, quote):
        """3. 通用 Quote 廣播回呼"""
        code = quote.get("Code", "")
        if not code and isinstance(topic, str) and "/" in topic:
            code = topic.rsplit("/", 1)[-1]
            
        if not code:
            return
            
        close_raw = quote.get("Close", [0.0])
        close = close_raw[0] if isinstance(close_raw, list) else close_raw
        vol_raw = quote.get("VolSum", [0])
        total_vol = vol_raw[0] if isinstance(vol_raw, list) else vol_raw
        
        self._process_raw_tick(code, close, 1, total_vol)


# ───────────────────────────────────────────
# Pipeline 各階段
# ───────────────────────────────────────────

def stage_init() -> list:
    """Stage 1: 載入設定，解析要訂閱的期貨標的"""
    targets = config.FT_TARGETS
    log(f"解析到期貨標的數量: {len(targets)} | 標的: {targets}")
    return targets


def stage_connect():
    """Stage 2: 建立 Redis & Shioaji 連線"""
    r = connect_redis()
    api = connect_shioaji()
    return api, r


def stage_cleanup(r, targets):
    """Stage 3: 盤前清理該標的之前殘留的 Redis 資料"""
    # 3.1 刪除 Snapshot
    r.delete(config.REDIS_FT_SNAPSHOT_KEY)
    r.delete(config.REDIS_FT_K1_LATEST)
    r.delete(config.REDIS_FT_K5_LATEST)
    r.delete(config.REDIS_FT_HEARTBEAT_KEY)
    
    # 3.2 刪除每個商品的 List (Tick List & K線 List)
    for code in targets:
        r.delete(f"FT:Ticks:{code}")
        r.delete(f"FT:K1:List:{code}")
        r.delete(f"FT:K5:List:{code}")
            
    log(f"Redis 盤前期貨快照與歷史 K 線/Tick 清理完畢")


def stage_register(api, r) -> FuturesQuoteHandler:
    """Stage 4: 註冊報價回呼 (雙重回呼通道，防範 Shioaji 夜盤漏報 Bug)"""
    handler = FuturesQuoteHandler(api, r)
    
    # 註冊新版 FOP 管道
    api.quote.set_on_tick_fop_v1_callback(handler.on_tick_fop)
    # 註冊 Quote 廣播管道
    api.quote.set_quote_callback(handler.on_quote)
    
    log("已註冊雙重期貨行情回呼通道 (FOP_v1 + Quote廣播)，完整覆蓋夜盤報價")
    return handler


def stage_subscribe(api, targets) -> tuple:
    """Stage 5: 搜尋期貨合約並完成訂閱 (TXFR1 & TXFR2)"""
    subscribed_codes = []  # 這將會是真實代碼列表, 如 ['TXFF6', 'TXFG6']
    code_map = {}          # {真實代碼: 別名}, 如 {"TXFF6": "TXFR1", "TXFG6": "TXFR2"}
    log("開始篩選與訂閱期貨合約...")

    # 1. 取得所有 TXF 的具體月份合約，並按交割年月排序
    txf_category = getattr(api.Contracts.Futures, "TXF", None)
    contract_alias_map = {}
    if txf_category:
        # 篩選出具體月份合約 (排除別名如 TXFR1, TXFR2)
        real_contracts = [c for c in txf_category if len(c.code) == 5 and not c.code.startswith("TXFR")]
        # 按交割年月排序
        real_contracts.sort(key=lambda c: c.delivery_month)
        
        # 近月真實合約與次近月真實合約
        real_txfr1 = real_contracts[0] if len(real_contracts) > 0 else None
        real_txfr2 = real_contracts[1] if len(real_contracts) > 1 else None
        
        # 將別名對應到真實合約物件
        if real_txfr1:
            contract_alias_map["TXFR1"] = real_txfr1
        if real_txfr2:
            contract_alias_map["TXFR2"] = real_txfr2

    # 2. 進行訂閱與對照字典建立
    for t in targets:
        try:
            # 從我們的動態對映中取得真實合約物件，若無則降維使用 Shioaji 原生屬性
            contract = contract_alias_map.get(t, getattr(api.Contracts.Futures, t, None))
            
            if contract:
                api.quote.subscribe(contract)
                subscribed_codes.append(contract.code)
                code_map[contract.code] = t  # 建立對照，如 {"TXFF6": "TXFR1"}
                log(f"成功訂閱期貨: {contract.code} (交易所: {contract.exchange}) -> 對應別名: {t}")
                time.sleep(0.2)
            else:
                log(f"找不到 {t} 的有效期貨合約")
                
        except Exception as e:
            log(f"訂閱 {t} 失敗: {e}")

    log(f"訂閱完成！共訂閱 {len(subscribed_codes)} 檔期貨合約: {subscribed_codes}")
    return subscribed_codes, code_map


# (已由 BaseMonitor 基類替代，刪除冗餘程式碼)


def stage_run():
    """Stage 7: 主迴圈等待"""
    log("期貨資料接收程式啟動完成，等待 Tick 報價與 K 線轉換中... (Ctrl+C 結束)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("接收到中斷訊號，準備關閉連線...")


# ───────────────────────────────────────────
# 主程式入口
# ───────────────────────────────────────────

def main():
    api = None
    r = None
    
    # 允許 Ctrl+C 優雅中斷
    signal.signal(signal.SIGINT, signal.default_int_handler)

    try:
        log("=" * 60)
        log("KKTrader 期貨即時資料接收與 K 線轉換系統 — 啟動")
        log("=" * 60)

        # Pipeline
        targets = stage_init()               # 1. Init
        api, r = stage_connect()             # 2. Connect
        stage_cleanup(r, targets)            # 3. Cleanup
        handler = stage_register(api, r)     # 4. Register callback
        codes, code_map = stage_subscribe(api, targets)# 5. Subscribe contracts
        handler.set_subscribed_codes(codes, code_map)  # 綁定已訂閱的合約與對照字典給 Handler
        handler.start_heartbeat()            # 6. Heartbeat (自基類繼承)
        handler.start_active_emitter()       # 6.5 Active Emitter (自基類繼承)
        stage_run()                          # 7. Run

    except Exception as e:
        log(f"期貨接收程式發生嚴重錯誤: {e}")
    finally:
        log("正在清理資源並關閉連線...")
        disconnect(api, r)
        log("系統已安全中斷，程式結束")


if __name__ == "__main__":
    main()
