# -*- coding: utf-8 -*-
"""
manager.py — KKTrader 指標管理與動態加載器

功能:
  讀取 settings.ini 中的 [Indicators] 設定，依據目前繪圖或策略的「K線週期 (interval)」，
  自動套用對應的指標計算，免去複雜參數輸入。
"""

import os
import configparser
import pandas as pd
from Indicators.kd import calculate_kd
from Indicators.powerline import calculate_powerline

# 💡 本地映射表，防止循環匯入
INDICATOR_MAP = {
    "KD": calculate_kd,
    "PowerLine": calculate_powerline
}


class IndicatorManager:
    def __init__(self, settings_path: str = None):
        if settings_path is None:
            # 尋找 settings.ini (優先當前目錄，次為上層目錄)
            possible_paths = ["settings.ini", "../settings.ini", "../../settings.ini"]
            for path in possible_paths:
                if os.path.exists(path):
                    settings_path = path
                    break
                    
        self.settings_path = settings_path
        self.active_indicators = []
        self.configs = {}  # 格式: { 別名: {"type": 指標類型, "timeframes": [適用週期列表]} }
        
        self.load_configs()
        
    def load_configs(self):
        """讀取設定檔中的指標配置"""
        if not self.settings_path or not os.path.exists(self.settings_path):
            print(f"[Indicators] 找不到設定檔: {self.settings_path}，指標管理器將不啟用任何指標。")
            return
            
        try:
            config = configparser.ConfigParser()
            config.read(self.settings_path, encoding='utf-8')
            
            if not config.has_section("Indicators"):
                return
                
            # 1. 取得啟用的指標別名清單
            active_str = config.get("Indicators", "active_indicators", fallback="")
            self.active_indicators = [x.strip() for x in active_str.split(",") if x.strip()]
            
            # 2. 解析每個指標的類型與套用週期
            for alias in self.active_indicators:
                if config.has_option("Indicators", alias):
                    val = config.get("Indicators", alias)
                    parts = val.split("|")
                    if len(parts) == 2:
                        ind_type = parts[0].strip()
                        tf_str = parts[1].strip()
                        
                        # 解析適用週期 (以逗號隔開的整數，如 5,15,30)
                        timeframes = [int(x.strip()) for x in tf_str.split(",") if x.strip()]
                        
                        self.configs[alias] = {
                            "type": ind_type,
                            "timeframes": timeframes
                        }
                    else:
                        print(f"[Indicators] 指標 {alias} 的設定格式不正確: {val} (應為: 類型 | 週期清單)")
        except Exception as e:
            print(f"[Indicators] 載入指標設定失敗: {e}")

    def apply_indicators(self, df: pd.DataFrame, interval: int) -> pd.DataFrame:
        """
        對指定週期的 K 線 DataFrame 動態套用所有適用的啟用指標
        
        參數:
          df: 原始 K 線 DataFrame
          interval: 當前 K 線的週期 (分鐘數)
          
        傳回:
          pd.DataFrame: 套用指標計算後的 DataFrame (新增對應指標欄位)
        """
        if df.empty:
            return df
            
        annotated_df = df.copy()
        
        for alias, cfg in self.configs.items():
            # 檢查當前週期是否在該指標的適用範圍內
            if interval in cfg["timeframes"]:
                ind_type = cfg["type"]
                func = INDICATOR_MAP.get(ind_type)
                
                if func:
                    try:
                        # 呼叫對應指標計算函數 (使用該指標預設的標準參數)
                        annotated_df = func(annotated_df)
                    except Exception as e:
                        print(f"[Indicators] 計算指標 {alias} ({ind_type}) 錯誤: {e}")
                else:
                    print(f"[Indicators] 指標註冊表未找到類型: {ind_type}")
                    
        return annotated_df
