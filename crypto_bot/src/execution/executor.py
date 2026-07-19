"""
订单执行器
负责将策略信号转化为实际订单
"""

from typing import Optional
from loguru import logger
from dataclasses import dataclass, field

from ..exchange import ExchangeClient
from ..strategies import StrategyResult, Signal
from ..risk import RiskManager
from ..notification import Notifier


@dataclass
class Position:
    symbol: str
    entry_price: float
    amount: float
    stop_loss: float
    take_profit: float
    entry_time: str = ""


class OrderExecutor:
    """订单执行器"""

    def __init__(self, exchange: ExchangeClient, risk: RiskManager,
                 notifier: Optional[Notifier] = None, config: dict = None):
        self.exchange = exchange
        self.risk = risk
        self.notifier = notifier
        self.config = config or {}
        self.positions: dict[str, Position] = {}
        self.trade_log: list[dict] = []

    def execute(self, result: StrategyResult, symbol: str):
        """执行策略信号"""
        quote = self.exchange.config["trading"]["quote_currency"]
        equity = self.exchange.fetch_balance_quote(quote)

        if not self.risk.can_trade(equity):
            logger.warning("风险控制禁止交易，跳过执行")
            return

        bid, ask = self.exchange.get_bid_ask(symbol)
        current_price = ask if result.signal == Signal.BUY else bid

        # 检查已有持仓的止损止盈
        if symbol in self.positions:
            pos = self.positions[symbol]
            if self.risk.check_stop_loss(pos.entry_price, current_price, pos.amount):
                self._close_position(symbol, "止损")
                return
            if self.risk.check_take_profit(pos.entry_price, current_price, pos.amount):
                self._close_position(symbol, "止盈")
                return
            if self.risk.update_trailing_stop(symbol, pos.entry_price,
                                               current_price, pos.amount):
                self._close_position(symbol, "追踪止损")
                return

        if result.signal == Signal.BUY:
            self._execute_buy(result, symbol, equity, current_price)
        elif result.signal == Signal.SELL:
            self._execute_sell(result, symbol, current_price)

    def _execute_buy(self, result: StrategyResult, symbol: str,
                      equity: float, current_price: float):
        # 已持仓不重复买入
        if symbol in self.positions:
            logger.info(f"[{symbol}] 已有持仓，跳过买入")
            return

        amount = self.risk.calculate_position_size(equity, current_price, symbol)
        if amount * current_price < 10:
            logger.warning(f"[{symbol}] 订单金额过小，跳过")
            return

        order = self.exchange.create_market_buy(symbol, amount)
        if order:
            self.positions[symbol] = Position(
                symbol=symbol,
                entry_price=current_price,
                amount=amount,
                stop_loss=result.stop_loss_price,
                take_profit=result.take_profit_price,
            )
            msg = (f"✅ 买入 [{symbol}]\n"
                   f"价格: {current_price:.4f}\n"
                   f"数量: {amount:.6f}\n"
                   f"止损: {result.stop_loss_price:.4f}\n"
                   f"止盈: {result.take_profit_price:.4f}\n"
                   f"原因: {result.metadata.get('reason', '')}")
            logger.info(msg)
            self._notify(msg)
            self.trade_log.append({"action": "BUY", "symbol": symbol,
                                   "price": current_price, "amount": amount,
                                   "reason": result.metadata})

    def _execute_sell(self, result: StrategyResult, symbol: str,
                       current_price: float):
        if symbol not in self.positions:
            logger.info(f"[{symbol}] 无持仓，跳过卖出")
            return

        pos = self.positions[symbol]
        order = self.exchange.create_market_sell(symbol, pos.amount)
        if order:
            pnl = (current_price - pos.entry_price) * pos.amount
            pnl_pct = (current_price - pos.entry_price) / pos.entry_price
            self.risk.record_trade(pnl, pnl > 0)

            msg = (f"{'✅' if pnl > 0 else '❌'} 卖出 [{symbol}]\n"
                   f"入场: {pos.entry_price:.4f} → 出场: {current_price:.4f}\n"
                   f"盈亏: {pnl:.2f} USDT ({pnl_pct:+.2%})\n"
                   f"原因: {result.metadata.get('reason', '')}")
            logger.info(msg)
            self._notify(msg)
            self.trade_log.append({"action": "SELL", "symbol": symbol,
                                   "price": current_price, "amount": pos.amount,
                                   "pnl": pnl, "pnl_pct": pnl_pct,
                                   "reason": result.metadata})
            del self.positions[symbol]

    def _close_position(self, symbol: str, reason: str):
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        bid, _ = self.exchange.get_bid_ask(symbol)
        order = self.exchange.create_market_sell(symbol, pos.amount)
        if order:
            pnl = (bid - pos.entry_price) * pos.amount
            pnl_pct = (bid - pos.entry_price) / pos.entry_price
            self.risk.record_trade(pnl, pnl > 0)

            msg = (f"🛑 {reason} [{symbol}]\n"
                   f"入场: {pos.entry_price:.4f} → 出场: {bid:.4f}\n"
                   f"盈亏: {pnl:.2f} USDT ({pnl_pct:+.2%})")
            logger.info(msg)
            self._notify(msg)
            self.trade_log.append({"action": "SELL", "symbol": symbol,
                                   "price": bid, "amount": pos.amount,
                                   "pnl": pnl, "pnl_pct": pnl_pct,
                                   "reason": reason})
            del self.positions[symbol]

    def _notify(self, msg: str):
        if self.notifier:
            self.notifier.send(msg)

    def get_summary(self) -> dict:
        return {
            "positions": {
                sym: {
                    "entry": p.entry_price,
                    "amount": p.amount,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                }
                for sym, p in self.positions.items()
            },
            "risk": self.risk.get_stats(),
            "trade_count": len(self.trade_log),
        }