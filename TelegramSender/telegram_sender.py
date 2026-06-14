# -*- coding: utf-8 -*-
"""
telegram_sender.py — 獨立的多時框 Telegram K 線自動發送服務 (時段重置重採樣版本)

使用方法:
  python telegram_sender.py
"""

import os
import sys
import json
import time
import sqlite3
import threading
import configparser
import urllib.request
import urllib.parse
from datetime import datetime, time as datetime_time, timedelta

# 檢查必要套件
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    import pandas as pd
    import redis
except ImportError as e:
    print(f"\n[ERROR] 缺少必要套件: {e}")
    print("請在您的虛擬環境中執行以下指令進行安裝:")
    print("pip install matplotlib pandas redis\n")
    sys.exit(1)

# ----------------------------------------------------
# 1. 讀取設定檔 (支援尋找目前目錄或上層目錄的 settings.ini)
# ----------------------------------------------------
config_parser = configparser.ConfigParser()
ini_name = "settings.ini"
ini_path = ini_name

# 如果當前目錄找不到，往上一層目錄找 (方便放在獨立資料夾中執行)
if not os.path.exists(ini_path):
    ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ini_name)
    
if not os.path.exists(ini_path):
    raise FileNotFoundError(f"找不到設定檔 settings.ini (搜尋路徑: {os.path.abspath(ini_name)} 或 {os.path.abspath(ini_path)})")

config_parser.read(ini_path, encoding="utf-8")

# Redis 連線設定組裝
use_cloud = config_parser.getboolean("Redis", "use_cloud_redis", fallback=False)
password = config_parser.get("Redis", "password", fallback="")
if use_cloud:
    host = config_parser.get("Redis", "cloud_host")
    port = config_parser.getint("Redis", "cloud_port")
else:
    host = config_parser.get("Redis", "local_host", fallback="localhost")
    port = config_parser.getint("Redis", "local_port", fallback=6379)

if password and password.strip():
    REDIS_URL = f"redis://default:{password}@{host}:{port}"
else:
    REDIS_URL = f"redis://{host}:{port}"

# 讀取 Telegram 設定參數
TELEGRAM_BOT_TOKEN = config_parser.get("Telegram", "bot_token", fallback="")
TELEGRAM_CHAT_ID = config_parser.get("Telegram", "chat_id", fallback="")
TELEGRAM_ENABLE_SEND = config_parser.getboolean("Telegram", "enable_send", fallback=False)
TELEGRAM_SEND_BAR_COUNT = config_parser.getint("Telegram", "send_bar_count", fallback=100)

# SQLite 資料庫儲存路徑
_DB_PATH = os.path.join(os.path.dirname(ini_path), "history.db")

# ----------------------------------------------------
# 2. 解析規則配置與交易時段定義
# ----------------------------------------------------
# 讀取啟用的規則清單
active_rules_str = config_parser.get("Telegram", "active_rules", fallback="")
ACTIVE_RULES = [r.strip() for r in active_rules_str.split(",") if r.strip()]

# 解析每條啟用規則的詳細屬性
RULE_CONFIGS = {}
for rule in ACTIVE_RULES:
    if config_parser.has_option("Telegram", rule):
        val = config_parser.get("Telegram", rule)
        try:
            parts = val.split("|")
            code = parts[0].strip()
            intervals = [int(i.strip()) for i in parts[1].split(",") if i.strip()]
            session_name = parts[2].strip()
            RULE_CONFIGS[rule] = {
                "code": code,
                "intervals": intervals,
                "session": session_name
            }
        except Exception as e:
            print(f"[警告] 解析規則 {rule} 失敗: {e}")

