"""
回测引擎
用历史数据模拟策略交易
"""

import pandas as pd
import numpy as np
from datetime import datetime
from loguru import logger
from dataclasses import dataclass, field
from typing import List

from ..strategies import BaseStrategy, StrategyResult, Signal


@dataclass
class Trade:
    symbol: str
    entry_time: datetime
    exit_time: datetime = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    amount: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    direction: str = "long"


@dataclass
class BacktestResult:
    total_return: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    profit_factor: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.Series = None


class BacktestEngine:
    """
    回测引擎
    使用向量化方式逐 K 线模拟交易
    """

    def __init__(self, config: dict):
        self.config = config
        self.initial_capital = config["backtest"]["initial_capital"]
        self.commission = 0.001  # 0.1% 手续费

    def run(self, strategy: BaseStrategy, df: pd.DataFrame,
            symbol: str = "BTC/USDT") -> BacktestResult:
        """运行回测"""
        capital = self.initial_capital
        position = 0.0
        entry_price = 0.0
        trades = []
        equity_history = []
        equity_peak = capital

        risk_config = self.config["risk"]
        stop_loss_pct = risk_config["stop_loss_pct"]
        take_profit_pct = risk_config["take_profit_pct"]
        max_position_pct = risk_config["max_position_pct"]

        # 需要足够数据才能计算指标
        min_bars = 100

        for i in range(min_bars, len(df)):
            current_df = df.iloc[:i + 1]
            current_price = current_df["close"].iloc[-1]
            current_time = current_df.index[-1]

            # 计算当前权益
            equity = capital + position * current_price
            equity_history.append(equity)
            equity_peak = max(equity_peak, equity)

            # 检查已有持仓的止损/止盈
            if position > 0:
                unrealized_pnl_pct = (current_price - entry_price) / entry_price
                if unrealized_pnl_pct <= -stop_loss_pct:
                    # 止损
                    exit_value = position * current_price * (1 - self.commission)
                    pnl = exit_value - position * entry_price
                    capital += exit_value
                    trades.append(Trade(
                        symbol=symbol, entry_time=entry_time, exit_time=current_time,
                        entry_price=entry_price, exit_price=current_price,
                        amount=position, pnl=pnl, pnl_pct=unrealized_pnl_pct,
                    ))
                    position = 0.0
                    entry_price = 0.0
                    continue
                elif unrealized_pnl_pct >= take_profit_pct:
                    # 止盈
                    exit_value = position * current_price * (1 - self.commission)
                    pnl = exit_value - position * entry_price
                    capital += exit_value
                    trades.append(Trade(
                        symbol=symbol, entry_time=entry_time, exit_time=current_time,
                        entry_price=entry_price, exit_price=current_price,
                        amount=position, pnl=pnl, pnl_pct=unrealized_pnl_pct,
                    ))
                    position = 0.0
                    entry_price = 0.0
                    continue

            # 生成信号
            result = strategy.generate_signal(current_df, symbol)

            if result.signal == Signal.BUY and position == 0:
                invest = capital * max_position_pct
                amount = invest / (current_price * (1 + self.commission))
                if amount * current_price >= 10:
                    position = amount
                    entry_price = current_price
                    entry_time = current_time
                    capital -= invest

            elif result.signal == Signal.SELL and position > 0:
                exit_value = position * current_price * (1 - self.commission)
                pnl = exit_value - position * entry_price
                pnl_pct = (current_price - entry_price) / entry_price
                capital += exit_value
                trades.append(Trade(
                    symbol=symbol, entry_time=entry_time, exit_time=current_time,
                    entry_price=entry_price, exit_price=current_price,
                    amount=position, pnl=pnl, pnl_pct=pnl_pct,
                ))
                position = 0.0
                entry_price = 0.0

        # 平仓剩余持仓
        if position > 0:
            final_price = df["close"].iloc[-1]
            exit_value = position * final_price * (1 - self.commission)
            pnl = exit_value - position * entry_price
            capital += exit_value
            trades.append(Trade(
                symbol=symbol, entry_time=entry_time, exit_time=df.index[-1],
                entry_price=entry_price, exit_price=final_price,
                amount=position, pnl=pnl,
                pnl_pct=(final_price - entry_price) / entry_price,
            ))

        # 计算指标
        total_return = capital - self.initial_capital
        total_return_pct = total_return / self.initial_capital

        equity_series = pd.Series(equity_history, index=df.index[min_bars:])
        daily_returns = equity_series.pct_change().dropna()

        sharpe = 0.0
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)

        max_drawdown = 0.0
        if len(equity_history) > 0:
            peak = np.maximum.accumulate(np.array(equity_history))
            drawdown = (np.array(equity_history) - peak) / peak
            max_drawdown = abs(drawdown.min())

        winning = [t for t in trades if t.pnl > 0]
        win_rate = len(winning) / len(trades) if trades else 0

        total_profit = sum(t.pnl for t in trades if t.pnl > 0)
        total_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = total_profit / total_loss if total_loss != 0 else float("inf")

        logger.info(f"回测完成: {symbol}")
        logger.info(f"  总收益率: {total_return_pct:.2%}")
        logger.info(f"  夏普比率: {sharpe:.2f}")
        logger.info(f"  最大回撤: {max_drawdown:.2%}")
        logger.info(f"  胜率: {win_rate:.2%}")
        logger.info(f"  交易次数: {len(trades)}")
        logger.info(f"  盈亏比: {profit_factor:.2f}")

        return BacktestResult(
            total_return=total_return,
            total_return_pct=total_return_pct,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            total_trades=len(trades),
            profit_factor=profit_factor,
            trades=trades,
            equity_curve=equity_series,
        )