"""python -m bot.api [--port 8765]  -> http://127.0.0.1:8765 (localhost only; no remote access by design)."""

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m bot.api")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    # Bound to 127.0.0.1 on purpose: there is no authentication, so it must not be reachable from the network.
    uvicorn.run("bot.api.app:app", host="127.0.0.1", port=a.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
