import ccxt
import pandas as pd
from loguru import logger
from typing import Optional


class ExchangeClient:
    """交易所 API 抽象层，基于 ccxt 库"""

    def __init__(self, config: dict):
        self.config = config
        exchange_id = config["exchange"]
        exchange_class = getattr(ccxt, exchange_id)

        params = {
            "apiKey": config["api_key"],
            "secret": config["api_secret"],
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }

        if config.get("testnet"):
            params["testnet"] = True
            # 某些交易所需要特殊设置
            if exchange_id == "binance":
                params["urls"] = {"api": {"public": "https://testnet.binance.vision/api"}}

        self.exchange: ccxt.Exchange = exchange_class(params)
        logger.info(f"交易所连接: {exchange_id} (testnet={config['testnet']})")

    def fetch_balance(self, quote: str = "USDT") -> dict:
        """获取账户余额"""
        balance = self.exchange.fetch_balance()
        free = balance.get("free", {})
        return {
            symbol: free.get(symbol, 0)
            for symbol in self.config["trading"]["symbols"]
            if free.get(symbol.split("/")[0], 0) > 0 or free.get(quote, 0) > 0
        }

    def fetch_balance_quote(self, quote: str = "USDT") -> float:
        """获取报价货币余额"""
        balance = self.exchange.fetch_balance()
        return balance.get("free", {}).get(quote, 0)

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200
                    ) -> pd.DataFrame:
        """
        获取 K 线数据，返回 DataFrame
        """
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def fetch_ticker(self, symbol: str) -> dict:
        return self.exchange.fetch_ticker(symbol)

    def create_market_buy(self, symbol: str, amount: float) -> Optional[dict]:
        """市价买入"""
        try:
            return self.exchange.create_market_buy_order(symbol, amount)
        except Exception as e:
            logger.error(f"市价买入失败 {symbol}: {e}")
            return None

    def create_market_sell(self, symbol: str, amount: float) -> Optional[dict]:
        """市价卖出"""
        try:
            return self.exchange.create_market_sell_order(symbol, amount)
        except Exception as e:
            logger.error(f"市价卖出失败 {symbol}: {e}")
            return None

    def create_limit_buy(self, symbol: str, amount: float, price: float
                         ) -> Optional[dict]:
        """限价买入"""
        try:
            return self.exchange.create_limit_buy_order(symbol, amount, price)
        except Exception as e:
            logger.error(f"限价买入失败 {symbol}: {e}")
            return None

    def create_limit_sell(self, symbol: str, amount: float, price: float
                          ) -> Optional[dict]:
        """限价卖出"""
        try:
            return self.exchange.create_limit_sell_order(symbol, amount, price)
        except Exception as e:
            logger.error(f"限价卖出失败 {symbol}: {e}")
            return None

    def fetch_open_orders(self, symbol: Optional[str] = None) -> list:
        return self.exchange.fetch_open_orders(symbol)

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            self.exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"取消订单失败 {order_id}: {e}")
            return False

    def get_position(self, symbol: str) -> float:
        """获取现货持仓数量"""
        base = symbol.split("/")[0]
        balance = self.exchange.fetch_balance()
        return balance.get("free", {}).get(base, 0)

    def get_bid_ask(self, symbol: str) -> tuple:
        """获取当前买一/卖一价"""
        ticker = self.exchange.fetch_ticker(symbol)
        return ticker["bid"], ticker["ask"]