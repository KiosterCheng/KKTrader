# 📊 Telegram K 線圖表發送器 (TelegramSender)

本目錄包含一個獨立的 **多時框 Telegram K 線圖表自動發送服務**，它完全與主系統的報價接收端解耦。它會訂閱 Redis 的 `*:K1:Final:*` 頻道，在每一根 1分K 定稿時，自動觸發重採樣運算。若重採樣後的時框（如 2分K, 3分K, 5分K, 15分K, 30分K, 60分K, 日K）也在此刻定稿，程式會自動從 SQLite 讀取最近的歷史資料、使用 matplotlib 繪製深色看盤圖表，並打包發送至您的 Telegram。

## 📂 移植說明 (How to Transplant)
本模組具有 100% 的獨立可移植性，不依賴本專案 `Lib/` 底下的任何程式碼。移植到其他主機或專案時：
1. 複製整個 `TelegramSender` 資料夾。
2. 確保安裝了必要套件（**免安裝 requests，防範 OpenSSL 錯誤**）：
   ```cmd
   pip install matplotlib pandas redis
   ```
3. 確保目標環境中有 `settings.ini` 與隨附的 SQLite 資料庫 `history.db`（放在與 `settings.ini` 同級的目錄下即可）。
   * 程式會自動尋找同目錄或上層目錄的 `settings.ini` 與 `history.db`。

## 🚀 執行方法
在已安裝套件的虛擬環境下執行：
```cmd
python telegram_sender.py
```

## ⚙️ 參數設定 (settings.ini)
請在 `settings.ini` 的 `[Telegram]` 區塊填入您的設定：
* `bot_token`: 您的 Telegram Bot API Token
* `chat_id`: 您的 Telegram Chat ID (個人或群組)
* `enable_send`: 必須設為 `True` 才會實際發送圖片。
* `send_bar_count`: 圖表顯示的歷史 K 線根數 (預設為 `100` 根)
* `active_rules`: 要啟用的發送規則名稱清單 (例如 `TXF_Day, BTC_Data`)

### 規則定義 (格式):
`規則名稱 = 商品代碼 | 週期清單 | 交易時段名稱`
* 例如: `TXF_Day = TXFR1 | 5,15,30,60,1440 | session_tw_fut_day`

### 交易時段配置 ([Sessions]):
您可在 `settings.ini` 的 `[Sessions]` 區塊自訂各市場的時間段，重採樣引擎會自動進行時段重置計算，避免休市空窗影響指標。
* 例如: `session_tw_fut_full = 15:00-23:59, 00:00-05:00, 08:45-13:45`

