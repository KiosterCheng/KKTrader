# 💾 SQLite K 線歷史記錄器 (SQLiteLogger)

本目錄包含一個獨立的 **SQLite K 線記錄器**，它完全與主系統的報價接收解耦。它會訂閱 Redis 的 K 線定稿廣播，並自動寫入 `history.db` 本地資料庫。

## 📂 移植說明 (How to Transplant)
本程式具有 100% 的獨立性，不依賴本專案 `Lib/` 底下的任何程式碼。移植到其他主機或專案時：
1. 複製整個 `SQLiteLogger` 資料夾。
2. 確保目標環境中有一個 `settings.ini` 設定檔。
   * 本程式會優先尋找同目錄下的 `settings.ini`。
   * 若找不到，則會自動搜尋上層目錄中的 `settings.ini`。
3. 確保安裝了 `redis` 套件：
   ```cmd
   pip install redis
   ```

## 🚀 執行方法
在虛擬環境下，執行以下指令啟動：
```cmd
python sqlite_logger.py
```

## 📊 資料庫欄位結構
資料會儲存於 `history.db`（與 `settings.ini` 同目錄下）的 `klines` 資料表中：
* `code`: 商品代碼 (例如: `TXFR1`)
* `interval`: 時間框架週期 (1 代表 1分K，5 代表 5分K)
* `datetime`: 完整日期時間 (例如: `2026-06-14 09:00:00`)
* `open`, `high`, `low`, `close`: 開高低收價格 (REAL)
* `volume`: 成交量 (INTEGER)
* **主鍵 (PRIMARY KEY)**: `(code, interval, datetime)`，可完全避免重複寫入。
