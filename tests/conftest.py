import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.broker.paper import PaperBroker  # noqa: E402
from bot.config import Settings  # noqa: E402
from bot.engine import Engine  # noqa: E402
from bot.feeds import ReplayFeed  # noqa: E402
from bot.ledger import Ledger  # noqa: E402
from bot.model import PROB_COLUMNS  # noqa: E402
from bot.state import State  # noqa: E402

SYM = "BTC/USD:USD"


def make_candles(n=700, start="2026-01-01", seed=1, drift=0.0, vol=0.002, base=60000.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="15min", tz="UTC", name="date")
    close = base * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    open_ = np.r_[base, close[:-1]]
    hi = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, vol / 3, n)))
    lo = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, vol / 3, n)))
    return pd.DataFrame({"open": open_, "high": hi, "low": lo, "close": close,
                         "volume": rng.uniform(50, 150, n)}, index=idx)


class FixedModel:
    """Returns the same probabilities for every row (test double for the LightGBM model)."""

    def __init__(self, p_down=0.1, p_flat=0.1, p_up=0.8):
        self.p = (p_down, p_flat, p_up)

    def predict_proba(self, X):
        out = pd.DataFrame(np.nan, index=X.index, columns=PROB_COLUMNS)
        out.loc[X.notna().all(axis=1), PROB_COLUMNS] = self.p
        return out


@pytest.fixture
def cfg():
    return Settings(mode="replay", start_equity=1000.0, symbols=(SYM,))


@pytest.fixture
def world(tmp_path, cfg):
    data = {SYM: make_candles()}
    feed = ReplayFeed(data, cfg)
    feed.set_time(data[SYM].index[400])
    broker = PaperBroker(feed, cfg, tmp_path / "ex.json")
    state = State(tmp_path / "state.db")
    ledger = Ledger(tmp_path / "ledger.csv", state)
    alerts: list[str] = []

    def make_engine(model=None):
        return Engine(cfg, broker, feed, model or FixedModel(), state, ledger, notify=alerts.append)

    return dict(cfg=cfg, data=data, feed=feed, broker=broker, state=state, ledger=ledger,
                alerts=alerts, make_engine=make_engine, tmp=tmp_path)
