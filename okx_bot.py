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


...