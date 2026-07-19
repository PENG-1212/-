from .base import BaseStrategy, StrategyResult, Signal
from .ema_cross import EMACrossStrategy
from .macd import MACDStrategy
from .rsi import RSIStrategy
from .grid import GridStrategy

STRATEGY_MAP = {
    "ema_cross": EMACrossStrategy,
    "macd": MACDStrategy,
    "rsi": RSIStrategy,
    "grid": GridStrategy,
}


def create_strategy(config: dict) -> BaseStrategy:
    active = config["strategies"]["active"]
    strategy_cls = STRATEGY_MAP.get(active)
    if strategy_cls is None:
        raise ValueError(f"未知策略: {active}，可选: {list(STRATEGY_MAP.keys())}")
    return strategy_cls(config)