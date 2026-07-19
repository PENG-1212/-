import pandas as pd
from .base import BaseStrategy, StrategyResult, Signal
from ..indicators import Indicator


class EMACrossStrategy(BaseStrategy):
    """EMA 双均线交叉策略"""

    def __init__(self, config: dict):
        super().__init__(config)
        params = config["strategies"]["ema_cross"]
        self.fast_period = params["fast"]
        self.slow_period = params["slow"]
        self.signal_period = params["signal"]

    def generate_signal(self, df: pd.DataFrame, symbol: str = ""
                        ) -> StrategyResult:
        close = df["close"]
        ema_fast = Indicator.ema(close, self.fast_period)
        ema_slow = Indicator.ema(close, self.slow_period)

        if len(ema_fast) < self.slow_period + 1:
            return StrategyResult(Signal.HOLD, metadata={"reason": "数据不足"})

        # 金叉: 快线上穿慢线
        cross_up = (ema_fast.iloc[-2] < ema_slow.iloc[-2] and
                    ema_fast.iloc[-1] > ema_slow.iloc[-1])
        # 死叉: 快线下穿慢线
        cross_down = (ema_fast.iloc[-2] > ema_slow.iloc[-2] and
                      ema_fast.iloc[-1] < ema_slow.iloc[-1])

        current_price = close.iloc[-1]
        risk_config = self.config["risk"]

        if cross_up:
            return StrategyResult(
                signal=Signal.BUY,
                confidence=0.75,
                stop_loss_price=current_price * (1 - risk_config["stop_loss_pct"]),
                take_profit_price=current_price * (1 + risk_config["take_profit_pct"]),
                metadata={
                    "reason": "EMA 金叉",
                    "ema_fast": ema_fast.iloc[-1],
                    "ema_slow": ema_slow.iloc[-1],
                },
            )
        elif cross_down:
            return StrategyResult(
                signal=Signal.SELL,
                confidence=0.75,
                metadata={
                    "reason": "EMA 死叉",
                    "ema_fast": ema_fast.iloc[-1],
                    "ema_slow": ema_slow.iloc[-1],
                },
            )

        # 趋势跟随: 没有交叉，跟随趋势方向
        trend = "up" if ema_fast.iloc[-1] > ema_slow.iloc[-1] else "down"
        return StrategyResult(
            Signal.HOLD,
            confidence=0.5,
            metadata={"trend": trend, "reason": "无交叉，等待信号"},
        )