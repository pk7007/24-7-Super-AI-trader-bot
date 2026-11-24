"""Optional Telegram alerts. Token/chat id come from the environment only (RULE 6)."""

from __future__ import annotations

import logging
import os
import urllib.parse
import urllib.request

log = logging.getLogger("notify")


def send(text: str) -> None:
    log.warning("ALERT: %s", text)
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text[:3500]}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=10)
    except Exception as exc:  # alerts must never crash the bot
        log.error("telegram send failed: %s", type(exc).__name__)
