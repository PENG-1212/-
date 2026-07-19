import pandas as pd
from .base import BaseStrategy, StrategyResult, Signal
from ..indicators import Indicator


class GridStrategy(BaseStrategy):
    """
    网格交易策略
    在价格区间内自动低买高卖
    """

    def __init__(self, config: dict):
        super().__init__(config)
        params = config["strategies"]["grid"]
        self.grid_count = params["grid_count"]
        self.upper_price = params["upper_price"]
        self.lower_price = params["lower_price"]
        self.order_size = params["order_size"]

        # 网格状态
        self.grid_levels = []
        self.last_action_index = -1

    def _calculate_grid(self, df: pd.DataFrame):
        """计算网格价格层级"""
        close = df["close"]
        recent_high = close.tail(50).max()
        recent_low = close.tail(50).min()

        upper = self.upper_price if self.upper_price > 0 else recent_high * 1.05
        lower = self.lower_price if self.lower_price > 0 else recent_low * 0.95

        self.grid_levels = [
            lower + (upper - lower) * i / (self.grid_count - 1)
            for i in range(self.grid_count)
        ]
        return upper, lower

    def generate_signal(self, df: pd.DataFrame, symbol: str = ""
                        ) -> StrategyResult:
        if len(df) < 50:
            return StrategyResult(Signal.HOLD, metadata={"reason": "数据不足"})

        close = df["close"]
        current_price = close.iloc[-1]
        self._calculate_grid(df)

        # 找到当前价格所在的网格层级
        current_level = 0
        for i, level in enumerate(self.grid_levels):
            if current_price >= level:
                current_level = i

        risk_config = self.config["risk"]

        # 价格在上轨附近 → 卖出
        if current_level >= self.grid_count - 2:
            if self.last_action_index != current_level:
                self.last_action_index = current_level
                return StrategyResult(
                    signal=Signal.SELL,
                    confidence=0.7,
                    take_profit_price=self.grid_levels[-1],
                    metadata={
                        "reason": f"网格上轨卖出",
                        "level": current_level,
                        "price": current_price,
                    },
                )

        # 价格在下轨附近 → 买入
        if current_level <= 1:
            if self.last_action_index != current_level:
                self.last_action_index = current_level
                return StrategyResult(
                    signal=Signal.BUY,
                    confidence=0.7,
                    stop_loss_price=current_price * (1 - risk_config["stop_loss_pct"]),
                    take_profit_price=(self.grid_levels[min(current_level + 2, self.grid_count - 1)]
                                       if current_level + 2 < self.grid_count else
                                       current_price * 1.03),
                    metadata={
                        "reason": f"网格下轨买入",
                        "level": current_level,
                        "price": current_price,
                    },
                )

        return StrategyResult(
            Signal.HOLD, confidence=0.5,
            metadata={
                "reason": "网格等待",
                "level": current_level,
                "price": current_price,
            },
        )