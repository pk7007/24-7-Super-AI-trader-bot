"""Data feed resilience: transient Binance connection drops must not cost a whole candle."""

import logging

import ccxt
import pytest

from bot.data import BINANCE_HOSTS, ResilientExchange


class FakeEx:
    """Minimal stand-in for ccxt.binance: fails the first ``fail`` calls with ``err``."""

    def __init__(self, fail=0, err=ccxt.NetworkError("SSLEOFError")):
        self.urls = {"api": {"public": "https://api.binance.com/api/v3", "private": "https://api.binance.com/api/v3"}}
        self.fail, self.err, self.calls, self.hosts_seen = fail, err, 0, []
        self.id = "binance"

    def fetch_ohlcv(self, *a, **k):
        self.calls += 1
        self.hosts_seen.append(self.urls["api"]["public"])
        if self.calls <= self.fail:
            raise self.err
        return [[1, 1.0, 1.0, 1.0, 1.0, 1.0]]

    def load_markets(self):
        return {}


def make(fail, **kw):
    sleeps = []
    ex = FakeEx(fail, **kw)
    return ResilientExchange(ex, sleep=sleeps.append), ex, sleeps


def test_transient_drop_is_retried_on_next_host_and_sticks(caplog):
    r, ex, sleeps = make(fail=1)
    with caplog.at_level(logging.WARNING, logger="data"):
        assert r.fetch_ohlcv("BTC/USDT", "15m") == [[1, 1.0, 1.0, 1.0, 1.0, 1.0]]
    assert ex.calls == 2 and sleeps == [2]
    assert ex.hosts_seen[0].startswith(BINANCE_HOSTS[0]) and ex.hosts_seen[1].startswith(BINANCE_HOSTS[1])
    assert "retry" in caplog.text.lower()  # retries are logged, never silent
    r.fetch_ohlcv("BTC/USDT", "15m")
    assert ex.hosts_seen[-1].startswith(BINANCE_HOSTS[1])  # stays on the host that worked


def test_gives_up_after_all_attempts_and_reraises():
    r, ex, sleeps = make(fail=99)
    with pytest.raises(ccxt.NetworkError):
        r.fetch_ohlcv("BTC/USDT", "15m")
    assert ex.calls == r.attempts and len(sleeps) == r.attempts - 1


def test_non_network_errors_are_not_retried():
    r, ex, sleeps = make(fail=99, err=ccxt.BadSymbol("no such pair"))
    with pytest.raises(ccxt.BadSymbol):
        r.fetch_ohlcv("XXX/USDT", "15m")
    assert ex.calls == 1 and sleeps == []


def test_other_attributes_pass_through():
    r, ex, _ = make(fail=0)
    assert r.id == "binance" and r.load_markets() == {}


def test_live_feed_uses_resilient_binance_by_default():
    from bot.config import Settings
    from bot.data import source_exchange

    ex = source_exchange(Settings())
    assert isinstance(ex, ResilientExchange)
    assert ex.options["fetchMarkets"]["types"] == ["spot"]  # fewer calls at startup, smaller failure surface


@pytest.mark.parametrize("err", [ccxt.RateLimitExceeded("429"), ccxt.DDoSProtection("418")])
def test_rate_limit_is_not_hammered_across_hosts(err):
    r, ex, sleeps = make(fail=99, err=err)
    with pytest.raises(type(err)):
        r.fetch_ohlcv("BTC/USDT", "15m")
    assert ex.calls == 1 and sleeps == []


def test_only_public_url_is_redirected():
    r, ex, _ = make(fail=1)
    r.fetch_ohlcv("BTC/USDT", "15m")
    assert ex.urls["api"]["private"] == "https://api.binance.com/api/v3"


def test_host_rotation_wraps_around_and_copy_is_safe():
    import copy

    r, ex, _ = make(fail=3)  # 3 failures over 3 hosts, 4th attempt back on the first host
    r.fetch_ohlcv("BTC/USDT", "15m")
    assert ex.hosts_seen[-1].startswith(BINANCE_HOSTS[0])
    copy.copy(r)  # must not recurse