# 解析 [Sessions] 時段定義
SESSION_RANGES = {}
if config_parser.has_section("Sessions"):
    for key in config_parser.options("Sessions"):
        val = config_parser.get("Sessions", key)
        ranges = []
        for r in val.split(","):
            r = r.strip()
            if not r:
                continue
            try:
                start_str, end_str = r.split("-")
                sh, sm = map(int, start_str.split(":"))
                eh, em = map(int, end_str.split(":"))
                ranges.append({
                    "start": datetime_time(sh, sm),
                    "end": datetime_time(eh, em)
                })
            except Exception as e:
                print(f"[警告] 解析時段 {key} 的區間 {r} 失敗: {e}")
        SESSION_RANGES[key] = ranges

# ----------------------------------------------------
# 3. 交易時段與重採樣 (Resampling) 計算邏輯
# ----------------------------------------------------
def is_time_in_range(t: datetime_time, start: datetime_time, end: datetime_time) -> bool:
    """判斷時間是否在區間內 (支援跨午夜)"""
    if start <= end:
        return start <= t <= end
    else: # 跨午夜情況，如 15:00-05:00
        return t >= start or t <= end

def get_session_info(dt: datetime, session_name: str):
    """
    依據時間與 Session 定義，傳回: (交易日字串, 子時段索引, 是否為有效交易時間)
    """
    t = dt.time()
    date_str = dt.strftime("%Y-%m-%d")
    
    ranges = SESSION_RANGES.get(session_name, [])
    if not ranges:
        return date_str, 0, True # 找不到配置時退化為普通日曆天
        
    for idx, r in enumerate(ranges):
        start = r["start"]
        end = r["end"]
        if is_time_in_range(t, start, end):
            trading_day = date_str
            # 交易日變更規則：若子時段起點為 15:00 且當前時間大於等於 15:00，屬於「下一個交易日」
            if start == datetime_time(15, 0) and t >= datetime_time(15, 0):
                next_day = dt + timedelta(days=1)
                # 跳過週六、週日
                while next_day.weekday() >= 5:
                    next_day += timedelta(days=1)
                trading_day = next_day.strftime("%Y-%m-%d")
            return trading_day, idx, True
            
    return date_str, -1, False

def resample_klines(df_5m: pd.DataFrame, interval: int, session_name: str) -> pd.DataFrame:
    """
    實作方案二 (時段重置)：以 (交易日, 子時段) 作為分組邊界，分別進行 Pandas 重採樣，避免休市空窗干擾
    """
    if df_5m.empty:
        return pd.DataFrame()
        
    df = df_5m.copy()
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # 標記時段資訊
    session_infos = df['datetime'].apply(lambda dt: get_session_info(dt, session_name))
    df['trading_day'] = [info[0] for info in session_infos]
    df['sub_session'] = [info[1] for info in session_infos]
    df['is_valid'] = [info[2] for info in session_infos]
    
    # 剔除非交易時段
    df = df[df['is_valid']].copy()
    if df.empty:
        return pd.DataFrame()
        
    # 依交易時間排序並分組
    df = df.sort_values('datetime')
    grouped = df.groupby(['trading_day', 'sub_session'])
    
    resampled_parts = []
    for name, group in grouped:
        group = group.set_index('datetime')
        
        # 重採樣規則 (例如 '15T', '30T', '60T')
        rule = f"{interval}T"
        agg_rules = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        
        # 使用 closed='left', label='left' 與專業看盤軟體對齊
        resampled = group.resample(rule, closed='left', label='left').agg(agg_rules)
        resampled = resampled.dropna(subset=['close'])
        resampled = resampled.reset_index()
        
        # 標回分組標籤
        resampled['trading_day'] = name[0]
        resampled['sub_session'] = name[1]
        
        resampled_parts.append(resampled)
        
    if not resampled_parts:
        return pd.DataFrame()
        
    return pd.concat(resampled_parts).sort_values('datetime').reset_index(drop=True)

