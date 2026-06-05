import streamlit as st
import pandas as pd
import json
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import redis
from Lib import config

# --- 1. 網頁骨架與 CSS 設定 ---
st.set_page_config(layout="wide", page_title="KKTrader 量化 K 線視覺化驗證面板")

# 設置 premium 暗色系與美化 CSS
st.markdown("""
    <style>
        .reportview-container {
            background: #0e1117;
        }
        h1, h2, h3 {
            color: #f0f2f6 !important;
            font-family: 'Inter', sans-serif;
        }
        /* 讓 Streamlit 繪圖元件寬度撐滿 */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
    </style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_redis_conn():
    """獲取 Redis 連線，使用 config.py 中已合併的 settings.ini 連線資訊"""
    try:
        # config.REDIS_URL 已經完美組裝好 (支援無密碼與有密碼本地連線)
        return redis.from_url(config.REDIS_URL, decode_responses=True)
    except Exception as e:
        st.error(f"無法連線至 Redis: {e}")
        return None


def load_raw_bars(r, code: str, interval: int) -> list:
    """從 Redis 列表中載入定稿的 K 線 JSON 數據"""
    list_key = f"FT:K1:List:{code}" if interval == 1 else f"FT:K5:List:{code}"
    # 獲取清單中所有元素
    raw_data = r.lrange(list_key, 0, -1)
    bars = []
    for item in raw_data:
        try:
            bars.append(json.loads(item))
        except Exception:
            continue
    return bars


def resample_bars(df: pd.DataFrame, timeframe_min: int) -> pd.DataFrame:
    """
    動態重採樣功能 (Quant Resampling Black Magic)
    利用背景儲存的 1分K 數據，在前端即時融合成 5K / 15K / 30K / 60K / 日K！
    """
    if df.empty:
        return df

    # 複製一份以防修改原資料
    df = df.copy()
    
    # 為了進行重採樣，必須將時間戳記轉為 DatetimeIndex
    # 假設今日日期為基礎組裝完整時間
    today_str = datetime.today().strftime("%Y-%m-%d")
    df['datetime'] = pd.to_datetime(today_str + ' ' + df['time'])
    df.set_index('datetime', inplace=True)
    
    # 計算重採樣規則
    if timeframe_min == 1440:
        rule = '1D'
    else:
        rule = f'{timeframe_min}T'
        
    # 重採樣聚合：
    # - open: 區間內第一筆
    # - high: 區間內最大值
    # - low: 區間內最小值
    # - close: 區間內最後一筆
    # - volume: 區間內成交量加總
    resampler = df.resample(rule, label='left', closed='left')
    resampled_df = resampler.agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    
    # 重新還原 time 欄位格式 HH:MM:00
    resampled_df['time'] = resampled_df.index.strftime("%H:%M:%00")
    resampled_df.reset_index(drop=True, inplace=True)
    
    return resampled_df


def main():
    st.title("📊 KKTrader 期貨即時 K 線視覺化驗證面板")
    st.markdown("本系統直接從本地 Redis 獲取即時定稿的 K 線數據。您可以利用此面板與您的股票看盤軟體進行毫秒級的價格與成交量核對。")

    r = get_redis_conn()
    if not r:
        st.error("❌ Redis 連線失敗，請確保 `run_futures_app.bat` 正在背景運行且 Redis 已正常啟動。")
        return

    # --- 2. 側邊控制欄 (Sidebar Controllers) ---
    st.sidebar.header("🛠️ 儀表板控制台")
    
    # A. 自動刷新頻率設定 (絲滑呼吸跳動核心 🚀)
    st.sidebar.subheader("🔄 自動刷新頻率")
    refresh_interval = st.sidebar.selectbox(
        "選擇刷新頻率 (核對價格請選手動)",
        ["每 1 秒 (絲滑即時)", "每 5 秒", "每 10 秒", "手動刷新"],
        index=0
    )
    st.sidebar.markdown("---")
    
    # B. 選擇商品別名
    code_options = config.FT_TARGETS  # ['TXFR1', 'TXFR2']
    selected_code = st.sidebar.selectbox("🎯 選擇交易商品", code_options, index=0)
    
    # B. 選擇時間框架 (Timeframe Selection)
    # 我們極具遠見地提供從 1K 直到 日K 的選擇，並在背景動態 Resample！
    timeframe_map = {
        "1分K (1M)": 1,
        "5分K (5M)": 5,
        "15分K (15M)": 15,
        "30分K (30M)": 30,
        "60分K (60M)": 60,
        "日K (Daily)": 1440
    }
    selected_tf_name = st.sidebar.selectbox("⏰ 選擇時間框架", list(timeframe_map.keys()), index=0)
    timeframe_min = timeframe_map[selected_tf_name]

    # C. 策略買賣訊號開關 (為未來擴充預留的開關 🚀)
    st.sidebar.markdown("---")
    st.sidebar.subheader("📈 策略疊加 (預留功能)")
    show_signals = st.sidebar.checkbox("顯示策略進出點 (買賣訊號)", value=False)
    
    # 載入原始 1分K 數據
    raw_bars = load_raw_bars(r, selected_code, interval=1)
    
    if not raw_bars:
        st.warning(f"⚠️ 尚未在 Redis 中找到商品 {selected_code} 的 1分K 歷史數據。請確保接收程式已開始接收 Tick 報價！")
        return

    # 轉為 DataFrame
    df = pd.DataFrame(raw_bars)
    
    # 動態進行重採樣聚合
    if timeframe_min != 1:
        with st.spinner(f"正在將 1分K 數據動態重採樣融合為 {selected_tf_name}..."):
            df = resample_bars(df, timeframe_min)

    if df.empty:
        st.warning("⚠️ 當前時間範圍或重採樣後無有效數據，請等待更多報價資料收集。")
        return

    # --- 3. 起始時間過濾欄 (Time Range Filter Slider) ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("📅 時間區間篩選")
    
    # 提供時間篩選滑桿
    time_list = df['time'].tolist()
    if len(time_list) > 1:
        start_time, end_time = st.sidebar.select_slider(
            "選擇顯示的時間範圍",
            options=time_list,
            value=(time_list[0], time_list[-1])
        )
        
        # 根據滑桿篩選 DataFrame
        start_idx = time_list.index(start_time)
        end_idx = time_list.index(end_time)
        df_filtered = df.iloc[start_idx:end_idx + 1].copy()
    else:
        df_filtered = df.copy()

    # --- 4. 繪製大師級 K 線與成交量圖表 (Plotly Subplots) ---
    # 創建雙圖：1. 燭台圖 (Candlestick), 2. 成交量圖 (Volume)
    # 共享 X 軸，並設置行高度比例 (K線 75% : 成交量 25%)
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.75, 0.25]
    )

    # A. 繪製紅綠燭台 (台灣配色習慣：收 > 開 為紅，收 < 開 為綠)
    fig.add_trace(
        go.Candlestick(
            x=df_filtered['time'],
            open=df_filtered['open'],
            high=df_filtered['high'],
            low=df_filtered['low'],
            close=df_filtered['close'],
            name=f"{selected_code} {selected_tf_name}",
            increasing_line_color='red',
            increasing_fillcolor='red',
            decreasing_line_color='green',
            decreasing_fillcolor='green',
            hoverlabel=dict(font=dict(size=14))
        ),
        row=1, col=1
    )

    # B. 繪製成交量直條圖
    # 設定成交量柱狀體配色：若該根 K 線為收漲，成交量顯示淡紅色，否則顯示淡綠色
    volume_colors = [
        'rgba(255, 0, 0, 0.5)' if c >= o else 'rgba(0, 255, 0, 0.5)'
        for o, c in zip(df_filtered['open'], df_filtered['close'])
    ]
    
    fig.add_trace(
        go.Bar(
            x=df_filtered['time'],
            y=df_filtered['volume'],
            name="成交量",
            marker_color=volume_colors,
            showlegend=False
        ),
        row=2, col=1
    )

    # C. 動態疊加模擬的「策略進出點」 (提供給使用者的未來演示 🚀)
    if show_signals:
        # 我們在過濾後的第 1/3 和 2/3 處動態產生模擬買賣點，展示圖表的無縫疊加實力！
        df_len = len(df_filtered)
        if df_len >= 3:
            buy_idx = df_len // 3
            sell_idx = (df_len // 3) * 2
            
            buy_time = df_filtered.iloc[buy_idx]['time']
            buy_price = df_filtered.iloc[buy_idx]['low'] * 0.9998
            
            sell_time = df_filtered.iloc[sell_idx]['time']
            sell_price = df_filtered.iloc[sell_idx]['high'] * 1.0002
            
            # 買入訊號：金色向上三角形
            fig.add_trace(
                go.Scatter(
                    x=[buy_time],
                    y=[buy_price],
                    mode="markers+text",
                    marker=dict(symbol="triangle-up", size=15, color="#FFD700"),
                    text=["💡 STRATEGY BUY"],
                    textposition="bottom center",
                    name="策略買入訊號",
                    textfont=dict(color="#FFD700", size=12)
                ),
                row=1, col=1
            )
            
            # 賣出訊號：天藍色向下三角形
            fig.add_trace(
                go.Scatter(
                    x=[sell_time],
                    y=[sell_price],
                    mode="markers+text",
                    marker=dict(symbol="triangle-down", size=15, color="#00BFFF"),
                    text=["🚨 STRATEGY SELL"],
                    textposition="top center",
                    name="策略賣出訊號",
                    textfont=dict(color="#00BFFF", size=12)
                ),
                row=1, col=1
            )

    # D. 圖表 Layout 細節精雕細琢
    fig.update_layout(
        height=680,
        title_text=f"📈 {selected_code} — {selected_tf_name} 即時 K 線主圖與成交量副圖",
        title_font=dict(size=20),
        xaxis_rangeslider_visible=False,  # 關閉預設 Rangeslider 以保持雙圖清爽
        hovermode="x unified",            # 游標移上去時一併顯示所有數據
        paper_bgcolor="#0e1117",
        plot_bgcolor="#161b22",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        xaxis=dict(gridcolor="#30363d"),
        yaxis=dict(title="價格", gridcolor="#30363d", tickformat=".0f"),
        yaxis2=dict(title="成交量", gridcolor="#30363d")
    )

    # --- 5. 渲染網頁圖表與數據表格 ---
    st.plotly_chart(fig, use_container_width=True)

    # 額外提供原始數據表格供點對點精確核對
    with st.expander("📋 點此查看與導出 K 線原始數據 (點對點核對數值專用)"):
        st.dataframe(
            df_filtered[['time', 'open', 'high', 'low', 'close', 'volume']].sort_index(ascending=False),
            width='stretch'
        )

    # --- 6. 處理自動定時刷新 (Auto-Refresh Core) ---
    if refresh_interval != "手動刷新":
        sec_map = {
            "每 1 秒 (絲滑即時)": 1.0,
            "每 5 秒": 5.0,
            "每 10 秒": 10.0
        }
        import time
        time.sleep(sec_map[refresh_interval])
        # 呼叫相容性 Rerun
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()


if __name__ == "__main__":
    main()
