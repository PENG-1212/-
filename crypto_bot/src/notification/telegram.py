"""
通知模块
支持 Telegram Bot 通知
"""

import requests
from loguru import logger
from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    @abstractmethod
    def send(self, message: str) -> bool:
        pass


class TelegramNotifier(BaseNotifier):
    """Telegram Bot 通知器"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send(self, message: str) -> bool:
        try:
            url = f"{self.base_url}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10)
            if resp.status_code == 200:
                return True
            logger.warning(f"Telegram 发送失败: {resp.text}")
            return False
        except Exception as e:
            logger.error(f"Telegram 通知异常: {e}")
            return False


class ConsoleNotifier(BaseNotifier):
    """控制台通知器（调试用）"""

    def send(self, message: str) -> bool:
        logger.info(f"[通知] {message}")
        return True


class Notifier:
    """统一通知器"""

    def __init__(self, config: dict):
        self.notifiers: list[BaseNotifier] = []
        self.notifiers.append(ConsoleNotifier())

        tg_config = config.get("notification", {}).get("telegram", {})
        if tg_config.get("enabled") and tg_config.get("bot_token"):
            self.notifiers.append(
                TelegramNotifier(tg_config["bot_token"], tg_config["chat_id"])
            )
            logger.info("Telegram 通知已启用")

    def send(self, message: str) -> bool:
        results = []
        for notifier in self.notifiers:
            results.append(notifier.send(message))
        return any(results)