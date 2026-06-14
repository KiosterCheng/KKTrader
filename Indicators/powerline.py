# -*- coding: utf-8 -*-
"""
powerline.py — 軌道秧四滿指標 v1 (PowerLine)
"""

import pandas as pd
import numpy as np


def calculate_powerline(df: pd.DataFrame, day_range_rate: float = 0.0078) -> pd.DataFrame:
    """
    計算「軌道秧四滿指標 v1」 (PowerLine)
    
    算法說明:
      - 每日日盤開盤 (08:45) 為基準點，記錄該棒的 open 作為 dayOpen。
      - 初始區間 DayRange = dayOpen * day_range_rate。
      - 在該日盤群組內 (從 08:45 開始至隔日 08:44 結束)，動態追蹤當日最高價 dayHigh 與最低價 dayLow。
      - 調整上方黃線: upperLine = dayOpen + DayRange - (dayOpen - dayLow) 
                     => 數學上等同於: DayRange + dayLow
      - 調整下方黃線: lowerLine = dayOpen - DayRange + (dayHigh - dayOpen)
                     => 數學上等同於: dayHigh - DayRange
      - 限制邊界: upperLine 需大於等於 dayHigh，lowerLine 需小於等於 dayLow。
      - 中線: dayMid = (dayHigh + dayLow) / 2
      
    參數:
      df: pd.DataFrame，必須包含 ['datetime', 'open', 'high', 'low', 'close', 'volume']
      day_range_rate: 日波幅比率，預設為 0.0078
      
    傳回:
      pd.DataFrame: 新增 'power_upper', 'power_lower', 'day_high', 'day_low', 'day_mid' 欄位
    """
    if df.empty:
        out = df.copy()
        out['power_upper'] = np.nan
        out['power_lower'] = np.nan
        out['day_high'] = np.nan
        out['day_low'] = np.nan
        out['day_mid'] = np.nan
        return out
        
    out = df.copy()
    out['datetime'] = pd.to_datetime(out['datetime'])
    out['open'] = out['open'].astype(float)
    out['high'] = out['high'].astype(float)
    out['low'] = out['low'].astype(float)
    out['close'] = out['close'].astype(float)
    
    # 1. 判定是否為日盤開盤起點 (08:45)
    out['is_day_start'] = (out['datetime'].dt.hour == 8) & (out['datetime'].dt.minute == 45)
    
    # 2. 進行分組累加 (cumsum)，使 08:45-隔日08:44 處於同一個 day_group
    out['day_group'] = out['is_day_start'].cumsum()
    
    # 3. 取得每個 group 的第一個開盤價 (即 08:45 的 open)
    # 若首筆資料前無 08:45，則以當前 group 的第一根 open 為基準
    out['dayOpen'] = out.groupby('day_group')['open'].transform('first')
    
    # 4. 追蹤當日最高與最低價
    out['day_high'] = out.groupby('day_group')['high'].cummax()
    out['day_low'] = out.groupby('day_group')['low'].cummin()
    
    # 5. 計算動態波動區間
    out['DayRange'] = out['dayOpen'] * day_range_rate
    
    # 6. 計算 upperLine 與 lowerLine
    out['power_upper'] = out['dayOpen'] + out['DayRange'] - (out['dayOpen'] - out['day_low'])
    out['power_lower'] = out['dayOpen'] - out['DayRange'] + (out['day_high'] - out['dayOpen'])
    
    # 7. 確保邊界限制
    out['power_upper'] = np.maximum(out['power_upper'], out['day_high'])
    out['power_lower'] = np.minimum(out['power_lower'], out['day_low'])
    
    # 8. 計算日中線 (開盤首根設為 NaN)
    out['day_mid'] = (out['day_high'] + out['day_low']) / 2
    out.loc[out['is_day_start'], 'day_mid'] = np.nan
    
    # 清理中間輔助欄位，保持輸出乾淨
    out.drop(columns=['is_day_start', 'day_group', 'dayOpen', 'DayRange'], inplace=True, errors='ignore')
    
    return out
