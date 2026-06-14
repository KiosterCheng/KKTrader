"""
設定模組 — 從 settings.ini + secrets.ini 讀取所有參數

settings.ini: 非機密設定（可 commit 到 GitHub）
secrets.ini:  機密資訊（gitignore，不上傳）
"""
import configparser
import os

_base_dir = os.path.dirname(os.path.dirname(__file__))

# --- 讀取 settings.ini（非機密設定）---
_cfg = configparser.ConfigParser()
_ini_path = os.path.join(_base_dir, "settings.ini")

if not os.path.exists(_ini_path):
    raise FileNotFoundError(f"找不到設定檔: {_ini_path}")

_cfg.read(_ini_path, encoding="utf-8")

# --- Redis 連線 ---
USE_CLOUD_REDIS = _cfg.getboolean("Redis", "use_cloud_redis", fallback=True)

REDIS_CLOUD_HOST = _cfg.get("Redis", "cloud_host")
REDIS_CLOUD_PORT = _cfg.getint("Redis", "cloud_port")
REDIS_LOCAL_HOST = _cfg.get("Redis", "local_host", fallback="localhost")
REDIS_LOCAL_PORT = _cfg.getint("Redis", "local_port", fallback=6379)

REDIS_PASSWORD = _cfg.get("Redis", "password", fallback="")

# 根據 Flag 自動組裝 Redis URL
if USE_CLOUD_REDIS:
    if REDIS_PASSWORD and REDIS_PASSWORD.strip():
        REDIS_URL = f"redis://default:{REDIS_PASSWORD}@{REDIS_CLOUD_HOST}:{REDIS_CLOUD_PORT}"
    else:
        REDIS_URL = f"redis://{REDIS_CLOUD_HOST}:{REDIS_CLOUD_PORT}"
else:
    if REDIS_PASSWORD and REDIS_PASSWORD.strip():
        REDIS_URL = f"redis://default:{REDIS_PASSWORD}@{REDIS_LOCAL_HOST}:{REDIS_LOCAL_PORT}"
    else:
        REDIS_URL = f"redis://{REDIS_LOCAL_HOST}:{REDIS_LOCAL_PORT}"

# --- Shioaji API ---
SHIOAJI_API_KEY = _cfg.get("Shioaji", "api_key", fallback="")
SHIOAJI_SECRET_KEY = _cfg.get("Shioaji", "secret_key", fallback="")
SHIOAJI_SIMULATION = _cfg.getboolean("Shioaji", "simulation", fallback=True)

# --- 監控參數 ---
DEFAULT_TRIGGER_TIME = _cfg.get("Monitor", "trigger_time", fallback="11:00:00")
DEFAULT_OPTION_MODE = _cfg.get("Monitor", "option_mode", fallback="TXO")
ATM_SOURCE = _cfg.get("Monitor", "atm_source", fallback="index")
STRIKE_STEP = _cfg.getint("Monitor", "strike_step", fallback=50)
STRIKE_RANGE = _cfg.getint("Monitor", "strike_range", fallback=5)
SUBSCRIBE_DELAY = _cfg.getfloat("Monitor", "subscribe_delay", fallback=0.5)
HEARTBEAT_INTERVAL = _cfg.getint("Monitor", "heartbeat_interval", fallback=5)
HEARTBEAT_TTL = _cfg.getint("Monitor", "heartbeat_ttl", fallback=10)

# --- Redis Key 名稱 ---
REDIS_SNAPSHOT_KEY = "TXO:Snapshot"
REDIS_HEARTBEAT_KEY = "status:ingestor:heartbeat"

# --- 期貨參數 ---
FT_TARGETS = [t.strip() for t in _cfg.get("Futures", "targets", fallback="TXFR1,TXFR2").split(",") if t.strip()]
FT_SAVE_TICKS = _cfg.getboolean("Futures", "save_ticks", fallback=True)
FT_TICK_LIMIT = _cfg.getint("Futures", "tick_limit", fallback=500)
FT_K1_LIMIT = _cfg.getint("Futures", "k1_limit", fallback=300)
FT_K5_LIMIT = _cfg.getint("Futures", "k5_limit", fallback=300)

# --- 期貨 Redis Key 名稱 ---
REDIS_FT_SNAPSHOT_KEY = "FT:Snapshot"
REDIS_FT_HEARTBEAT_KEY = "status:ft_ingestor:heartbeat"
REDIS_FT_K1_LATEST = "FT:K1:Latest"
REDIS_FT_K5_LATEST = "FT:K5:Latest"

# --- Telegram 參數 ---
TELEGRAM_BOT_TOKEN = _cfg.get("Telegram", "bot_token", fallback="")
TELEGRAM_CHAT_ID = _cfg.get("Telegram", "chat_id", fallback="")
TELEGRAM_ENABLE_SEND = _cfg.getboolean("Telegram", "enable_send", fallback=False)
TELEGRAM_SEND_INTERVAL = _cfg.getint("Telegram", "send_interval", fallback=5)
TELEGRAM_SEND_BAR_COUNT = _cfg.getint("Telegram", "send_bar_count", fallback=100)

