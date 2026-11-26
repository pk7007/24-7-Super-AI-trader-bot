"""FastAPI app: GET-only, read-only, localhost by default. Contract: FRONTEND_API_CONTRACT.md."""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import ROOT
from . import sources as s

SCHEMA_VERSION = "1.0"
DIST = ROOT / "frontend" / "dist"


class Mode(str, Enum):
    paper = "paper"
    shadow = "shadow"


class Symbol(str, Enum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"


class CandleSource(str, Enum):
    live = "live"
    cached = "cached"


class Envelope(BaseModel):
    schema_version: str
    observed_utc: str
    data: Any


def _clean(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def env(data) -> dict:
    return {"schema_version": SCHEMA_VERSION, "observed_utc": s.iso(s.now_utc()), "data": _clean(data)}


app = FastAPI(title="AI Trade Labs observational API", version=SCHEMA_VERSION, docs_url="/api/docs",
              redoc_url=None, openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                   allow_methods=["GET"], allow_headers=[], allow_credentials=False)


@app.middleware("http")
async def read_only_and_headers(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        return JSONResponse({"detail": "read-only API: only GET is allowed"}, status_code=405)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    else:
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
    return resp


@app.exception_handler(Exception)
async def safe_errors(request: Request, exc: Exception):  # never leak paths, env or tracebacks
    return JSONResponse({"detail": f"internal error ({type(exc).__name__})"}, status_code=500)


@app.get("/api/v1/overview", response_model=Envelope)
def overview():
    from .. import readiness as r
    rd = s.readiness()
    rep = rd["report"]
    return env({"modes": {m: s.mode_overview(m) for m in s.MODES},
                "readiness": {"score": rep.get("overall_score"), "classification": rep.get("classification"),
                              "generated_utc": rep.get("generated_utc"), "deployment_state": r.current_state(),
                              "live_trading_allowed": bool(rep.get("live_trading_allowed", False)),
                              "blockers": rep.get("mandatory_blockers") or rep.get("blockers") or []},
                "live_trading": "disabled: no live service exists; live needs BOT_MODE=live + human approval"})


@app.get("/api/v1/markets", response_model=Envelope)
def markets():
    return env(s.markets())


@app.get("/api/v1/candles", response_model=Envelope)
def candles(symbol: Symbol = Symbol.BTC, limit: int = Query(300, ge=20, le=1000),
            source: CandleSource = CandleSource.live):
    return env(s.candles(symbol.value, limit, source.value))


@app.get("/api/v1/positions", response_model=Envelope)
def positions(mode: Mode = Mode.paper):
    return env(s.positions(mode.value))


@app.get("/api/v1/fills", response_model=Envelope)
def fills(mode: Mode = Mode.paper):
    db = s.db_read(mode.value)
    return env({"availability": db["availability"], "rows": db["fills"], "source": db["source"], "simulated": True})


@app.get("/api/v1/signals", response_model=Envelope)
def signals(mode: Mode = Mode.paper, limit: int = Query(200, ge=1, le=2000)):
    ev = s.candle_events(mode.value)
    return env({"rows": ev[-limit:][::-1], "source": f"state/{mode.value}.log (engine heartbeat lines)",
                "note": "decisions are the engine's own outputs per closed 15m candle; no probabilities are shown"})


@app.get("/api/v1/intents", response_model=Envelope)
def intents():
    return env(s.shadow_intents())


@app.get("/api/v1/risk", response_model=Envelope)
def risk():
    return env(s.risk_view())


@app.get("/api/v1/strategies", response_model=Envelope)
def strategies():
    return env(s.strategies())


@app.get("/api/v1/backtests", response_model=Envelope)
def backtests():
    return env({"lab_reports": s.lab_reports(), "historical_equity": s.backtest_equity()})


@app.get("/api/v1/readiness", response_model=Envelope)
def readiness():
    return env(s.readiness())


@app.get("/api/v1/feasibility", response_model=Envelope)
def feasibility():
    return env(s.feasibility())


@app.get("/api/v1/ledger", response_model=Envelope)
def ledger(mode: Mode = Mode.paper):
    return env({**s.ledger_rows(mode.value), "simulated": True,
                "note": "paper/shadow ledgers are simulations. Tax figures are estimates, not filing advice"})


@app.get("/api/v1/health", response_model=Envelope)
def health():
    return env(s.health())


@app.get("/api/v1/events", response_model=Envelope)
def events(mode: Mode = Mode.paper, limit: int = Query(200, ge=1, le=1000)):
    return env({"rows": s.events(mode.value, limit), "source": f"state/{mode.value}.log"})


# ------------------------------------------------------------------ built frontend (single origin, no CORS needed)
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        return JSONResponse({"detail": "not found"}, status_code=404)
    f = (DIST / path).resolve()
    if path and f.is_file() and DIST.resolve() in f.parents:  # no path traversal outside dist/
        return FileResponse(f)
    idx = DIST / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return JSONResponse({"detail": "frontend not built: run `npm run build` in frontend/"}, status_code=404)
