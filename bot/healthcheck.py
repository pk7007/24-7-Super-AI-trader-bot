"""Container health from successful engine candles, never from error-log activity."""

import argparse

from .api.sources import heartbeat


def healthy(mode: str) -> bool:
    hb = heartbeat(mode)
    age = hb.get("age_min")
    return hb.get("status") == "alive" and age is not None and age >= 0 and hb.get("step_completed") is True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("paper", "shadow"))
    raise SystemExit(0 if healthy(parser.parse_args().mode) else 1)


if __name__ == "__main__":
    main()
