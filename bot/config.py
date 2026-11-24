"""Central settings. Secrets are read from the environment / .env only (rule 6)."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAINNET_API = "https://api.india.delta.exchange"
TESTNET_API = "https://cdn-ind.testnet.deltaex.org"


def load_env(path: Path | str | None = None) -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    p = Path(path) if path else ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    mode: str = "paper"
    symbols: tuple[str, ...] = ("BTC/USD:USD", "ETH/USD:USD", "SOL/USD:USD")
    timeframe: str = "15m"
    tf_minutes: int = 15

    # signal / labels
    horizon: int = 16  # max candles a trade is held (4h)
    label_k: float = 3.0  # ATR multiples a forward move must exceed to be "up"/"down"
    p_enter: float = 0.45
    p_margin: float = 0.10

    # exits / sizing
    stop_atr: float = 1.5
    tp_atr: float = 3.0
    risk_per_trade: float = 0.005
    max_leverage: float = 3.0
    max_positions: int = 2
    daily_loss_limit: float = 0.01    # policy defaults from the user's master prompt (1% / 3% / 5%)
    weekly_loss_limit: float = 0.03
    monthly_loss_limit: float = 0.05

    # costs (Delta India: taker 0.05%, maker 0.02%, GST 18% on fees -- verify on your fee tier)
    taker_fee: float = 0.0005
    maker_fee: float = 0.0002
    gst: float = 1.18
    slippage: float = 0.0002
    stop_slippage: float = 0.0005
    funding_per_8h: float = 0.0001

    start_equity: float = 1000.0
    usdt_inr: float = 88.0
    train_days: int = 90
    test_days: int = 14

    # Research/signal prices. Delta India's own candle history failed validation against Binance
    # (corrupt spikes, SOL ~80% wrong), so signals use Binance USDT pairs and Delta is execution only.
    data_source: str = "binance"
    max_venue_deviation: float = 0.005  # skip entries if Delta price differs >0.5% from the signal feed

    min_order_inr: float = 0.0  # spot profile sets 100 (ASSUMPTION - verify per exchange/pair)
    market: str = "perp"  # "spot" (default via from_env) or "perp" (opt-in: MARKET=perp)
    allow_short: bool = True  # from_env sets False for spot
    strategy: str = "ml"  # "trend" (default via .env/from_env) or "ml"
    trend_span_days: int = 14

    adopt_orphans: bool = False  # False: flatten unknown exchange positions on startup
    testnet: bool = True

    @property
    def api_base(self) -> str:
        return TESTNET_API if self.testnet else MAINNET_API

    @property
    def data_dir(self) -> Path:
        return ROOT / "data"

    @property
    def state_dir(self) -> Path:
        return ROOT / "state"

    @property
    def run_dir(self) -> Path:
        """Live state lives in ./state ; paper/replay are isolated so they can never pollute the
        real tax ledger."""
        return self.state_dir if self.mode == "live" else self.state_dir / self.mode

    @property
    def db_path(self) -> Path:
        return self.run_dir / "state.db"

    @property
    def ledger_csv(self) -> Path:
        return ROOT / "trades_ledger.csv" if self.mode == "live" else self.run_dir / "trades_ledger.csv"

    @property
    def paper_exchange_path(self) -> Path:
        return self.run_dir / "paper_exchange.json"

    @property
    def model_path(self) -> Path:
        return ROOT / "models" / "model.joblib"

    @classmethod
    def from_env(cls) -> "Settings":
        load_env()
        s = cls()
        chosen = os.environ.get("STRATEGY", "trend").lower()
        if chosen in ("trend", "ensemble"):
            # multi-day holds: daily-scale ATR stop, no time exit, no fixed take-profit
            s = replace(s, strategy=chosen, horizon=96 * 30, stop_atr=2.0, tp_atr=1000.0,
                        risk_per_trade=0.005, max_leverage=2.0, max_positions=2)
        if os.environ.get("MARKET", "spot").lower() == "spot":
            # Master-prompt default: spot, long-only, no leverage. Fee levels are ASSUMPTIONS
            # (typical Indian-exchange spot taker ~0.1% + 18% GST) - verify on your exchange's fee page.
            s = replace(s, market="spot", allow_short=False, max_leverage=1.0, funding_per_8h=0.0, min_order_inr=100.0,
                        taker_fee=0.001, maker_fee=0.001, slippage=0.0005, stop_slippage=0.001)
        return enforce_policy(replace(
            s,
            mode=os.environ.get("BOT_MODE", "paper").lower(),
            start_equity=float(os.environ.get("START_EQUITY_USD", s.start_equity)),
            usdt_inr=float(os.environ.get("USDT_INR", s.usdt_inr)),
            testnet=os.environ.get("DELTA_TESTNET", "1") == "1",
            risk_per_trade=float(os.environ.get("RISK_PER_TRADE", s.risk_per_trade)),
            max_positions=int(os.environ.get("MAX_POSITIONS", s.max_positions)),
            daily_loss_limit=float(os.environ.get("DAILY_LOSS_LIMIT", s.daily_loss_limit)),
            weekly_loss_limit=float(os.environ.get("WEEKLY_LOSS_LIMIT", s.weekly_loss_limit)),
            monthly_loss_limit=float(os.environ.get("MONTHLY_LOSS_LIMIT", s.monthly_loss_limit)),
        ))


# Policy ceilings (user's risk policy + SAFETY_RULES.md rule 4). Environment overrides may only make risk
# STRICTER. Loosening any of these is a human decision made by editing this table, not an env var.
POLICY_CEILING = {"risk_per_trade": 0.005, "max_positions": 2, "daily_loss_limit": 0.03,
                  "weekly_loss_limit": 0.03, "monthly_loss_limit": 0.05}


def enforce_policy(s: "Settings") -> "Settings":
    """Refuse to start with risk settings looser than policy, or with nonsensical (<= 0) values."""
    bad = [f"{k}={getattr(s, k)} (allowed: > 0 and <= {cap})" for k, cap in POLICY_CEILING.items()
           if not (0 < getattr(s, k) <= cap)]
    if bad:
        raise ValueError("risk settings outside policy, refusing to start: " + "; ".join(bad))
    return s
