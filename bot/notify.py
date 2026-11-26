"""Optional Telegram alerts. Token/chat id come from the environment only (RULE 6)."""

from __future__ import annotations

import logging
import os
import urllib.parse
import urllib.request

log = logging.getLogger("notify")


def send(text: str) -> bool:
    """Log the alert, and send it to Telegram when configured. Returns False only if a configured
    channel failed, so callers can retry instead of assuming delivery. Never raises."""
    log.warning("ALERT: %s", text)
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return True  # only the log channel is configured, and that succeeded
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text[:3500]}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=10)
        return True
    except Exception as exc:  # alerts must never crash the bot
        log.error("telegram send failed: %s", type(exc).__name__)
        return False
