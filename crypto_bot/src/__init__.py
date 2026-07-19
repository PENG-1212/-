import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def load_config() -> dict:
    config_path = BASE_DIR / "config" / "settings.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # 从环境变量覆盖 API 密钥
    if os.getenv("API_KEY"):
        config["api_key"] = os.getenv("API_KEY")
    if os.getenv("API_SECRET"):
        config["api_secret"] = os.getenv("API_SECRET")

    # 从环境变量覆盖 Telegram
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        config["notification"]["telegram"]["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
    if os.getenv("TELEGRAM_CHAT_ID"):
        config["notification"]["telegram"]["chat_id"] = os.getenv("TELEGRAM_CHAT_ID")

    return config


__all__ = ["load_config", "BASE_DIR"]