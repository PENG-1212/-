from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import parse, request

import ccxt
import pandas as pd
from dotenv import load_dotenv


STATE_DEFAULT_PATH = Path(os.getenv("BOT_STATE_FILE", "bot_state.json"))


@dataclass
class BotConfig:
    api_key: str
    api_secret: str
    passphrase: str
    symbol: str = "BTC/USDT"
    timeframe: str = "1m"
    fast_sma: int = 10
    slow_sma: int = 30
    rsi_period: int = 14
    rsi_buy_max: float = 70.0
    rsi_sell_min: float = 30.0
    risk_fraction: float = 0.02
    max_position_usdt: float = 100.0
    stop_loss_pct: float = 0.01
    take_profit_pct: float = 0.02
    dry_run: bool = True
    allow_live_trading: bool = False
    poll_interval_sec: int = 60
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


@dataclass
class PositionState:
    side: str = "flat"  # flat or long
    amount: float = 0.0
    entry_price: float = 0.0
    opened_at: str = ""


@dataclass
class BotState:
    position: PositionState = field(default_factory=PositionState)
    last_signal: str = "HOLD"
    last_trade_at: str = ""
    last_error: str = ""


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
        rsi_period=env_int("RSI_PERIOD", 14),
        rsi_buy_max=env_float("RSI_BUY_MAX", 70.0),
        rsi_sell_min=env_float("RSI_SELL_MIN", 30.0),
        risk_fraction=env_float("RISK_FRACTION", 0.02),
        max_position_usdt=env_float("MAX_POSITION_USDT", 100.0),
        stop_loss_pct=env_float("STOP_LOSS_PCT", 0.01),
        take_profit_pct=env_float("TAKE_PROFIT_PCT", 0.02),
        dry_run=env_bool("DRY_RUN", True),
        allow_live_trading=env_bool("ALLOW_LIVE_TRADING", False),
        poll_interval_sec=env_int("POLL_INTERVAL_SEC", 60),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )


