from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import ccxt
import pandas as pd
from dotenv import load_dotenv


@dataclass
class BotConfig:
    api_key: str
    api_secret: str
    passphrase: str
    symbol: str = "BTC/USDT"
    timeframe: str = "1m"
    fast_sma: int = 10
    slow_sma: int = 30
    risk_fraction: float = 0.02
    max_position_usdt: float = 100.0
    stop_loss_pct: float = 0.01
    take_profit_pct: float = 0.02
    dry_run: bool = True
    allow_live_trading: bool = False


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None and value != "" else default


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None and value != "" else default


def load_config() -> BotConfig:
    load_dotenv()
    return BotConfig(
        api_key=os.getenv("OKX_API_KEY", ""),
        api_secret=os.getenv("OKX_API_SECRET", ""),
        passphrase=os.getenv("OKX_API_PASSPHRASE", ""),
        symbol=os.getenv("OKX_SYMBOL", "BTC/USDT"),
        timeframe=os.getenv("OKX_TIMEFRAME", "1m"),
        fast_sma=env_int("FAST_SMA", 10),
        slow_sma=env_int("SLOW_SMA", 30),
        risk_fraction=env_float("RISK_FRACTION", 0.02),
        max_position_usdt=env_float("MAX_POSITION_USDT", 100.0),
        stop_loss_pct=env_float("STOP_LOSS_PCT", 0.01),
        take_profit_pct=env_float("TAKE_PROFIT_PCT", 0.02),
        dry_run=env_bool("DRY_RUN", True),
        allow_live_trading=env_bool("ALLOW_LIVE_TRADING", False),
    )


def make_exchange(cfg: BotConfig) -> ccxt.okx:
    if not cfg.api_key or not cfg.api_secret or not cfg.passphrase:
        raise ValueError("Missing OKX API credentials in environment variables.")

    exchange = ccxt.okx(
        {
            "apiKey": cfg.api_key,
            "secret": cfg.api_secret,
            "password": cfg.passphrase,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        }
    )
    return exchange


def fetch_candles(exchange: ccxt.okx, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


def compute_signal(df: pd.DataFrame, fast_sma: int, slow_sma: int) -> str:
    if len(df) < slow_sma + 2:
        return "HOLD"

    close = df["close"]
    fast = close.rolling(fast_sma).mean()
    slow = close.rolling(slow_sma).mean()

    prev_fast, prev_slow = fast.iloc[-2], slow.iloc[-2]
    curr_fast, curr_slow = fast.iloc[-1], slow.iloc[-1]

    if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
        return "HOLD"

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "BUY"
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "SELL"
    return "HOLD"


def get_last_price(df: pd.DataFrame) -> float:
    return float(df["close"].iloc[-1])


def calc_position_size_usdt(balance_usdt: float, cfg: BotConfig) -> float:
    risk_budget = balance_usdt * cfg.risk_fraction
    return max(0.0, min(risk_budget, cfg.max_position_usdt))


def place_order(
    exchange: ccxt.okx,
    symbol: str,
    side: str,
    size_usdt: float,
    last_price: float,
    dry_run: bool,
) -> dict:
    amount = size_usdt / last_price
    amount = float(exchange.amount_to_precision(symbol, amount))

    order_preview = {
        "symbol": symbol,
        "side": side,
        "size_usdt": round(size_usdt, 2),
        "amount": amount,
        "price": last_price,
        "dry_run": dry_run,
    }

    if dry_run:
        print("[DRY RUN]", order_preview)
        return order_preview

    order = exchange.create_market_order(symbol, side.lower(), amount)
    print("[LIVE ORDER]", order)
    return order


def main() -> None:
    cfg = load_config()
    if not cfg.allow_live_trading:
        cfg.dry_run = True

    exchange = make_exchange(cfg)
    exchange.load_markets()

    df = fetch_candles(exchange, cfg.symbol, cfg.timeframe)
    signal = compute_signal(df, cfg.fast_sma, cfg.slow_sma)
    last_price = get_last_price(df)

    print(
        {
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "last_price": last_price,
            "signal": signal,
            "dry_run": cfg.dry_run,
        }
    )

    if signal == "HOLD":
        return

    balance_usdt = 0.0
    try:
        balance = exchange.fetch_balance()
        balance_usdt = float(balance.get("USDT", {}).get("free", 0.0) or 0.0)
    except Exception as exc:
        print(f"Could not fetch balance: {exc}")
        if cfg.dry_run:
            balance_usdt = cfg.max_position_usdt
        else:
            return

    size_usdt = calc_position_size_usdt(balance_usdt, cfg)
    if size_usdt <= 0:
        print("No usable USDT balance. Skipping.")
        return

    side = "buy" if signal == "BUY" else "sell"
    place_order(exchange, cfg.symbol, side, size_usdt, last_price, cfg.dry_run)


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:
            print(f"Bot error: {exc}")
        time.sleep(60)
