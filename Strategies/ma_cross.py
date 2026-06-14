# -*- coding: utf-8 -*-
"""
ma_cross.py — 雙均線交叉策略 (Moving Average Crossover)
"""

import pandas as pd


class MACrossStrategy:
    """
    均線交叉策略
    """
    def __init__(self, fast_window: int = 5, slow_window: int = 20):
        self.fast_window = int(fast_window)
        self.slow_window = int(slow_window)
        
    def next(self, df: pd.DataFrame) -> str:
        """
        根據輸入的歷史 K 線 DataFrame 進行策略判定。
        
        傳回值:
          "BUY"   - 買入訊號
          "SELL"  - 賣出訊號
          None    - 無訊號
        """
        required_len = max(self.fast_window, self.slow_window) + 2
        if len(df) < required_len:
            return None
            
        df = df.copy()
        df['close'] = df['close'].astype(float)
        
        # 計算快線與慢線
        df['fast_ma'] = df['close'].rolling(window=self.fast_window).mean()
        df['slow_ma'] = df['close'].rolling(window=self.slow_window).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 快線向上突破慢線 ➡️ 黃金交叉 BUY
        if prev['fast_ma'] <= prev['slow_ma'] and last['fast_ma'] > last['slow_ma']:
            return "BUY"
            
        # 快線跌破慢線 ➡️ 死亡交叉 SELL
        elif prev['fast_ma'] >= prev['slow_ma'] and last['fast_ma'] < last['slow_ma']:
            return "SELL"
            
        return None
