from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import ccxt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from okx_bot import compute_rsi, compute_signal


st.set_page_config(page_title="OKX Trading Dashboard", page_icon="📈", layout="wide")


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    metrics: dict[str, Any]


@st.cache_data(ttl=60)
def fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    exchange = ccxt.okx({"enableRateLimit": True, "options": {"defaultType": "spot"}})
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


def mark_to_market_equity(cash: float, position_amount: float, price: float) -> float:
    return cash + position_amount * price


def backtest_strategy(
    df: pd.DataFrame,
    fast_sma: int,
    slow_sma: int,
    rsi_period: int,
    rsi_buy_max: float,
    rsi_sell_min: float,
    initial_capital: float,
    risk_fraction: float,
    max_position_usdt: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    fee_rate: float,
    slippage_bps: float,
) -> BacktestResult:
    if df.empty:
        raise ValueError("No market data available for backtest.")

    df = df.copy().reset_index(drop=True)
    close = df["close"]
    df["fast_sma"] = close.rolling(fast_sma).mean()
    df["slow_sma"] = close.rolling(slow_sma).mean()
    df["rsi"] = compute_rsi(close, rsi_period)

    cash = float(initial_capital)
    position_amount = 0.0
    entry_price = 0.0
    entry_time = None
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    peak_equity = initial_capital
    max_drawdown = 0.0

    def enter_long(idx: int, exec_price: float) -> None:
        nonlocal cash, position_amount, entry_price, entry_time
        trade_usdt = min(cash * risk_fraction, max_position_usdt)
        if trade_usdt <= 0:
            return
        amount = trade_usdt / exec_price
        buy_fee = trade_usdt * fee_rate
        cash -= trade_usdt + buy_fee
        position_amount = amount
        entry_price = exec_price
        entry_time = df.loc[idx, "timestamp"]
        trades.append(
            {
                "entry_time": entry_time,
                "side": "BUY",
                "price": exec_price,
                "amount": amount,
                "value_usdt": trade_usdt,
                "fee_usdt": buy_fee,
                "reason": "signal_buy",
            }
        )

    def exit_long(idx: int, exec_price: float, reason: str) -> None:
        nonlocal cash, position_amount, entry_price, entry_time
        if position_amount <= 0:
            return
        proceeds = position_amount * exec_price
        sell_fee = proceeds * fee_rate
        pnl = proceeds - sell_fee - (position_amount * entry_price)
        cash += proceeds - sell_fee
        trades.append(
            {
                "entry_time": entry_time,
                "exit_time": df.loc[idx, "timestamp"],
                "side": "SELL",
                "price": exec_price,
                "amount": position_amount,
                "value_usdt": proceeds,
                "fee_usdt": sell_fee,
                "pnl_usdt": pnl,
                "return_pct": (exec_price / entry_price - 1) * 100,
                "reason": reason,
            }
        )
        position_amount = 0.0
        entry_price = 0.0
        entry_time = None

    for idx in range(len(df)):
        row = df.iloc[idx]
        price = float(row["close"])
        rsi = row["rsi"]
        fast = row["fast_sma"]
        slow = row["slow_sma"]

        if pd.isna(fast) or pd.isna(slow) or pd.isna(rsi):
            equity = mark_to_market_equity(cash, position_amount, price)
            peak_equity = max(peak_equity, equity)
            drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
            max_drawdown = max(max_drawdown, drawdown)
            equity_rows.append({"timestamp": row["timestamp"], "equity": equity, "drawdown": drawdown})
            continue

        signal_info = compute_signal(df.iloc[: idx + 1], fast_sma, slow_sma, rsi_period)
        signal = signal_info["signal"]

        if position_amount > 0:
            stop_price = entry_price * (1 - stop_loss_pct)
            take_profit_price = entry_price * (1 + take_profit_pct)

            if float(row["low"]) <= stop_price:
                exit_long(idx, stop_price * (1 - slippage_bps / 10000), "stop_loss")
            elif float(row["high"]) >= take_profit_price:
                exit_long(idx, take_profit_price * (1 - slippage_bps / 10000), "take_profit")
            elif signal == "SELL" or (fast < slow):
                exit_long(idx, price * (1 - slippage_bps / 10000), "signal_exit")

        if position_amount == 0 and signal == "BUY" and rsi <= rsi_buy_max:
            enter_long(idx, price * (1 + slippage_bps / 10000))

        equity = mark_to_market_equity(cash, position_amount, price)
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)
        equity_rows.append({"timestamp": row["timestamp"], "equity": equity, "drawdown": drawdown})

    final_equity = equity_rows[-1]["equity"] if equity_rows else initial_capital
    closed_trades = [t for t in trades if t.get("side") == "SELL"]
    wins = [t for t in closed_trades if t.get("pnl_usdt", 0.0) > 0]
    gross_profit = sum(t.get("pnl_usdt", 0.0) for t in closed_trades if t.get("pnl_usdt", 0.0) > 0)
    gross_loss = abs(sum(t.get("pnl_usdt", 0.0) for t in closed_trades if t.get("pnl_usdt", 0.0) < 0))

    metrics = {
        "initial_capital": initial_capital,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / initial_capital - 1) * 100, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "trade_count": len(closed_trades),
        "win_rate_pct": round((len(wins) / len(closed_trades) * 100) if closed_trades else 0.0, 2),
        "profit_factor": round((gross_profit / gross_loss) if gross_loss > 0 else float("inf"), 2),
    }

    return BacktestResult(
        trades=pd.DataFrame(trades),
        equity_curve=pd.DataFrame(equity_rows),
        metrics=metrics,
    )


