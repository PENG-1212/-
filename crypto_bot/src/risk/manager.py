"""
风险控制模块
- 仓位计算
- 止损止盈检查
- 日亏损限制
"""

from datetime import datetime, date
from loguru import logger
from typing import Optional


class RiskManager:
    """风险管理器"""

    def __init__(self, config: dict):
        risk = config["risk"]
        self.max_position_pct = risk["max_position_pct"]
        self.max_total_exposure = risk["max_total_exposure"]
        self.max_loss_per_trade = risk["max_loss_per_trade_pct"]
        self.max_daily_loss = risk["max_daily_loss_pct"]
        self.stop_loss_pct = risk["stop_loss_pct"]
        self.take_profit_pct = risk["take_profit_pct"]
        self.trailing_stop = risk.get("trailing_stop", False)

        self.daily_pnl = 0.0
        self.today = date.today()
        self.total_trades = 0
        self.winning_trades = 0
        self.highest_price = {}  # {symbol: highest_price} 用于追踪止损

    def _reset_daily_if_needed(self):
        if date.today() != self.today:
            self.daily_pnl = 0.0
            self.today = date.today()

    def can_trade(self, total_equity: float) -> bool:
        """检查是否达到日亏损上限"""
        self._reset_daily_if_needed()
        if total_equity <= 0:
            return False
        daily_loss_pct = abs(self.daily_pnl) / total_equity
        if daily_loss_pct >= self.max_daily_loss:
            logger.warning(
                f"日内亏损已达上限 {daily_loss_pct:.2%}，停止交易"
            )
            return False
        return True

    def calculate_position_size(self, equity: float, price: float,
                                 symbol: str = "") -> float:
        """
        计算仓位大小
        返回: 应买入的币的数量
        """
        max_invest = equity * self.max_position_pct
        amount = max_invest / price
        logger.info(
            f"仓位计算 [{symbol}]: 权益={equity:.2f}, "
            f"最大投入={max_invest:.2f}, 数量={amount:.6f}"
        )
        return amount

    def check_stop_loss(self, entry_price: float, current_price: float,
                         position: float) -> bool:
        """检查是否触发止损"""
        if position <= 0:
            return False
        loss_pct = (current_price - entry_price) / entry_price
        if loss_pct <= -self.stop_loss_pct:
            logger.warning(
                f"止损触发! 入场={entry_price}, 当前={current_price}, "
                f"亏损={loss_pct:.2%}"
            )
            return True
        return False

    def check_take_profit(self, entry_price: float, current_price: float,
                           position: float) -> bool:
        """检查是否触发止盈"""
        if position <= 0:
            return False
        profit_pct = (current_price - entry_price) / entry_price
        if profit_pct >= self.take_profit_pct:
            logger.info(
                f"止盈触发! 入场={entry_price}, 当前={current_price}, "
                f"盈利={profit_pct:.2%}"
            )
            return True
        return False

    def update_trailing_stop(self, symbol: str, entry_price: float,
                              current_price: float, position: float) -> bool:
        """
        追踪止损: 价格从最高点回落一定比例则止损
        返回 True 表示触发止损
        """
        if not self.trailing_stop or position <= 0:
            return False

        if symbol not in self.highest_price:
            self.highest_price[symbol] = entry_price
        self.highest_price[symbol] = max(self.highest_price[symbol], current_price)

        drawdown = (self.highest_price[symbol] - current_price) / self.highest_price[symbol]
        if drawdown >= self.stop_loss_pct:
            logger.warning(
                f"追踪止损触发 [{symbol}]: 最高={self.highest_price[symbol]:.4f}, "
                f"当前={current_price:.4f}, 回撤={drawdown:.2%}"
            )
            return True
        return False

    def record_trade(self, pnl: float, is_win: bool):
        self.daily_pnl += pnl
        self.total_trades += 1
        if is_win:
            self.winning_trades += 1

    def get_stats(self) -> dict:
        return {
            "daily_pnl": self.daily_pnl,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": (self.winning_trades / self.total_trades
                         if self.total_trades > 0 else 0),
        }