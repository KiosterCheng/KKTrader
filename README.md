# 📊 KKTrader — 台指期貨即時監控、量化交易與視覺化戰情室 🚀

> [!IMPORTANT]
> ### 🚨 **重要開發與執行前置步驟 (必看)**
> 本專案使用指定的 Conda 虛擬環境執行 Python 程式。**在進行任何開發、代碼閱讀、語法驗證（如 `py_compile`）或執行任何腳本前，請務必先載入環境啟動器**：
> *   **Windows 傳統 CMD 使用者**：請雙擊或在終端機執行 `start_py.bat`。
> *   **PowerShell 使用者**：請在專案根目錄下執行 `.\start_py.ps1` (或 `start_py.ps` 以載入環境)。
> 
> 這些啟動器會自動載入位於 `C:\ProgramData\Anaconda3\Scripts\activate.bat` 的 Conda `base` 虛擬環境，確保 `shioaji`, `redis`, `pandas`, `matplotlib`, `requests` 等關鍵套件在正確的路徑中。若未安裝相關套件，請在已載入環境的視窗中執行：
> ```cmd
> pip install -r requirements.txt
> ```

---

## 📖 1. 系統架構與設計理念

KKTrader 是一套專為台灣期貨市場（台指期貨）設計的 **工業級即時報價監控、K 線聚合與量化交易視覺化系統**。

本系統採用 **生產者–消費者 (Producer-Consumer) 與微服務解耦 (Decoupling) 架構**，以高性能的 **Redis** 記憶體緩衝區作為高速中介通訊層，確保盤中高頻 Tick 報價採集、K 線切片指標計算、資料持久化寫入及視覺化展示之間 100% 獨立運行，徹底告別傳統單體交易程式卡死、漏單與閃退的缺陷。

### 系統資料流與模組關係圖

```text
[ 盤中即時流動 ]

券商 API (永豐金 Shioaji)
   │
   ▼
[1. 期貨報價接收端] (FuturesMonitor.py)
   │
   ▼ (高速寫入 / 發布)
 ⭕ Redis 記憶體中介層 (Redis/)
   │
   ├─► [2. 歷史資料記錄器] (SQLiteLogger/sqlite_logger.py) ──► 💾 history.db (SQLite 歷史庫)
   │
   ├─► [3. 策略與指標運算引擎] (StrategyEngine.py)
   │      │
   │      ▼ (發布策略訊號 Signal)
   │    ⭕ Redis 記憶體中介層 (頻道: FT:Strategy:Signal)
   │      │
   │      ▼ 
   │    [風控與自動下單執行器] (預留擴充) ──► 送單至券商 API
   │
   ├─► [4. K線圖表發送器] (TelegramSender/telegram_sender.py) ──► 📱 Telegram 手機監控
   │
   └─► 🖥️ [視覺化監控看板] (check_futures.py 戰情室 / show_kline.py 網頁)
```

---

## 📂 2. 目錄結構與模組分工

```text
KKTrader/
├── settings.ini               # 核心設定檔 (Redis、Shioaji 密鑰、Telegram 與監控參數)
├── requirements.txt           # 專案依賴套件清單 (Pip 安裝對象)
├── start_py.bat               # Conda 虛擬環境啟動器 (Windows CMD)
├── start_py.ps1               # Conda 虛擬環境啟動器 (PowerShell)
│
├── run_futures_app.bat        # 一鍵智慧喚醒 Redis、拉起期貨接收端 (FuturesMonitor.py)
├── run_sqlite_logger.bat      # 一鍵啟動 SQLite 資料庫記錄服務 (SQLiteLogger)
├── run_telegram_sender.bat    # 一鍵啟動 Telegram 圖表發送服務 (TelegramSender)
├── run_check_futures.bat      # 一鍵啟動 CMD 原地消閃爍即時行情監控戰情室 (check_futures.py)
├── run_kline_dashboard.bat    # 一鍵啟動 Streamlit 網頁互動式驗證看板 (show_kline.py)
│
├── FuturesMonitor.py          # 數據採集端：訂閱 Shioaji 行情，發送 Tick 並透過 BarGenerator 生成 K 線
├── StrategyEngine.py          # 策略計算端：訂閱定稿 K 線頻道，計算 5MA 平均線並發布買賣訊號
├── check_futures.py           # 監控終端：即時從 Redis 讀取快照與心跳，渲染文字戰情室
├── show_kline.py              # 網頁控制台：Streamlit + Plotly 每秒自動重繪/重採樣 K 線圖表
│
├── Redis/                     # 【獨立資料夾】Windows Redis 64位元綠色免安裝伺服器包
│   ├── redis-server.exe       # Redis 伺服器主進程
│   ├── redis-cli.exe          # Redis 命令行工具
│   └── README.md              # Redis 移植與維護說明文件
│
├── SQLiteLogger/              # 【獨立資料夾】SQLite K 線歷史記錄器 (高移植性)
│   ├── sqlite_logger.py       # 訂閱 Redis 定稿事件，寫入 history.db
│   └── README.md              # 移植與資料庫欄位說明文件
│
├── TelegramSender/            # 【獨立資料夾】Telegram 圖表發送器 (高移植性)
│   ├── telegram_sender.py     # 訂閱 Redis 定稿，從 SQLite 抓取歷史並用 matplotlib 繪圖發送
│   └── README.md              # 移植與設定說明文件
│
└── Lib/                       # 核心共享模組庫
    ├── config.py              # 解析 settings.ini
    ├── connection.py          # 管理 Redis 連線 (含重試、keepalive) 與 Shioaji API 登入
    ├── bar_generator.py       # 核心 K 線切片與對齊引擎 (含向下對齊與補零機制)
    ├── heartbeat.py           # 背景守護執行緒：行情接收器心跳
    └── logger.py              # 格式化日誌輸出工具
```

