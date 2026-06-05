# 📊 KKTrader — 台指期貨即時監控與 K 線量化戰情室 🚀

> [!IMPORTANT]
> **🚀 開發環境與虛擬環境啟動重要提示（必看）**
> 
> 本專案使用指定的 Conda 虛擬環境執行 Python 程式。**在進行任何開發、語法驗證（如 `py_compile`）或執行腳本前，請務必先執行以下環境啟動器**：
> *   **PowerShell 使用者**：請在專案根目錄下執行 `.\start_py.ps1` (或 `start_py.ps` 以載入環境)。
> *   **Windows 傳統 CMD 使用者**：請雙擊或執行 `start_py.bat`。
> 
> 這些啟動器會自動加載位於 `C:\ProgramData\Anaconda3\Scripts\activate.bat` 的 Conda `base` 虛擬環境，確保 `shioaji`, `redis`, `pandas` 等關鍵套件在正確的路徑中。

KKTrader 是一套專為台灣期貨市場（台指期貨）設計的 **工業級即時報價監控、K 線聚合與量化交易視覺化系統**。

本系統採用 **生產者–消費者 (Producer-Consumer) 與微服務解耦 (Decoupling) 架構**，以高性能的 **Redis** 記憶體緩衝區作為高速中介通訊層，確保盤中高頻 Tick 報價採集、K 線切片指標計算、及視覺化展示之間 100% 獨立運行，徹底告別傳統單體交易程式卡死、漏單與閃退的缺陷。

---

## 📖 核心設計理念與微服務總架構

本系統將整體量化交易微服務劃分為 **4 支盤中常駐程式** 與 **1 支盤後離線回測程式**，盤中各自獨立運作、互不干擾，統一透過 Redis 進行通訊。

### 系統資料流架構圖

```text
[ 盤中即時流動 ]

券商 API (永豐金 Shioaji)
   │
   ▼
[1. 期貨報價接收端] (FuturesMonitor.py)
   │
   ▼ (高速寫入 / 發布)
 ⭕ Redis 記憶體中介層 (即時快照、K線歷史列表)
   │
   ├─► [4. 歷史資料記錄器 (Data Logger)] ──► 💾 SQLite 歷史庫 (盤後分析子彈)
   │
   ├─► [2. 策略與指標運算引擎] (計算 MA, 波動度, 產生買賣訊號)
   │      │
   │      ▼ (發布策略訊號 Signal)
   │    ⭕ Redis 記憶體中介層
   │      │
   │      ▼ (監聽訊號)
   │    [3. 風控與自動下單執行器] ──► 送單至券商 API
   │
   └─► 🖥️ [視覺化監控看板] (check_futures.py 戰情室 / show_kline.py 網頁)
```

---

## 🛠️ 1. 台指期貨即時監控與 K 線聚合系統 (FuturesMonitor)

本模組實作了台指期貨近月（`TXFR1`）與次近月（`TXFR2`）Tick 報價接收、K 線即時切片、以及大師級看盤驗證面板。

### 🚀 核心黑科技與架構亮點

1.  **智慧一鍵綠色部署與自動喚醒 Redis 核心**
    *   一鍵啟動腳本 `run_futures_app.bat` 會自動檢測 localhost `6379` 埠口。若 Redis 未運行，會自動發起極速下載，並 **僅提取核心執行檔 `redis-server.exe` 寫入專案目錄**，既保持了專案目錄的極致乾淨，又實現了「開箱即用、零秒安裝」的極致體驗！
2.  **高階原生 PowerShell TcpClient 埠口偵測**
    *   不再使用易受 Windows 本地語言環境或編碼錯位干擾的 `netstat` 命令，改用 .NET 原生的 `TcpClient` 套接字進行連線探針。**100% 根絕了 `'tstat'` 等神祕的指令解析錯誤！**
3.  **雙重行情降維回呼容錯 (Double Channel Fallback)**
    *   為了解決 Shioaji 最新 SolaceAPI 在下午 3 點以後的**「期貨夜盤行情漏報」**底層 Bug，同時註冊了新版 Solace 期權回呼 `set_on_tick_fop_v1_callback` 與通用廣播回呼 `set_quote_callback`，**100% 絕對不會漏接任何一筆夜盤報價！**
4.  **交割年月動態對照字典 (Delivery Month Alias Mapper)**
    *   啟動時自動抓取期貨合約並依交割月份升冪排序，將真實合約代碼（如 `TXFF6`）對應還原為穩定的連續月別名（如 `TXFR1`）寫入 Redis，解決了讀寫端合約代碼不匹配的通病。
5.  **台灣標準 K 線「向下捨去開盤對齊」與雙位數強固補零**
    *   **開盤對齊時間戳記**：符合台灣主流股票與期貨軟體直覺（向下捨去，Bar Open Time），例如 `20:01:30` 的第一筆 Tick 歸入 `20:01:00` K 棒；而 `20:02:00 ~ 20:02:59` 的成交資料，則完整歸入第二根 `20:02:00` 1分K 棒中，確保數值毫釐不差。
    *   **時間戳記強固補零**：對小時與分鐘進行雙位數補零（如 `09:00:00`），**徹底消滅了** Redis 字串大小比較中 `"09:00:00" > " 9:00:00"` 判定跨越 K 棒的經典時序 Bug。
