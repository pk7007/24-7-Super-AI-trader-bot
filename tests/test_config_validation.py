"""Configuration parsing is fail-closed and can use an isolated, credential-free snapshot."""
import os

import pytest

from bot.config import Settings


def test_snapshot_settings_do_not_load_dotenv_or_mutate_environment(monkeypatch):
    from bot import config
    monkeypatch.setattr(config, "load_env", lambda: pytest.fail("dotenv must not be read"))
    before = dict(os.environ)
    cfg = Settings.from_env(environ={"BOT_MODE": "shadow", "STRATEGY": "ensemble"}, read_dotenv=False)
    assert cfg.mode == "shadow" and cfg.strategy == "ensemble" and cfg.market == "spot"
    assert dict(os.environ) == before


@pytest.mark.parametrize("key,value", [("BOT_MODE", "../live"), ("STRATEGY", "typo"),
                                     ("MARKET", "spoot"), ("DELTA_TESTNET", "true"),
                                     ("START_EQUITY_USD", "nan"), ("START_EQUITY_USD", "0"),
                                     ("USDT_INR", "inf"), ("USDT_INR", "-1")])
def test_invalid_environment_refuses_startup(key, value, monkeypatch):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        Settings.from_env()
