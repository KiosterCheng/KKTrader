# 📈 經典 KD 指標說明文件 (Stochastic Oscillator)

本文件詳細記錄了 `Indicators/kd.py` 模組的數學公式、參數配置、輸入與輸出規格，以利未來策略開發與指標移植。

---

## 1. 數學公式與演算法

KD 指標是量化交易中用來判定市場動量與超買/超賣區間的經典指標，由以下三個步驟構成：

### 1.1 步驟一：計算 RSV (Raw Stochastic Value)
RSV 代表當前收盤價在過去 $n$ 根 K 線區間內的相對位置：
$$RSV_t = \frac{Close_t - Low_n}{High_n - Low_n} \times 100$$
*   **$Close_t$**：當前 K 線收盤價。
*   **$Low_n$**：過去 $n$ 根 K 線中的最低價。
*   **$High_n$**：過去 $n$ 根 K 線中的最高價。
*   *備註：若區間最高價與最低價相等（分母為 0），則 RSV 預設填為 50.0。*

### 1.2 步驟二：計算 K 值
K 值為當前 RSV 與前一日 K 值的指數加權移動平均 (EMA)：
$$K_t = (1 - \frac{1}{k\_smooth}) \times K_{t-1} + \frac{1}{k\_smooth} \times RSV_t$$
*   一般預設 $k\_smooth = 3.0$（即當日 K 值 = $\frac{2}{3} K_{t-1} + \frac{1}{3} RSV_t$）。
*   初始值 $K_0 = 50.0$。

### 1.3 步驟三：計算 D 值
D 值為當前 K 值與前一日 D 值的指數加權移動平均 (EMA)：
$$D_t = (1 - \frac{1}{d\_smooth}) \times D_{t-1} + \frac{1}{d\_smooth} \times K_t$$
*   一般預設 $d\_smooth = 3.0$（即當日 D 值 = $\frac{2}{3} D_{t-1} + \frac{1}{3} K_t$）。
*   初始值 $D_0 = 50.0$。

---

## 2. 參數配置

在 `settings.ini` 中，KD 指標配置格式如下：
```ini
# 指標欄位名稱 = KD | RSV週期, K平滑系數, D平滑系數 | 適用週期
my_kd = KD | 9, 3, 3 | 5, 15, 30
```

*   `n` (RSV週期)：預設 `9`。
*   `k_smooth` (K平滑)：預設 `3`。
*   `d_smooth` (D平滑)：預設 `3`。

---

## 3. 輸入與輸出規格

### 3.1 輸入 DataFrame 必備欄位
您的輸入 DataFrame 必須至少包含以下時間與價格欄位，且型態需能被轉型為數值：
*   `open`
*   `high`
*   `low`
*   `close`
*   `volume`

### 3.2 輸出 DataFrame 新增欄位
函數計算完成後，會回傳包含原欄位並額外新增以下三個浮點數序列（Series）的 DataFrame：
*   `rsv` (分佈區間: 0 ~ 100)
*   `k` (分佈區間: 0 ~ 100)
*   `d` (分佈區間: 0 ~ 100)
*   *注意：由於需要回溯 $n$ 根 K 線，前 $n-1$ 根數據將輸出為 `NaN` (空值)。*

---

## 4. Python 使用範例

```python
import pandas as pd
from Indicators.kd import calculate_kd

# 1. 準備 OHLCV 資料
df = pd.read_csv("history_data.csv")

# 2. 計算 KD
df_kd = calculate_kd(df, n=9, k_smooth=3.0, d_smooth=3.0)

# 3. 取得最新一根的 K 值與 D 值
latest_k = df_kd['k'].iloc[-1]
latest_d = df_kd['d'].iloc[-1]
print(f"最新 K 值: {latest_k:.2f} | D 值: {latest_d:.2f}")
```
