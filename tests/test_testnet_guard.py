import pytest

from bot.config import Settings
from bot.testnet_check import TestnetOnly, guard


def test_testnet_check_refuses_mainnet(monkeypatch):
    monkeypatch.setenv("DELTA_TESTNET", "0")
    with pytest.raises(TestnetOnly):
        guard(Settings(testnet=False))


def test_testnet_check_needs_live_consent(monkeypatch):
    from bot.broker.delta import LiveTradingNotAllowed

    monkeypatch.setenv("DELTA_TESTNET", "1")
    monkeypatch.setenv("BOT_MODE", "paper")
    monkeypatch.delenv("I_UNDERSTAND_LIVE_RISK", raising=False)
    with pytest.raises(LiveTradingNotAllowed):
        guard(Settings(testnet=True))
