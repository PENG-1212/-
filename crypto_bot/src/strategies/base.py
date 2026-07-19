"""
策略基类
所有策略必须继承此基类，实现 generate_signal() 方法
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
import pandas as pd


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class StrategyResult:
    signal: Signal
    confidence: float = 0.0         # 0.0 ~ 1.0
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, config: dict):
        self.config = config
        self.name = self.__class__.__name__
        self.symbol = ""

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, symbol: str = ""
                        ) -> StrategyResult:
        """根据 K 线数据生成交易信号"""
        pass

    def set_params(self, **kwargs):
        """动态设置策略参数"""
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)