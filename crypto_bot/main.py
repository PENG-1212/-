#!/usr/bin/env python3
"""
加密货币自动交易机器人
========================
用法:
  python main.py run          # 启动实盘交易
  python main.py backtest      # 运行回测
  python main.py status        # 查看当前状态
  python main.py --help        # 帮助
"""

import sys
import time
import argparse
from datetime import datetime
from loguru import logger

from src import load_config
from src.exchange import ExchangeClient
from src.strategies import create_strategy
from src.risk import RiskManager
from src.execution import OrderExecutor
from src.backtest import BacktestEngine
from src.notification import Notifier

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO",
)
logger.add(
    "logs/trading_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO",
)


def run_live(config: dict):
    """启动实盘交易"""
    logger.info("=" * 50)
    logger.info("启动自动交易机器人")
    logger.info(f"交易所: {config['exchange']}")
    logger.info(f"策略: {config['strategies']['active']}")
    logger.info(f"交易对: {config['trading']['symbols']}")
    logger.info(f"周期: {config['trading']['timeframe']}")
    logger.info("=" * 50)

    exchange = ExchangeClient(config)
    risk = RiskManager(config)
    notifier = Notifier(config)
    strategy = create_strategy(config)
    executor = OrderExecutor(exchange, risk, notifier, config)

    notifier.send(f"🤖 交易机器人已启动\n策略: {config['strategies']['active']}\n模式: {'测试网' if config['testnet'] else '实盘'}")

    iteration = 0
    while True:
        try:
            iteration += 1
            logger.info(f"--- 第 {iteration} 轮扫描 ---")

            for symbol in config["trading"]["symbols"]:
                logger.info(f"分析 [{symbol}]...")

                # 获取 K 线
                df = exchange.fetch_ohlcv(
                    symbol,
                    timeframe=config["trading"]["timeframe"],
                    limit=200,
                )

                if len(df) < 50:
                    logger.warning(f"[{symbol}] 数据不足，跳过")
                    continue

                # 生成信号
                result = strategy.generate_signal(df, symbol)
                logger.info(
                    f"[{symbol}] 信号: {result.signal.value} "
                    f"信心: {result.confidence:.2f} "
                    f"原因: {result.metadata.get('reason', '')}"
                )

                # 执行交易
                executor.execute(result, symbol)

            # 状态摘要
            summary = executor.get_summary()
            logger.info(f"持仓: {list(summary['positions'].keys()) or '无'}")
            logger.info(f"日盈亏: {summary['risk']['daily_pnl']:.2f}")
            logger.info(f"胜率: {summary['risk']['win_rate']:.2%}")

            # 等待下一轮（根据时间周期）
            timeframe = config["trading"]["timeframe"]
            sleep_seconds = _timeframe_to_seconds(timeframe)
            logger.info(f"等待 {sleep_seconds}s 后进行下一轮扫描...")
            time.sleep(sleep_seconds)

        except KeyboardInterrupt:
            logger.info("收到停止信号，正在退出...")
            notifier.send("🛑 交易机器人已手动停止")
            break
        except Exception as e:
            logger.error(f"运行异常: {e}")
            notifier.send(f"⚠️ 交易机器人异常: {e}")
            time.sleep(60)


