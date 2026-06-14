# -*- coding: utf-8 -*-
"""
Strategies 包的初始化與策略映射表
"""

from .ma_cross import MACrossStrategy

# 💡 註冊表：將 settings.ini 中定義的策略種類名稱對應到實體類別
STRATEGY_MAP = {
    "MA_Cross": MACrossStrategy
}
