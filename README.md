# OKX Trading Bot Starter

A small Python starter for a conservative OKX trading bot.

## Features

- Loads credentials from environment variables
- Uses `ccxt` to talk to OKX
- Supports `dry run` by default
- Includes a simple moving-average crossover signal
- Includes basic risk controls

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
- The bot uses a small position fraction by default
- If there is not enough balance, it will skip the trade

## Notes

This is a starter template, not a profit guarantee. Always test in dry-run mode first.