def run_backtest(config: dict):
    """运行回测"""
    logger.info("=" * 50)
    logger.info("启动回测模式")
    logger.info(f"策略: {config['strategies']['active']}")
    logger.info(f"初始资金: {config['backtest']['initial_capital']}")
    logger.info(f"时间范围: {config['backtest']['start_date']} ~ {config['backtest']['end_date']}")
    logger.info("=" * 50)

    import ccxt
    exchange_class = getattr(ccxt, config["exchange"])
    exchange = exchange_class({"enableRateLimit": True})

    engine = BacktestEngine(config)
    strategy = create_strategy(config)

    for symbol in config["trading"]["symbols"]:
        logger.info(f"获取 [{symbol}] 历史数据...")
        since = exchange.parse8601(f"{config['backtest']['start_date']}T00:00:00Z")
        ohlcv = exchange.fetch_ohlcv(
            symbol, config["trading"]["timeframe"], since=since, limit=5000
        )

        import pandas as pd
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)

        end = pd.Timestamp(config["backtest"]["end_date"])
        df = df[df.index <= end]

        logger.info(f"  [{symbol}] 数据: {len(df)} 根K线")
        result = engine.run(strategy, df, symbol)

        print("\n" + "=" * 50)
        print(f"回测结果: {symbol}")
        print("=" * 50)
        print(f"总收益率:   {result.total_return_pct:+.2%}")
        print(f"总收益:     {result.total_return:+.2f} USDT")
        print(f"夏普比率:   {result.sharpe_ratio:.2f}")
        print(f"最大回撤:   {result.max_drawdown:.2%}")
        print(f"胜率:       {result.win_rate:.2%}")
        print(f"交易次数:   {result.total_trades}")
        print(f"盈亏比:     {result.profit_factor:.2f}")
        print("=" * 50)


def run_status(config: dict):
    """查看当前状态"""
    exchange = ExchangeClient(config)
    risk = RiskManager(config)

    print("\n" + "=" * 50)
    print("交易机器人状态")
    print("=" * 50)
    print(f"交易所: {config['exchange']}")
    print(f"模式: {'测试网' if config['testnet'] else '实盘'}")
    print(f"策略: {config['strategies']['active']}")

    try:
        quote = config["trading"]["quote_currency"]
        balance = exchange.fetch_balance_quote(quote)
        print(f"\n账户余额: {balance:.2f} {quote}")

        for symbol in config["trading"]["symbols"]:
            pos = exchange.get_position(symbol)
            ticker = exchange.fetch_ticker(symbol)
            if pos > 0:
                value = pos * ticker["last"]
                print(f"\n[{symbol}]")
                print(f"  持仓: {pos:.6f}")
                print(f"  价值: {value:.2f} {quote}")
                print(f"  当前价: {ticker['last']:.4f}")
                print(f"  24h涨跌: {ticker['percentage']:.2f}%")
            else:
                print(f"\n[{symbol}] 无持仓 | 当前价: {ticker['last']:.4f}")

    except Exception as e:
        print(f"获取状态失败: {e}")

    risk_stats = risk.get_stats()
    print(f"\n风险统计:")
    print(f"  日盈亏: {risk_stats['daily_pnl']:.2f}")
    print(f"  总交易: {risk_stats['total_trades']}")
    print(f"  胜率: {risk_stats['win_rate']:.2%}")
    print("=" * 50)


def _timeframe_to_seconds(tf: str) -> int:
    """时间周期转秒"""
    unit = tf[-1]
    value = int(tf[:-1])
    mapping = {"m": 60, "h": 3600, "d": 86400}
    return value * mapping.get(unit, 60)


def main():
    parser = argparse.ArgumentParser(description="加密货币自动交易机器人")
    parser.add_argument(
        "command",
        choices=["run", "backtest", "status"],
        default="run",
        nargs="?",
        help="运行模式: run(实盘), backtest(回测), status(状态)",
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="配置文件路径",
    )
    parser.add_argument(
        "--symbol", "-s",
        default=None,
        help="指定交易对（覆盖配置）",
    )
    args = parser.parse_args()

    config = load_config()
    if args.symbol:
        config["trading"]["symbols"] = [args.symbol]

    if not config["api_key"] or config["api_key"] == "your_api_key_here":
        logger.error("请先在 .env 文件中设置 API_KEY 和 API_SECRET")
        sys.exit(1)

    commands = {
        "run": run_live,
        "backtest": run_backtest,
        "status": run_status,
    }
    commands[args.command](config)


if __name__ == "__main__":
    main()