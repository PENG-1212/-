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
- Includes a Streamlit web dashboard for backtesting and signal viewing

## Quick start

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your values.
4. Run the web dashboard:

```bash
streamlit run web_app.py
```

5. Run the bot loop separately if you want the polling trader:

```bash
python okx_bot.py
```

## Safety defaults

- Live trading is disabled unless `ALLOW_LIVE_TRADING=true`
- Dry-run remains on unless live trading is explicitly enabled
- Position size is capped by `MAX_POSITION_USDT`
- Exits are protected by `STOP_LOSS_PCT` and `TAKE_PROFIT_PCT`
- The web dashboard is for analysis and backtesting, not custody

## Files

- `web_app.py` — Streamlit dashboard
- `okx_bot.py` — main bot loop
- `bot_state.json` — local position/state file
- `.env.example` — configuration template

## Notes

This is a starter template, not a profit guarantee. Test in dry-run mode first, then use a small amount of capital if you decide to go live.
