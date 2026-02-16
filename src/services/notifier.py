"""Notification service for sending trade alerts.

Currently supports Telegram.
"""

import aiohttp
from loguru import logger

from src.config import AppSettings


class TelegramNotifier:
    """Async Telegram notification handler."""

    def __init__(self, settings: AppSettings) -> None:
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.enabled = bool(self.token and self.chat_id)
        if not self.enabled:
            logger.info("Telegram notifications disabled (missing token/chat_id)")

    async def send(self, message: str) -> bool:
        """Send a message to the configured Telegram chat."""
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.debug("Telegram message sent")
                        return True
                    else:
                        text = await response.text()
                        logger.error(f"Failed to send Telegram message: {response.status} - {text}")
                        return False
        except Exception as e:
            logger.error(f"Telegram connection error: {e}")
            return False
