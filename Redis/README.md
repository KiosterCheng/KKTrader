# ⭕ Windows Redis 伺服器綠色安裝包 (Redis)

本目錄包含適用於 Windows 64位元系統的 **Redis 記憶體資料庫綠色版** 二進位檔案及設定檔。

## 📂 移植說明 (How to Transplant)
本目錄是完全獨立的綠色免安裝包。若要在其他 Windows 伺服器或個人電腦上部署 Redis：
1. 複製整個 `Redis` 資料夾。
2. 雙擊執行 `redis-server.exe`，或在命令列中帶設定檔啟動即可：
   ```cmd
   redis-server.exe redis.windows.conf
   ```

## ⚙️ 核心檔案清單
* `redis-server.exe`: Redis 伺服器主進程。
* `redis-cli.exe`: Redis 命令列控制台（可用於測試與查詢資料）。
* `redis.windows.conf`: 本地運行設定檔（預設監聽 `localhost:6379`，無密碼）。
* `dump.rdb`: Redis 資料持久化磁碟快照檔案。

## 🛠️ 常用指令與維護
如果您需要手動進行管理，可在本目錄開啟命令列並執行：

* **測試連線 (Ping)**:
  ```cmd
  redis-cli.exe ping
  ```
  *(回傳 `PONG` 代表伺服器正常運作中)*

* **清除所有快取資料 (Flush All)**:
  ```cmd
  redis-cli.exe flushall
  ```

* **查詢所有 Key**:
  ```cmd
  redis-cli.exe keys *
  ```
