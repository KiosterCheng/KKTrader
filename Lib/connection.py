"""
連線模組 — 管理 Shioaji 與 Redis 的建立 / 清理 / 關閉
"""
import time
import shioaji as sj
import redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from redis.exceptions import ConnectionError, TimeoutError as RedisTimeoutError
from Lib import config
from Lib.logger import log

# Redis 連線重試設定
_REDIS_MAX_RETRIES = 5
_REDIS_RETRY_DELAY = 3  # 首次重試等待秒數


def connect_redis() -> redis.Redis:
    """建立 Redis 連線並驗證（含重試與 keepalive）"""
    retry = Retry(ExponentialBackoff(), retries=3)
    r = redis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        socket_timeout=10,
        socket_connect_timeout=10,
        socket_keepalive=True,
        retry_on_timeout=True,
        retry=retry,
        health_check_interval=30,
    )

    for attempt in range(1, _REDIS_MAX_RETRIES + 1):
        try:
            if r.ping():
                log("Redis 連線成功 (PING OK)")
                info = r.info("memory")
                log(f"記憶體使用中: {info['used_memory_human']}")
                clients = r.info("clients")
                log(f"目前連線人數: {clients['connected_clients']}")
                log(f"目前 Key 總數: {r.dbsize()}")
            return r
        except (ConnectionError, RedisTimeoutError, OSError) as e:
            wait = _REDIS_RETRY_DELAY * attempt
            log(f"Redis 連線失敗 (第 {attempt}/{_REDIS_MAX_RETRIES} 次): {e}")
            if attempt < _REDIS_MAX_RETRIES:
                log(f"等待 {wait} 秒後重試...")
                time.sleep(wait)
            else:
                raise ConnectionError(
                    f"Redis 連線失敗，已重試 {_REDIS_MAX_RETRIES} 次仍無法連線"
                ) from e
    return r


def connect_shioaji() -> sj.Shioaji:
    """建立 Shioaji 連線並登入"""
    if not config.SHIOAJI_API_KEY or not config.SHIOAJI_SECRET_KEY:
        raise ValueError("請設定環境變數 SHIOAJI_API 與 SHIOAJI_SEC")

    api = sj.Shioaji(simulation=config.SHIOAJI_SIMULATION)
    api.login(api_key=config.SHIOAJI_API_KEY, secret_key=config.SHIOAJI_SECRET_KEY)

    accounts = api.list_accounts()
    log(f"Shioaji 登入成功，帳號：{accounts[0].account_id}")
    log(f"帳號資訊: {accounts}")

    try:
        log(f"額度資訊: {api.usage()}")
    except TimeoutError:
        log("額度查詢逾時，但連線正常，繼續執行...")
    except Exception as e:
        log(f"查詢額度發生其他錯誤: {e}")

    return api


def disconnect(api, r):
    """安全關閉所有連線"""
    if api:
        try:
            api.logout()
            log("Shioaji 已登出")
        except Exception:
            pass
    if r:
        try:
            r.close()
            r.connection_pool.disconnect()
            log("Redis 已中斷")
        except Exception:
            pass
