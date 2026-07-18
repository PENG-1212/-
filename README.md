# OKX Trading Bot Starter

A conservative Python starter for an OKX trading bot.

## What this version does

- Reads OKX credentials from environment variables
- Uses `ccxt` to talk to OKX spot markets
- Defaults to dry-run mode
- Uses SMA crossovers plus RSI filtering
- Persists bot state locally in `bot_state.json`
- Supports stop-loss and take-profit exits
- Can send Telegram alerts

## Quick start

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your values.
4. Run the bot:

```bash
python okx_bot.py
```

## Safety defaults

- Live trading is disabled unless `ALLOW_LIVE_TRADING=true`
- Dry-run remains on unless live trading is explicitly enabled
- Position size is capped by `MAX_POSITION_USDT`
- Exits are protected by `STOP_LOSS_PCT` and `TAKE_PROFIT_PCT`

## Files

- `okx_bot.py` — main bot loop
- `bot_state.json` — local position/state file
- `.env.example` — configuration template

## Notes

This is a starter template, not a profit guarantee. Test in dry-run mode first, then use a small amount of capital if you decide to go live.
