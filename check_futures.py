# -*- coding: utf-8 -*-
"""
check_futures.py - 期貨 Redis 資料即時檢查與驗證工具
"""
import json
import sys
import time
import io
from datetime import datetime
import redis
import os

def enable_windows_ansi():
    """在 Windows 系統上原生啟用 ANSI 虛擬終端序列支援，保證游標重置消閃爍正常運作"""
    if os.name == 'nt':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h_stdout = kernel32.GetStdHandle(-11) # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(h_stdout, ctypes.byref(mode)):
            kernel32.SetConsoleMode(h_stdout, mode.value | 0x0004) # ENABLE_VIRTUAL_TERMINAL_PROCESSING

# 解決 Windows 主控台可能發生的中文編碼問題
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from Lib.config import (
    REDIS_URL, 
    REDIS_FT_SNAPSHOT_KEY, 
    REDIS_FT_HEARTBEAT_KEY,
    REDIS_FT_K1_LATEST,
    REDIS_FT_K5_LATEST,
    FT_TARGETS
)


def print_title(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def monitor_loop(r):
    """即時監控畫面，每秒重繪一次 (優化消閃爍與零延遲覆寫)"""
    import os
    enable_windows_ansi()  # 原生啟用 Windows 的 ANSI 支援
    # 第一次啟動時，先清空一次螢幕，並在 Windows 上啟用 ANSI 支援
    os.system('cls' if os.name == 'nt' else 'clear')

    
    print("進入即時監控模式，按 Ctrl+C 退出...")
    time.sleep(0.5)
    
    try:
        while True:
            # 物理清空螢幕防護罩 (100% 徹底清除所有舊畫面，徹底終結等號累積 Bug)
            os.system('cls' if os.name == 'nt' else 'clear')
            
            # 使用 io.StringIO 收集所有的文字，避免多次 I/O 造成閃爍
            buffer = io.StringIO()
            
            # 同時保留 ANSI 游標重置以實現雙重強固
            buffer.write("\033[H")
            
            buffer.write("============================================================\n")
            buffer.write(f" KKTrader 期貨即時監控戰情室 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            buffer.write("============================================================\n")
            
            # 1. 檢查心跳
            hb_ft = r.get(REDIS_FT_HEARTBEAT_KEY)
            hb_strat = r.get("status:strategy_engine:heartbeat")
            hb_tg = r.get("status:telegram_sender:heartbeat")
            
            buffer.write("【系統服務狀態】:\n")
            buffer.write(f"  - 行情接收器 (Monitor): {'🟢 正常' if hb_ft else '🔴 已停止'} (TTL: {r.ttl(REDIS_FT_HEARTBEAT_KEY) if hb_ft else 0}s)\n")
            buffer.write(f"  - 策略計算機 (Strategy): {'🟢 正常' if hb_strat else '🔴 已停止'} (TTL: {r.ttl('status:strategy_engine:heartbeat') if hb_strat else 0}s)\n")
            buffer.write(f"  - 圖表發送器 (Telegram): {'🟢 正常' if hb_tg else '🔴 已停止'} (TTL: {r.ttl('status:telegram_sender:heartbeat') if hb_tg else 0}s)\n")
            
            # 2. 顯示 Snapshot 最新報價
            snapshot = r.hgetall(REDIS_FT_SNAPSHOT_KEY)
            buffer.write("\n[即時最新成交價快照 (FT:Snapshot)]\n")
            if snapshot:
                buffer.write(f" {'合約':<8} | {'成交價':<8} | {'單筆量':<6} | {'總成交量':<8} | {'時間':<10}\n")
                buffer.write("-" * 55 + "\n")
                for code, raw in sorted(snapshot.items()):
                    try:
                        d = json.loads(raw)
                        buffer.write(f" {code:<8} | {d.get('p', 0.0):<11.1f} | {d.get('v', 0):<9} | {d.get('tv', 0):<11} | {d.get('t', ''):<10}\n")
                    except Exception:
                        buffer.write(f" {code:<8} | 解析失敗 -> {raw}\n")
            else:
                buffer.write("  (尚未收到任何報價資料...)\n")

            # 3. 顯示進行中的 K 線
            k1_latest = r.hgetall(REDIS_FT_K1_LATEST)
            k5_latest = r.hgetall(REDIS_FT_K5_LATEST)
            
            buffer.write("\n[進行中的 K 線最新狀態]\n")
            buffer.write(f" {'合約':<8} | {'1分K (最新那一根狀態)':<50}\n")
            buffer.write("-" * 80 + "\n")
            if k1_latest:
                for code, raw in sorted(k1_latest.items()):
                    try:
                        d = json.loads(raw)
                        buffer.write(f" {code:<8} | 時間:{d.get('time')} 開:{d.get('open')} 高:{d.get('high')} 低:{d.get('low')} 收:{d.get('close')} 量:{d.get('volume')}\n")
                    except Exception:
                        pass
            else:
                buffer.write("  (無 1分K 狀態)\n")
                
            buffer.write("-" * 80 + "\n")
            buffer.write(f" {'合約':<8} | {'5分K (最新那一根狀態)':<50}\n")
            buffer.write("-" * 80 + "\n")
            if k5_latest:
                for code, raw in sorted(k5_latest.items()):
                    try:
                        d = json.loads(raw)
                        buffer.write(f" {code:<8} | 時間:{d.get('time')} 開:{d.get('open')} 開:{d.get('high')} 低:{d.get('low')} 收:{d.get('close')} 量:{d.get('volume')}\n")
                    except Exception:
                        pass
            else:
                buffer.write("  (無 5分K 狀態)\n")

            # 4. 顯示歷史 K 線與 Tick 累積筆數
            buffer.write("\n[Redis 歷史長度檢測]\n")
            buffer.write(f" {'合約':<8} | {'已儲存 Tick 數':<14} | {'已儲存 1分K 歷史':<16} | {'已儲存 5分K 歷史':<16}\n")
            buffer.write("-" * 70 + "\n")
            for code in FT_TARGETS:
                tick_len = r.llen(f"FT:Ticks:{code}")
                k1_len = r.llen(f"FT:K1:List:{code}")
                k5_len = r.llen(f"FT:K5:List:{code}")
                buffer.write(f" {code:<8} | {tick_len:<14} | {k1_len:<16} | {k5_len:<16}\n")
                
            buffer.write("\n(每 1 秒自動更新，按 Ctrl+C 可停止並退出)\n")
            buffer.write("============================================================\n")
            
            # 一次性高速輸出到螢幕上，原地字元覆蓋，完全不閃爍！
            sys.stdout.write(buffer.getvalue())
            sys.stdout.flush()
            buffer.close()
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n已退出即時監控模式")



def main():
    # 連線 Redis
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
    except Exception as e:
        print(f"\n[FAIL] 建立 Redis 連線失敗: {e}")
        return

    # 解析參數：是否有 --live 參數
    import argparse
    parser = argparse.ArgumentParser(description="期貨 Redis 資料檢查器")
    parser.add_argument("--live", action="store_true", help="開啟即時重新繪製監控模式")
    args = parser.parse_args()

    if args.live:
        monitor_loop(r)
        r.close()
        return

    # 一次性查詢模式
    print_title("KKTrader 期貨 Redis 狀態自我檢查")
    
    # 1. 檢查連線
    print(f"Redis 連線目標: {REDIS_URL.split('@')[-1]}")
    print(f"Key 總數: {r.dbsize()}")

    # 2. 檢查心跳
    hb_ft = r.get(REDIS_FT_HEARTBEAT_KEY)
    hb_strat = r.get("status:strategy_engine:heartbeat")
    hb_tg = r.get("status:telegram_sender:heartbeat")
    
    print_title("1. 各服務心跳狀態")
    print(f"   - 行情接收器 (Monitor): {'[🟢 正常] (TTL: ' + str(r.ttl(REDIS_FT_HEARTBEAT_KEY)) + '秒)' if hb_ft else '[🔴 停止]'}")
    print(f"   - 策略計算機 (Strategy): {'[🟢 正常] (TTL: ' + str(r.ttl('status:strategy_engine:heartbeat')) + '秒)' if hb_strat else '[🔴 停止]'}")
    print(f"   - 圖表發送器 (Telegram): {'[🟢 正常] (TTL: ' + str(r.ttl('status:telegram_sender:heartbeat')) + '秒)' if hb_tg else '[🔴 停止]'}")

    # 3. 檢查即時 Snapshot
    print_title("2. 即時價格快照")
    snapshot = r.hgetall(REDIS_FT_SNAPSHOT_KEY)
    if snapshot:
        print(f"共發現 {len(snapshot)} 個商品的 Snapshot:")
        for code, raw in sorted(snapshot.items()):
            try:
                d = json.loads(raw)
                print(f"   - {code:<8}: 最新價={d.get('p', 0.0):<8.1f} | 單筆量={d.get('v', 0):<4} | 總量={d.get('tv', 0):<6} | 時間={d.get('t')}")
            except Exception:
                print(f"   - {code:<8}: 解析失敗 -> {raw}")
    else:
        print("[WARN] Redis 中無任何 FT:Snapshot 資料。")

    # 4. 檢查最新進行中的 K 線
    print_title("3. 進行中 (Real-time) K 線最新快照")
    k1_latest = r.hgetall(REDIS_FT_K1_LATEST)
    k5_latest = r.hgetall(REDIS_FT_K5_LATEST)
    
    print("【1分K 最新一根狀態】")
    if k1_latest:
        for code, raw in sorted(k1_latest.items()):
            print(f"   - {code:<8}: {raw}")
    else:
        print("   (無資料)")
        
    print("\n【5分K 最新一根狀態】")
    if k5_latest:
        for code, raw in sorted(k5_latest.items()):
            print(f"   - {code:<8}: {raw}")
    else:
        print("   (無資料)")

    # 5. 歷史 K 線與 Tick 長度檢查
    print_title("4. 歷史儲存庫檢查")
    for code in FT_TARGETS:
        tick_key = f"FT:Ticks:{code}"
        k1_list_key = f"FT:K1:List:{code}"
        k5_list_key = f"FT:K5:List:{code}"
        
        tick_len = r.llen(tick_key)
        k1_len = r.llen(k1_list_key)
        k5_len = r.llen(k5_list_key)
        
        print(f"商品: {code}")
        print(f"   - Tick 明細資料長度: {tick_len} 筆")
        
        # 顯示最新歷史 K 線 (1分K)
        print(f"   - 1分K 歷史長度: {k1_len} 根")
        if k1_len > 0:
            latest_k1 = r.lindex(k1_list_key, -1)
            print(f"     └─ 最新一根定稿: {latest_k1}")
            
        # 顯示最新歷史 K 線 (5分K)
        print(f"   - 5分K 歷史長度: {k5_len} 根")
        if k5_len > 0:
            latest_k5 = r.lindex(k5_list_key, -1)
            print(f"     └─ 最新一根定稿: {latest_k5}")
        print()

    print("=" * 60)
    print(" 提示: 執行 `python check_futures.py --live` 可進入每秒重新整理的動態戰情室")
    print("=" * 60)
    
    r.close()


if __name__ == "__main__":
    main()
