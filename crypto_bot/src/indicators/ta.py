"""
技术指标计算模块
不依赖 talib，纯 pandas/numpy 实现，方便部署
"""

import pandas as pd
import numpy as np
from typing import Tuple


class Indicator:

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        return series.rolling(window=period).mean()

    @staticmethod
    def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
             ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """返回 MACD 线、信号线、柱状图"""
        ema_fast = Indicator.ema(close, fast)
        ema_slow = Indicator.ema(close, slow)
        macd_line = ema_fast - ema_slow
        signal_line = Indicator.ema(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def bollinger_bands(close: pd.Series, period: int = 20, std: int = 2
                        ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """返回上轨、中轨、下轨"""
        middle = Indicator.sma(close, period)
        std_dev = close.rolling(window=period).std()
        upper = middle + std * std_dev
        lower = middle - std * std_dev
        return upper, middle, lower

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
            ) -> pd.Series:
        """平均真实波幅"""
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return Indicator.ema(tr, period)

    @staticmethod
    def support_resistance(high: pd.Series, low: pd.Series, window: int = 20
                           ) -> Tuple[float, float]:
        """计算最近支撑位和阻力位 (swing high/low)"""
        recent_high = high.tail(window).max()
        recent_low = low.tail(window).min()
        return recent_low, recent_high

    @staticmethod
    def trend_strength(close: pd.Series, period: int = 20) -> float:
        """趋势强度: 正值表示上涨趋势，负值表示下跌"""
        slope = (close.iloc[-1] - close.iloc[-period]) / close.iloc[-period]
        return slope

    @staticmethod
    def volume_profile(close: pd.Series, volume: pd.Series, bins: int = 10
                       ) -> pd.Series:
        """成交量分布"""
        price_bins = pd.cut(close, bins=bins)
        return volume.groupby(price_bins).sum()