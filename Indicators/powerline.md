# 📊 軌道秧四滿指標 v1 說明文件 (PowerLine)

本文件詳細記錄了 `Indicators/powerline.py` 模組的設計原理、數學公式、參數配置、輸入與輸出規格，以利未來策略開發與指標移植。

---

## 1. 設計原理與數學公式

「軌道秧四滿指標 v1」是一款專為日內波動突破與收縮設計的通道型技術指標。該指標以**每日日盤開盤時間 (08:45)** 為基準錨定點，在日內動態追蹤市場的極端價格並調整軌道寬度。

### 1.1 基準值初始化 (當日盤開盤 08:45)
當時間處於 `08:45` 時，系統鎖定該 K 線的開盤價 $Open_{0845}$ 作為當日開盤基準價：
$$dayOpen = Open_{0845}$$
同時，計算初始波幅寬度 $DayRange$：
$$DayRange = dayOpen \times day\_range\_rate$$
*(預設 $day\_range\_rate = 0.0078$，即 0.78% 的指數波幅)*

### 1.2 日內極端值追蹤
在同一個交易日內（即今日 `08:45` 到明日 `08:44` 之間），系統會實時追蹤並更新**當日最高價 $dayHigh$** 與**當日最低價 $dayLow$**：
$$dayHigh_t = \max(dayHigh_{t-1}, High_t)$$
$$dayLow_t = \min(dayLow_{t-1}, Low_t)$$
日中線 $dayMid$ 計算公式為：
$$dayMid_t = \frac{dayHigh_t + dayLow_t}{2}$$

### 1.3 上下軌道線 (PowerLine) 的動態調整
當價格刷新日內最低價時，上軌道會主動向下收斂；當價格刷新日內最高價時，下軌道會主動向上抬升。
*   **上軌道線 ($power\_upper$)**：
    $$power\_upper_t = dayOpen + DayRange - (dayOpen - dayLow_t)$$
    *(數學上等同於：$DayRange + dayLow_t$。)*
    *邊界防護：確保上軌不低於當日最高點：$power\_upper_t = \max(power\_upper_t, dayHigh_t)$。*

*   **下軌道線 ($power\_lower$)**：
    $$power\_lower_t = dayOpen - DayRange + (dayHigh_t - dayOpen)$$
    *(數學上等同於：$dayHigh_t - DayRange$。)*
    *邊界防護：確保下軌不高於當日最低點：$power\_lower_t = \min(power\_lower_t, dayLow_t)$。*

---

## 2. 參數配置

在 `settings.ini` 中，PowerLine 指標配置格式如下：
```ini
# 指標欄位名稱 = PowerLine | 日波幅比率 | 適用週期
powerline = PowerLine | 0.0078 | 5, 15
```

*   `day_range_rate`：預設為 `0.0078` (即 0.78%)。

---

## 3. 輸入與輸出規格

### 3.1 輸入 DataFrame 必備欄位
*   `datetime` (時間戳記，格式需含小時與分鐘)
*   `open`
*   `high`
*   `low`
*   `close`
*   `volume`

### 3.2 輸出 DataFrame 新增欄位
*   `power_upper` (上軌道黃線，浮點數)
*   `power_lower` (下軌道黃線，浮點數)
*   `day_high` (當日累計最高價紅線，浮點數)
*   `day_low` (當日累計最低價綠線，浮點數)
*   `day_mid` (當日累計中線灰線，浮點數，首根開盤為 `NaN`)

---

## 4. Python 使用範例

```python
import pandas as pd
from Indicators.powerline import calculate_powerline

# 1. 讀取與時間解析
df = pd.read_sql("SELECT * FROM klines WHERE code='TXFR1'", conn)
df['datetime'] = pd.to_datetime(df['datetime'])

# 2. 計算 PowerLine
df_power = calculate_powerline(df, day_range_rate=0.0078)

# 3. 獲取最新軌道線數值
latest = df_power.iloc[-1]
print(f"最新價: {latest['close']:.0f} | 軌道上: {latest['power_upper']:.1f} | 軌道下: {latest['power_lower']:.1f}")
```
