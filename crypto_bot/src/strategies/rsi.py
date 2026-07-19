import pandas as pd
from .base import BaseStrategy, StrategyResult, Signal
from ..indicators import Indicator


class RSIStrategy(BaseStrategy):
    """RSI 超买超卖策略"""

    def __init__(self, config: dict):
        super().__init__(config)
        params = config["strategies"]["rsi"]
        self.period = params["period"]
        self.oversold = params["oversold"]
        self.overbought = params["overbought"]

    def generate_signal(self, df: pd.DataFrame, symbol: str = ""
                        ) -> StrategyResult:
        close = df["close"]
        rsi = Indicator.rsi(close, self.period)

        if len(rsi) < self.period + 1:
            return StrategyResult(Signal.HOLD, metadata={"reason": "数据不足"})

        current_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        current_price = close.iloc[-1]
        risk_config = self.config["risk"]

        # RSI 从超卖区向上突破 → 买入
        if prev_rsi < self.oversold and current_rsi > self.oversold:
            return StrategyResult(
                signal=Signal.BUY,
                confidence=0.8,
                stop_loss_price=current_price * (1 - risk_config["stop_loss_pct"]),
                take_profit_price=current_price * (1 + risk_config["take_profit_pct"]),
                metadata={"reason": "RSI 超卖反弹", "rsi": current_rsi},
            )

        # RSI 从超买区向下突破 → 卖出
        if prev_rsi > self.overbought and current_rsi < self.overbought:
            return StrategyResult(
                signal=Signal.SELL,
                confidence=0.8,
                metadata={"reason": "RSI 超买回落", "rsi": current_rsi},
            )

        # 极值区域
        if current_rsi < self.oversold:
            return StrategyResult(
                Signal.HOLD, confidence=0.3,
                metadata={"reason": "RSI 超卖区等待", "rsi": current_rsi},
            )
        if current_rsi > self.overbought:
            return StrategyResult(
                Signal.HOLD, confidence=0.3,
                metadata={"reason": "RSI 超买区预警", "rsi": current_rsi},
            )

        return StrategyResult(
            Signal.HOLD, confidence=0.5,
            metadata={"reason": "RSI 中性区间", "rsi": current_rsi},
        )