def make_exchange(cfg: BotConfig) -> ccxt.okx:
    if not cfg.api_key or not cfg.api_secret or not cfg.passphrase:
        raise ValueError("Missing OKX API credentials in environment variables.")

    return ccxt.okx(
        {
            "apiKey": cfg.api_key,
            "secret": cfg.api_secret,
            "password": cfg.passphrase,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
    )


def load_state(path: Path = STATE_DEFAULT_PATH) -> BotState:
    if not path.exists():
        return BotState()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        position_raw = raw.get("position", {}) or {}
        return BotState(
            position=PositionState(
                side=position_raw.get("side", "flat"),
                amount=float(position_raw.get("amount", 0.0) or 0.0),
                entry_price=float(position_raw.get("entry_price", 0.0) or 0.0),
                opened_at=position_raw.get("opened_at", ""),
            ),
            last_signal=raw.get("last_signal", "HOLD"),
            last_trade_at=raw.get("last_trade_at", ""),
            last_error=raw.get("last_error", ""),
        )
    except Exception:
        return BotState()


def save_state(state: BotState, path: Path = STATE_DEFAULT_PATH) -> None:
    payload = {
        "position": asdict(state.position),
        "last_signal": state.last_signal,
        "last_trade_at": state.last_trade_at,
        "last_error": state.last_error,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def send_telegram(cfg: BotConfig, message: str) -> None:
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        return

    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage"
    data = parse.urlencode({"chat_id": cfg.telegram_chat_id, "text": message}).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    try:
        with request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as exc:
        print(f"Telegram notify failed: {exc}")


def fetch_candles(exchange: ccxt.okx, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def compute_signal(df: pd.DataFrame, fast_sma: int, slow_sma: int, rsi_period: int) -> dict[str, Any]:
    if len(df) < slow_sma + 2:
        return {"signal": "HOLD", "reason": "not_enough_data"}

    close = df["close"]
    fast = close.rolling(fast_sma).mean()
    slow = close.rolling(slow_sma).mean()
    rsi = compute_rsi(close, rsi_period)

    prev_fast, prev_slow = fast.iloc[-2], slow.iloc[-2]
    curr_fast, curr_slow = fast.iloc[-1], slow.iloc[-1]
    curr_rsi = rsi.iloc[-1]

    if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow) or pd.isna(curr_rsi):
        return {"signal": "HOLD", "reason": "indicator_warmup"}

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return {"signal": "BUY", "reason": "golden_cross", "rsi": float(curr_rsi)}
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return {"signal": "SELL", "reason": "death_cross", "rsi": float(curr_rsi)}
    return {"signal": "HOLD", "reason": "no_cross", "rsi": float(curr_rsi)}


def get_last_price(df: pd.DataFrame) -> float:
    return float(df["close"].iloc[-1])


def calc_position_size_usdt(balance_usdt: float, cfg: BotConfig) -> float:
    risk_budget = balance_usdt * cfg.risk_fraction
    return max(0.0, min(risk_budget, cfg.max_position_usdt))


def normalize_amount(exchange: ccxt.okx, symbol: str, amount: float) -> float:
    return float(exchange.amount_to_precision(symbol, amount))


def place_order(
    exchange: ccxt.okx,
    symbol: str,
    side: str,
    amount: float,
    dry_run: bool,
) -> dict[str, Any]:
    preview = {"symbol": symbol, "side": side, "amount": amount, "dry_run": dry_run}
    if dry_run:
        print("[DRY RUN]", preview)
        return preview

    order = exchange.create_market_order(symbol, side.lower(), amount)
    print("[LIVE ORDER]", order)
    return order


def close_long_position(exchange: ccxt.okx, cfg: BotConfig, state: BotState, last_price: float) -> Optional[dict[str, Any]]:
    if state.position.side != "long" or state.position.amount <= 0:
        return None

    order = place_order(exchange, cfg.symbol, "sell", state.position.amount, cfg.dry_run)
    state.position = PositionState()
    state.last_trade_at = now_iso()
    return order


def open_long_position(exchange: ccxt.okx, cfg: BotConfig, state: BotState, last_price: float, size_usdt: float) -> Optional[dict[str, Any]]:
    amount = normalize_amount(exchange, cfg.symbol, size_usdt / last_price)
    if amount <= 0:
        return None

    order = place_order(exchange, cfg.symbol, "buy", amount, cfg.dry_run)
    state.position = PositionState(side="long", amount=amount, entry_price=last_price, opened_at=now_iso())
    state.last_trade_at = now_iso()
    return order


def should_force_exit(cfg: BotConfig, state: BotState, last_price: float) -> tuple[bool, str]:
    if state.position.side != "long" or state.position.entry_price <= 0:
        return False, ""

    stop_price = state.position.entry_price * (1 - cfg.stop_loss_pct)
    take_profit_price = state.position.entry_price * (1 + cfg.take_profit_pct)

    if last_price <= stop_price:
        return True, "stop_loss"
    if last_price >= take_profit_price:
        return True, "take_profit"
    return False, ""


def sync_spot_position_from_balance(exchange: ccxt.okx, cfg: BotConfig, state: BotState, last_price: float) -> None:
    try:
        balance = exchange.fetch_balance()
        base, _quote = cfg.symbol.split("/")
        base_free = float(balance.get(base, {}).get("free", 0.0) or 0.0)
        if base_free > 0 and state.position.side == "flat":
            state.position = PositionState(side="long", amount=base_free, entry_price=last_price, opened_at=now_iso())
    except Exception as exc:
        state.last_error = f"balance_sync_failed: {exc}"


def evaluate_once(exchange: ccxt.okx, cfg: BotConfig, state: BotState) -> BotState:
    df = fetch_candles(exchange, cfg.symbol, cfg.timeframe)
    last_price = get_last_price(df)
    signal_info = compute_signal(df, cfg.fast_sma, cfg.slow_sma, cfg.rsi_period)
    signal = signal_info["signal"]
    rsi = signal_info.get("rsi")

    state.last_signal = signal
    sync_spot_position_from_balance(exchange, cfg, state, last_price)

    snapshot = {
        "symbol": cfg.symbol,
        "timeframe": cfg.timeframe,
        "last_price": round(last_price, 6),
        "signal": signal,
        "reason": signal_info.get("reason"),
        "rsi": None if rsi is None else round(float(rsi), 2),
        "position": asdict(state.position),
        "dry_run": cfg.dry_run,
    }
    print(snapshot)

    force_exit, exit_reason = should_force_exit(cfg, state, last_price)
    if force_exit:
        close_long_position(exchange, cfg, state, last_price)
        msg = f"[{cfg.symbol}] EXIT {exit_reason} at {last_price:.6f}"
        print(msg)
        send_telegram(cfg, msg)
        state.last_error = ""
        return state

    if signal == "BUY" and state.position.side == "flat":
        if rsi is not None and rsi > cfg.rsi_buy_max:
            print(f"Skip BUY: RSI too high ({rsi:.2f})")
            return state

        balance_usdt = 0.0
        try:
            balance = exchange.fetch_balance()
            balance_usdt = float(balance.get("USDT", {}).get("free", 0.0) or 0.0)
        except Exception as exc:
            state.last_error = f"balance_fetch_failed: {exc}"
            print(state.last_error)
            if not cfg.dry_run:
                return state
            balance_usdt = cfg.max_position_usdt

        size_usdt = calc_position_size_usdt(balance_usdt, cfg)
        if size_usdt <= 0:
            print("No usable USDT balance. Skipping BUY.")
            return state

        open_long_position(exchange, cfg, state, last_price, size_usdt)
        msg = f"[{cfg.symbol}] BUY at {last_price:.6f} size_usdt≈{size_usdt:.2f}"
        print(msg)
        send_telegram(cfg, msg)
        state.last_error = ""
        return state

    if signal == "SELL" and state.position.side == "long":
        if rsi is not None and rsi < cfg.rsi_sell_min:
            print(f"Warning: SELL signal with low RSI ({rsi:.2f})")
        close_long_position(exchange, cfg, state, last_price)
        msg = f"[{cfg.symbol}] SELL at {last_price:.6f}"
        print(msg)
        send_telegram(cfg, msg)
        state.last_error = ""
        return state

    state.last_error = ""
    return state


def main() -> None:
    cfg = load_config()
    if not cfg.allow_live_trading:
        cfg.dry_run = True

    exchange = make_exchange(cfg)
    exchange.load_markets()

    state = load_state()
    while True:
        try:
            state = evaluate_once(exchange, cfg, state)
            save_state(state)
        except Exception as exc:
            state.last_error = str(exc)
            save_state(state)
            print(f"Bot error: {exc}")
            send_telegram(cfg, f"[BOT ERROR] {exc}")
        time.sleep(cfg.poll_interval_sec)


if __name__ == "__main__":
    main()
