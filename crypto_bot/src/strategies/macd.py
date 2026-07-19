import pandas as pd
from .base import BaseStrategy, StrategyResult, Signal
from ..indicators import Indicator


class MACDStrategy(BaseStrategy):
    """MACD 策略"""

    def __init__(self, config: dict):
        super().__init__(config)
        params = config["strategies"]["macd"]
        self.fast = params["fast"]
        self.slow = params["slow"]
        self.signal_period = params["signal"]

    def generate_signal(self, df: pd.DataFrame, symbol: str = ""
                        ) -> StrategyResult:
        close = df["close"]
        macd_line, signal_line, histogram = Indicator.macd(
            close, self.fast, self.slow, self.signal_period
        )

        if len(macd_line) < 2:
            return StrategyResult(Signal.HOLD, metadata={"reason": "数据不足"})

        # MACD 金叉: MACD 线上穿信号线
        cross_up = (macd_line.iloc[-2] < signal_line.iloc[-2] and
                    macd_line.iloc[-1] > signal_line.iloc[-1])
        # MACD 死叉: MACD 线下穿信号线
        cross_down = (macd_line.iloc[-2] > signal_line.iloc[-2] and
                      macd_line.iloc[-1] < signal_line.iloc[-1])

        current_price = close.iloc[-1]
        risk_config = self.config["risk"]

        if cross_up and histogram.iloc[-1] > 0:
            # 零轴上方金叉，信号更强
            return StrategyResult(
                signal=Signal.BUY,
                confidence=0.85 if macd_line.iloc[-1] > 0 else 0.65,
                stop_loss_price=current_price * (1 - risk_config["stop_loss_pct"]),
                take_profit_price=current_price * (1 + risk_config["take_profit_pct"]),
                metadata={
                    "reason": "MACD 金叉",
                    "macd": macd_line.iloc[-1],
                    "signal": signal_line.iloc[-1],
                    "histogram": histogram.iloc[-1],
                },
            )
        elif cross_down and histogram.iloc[-1] < 0:
            return StrategyResult(
                signal=Signal.SELL,
                confidence=0.85,
                metadata={
                    "reason": "MACD 死叉",
                    "macd": macd_line.iloc[-1],
                    "signal": signal_line.iloc[-1],
                },
            )

        return StrategyResult(
            Signal.HOLD,
            confidence=0.5,
            metadata={
                "trend": "bullish" if macd_line.iloc[-1] > signal_line.iloc[-1] else "bearish",
                "reason": "无信号",
            },
        )