def make_candlestick_chart(df: pd.DataFrame, fast_sma: int, slow_sma: int, title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="K线",
        )
    )
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["close"].rolling(fast_sma).mean(), mode="lines", name=f"SMA {fast_sma}"))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["close"].rolling(slow_sma).mean(), mode="lines", name=f"SMA {slow_sma}"))
    fig.update_layout(title=title, xaxis_title="Time", yaxis_title="Price", height=600)
    return fig


st.title("📈 OKX Trading Dashboard")
st.caption("回测、信号查看、参数调节都在这里。默认只做分析，不碰实盘。")

with st.sidebar:
    st.header("参数")
    symbol = st.selectbox("交易对", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"], index=0)
    timeframe = st.selectbox("周期", ["1m", "5m", "15m", "1h", "4h"], index=1)
    limit = st.slider("K线数量", 200, 2000, 500, 100)
    fast_sma = st.number_input("FAST_SMA", min_value=2, max_value=200, value=10)
    slow_sma = st.number_input("SLOW_SMA", min_value=3, max_value=400, value=30)
    rsi_period = st.number_input("RSI_PERIOD", min_value=2, max_value=100, value=14)
    rsi_buy_max = st.number_input("RSI_BUY_MAX", min_value=1.0, max_value=100.0, value=70.0)
    rsi_sell_min = st.number_input("RSI_SELL_MIN", min_value=1.0, max_value=100.0, value=30.0)
    initial_capital = st.number_input("初始资金 (USDT)", min_value=100.0, value=10000.0, step=100.0)
    risk_fraction = st.slider("单次风险比例", 0.1, 10.0, 2.0, 0.1) / 100.0
    max_position_usdt = st.number_input("单笔最大投入 (USDT)", min_value=10.0, value=1000.0, step=10.0)
    stop_loss_pct = st.slider("止损 %", 0.1, 10.0, 1.0, 0.1) / 100.0
    take_profit_pct = st.slider("止盈 %", 0.1, 20.0, 2.0, 0.1) / 100.0
    fee_rate = st.slider("手续费 %", 0.0, 1.0, 0.1, 0.01) / 100.0
    slippage_bps = st.slider("滑点 (bps)", 0, 100, 5, 1)

    run_backtest = st.button("开始回测", type="primary")
    refresh_signal = st.button("刷新最新信号")


col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("市场数据")
    try:
        df = fetch_ohlcv(symbol, timeframe, limit)
        st.dataframe(df.tail(20), use_container_width=True)
        st.plotly_chart(make_candlestick_chart(df, int(fast_sma), int(slow_sma), f"{symbol} · {timeframe}"), use_container_width=True)
    except Exception as exc:
        st.error(f"行情加载失败: {exc}")
        st.stop()

with col2:
    st.subheader("最新信号")
    try:
        latest_signal = compute_signal(df, int(fast_sma), int(slow_sma), int(rsi_period))
        latest_rsi = compute_rsi(df["close"], int(rsi_period)).iloc[-1]
        st.metric("Signal", latest_signal["signal"])
        st.metric("RSI", f"{float(latest_rsi):.2f}" if pd.notna(latest_rsi) else "N/A")
        st.write({"reason": latest_signal.get("reason")})
    except Exception as exc:
        st.warning(f"信号计算失败: {exc}")


if run_backtest:
    try:
        result = backtest_strategy(
            df=df,
            fast_sma=int(fast_sma),
            slow_sma=int(slow_sma),
            rsi_period=int(rsi_period),
            rsi_buy_max=float(rsi_buy_max),
            rsi_sell_min=float(rsi_sell_min),
            initial_capital=float(initial_capital),
            risk_fraction=float(risk_fraction),
            max_position_usdt=float(max_position_usdt),
            stop_loss_pct=float(stop_loss_pct),
            take_profit_pct=float(take_profit_pct),
            fee_rate=float(fee_rate),
            slippage_bps=float(slippage_bps),
        )

        st.subheader("回测结果")
        metric_cols = st.columns(6)
        metric_cols[0].metric("总收益", f"{result.metrics['total_return_pct']}%")
        metric_cols[1].metric("最大回撤", f"{result.metrics['max_drawdown_pct']}%")
        metric_cols[2].metric("胜率", f"{result.metrics['win_rate_pct']}%")
        metric_cols[3].metric("交易次数", f"{result.metrics['trade_count']}")
        metric_cols[4].metric("终值", f"{result.metrics['final_equity']}")
        metric_cols[5].metric("Profit Factor", f"{result.metrics['profit_factor']}")

        if not result.equity_curve.empty:
            eq_fig = go.Figure()
            eq_fig.add_trace(go.Scatter(x=result.equity_curve["timestamp"], y=result.equity_curve["equity"], mode="lines", name="Equity"))
            eq_fig.update_layout(title="权益曲线", xaxis_title="Time", yaxis_title="USDT", height=400)
            st.plotly_chart(eq_fig, use_container_width=True)

            dd_fig = go.Figure()
            dd_fig.add_trace(go.Scatter(x=result.equity_curve["timestamp"], y=result.equity_curve["drawdown"] * 100, mode="lines", name="Drawdown"))
            dd_fig.update_layout(title="回撤曲线", xaxis_title="Time", yaxis_title="Drawdown %", height=300)
            st.plotly_chart(dd_fig, use_container_width=True)

        if not result.trades.empty:
            st.subheader("交易记录")
            st.dataframe(result.trades, use_container_width=True)
            st.download_button(
                "下载交易记录 CSV",
                data=result.trades.to_csv(index=False).encode("utf-8"),
                file_name=f"backtest_trades_{symbol.replace('/', '_')}_{timeframe}.csv",
                mime="text/csv",
            )
        else:
            st.info("这组参数没有产生已平仓交易。")
    except Exception as exc:
        st.error(f"回测失败: {exc}")


st.divider()
st.subheader("部署方式")
st.code("streamlit run web_app.py", language="bash")
st.write("本页面适合本地运行或部署到你自己的服务器。API 密钥建议只填在你自己的环境里，不要交给第三方页面。")
