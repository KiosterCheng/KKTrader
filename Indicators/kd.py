# -*- coding: utf-8 -*-
"""
kd.py — 經典 KD 指標計算模組 (Stochastic Oscillator)
"""

import pandas as pd
import numpy as np


def calculate_kd(df: pd.DataFrame, n: int = 9, k_smooth: float = 3.0, d_smooth: float = 3.0) -> pd.DataFrame:
    """
    計算經典 KD 指標 — 台灣看盤軟體標準演算法
    
    參數:
      df: pd.DataFrame，包含 ['open', 'high', 'low', 'close', 'volume']
      n: RSV 週期
      k_smooth: K值平滑分母
      d_smooth: D值平滑分母
    """
    if df.empty or len(df) < n:
        out = df.copy()
        out['rsv'] = np.nan
        out['k'] = np.nan
        out['d'] = np.nan
        return out

    out = df.copy()
    out['high'] = out['high'].astype(float)
    out['low'] = out['low'].astype(float)
    out['close'] = out['close'].astype(float)
    
    # 計算 RSV
    low_min = out['low'].rolling(window=n).min()
    high_max = out['high'].rolling(window=n).max()
    denominator = high_max - low_min
    out['rsv'] = np.where(denominator != 0, (out['close'] - low_min) / denominator * 100, 50.0)
    
    # 遞迴計算 K, D
    k_vals = []
    d_vals = []
    current_k = 50.0
    current_d = 50.0
    k_alpha = 1.0 / k_smooth
    d_alpha = 1.0 / d_smooth
    
    for rsv in out['rsv']:
        if pd.isna(rsv):
            k_vals.append(np.nan)
            d_vals.append(np.nan)
        else:
            current_k = (1.0 - k_alpha) * current_k + k_alpha * rsv
            current_d = (1.0 - d_alpha) * current_d + d_alpha * current_k
            k_vals.append(current_k)
            d_vals.append(current_d)
            
    out['k'] = k_vals
    out['d'] = d_vals
    return out
