# 🪙 加密貨幣交易所數據對接指引 (Crypto Integration Guide)

為了讓 KKTrader 能夠擴充接收數位貨幣交易所（如 Binance, OKX, Bybit 等）的即時數據，我們重新設計並抽象化了數據管線 (Data Pipeline)。

本專案現已內建 **`BaseMonitor` 基類**，它將「接收 Tick ➔ Redis 快照 ➔ Redis 廣播 ➔ K線聚合 ➔ 存活心跳」等核心數據處理程序全部標準化。對接新交易所時，您只需要專注於「交易所連線與數據解析」即可。

---

## 🛠️ 1. 對接 Binance (幣安) 範例實作

以下是一個完整的範例程式碼，展示如何使用 `websocket-client` 訂閱幣安的即時交易 (Trade) 串流，並直接利用我們的系統生成 **加密貨幣的 1分K 與 5分K**。

### 📄 `BinanceMonitor.py` (範例程式)

```python
# -*- coding: utf-8 -*-
"""
BinanceMonitor.py — 幣安即時數據接收與 K 線轉換器 (範例)
"""

import json
import time
import redis
import websocket  # pip install websocket-client
from Lib.base_monitor import BaseMonitor
from Lib.logger import log

class BinanceMonitor(BaseMonitor):
    """幣安即時 Tick 數據接收器"""
    def __init__(self, r):
        # 1. 呼叫基類初始化，將資料源命名為 "Crypto"
        # 基類會自動生成:
        #   - Snapshot Key: "Crypto:Snapshot"
        #   - Heartbeat Key: "status:crypto_ingestor:heartbeat"
        #   - K線頻道: "Crypto:K1:Final:{Symbol}" 與 "Crypto:K5:Final:{Symbol}"
        super().__init__(source_name="Crypto", r=r)
        self.ws = None

    def start(self, symbols: list):
        # 2. 初始化目標商品（例如 ["BTCUSDT", "ETHUSDT"]）的 BarGenerator
        self.init_generators(symbols)
        
        # 3. 啟動基類的心跳與主動定稿補零引擎 (Active Emitter)
        self.start_heartbeat()
        self.start_active_emitter()
        
        # 4. 開始連線幣安 Websocket
        self._connect_websocket(symbols)

    def _connect_websocket(self, symbols: list):
        # 幣安 ws 連線網址，將商品名稱轉為小寫
        streams = "/".join([f"{s.lower()}@trade" for s in symbols])
        ws_url = f"wss://stream.binance.com:9443/ws/{streams}"
        
        log(f"[Binance] 正在連接 Websocket: {ws_url}")
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        self.ws.run_forever()

    def _on_message(self, ws, message):
        data = json.loads(message)
        # 幣安 trade 數據格式:
        #   - 's': Symbol (商品)
        #   - 'p': Price (成交價)
        #   - 'q': Quantity (成交量)
        symbol = data.get("s")
        price = float(data.get("p", 0.0))
        qty = float(data.get("q", 0.0)) # 虛擬貨幣量可為小數，系統內會自動轉為整數或保留精度
        
        # 5. 呼叫基類的標準化 tick 處理管線！
        # 這一行代碼會自動幫您: 寫入快照、廣播 Tick、記錄 List、生成 1分K/5分K 並廣播！
        self.process_tick(symbol, price, int(qty))

    def _on_error(self, ws, error):
        log(f"[Binance] Websocket 錯誤: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        log("[Binance] Websocket 連線已關閉")


if __name__ == "__main__":
    # 連線 Redis
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    
    # 建立監控實例
    monitor = BinanceMonitor(r)
    
    # 訂閱商品並啟動
    targets = ["BTCUSDT", "ETHUSDT"]
    monitor.start(targets)
```

---

## 📡 2. 產生的 Redis 資料結構對照

當啟動上述 `BinanceMonitor.py` 後，系統會在 Redis 中產生與台指期**完全鏡像對稱**的資料字典：

| 資料類型 | 期貨通道 (FT) | 加密貨幣通道 (Crypto) |
| :--- | :--- | :--- |
| **最新價快照 (Hash)** | `FT:Snapshot` | `Crypto:Snapshot` |
| **存活心跳 (String)** | `status:ft_ingestor:heartbeat` | `status:crypto_ingestor:heartbeat` |
| **即時 Tick 廣播** | `FT:Tick:TXFR1` | `Crypto:Tick:BTCUSDT` |
| **即時進行中 K 線** | `FT:K1:Latest` | `Crypto:K1:Latest` |
| **K 線定稿歷史 (List)** | `FT:K5:List:TXFR1` | `Crypto:K5:List:BTCUSDT` |
| **K 線定稿廣播 (Channel)** | `FT:K5:Final:TXFR1` | `Crypto:K5:Final:BTCUSDT` |

---

## 📈 3. 盤後 SQLite 記錄器與 Telegram 移植
因為我們已經將 `SQLiteLogger` 與 `TelegramSender` 模組化且各自獨立，您如果要擴充加密貨幣的儲存與發送，只需做微幅的移植：

1.  **複製 `SQLiteLogger` 資料夾**，修改其訂閱頻道為 `Crypto:K1:Final:*` 與 `Crypto:K5:Final:*`。
2.  資料庫寫入程式碼（`save_to_sqlite`）完全不用動，它會自動將商品代碼 `BTCUSDT` 與時間週期寫入 `klines` 資料表中，與 `TXFR1` 和諧共存於同一個 `history.db` 內！
3.  **複製 `TelegramSender` 資料夾**，修改其訂閱頻道與 K 線讀取參數，即可每 5 分鐘發送精美的 BTC K 線燭台圖到您的手機！