# ----------------------------------------------------
# 4. SQLite 資料庫讀取與繪圖
# ----------------------------------------------------
def fetch_base_klines(code: str, limit: int) -> pd.DataFrame:
    """從 SQLite 讀取最近的 1分K 基礎資料"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        query = """
            SELECT datetime, open, high, low, close, volume 
            FROM klines 
            WHERE code = ? AND interval = 1 
            ORDER BY datetime DESC 
            LIMIT ?
        """
        df = pd.read_sql(query, conn, params=(code, limit))
        conn.close()
        
        if not df.empty:
            df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception as e:
        print(f"[SQLite 讀取錯誤] {e}")
        return pd.DataFrame()

def draw_candlestick_chart(df: pd.DataFrame, code: str, interval: int, rule_name: str) -> str:
    """繪製大師級 K 線燭台與成交量圖"""
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    
    fig.patch.set_facecolor('#0e1117')
    ax1.set_facecolor('#161b22')
    ax2.set_facecolor('#161b22')
    
    for i in range(len(df)):
        row = df.iloc[i]
        is_up = row['close'] >= row['open']
        color = '#ff3b30' if is_up else '#34c759'
        
        # 影線
        ax1.plot([i, i], [row['low'], row['high']], color=color, linewidth=1.2)
        
        # 實體
        body_bottom = min(row['open'], row['close'])
        body_height = abs(row['close'] - row['open'])
        if body_height == 0:
            body_height = 0.5
            
        rect = patches.Rectangle(
            (i - 0.3, body_bottom),
            0.6,
            body_height,
            facecolor=color,
            edgecolor=color,
            linewidth=0.5
        )
        ax1.add_patch(rect)
        
        # 成交量
        ax2.bar(i, row['volume'], color=color, alpha=0.6, width=0.6)
        
    timeframe_label = f"{interval}分K" if interval < 1440 else "日K"
    ax1.set_title(f"📊 KKTrader — {rule_name} ({timeframe_label}) 即時戰情圖", color='#f0f2f6', fontsize=14, pad=15)
    ax1.grid(True, color='#30363d', linestyle=':', linewidth=0.5)
    ax2.grid(True, color='#30363d', linestyle=':', linewidth=0.5)
    
    ax1.spines['bottom'].set_visible(False)
    ax1.spines['top'].set_visible(False)
    ax1.spines['left'].set_color('#30363d')
    ax1.spines['right'].set_color('#30363d')
    ax2.spines['top'].set_visible(False)
    ax2.spines['bottom'].set_color('#30363d')
    ax2.spines['left'].set_color('#30363d')
    ax2.spines['right'].set_color('#30363d')
    
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, loc: f"{int(x):,}"))
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, loc: f"{int(x):,}"))
    
    # 時間軸格式：分K顯示月日與時分，日K僅顯示年月日
    df['time_label'] = df['datetime'].apply(
        lambda x: pd.to_datetime(x).strftime('%m-%d %H:%M') if interval < 1440 else pd.to_datetime(x).strftime('%Y-%m-%d')
    )
    
    step = max(1, len(df) // 8)
    ticks = range(0, len(df), step)
    labels = [df.iloc[x]['time_label'] for x in ticks]
    plt.xticks(ticks, labels, color='gray', fontsize=9)
    
    plt.tight_layout()
    filename = f"temp_kline_{rule_name}_{interval}.png"
    plt.savefig(filename, facecolor=fig.get_facecolor(), edgecolor='none', dpi=150)
    plt.close()
    return filename

# ----------------------------------------------------
# 5. Telegram API 發送 (使用 urllib)
# ----------------------------------------------------
def send_image_to_telegram(image_path: str, caption: str):
    """傳送圖片至 Telegram (免第三方庫，防範 OpenSSL 錯誤)"""
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    
    if not token or not chat_id or token == "your_telegram_bot_token" or chat_id == "your_telegram_chat_id":
        print("[Telegram] Token 或 Chat ID 未設定，跳過發送。")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = "===KKTraderBoundary==="
    
    try:
        with open(image_path, 'rb') as f:
            file_data = f.read()
            
        body = []
        # chat_id
        body.append(f"--{boundary}".encode("utf-8"))
        body.append('Content-Disposition: form-data; name="chat_id"'.encode("utf-8"))
        body.append(''.encode("utf-8"))
        body.append(str(chat_id).encode("utf-8"))
        
        # caption
        body.append(f"--{boundary}".encode("utf-8"))
        body.append('Content-Disposition: form-data; name="caption"'.encode("utf-8"))
        body.append(''.encode("utf-8"))
        body.append(caption.encode("utf-8"))
        
        # parse_mode
        body.append(f"--{boundary}".encode("utf-8"))
        body.append('Content-Disposition: form-data; name="parse_mode"'.encode("utf-8"))
        body.append(''.encode("utf-8"))
        body.append("Markdown".encode("utf-8"))
        
        # photo file
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(f'Content-Disposition: form-data; name="photo"; filename="{os.path.basename(image_path)}"'.encode("utf-8"))
        body.append('Content-Type: image/png'.encode("utf-8"))
        body.append(''.encode("utf-8"))
        body.append(file_data)
        
        # end boundary
        body.append(f"--{boundary}--".encode("utf-8"))
        body.append(''.encode("utf-8"))
        
        payload = b"\r\n".join(body)
        
        req = urllib.request.Request(url, data=payload)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("Content-Length", str(len(payload)))
        
        with urllib.request.urlopen(req, timeout=15) as response:
            response.read()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Telegram] 成功發送 K 線圖至 Chat: {chat_id}")
            
    except Exception as e:
        print(f"[Telegram 發送失敗 / 網路錯誤] {e}")
    finally:
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception:
                pass

# ----------------------------------------------------
# 6. 事件處理與核心重採樣觸發比對
# ----------------------------------------------------
def handle_finalized_bar(trigger_code: str, bar_time_str: str, bar_data: dict):
    """
    每當收到 5分K 定稿時觸發。進行重採樣，並比對最新重採樣棒的結束點，決定是否發送
    """
    # 延遲 0.5 秒，確保 SQLiteLogger 的寫入動作已經 Commit 存檔
    time.sleep(0.5)
    
    # 1. 取得 trigger K棒的結束時間 (對齊時間 + 1分鐘)
    try:
        today_str = datetime.today().strftime("%Y-%m-%d")
        start_dt = datetime.strptime(f"{today_str} {bar_time_str}", "%Y-%m-%d %H:%M:%S")
        trigger_end_dt = start_dt + timedelta(minutes=1)
    except Exception as e:
        print(f"[時間解析錯誤] {e}")
        return

    # 2. 遍歷所有啟用規則，過濾商品與週期
    for rule_name, cfg in RULE_CONFIGS.items():
        if cfg["code"] != trigger_code:
            continue
            
        # 從 SQLite 撈取足夠數量的 1分K 作為基礎重組資料 (為了畫 100 根日K，上限設為 30000 根)
        df_1m = fetch_base_klines(cfg["code"], 30000)
        if df_1m.empty:
            continue
            
        for interval in cfg["intervals"]:
            # 使用時段重置重組
            df_resampled = resample_klines(df_1m, interval, cfg["session"])
            if df_resampled.empty:
                continue
                
            latest_bar = df_resampled.iloc[-1]
            latest_bar_start_dt = pd.to_datetime(latest_bar['datetime'])
            
            # 計算最新這根重組 K棒的結束時間點
            latest_bar_end_dt = latest_bar_start_dt + timedelta(minutes=interval)
            
            # 關鍵比對：若重採樣 K棒的結束點剛好等於 5分K 結束點，代表此週期剛剛定稿！
            if latest_bar_end_dt == trigger_end_dt:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 偵測到 [{rule_name}] 的 {interval}M K線定稿！進行繪圖傳送...")
                
                # 裁切最近 N 根進行繪圖
                df_plot = df_resampled.tail(TELEGRAM_SEND_BAR_COUNT).copy()
                img_file = draw_candlestick_chart(df_plot, cfg["code"], interval, rule_name)
                
                # 整理 Caption
                interval_label = f"{interval}分K" if interval < 1440 else "日K"
                caption = (
                    f"📊 *{rule_name} ({interval_label}) 新棒定稿*\n"
                    f"⏰ 定稿時間: `{latest_bar_start_dt.strftime('%Y-%m-%d %H:%M')}`\n"
                    f"📈 開盤價: `{latest_bar['open']:.0f}`\n"
                    f"🔥 最高價: `{latest_bar['high']:.0f}`\n"
                    f"❄️ 最低價: `{latest_bar['low']:.0f}`\n"
                    f"💎 收盤價: `{latest_bar['close']:.0f}`\n"
                    f"📦 單根量: `{latest_bar['volume']}`\n"
                    f"🤖 _由 KKTrader 雲端主機自動發送_"
                )
                
                if TELEGRAM_ENABLE_SEND:
                    threading.Thread(
                        target=send_image_to_telegram, 
                        args=(img_file, caption), 
                        daemon=True
                    ).start()
                else:
                    # 測試用：若 enable_send=False 則在本地留存圖表並在 console 列印路徑
                    print(f"[DEBUG] [跳過發送] (enable_send=False) 圖表已儲存至: {os.path.abspath(img_file)}")

# ----------------------------------------------------
# 7. 背景心跳與主程式
# ----------------------------------------------------
def heartbeat_task(r):
    """註冊 Telegram 發送端心跳"""
    while True:
        try:
            r.set("status:telegram_sender:heartbeat", "running", ex=10)
        except Exception:
            pass
        time.sleep(5)

def main():
    print("=" * 60)
    print(" KKTrader 獨立多時框 Telegram 自動發送服務 (TelegramSender) 啟動")
    print("=" * 60)
    print(f"Redis 連線目標: {REDIS_URL.split('@')[-1]}")
    print(f"啟用發送規則 : {ACTIVE_RULES}")
    for rule, cfg in RULE_CONFIGS.items():
        print(f" - [{rule}] 商品: {cfg['code']} | 週期: {cfg['intervals']} | 時段: {cfg['session']}")
        
    if not TELEGRAM_ENABLE_SEND:
        print("[WARN] settings.ini 中的 enable_send 目前設為 False，將只在本地生成圖表，不進行 Telegram 發送。")
        
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        print("Redis 連線成功！")
    except Exception as e:
        print(f"無法連線至 Redis: {e}")
        return

    # 啟動心跳執行緒
    t_hb = threading.Thread(target=heartbeat_task, args=(r,), daemon=True)
    t_hb.start()

    # 訂閱模式：監聽所有來源(如FT/Crypto/ST)的 1分K 定稿廣播
    pubsub = r.pubsub()
    pubsub.psubscribe("*:K1:Final:*")
    print("訂閱 K 線定稿通知中 (*:K1:Final:*)...")
    print("開始監聽事件... (按 Ctrl+C 結束)")

    try:
        for message in pubsub.listen():
            # 模式訂閱傳回的訊息類型為 'pmessage'
            if message['type'] != 'pmessage':
                continue
                
            channel = message['channel']
            parts = channel.split(":")
            code = parts[-1]
            
            try:
                bar_data = json.loads(message['data'])
                bar_time = bar_data.get("time") # 對齊時間 "HH:MM:00"
                
                # 啟動非同步處理執行緒，不阻塞 Redis 監聽
                threading.Thread(
                    target=handle_finalized_bar,
                    args=(code, bar_time, bar_data),
                    daemon=True
                ).start()
            except Exception as e:
                print(f"處理定稿消息錯誤: {e}")
                
    except KeyboardInterrupt:
        print("\n中斷訊號觸發，發送服務安全退出。")
    finally:
        pubsub.close()
        r.close()

if __name__ == "__main__":
    main()