6.  **大師級 K 線互動驗證面板 (Streamlit + Plotly 每秒絲滑呼吸跳動) 📊**
    *   **台灣紅綠配色 K 線燭台**：上半部顯示極致精緻的 Candlestick（收漲為紅，收跌為綠），下半部為交易量副圖。
    *   **前端動態重採樣 (Resampling)**：背景只需接收 1分K 數據，網頁前端能動態融合成 `5分K / 15分K / 30分K / 60分K / 日K`，極大地節省了背景的系統資源！
    *   **每秒絲滑呼吸跳動**：採用虛擬 DOM 與 Canvas 渲染，頁面以 1 秒為間隔在原地自動呼吸刷新最新 Tick 數據，絕不閃爍！
    *   **核對價格專用手動鎖定**：切換至「手動刷新」可定格圖表，方便滑鼠縮放與核對數值。
    *   **價格精度優化**：Y 軸價格刻度自動格式化為整數精度（f5.0），視覺最清爽乾淨！

---

## ⚙️ 2. 系統配置與一鍵啟動指南

為了簡化部署，系統將所有敏感金鑰、Redis 連線配置及監控參數統一合併管理在 **`settings.ini`** 當中。

### 統一設定檔 `settings.ini` 說明
```ini
[Redis]
# True: 雲端 Redis / False: 本機 Redis
use_cloud_redis = False
cloud_host = redis-xxxxx.cloud.redislabs.com
cloud_port = 18301
local_host = localhost
local_port = 6379
# 連線密碼 (無密碼時留空)
password = 

[Shioaji]
simulation = True               # True: 模擬環境 / False: 正式環境
api_key = your_shioaji_api_key
secret_key = your_shioaji_secret_key
```

---

### 📂 專案結構大圖

```text
OptionMonitor/
├── settings.ini               # 唯一合併設定檔 (Redis、Shioaji 密鑰及參數)
├── requirements.txt           # 前端 Web (Streamlit/Plotly) 依賴套件
│
├── run_futures_app.bat        # 一鍵智慧喚醒 Redis、拉起期貨接收端 (FuturesMonitor.py)
├── run_check_futures.bat      # 一鍵啟動 Windows cmd ANSI 絲滑戰情室監控 (check_futures.py)
├── run_kline_dashboard.bat    # 一鍵啟動大師級每秒絲滑呼吸 K 線互動看板 (show_kline.py)
│
└── Lib/                       # 核心共享模組庫
    ├── config.py              # 從 settings.ini 載入與組裝 Redis URL (安全免 secrets.ini)
    ├── connection.py          # Shioaji 登入及 Redis 連線管理 (含重試、keepalive 與健康檢查)
    ├── bar_generator.py       # 台灣標準 K 線「向下捨去開盤對齊」與雙位數強固補零切片引擎
    ├── heartbeat.py           # 背景心跳 daemon 執行緒
    ├── logger.py              # 統一日誌格式化輸出 [HH:MM:SS]
    └── redis_utils.py         # Redis 盤前清理工具
```

---

### ⭕ Redis 即時資料結構 snapshots 定義

#### 1. 期貨即時快照 (Hash: `FT:Snapshot`)
*   **Field**: `TXFR1` (近月)、`TXFR2` (次近月)。
*   **Value** (JSON): `{"p": 21500.0, "v": 5, "tv": 16822, "t": "21:08:39"}` (最新價、單筆量、總累計量、時間)。

#### 2. 期貨歷史 K 線列表 (List: `FT:K1:List:{code}` & `FT:K5:List:{code}`)
*   **儲存方式**: Redis List。每次新 K 線定稿時，以 JSON 字串 `RPUSH` 寫入歷史列表中。
*   **Value** (JSON): `{"time": "20:02:00", "open": 21501.0, "high": 21505.0, "low": 21499.0, "close": 21502.0, "volume": 124}`。

---

### 🕹️ 一鍵啟動指令矩陣

| 監控標的 | 指令/啟動腳本 | 說明 |
|---|---|---|
| **期貨系統** | **雙擊執行 `run_futures_app.bat`** | 一鍵智慧喚醒並下載 Redis，並自動啟動期貨行情接收程式與 K 線聚合引擎 (`FuturesMonitor.py`)。 |
| **期貨戰情室** | **雙擊執行 `run_check_futures.bat`** | 一鍵啟動 Windows cmd 原地消閃爍即時行情監控戰情室。 |
| **期貨 K 線看板** | **雙擊執行 `run_kline_dashboard.bat`** | 一鍵啟動並在瀏覽器中彈出大師級每秒絲滑呼吸跳動的 K 線互動驗證看板。 |

---

### 🎓 快速環境建置指引
1.  **初始化 Streamlit 前端網頁環境**（首次使用）：
    ```cmd
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    ```
2.  打開 **`settings.ini`**，填入您的 Shioaji `api_key` 與 `secret_key`。
3.  一鍵啟動對應的腳本，開啟您在 KKTrader 的極致期貨交易與監控之旅！ 📈🎉
