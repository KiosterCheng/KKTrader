"""
Redis 工具模組 — 盤前清理等輔助函式
"""
from Lib import config
from Lib.logger import log


def cleanup_redis(r):
    """清除前一交易日殘留的快照與心跳 Key"""
    keys_to_delete = [config.REDIS_SNAPSHOT_KEY, config.REDIS_HEARTBEAT_KEY]

    deleted = 0
    for key in keys_to_delete:
        if r.exists(key):
            r.delete(key)
            log(f"已清除舊資料: {key}")
            deleted += 1

    remaining = r.dbsize()

    if deleted == 0 and remaining == 0:
        log("Redis 已是乾淨狀態，無需清理")
    elif remaining > 0:
        log(f"注意：Redis 內仍有 {remaining} 個 Key")
    else:
        log("初始化清理完成")
