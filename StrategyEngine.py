# -*- coding: utf-8 -*-
"""
StrategyEngine.py — 獨立、解耦的量化策略指標運算引擎

功能說明:
  1. 訂閱模式: 使用 Redis Pub/Sub 訂閱「定稿 K 線頻道」(如: FT:K1:Final:TXFR1)，完全不需訂閱高頻 Tick。
  2. 模組化設計: 策略計算邏輯與接收端完全解耦。未來若要接入股票或加密貨幣，只需修改 Redis 訂閱頻道。
  3. 指標運算: 當收到 1分K 定稿時，從 Redis List 中拉取最近的歷史 K 線，利用 pandas 計算 5MA (簡單移動平均線)。
  4. 訊號廣播: 產生 BUY / SELL 訊號後，再次以標準 JSON 廣播至 Redis 訊號中介層，供自動下單執行器監聽。

用法:
  python StrategyEngine.py
"""

import json
import redis
import pandas as pd
from Lib.config import REDIS_URL
from Lib.logger import log


def calculate_strategy(df: pd.DataFrame) -> str:
    """
    量化策略判定邏輯 (以 5MA 移動平均線黃金交叉 / 死亡交叉為例)
    
    參數:
      df: 包含歷史 K 線數據的 DataFrame (至少包含 time, open, high, low, close, volume)
    
    回傳:
      "BUY" (買入訊號), "SELL" (賣出訊號), 或 None (無訊號)
    """
    if len(df) < 6:
        # 數據量不足，無法計算 5MA
        return None
    
    try:
        # 1. 強制轉型價格為 float，確保計算正確
        df['close'] = df['close'].astype(float)
        
        # 2. 計算 5MA (Simple Moving Average)
        df['ma5'] = df['close'].rolling(window=5).mean()
        
        # 3. 取得最新一根 K 棒與前一根 K 棒的數值進行交叉判定
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        last_close = last_row['close']
        last_ma5 = last_row['ma5']
        prev_close = prev_row['close']
        prev_ma5 = prev_row['ma5']
        
        # 判斷 ma5 是否為有效值 (排除 NaN)
        if pd.isna(last_ma5) or pd.isna(prev_ma5):
            return None
            
        log(f"[策略運算] 前一根收盤={prev_close:.1f} (MA5={prev_ma5:.1f}) | 最新收盤={last_close:.1f} (MA5={last_ma5:.1f})")
        
        # 黃金交叉：前一根收盤價 <= 前一根 MA5，且最新收盤價 > 最新 MA5
        if prev_close <= prev_ma5 and last_close > last_ma5:
            return "BUY"
            
        # 死亡交叉：前一根收盤價 >= 前一根 MA5，且最新收盤價 < 最新 MA5
        elif prev_close >= prev_ma5 and last_close < last_ma5:
            return "SELL"
            
    except Exception as e:
        log(f"策略指標計算錯誤: {e}")
        
    return None


def main():
    log("=" * 60)
    log("KKTrader 獨立量化策略運算引擎 — 啟動")
    log("=" * 60)

    # 1. 建立 Redis 連線
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        log("Redis 連線成功 (PING OK)")
    except Exception as e:
        log(f"無法連線至 Redis: {e}")
        return

    # 2. 建立訂閱器並訂閱定稿 K 線頻道
    # 【未來擴充指引】：
    #   - 股票訂閱： "K1:Final:stock:2330"
    #   - 虛擬貨幣訂閱："K1:Final:crypto:BTCUSDT"
    #   目前維持與期貨接收器一致的 "FT:K1:Final:TXFR1"
    target_channel = "FT:K1:Final:TXFR1"
    history_list_key = "FT:K1:List:TXFR1"
    
    pubsub = r.pubsub()
    pubsub.subscribe(target_channel)
    log(f"策略引擎已成功訂閱定稿 K 線訊號，監聽頻道: {target_channel}")
    log("等待新 K 線定稿中... (Ctrl+C 結束)")

    try:
        for message in pubsub.listen():
            # 排除訂閱確認等元數據訊息，只處理真實廣播
            if message['type'] != 'message':
                continue
            
            try:
                # 3. 解析定稿 K 線數據
                new_bar = json.loads(message['data'])
                log(f"\n[🟢 收到定稿 K 線] 時間: {new_bar['time']} | 收盤: {new_bar['close']} | 成交量: {new_bar['volume']}")
                
                # 4. 從 Redis 歷史列表中拉取最近的 K 線數據 (通常取最近 50-100 根即可)
                # Redis List 儲存的是定稿歷史，-30 到 -1 代表最近的 30 根 K 線
                history_raw = r.lrange(history_list_key, -30, -1)
                if not history_raw:
                    log("⚠️ Redis 歷史 K 線列表為空，等待更多數據累積...")
                    continue
                    
                bars = [json.loads(item) for item in history_raw]
                df = pd.DataFrame(bars)
                
                # 5. 執行策略判定
                signal = calculate_strategy(df)
                
                if signal:
                    # 6. 發布策略買賣訊號至獨立頻道 "FT:Strategy:Signal"
                    signal_payload = {
                        "code": "TXFR1",
                        "action": signal,
                        "price": float(new_bar['close']),
                        "time": new_bar['time'],
                        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    signal_json = json.dumps(signal_payload)
                    r.publish("FT:Strategy:Signal", signal_json)
                    
                    log(f"🚨🚨🚨 策略觸發買賣訊號！發布廣播 -> {signal_payload}")
                
            except json.JSONDecodeError:
                log(f"解析 K 線 JSON 失敗: {message['data']}")
            except Exception as e:
                log(f"處理定稿消息時發生錯誤: {e}")

    except KeyboardInterrupt:
        log("接收到中斷訊號，策略引擎安全退出")
    finally:
        pubsub.close()
        r.close()
        log("Redis 連線已關閉，程式結束")


if __name__ == "__main__":
    main()