---

## 🔌 3. 服務狀態監測 (Heartbeat Mechanism)

為了利於無介面雲端部署與本機排障，本系統內建了全方位的 **Redis 心跳燈號機制**。各個常駐服務在啟動後都會在背景註冊一個存活 Key（生存時間 TTL 為 10 秒，每 5 秒更新一次）：

1.  **行情接收器**：`status:ft_ingestor:heartbeat`
2.  **策略計算機**：`status:strategy_engine:heartbeat`
3.  **圖表發送器**：`status:telegram_sender:heartbeat`
4.  **SQLite 記錄器**：`status:sqlite_logger:heartbeat`

這些狀態會即時反映在 `check_futures.py` 終端機戰情室中。若某個服務中斷，對應燈號會立刻變為紅色（🔴 已停止）。

---

## ⚙️ 4. 核心排程發送配置 (settings.ini)

`TelegramSender` 使用了高彈性的過濾與時段重採樣架構，全部設定皆透過 `settings.ini` 集中管理：

### 4.1 規則控制清單 (`[Telegram]`)
*   `active_rules`：決定當前啟用的發送規則列表（別名以逗號隔開）。
*   `規則別名 = 商品代碼 | 週期清單 | 交易時段名稱`：定義發送規則。
    *   例如：`TXF_Day = TXFR1 | 5,15,30,60,1440 | session_tw_fut_day`

### 4.2 交易時段配置 (`[Sessions]`)
時段設定決定了 K 線重採樣的邊界與日K的定稿時間點。
*   `session_tw_fut_day = 08:45-13:45` (台指期日盤)
*   `session_tw_fut_full = 15:00-23:59, 00:00-05:00, 08:45-13:45` (台指期全日盤，支援跨午夜)
*   `session_tw_stock = 09:00-13:30` (台股日盤)
*   `session_crypto = 00:00-23:59` (虛擬貨幣 24H)

---

## 🛠️ 5. 盤中一鍵啟動指令矩陣

請依序雙擊執行以下批次檔以啟動完整系統：

| 啟動順序 | 指令/啟動腳本 | 說明 |
| :--- | :--- | :--- |
| **1 (核心)** | **`run_futures_app.bat`** | 自動啟動本機 Redis 服務，並運行期貨行情接收程式與 K 線聚合引擎 (`FuturesMonitor.py`)。 |
| **2 (持久)** | **`run_sqlite_logger.bat`** | 啟動 K 線歷史資料庫寫入服務，使用 `psubscribe` 自動將所有商品 1K/5K 同步寫入 `history.db`。 |
| **3 (策略)** | **手動執行 `python StrategyEngine.py`** | 啟動量化策略運算引擎，開始監聽定稿 K 線並輸出交叉交易訊號。 |
| **4 (手機)** | **`run_telegram_sender.bat`** | 啟動 Telegram 自動圖表發送監聽器（請先於 `settings.ini` 設定 Token 與將 `enable_send` 設為 `True`）。 |
| **5 (監控)** | **`run_check_futures.bat`** | 一鍵開啟 CMD 即時不閃爍文字戰情室，隨時查看報價快照與各服務健康度。 |
| **6 (網頁)** | **`run_kline_dashboard.bat`** | 一鍵啟動 Streamlit 網頁互動式看盤控制台。 |

---

## 🤖 6. 致未來的 AI 開發夥伴：維護與修改指引

如果您是接手此專案的 AI 助手，在進行功能修改或新增策略時，請務必遵循以下規範：

### 6.1 重採樣與時段重置 (Session-Reset Resampling)
*   **行情接收端 (FuturesMonitor) 會生成 1分K 與 5分K 基礎資料**並儲存於 SQLite 資料庫。
*   其他自訂時框（例如 2分K、3分K、15分K、30分K、60分K、1440分K/日K）均由 `TelegramSender` 依據 `[Sessions]` 時段定義在 Pandas 記憶體中，以 **1分K** 為基準進行**動態重組**。這使系統能支援任何大於或等於 1 分鐘的自訂週期。
*   重組時會依據 `(trading_day, sub_session)` 進行分組重採樣，確保每個獨立交易時段（如日盤、夜盤）的邊界強制截斷重置，K 線切分不重疊。

### 6.2 零依賴發送與環境抗崩潰
*   `TelegramSender` 模組移除了對 `requests` 套件的依賴，採用 Python 內建的 `urllib.request` 進行 multipart 圖檔上傳。
*   這能防止 Windows 或 Anaconda 本機環境因 `pyopenssl` 或 `cryptography` 套件損壞引發的 SSL 連線崩潰。

### 6.3 保持高移植性目錄
*   `Redis/`、`SQLiteLogger/` 和 `TelegramSender/` 是精心設計的**完全解耦模組**。
*   當需要修改或優化這三者的功能時，請確保它們**不要引入**專案根目錄下 `Lib/` 的任何程式碼，保持其獨立載入 `settings.ini` 的能力，以方便未來隨時打包移植。

