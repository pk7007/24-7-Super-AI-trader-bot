"""Optional external heartbeat ("dead man's switch").

Alerts on this PC cannot fire when the PC itself is off or asleep. Set ``HEARTBEAT_URL`` in ``.env`` to the ping URL
of an outside monitor (for example a free healthchecks.io check, period 5 minutes, grace 7 minutes); the bot sends
an HTTPS GET every 5 minutes and right after each processed candle, and the monitor emails or messages you when
pings stop. Pings stop when the bot dies, the PC sleeps or the network drops, and also when a candle is skipped
after all its retries failed (until a later candle succeeds), so "running but broken" alerts too.
Nothing is sent when it is not set. Only https URLs are used. The URL is treated as a secret: it is never logged
or written to disk. Status goes to ``state/<mode>/heartbeat.json``.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("heartbeat")


_CTX: ssl.SSLContext | None = None


def _ssl_context() -> ssl.SSLContext:
    """System trust store plus certifi's bundle (full verification kept). On 2026-11-27 hc-ping.com moved to a
    Sectigo chain the Windows store did not have yet, and every ping failed; certifi already trusted it."""
    global _CTX
    if _CTX is None:
        ctx = ssl.create_default_context()
        try:
            import certifi

            ctx.load_verify_locations(certifi.where())
        except (ImportError, OSError):
            log.warning("certifi unavailable; heartbeat uses the system trust store only")
        _CTX = ctx
    return _CTX


def _open(url: str, timeout: float) -> None:
    urllib.request.urlopen(url, timeout=timeout, context=_ssl_context()).close()


def ping(status: Path, opener=_open, timeout: float = 10.0) -> bool | None:
    """True = delivered, False = configured but failed, None = not configured. Never raises."""
    url = os.environ.get("HEARTBEAT_URL", "").strip()
    if not url:
        return None
    status = Path(status)
    try:
        prev = json.loads(status.read_text()) if status.exists() else {}
    except (OSError, ValueError):
        prev = {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        if not url.lower().startswith("https://"):
            raise ValueError("HEARTBEAT_URL must start with https://")
        opener(url, timeout)
        rec, ok = {"last_ok_utc": now, "last_error": None, "fails": 0}, True
    except Exception as exc:  # noqa: BLE001 - monitoring must never stop trading
        rec = {"last_ok_utc": prev.get("last_ok_utc"), "last_error": f"{now} {type(exc).__name__}",
               "fails": int(prev.get("fails", 0)) + 1}
        ok = False
        log.warning("heartbeat ping failed (%s); the outside monitor will alert if this continues", type(exc).__name__)
    try:
        status.parent.mkdir(parents=True, exist_ok=True)
        status.write_text(json.dumps(rec))
    except OSError:
        pass
    return ok


EVERY_S = 300  # 5 minutes; set the outside monitor's period to 5 min and grace to about 7 min


class Pacer:
    """Pings every ``every_s`` seconds while healthy. A skipped candle stops pings until a candle succeeds."""

    def __init__(self, status: Path | str, every_s: float = EVERY_S, send=ping, now=time.monotonic):
        self.status, self.every_s, self.send, self.now = Path(status), every_s, send, now
        self.healthy, self.last = True, None

    def candle(self, ok: bool) -> None:
        """Call after each candle step: True = processed (ping now), False = skipped after every retry failed."""
        self.healthy = bool(ok)
        if self.healthy:
            self._send()

    def tick(self) -> None:
        """Call often (every wait slice); pings only when healthy and ``every_s`` has passed since the last ping."""
        if self.healthy and (self.last is None or self.now() - self.last >= self.every_s):
            self._send()

    def _send(self) -> None:
        self.last = self.now()  # set even if delivery fails, so a dead network is not hammered every slice
        self.send(self.status)


def recent_ok(status: Path, minutes: int = 60) -> bool:
    try:
        last = json.loads(Path(status).read_text()).get("last_ok_utc")
        return bool(last) and datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(minutes=minutes)
    except (OSError, ValueError, TypeError):
        return False
