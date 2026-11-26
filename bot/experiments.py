"""Champion-challenger pipeline: a logged promote-or-reject decision for every lab challenger.

Rules (MASTER_LOOP_PROMPT.md, self-improvement section). A challenger may only be PROPOSED when it:
1. passes the lab gate at base fees (0.10%) and at the 0.50% fee stress;
2. beats the champion's return AND profit factor at both fee levels;
3. passed its own untouched holdout run (HOLDOUT_PROTOCOL.md).
Even then it is only proposed for 30 days of shadow trading beside the champion, and switching needs the user's
approval. This module writes ``reports/experiments.md`` and NEVER changes the production strategy or any setting.

    python -m bot.experiments          # uses lab_spot_policy_mp2, lab_policy_fee_0.005, holdout_2021_2022
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT
from .stats import count_lab_trials

PROPOSE = "propose: 30 days in shadow, then your approval"
ROW = re.compile(r"^\| [\w-]+ \| (reject|propose)", re.M)


def _full(c: dict) -> tuple[float, float]:
    f = c.get("full", {})
    return float(f.get("return_pct") or 0.0), float(f.get("profit_factor") or 0.0)


def decide(base: dict, stress: dict, holdout: dict | None, champion: str) -> list[dict]:
    champ_b, champ_s = base["candidates"][champion], stress["candidates"].get(champion)
    out = []
    for name, c in base["candidates"].items():
        if name == champion:
            continue
        why = []
        if not c.get("promote"):
            why.append("fails the lab gate at 0.10% fees: " + "; ".join(c.get("rejected_because", [])))
        rb, pb = _full(c)
        if not (rb > _full(champ_b)[0] and pb > _full(champ_b)[1]):
            why.append(f"does not beat the champion at 0.10% fees ({rb:+.1f}% PF {pb} vs "
                       f"{_full(champ_b)[0]:+.1f}% PF {_full(champ_b)[1]})")
        s = stress["candidates"].get(name)
        if s is None or champ_s is None:
            why.append("not run at the 0.50% fee stress")
        else:
            rs, ps = _full(s)
            if not s.get("promote"):
                why.append("fails the lab gate at 0.50% fees")
            if not (rs > _full(champ_s)[0] and ps > _full(champ_s)[1]):
                why.append(f"does not beat the champion at 0.50% fees ({rs:+.1f}% PF {ps} vs "
                           f"{_full(champ_s)[0]:+.1f}% PF {_full(champ_s)[1]})")
        h = (holdout or {}).get("candidates", {}).get(name)
        if h is None:
            why.append("no untouched holdout run of its own")
        elif not h.get("promote"):
            why.append("failed its holdout")
        out.append({"challenger": name, "param": c.get("main_param"), "return_pct": rb, "profit_factor": pb,
                    "decision": "reject" if why else PROPOSE, "reasons": why})
    return out


def write_log(decisions: list[dict], path: Path, champion: str, base: dict, stress: dict, holdout: dict | None,
              n_trials: int) -> None:
    """Append one dated decision block (selection bias visible through the trial count)."""
    rb, pb = _full(base["candidates"][champion])
    h = (holdout or {}).get("candidates", {}).get(champion)
    lines = [f"## {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC - champion `{champion}`", "",
             f"Lab {base.get('window')} at {base.get('taker_fee', 0):.2%} taker: {rb:+.1f}%, PF {pb}. "
             + (f"0.50% fee stress: {_full(stress['candidates'][champion])[0]:+.1f}%, PF "
                f"{_full(stress['candidates'][champion])[1]}. " if champion in stress.get("candidates", {}) else "")
             + (f"Untouched holdout {holdout.get('window')}: {_full(h)[0]:+.1f}%, PF {_full(h)[1]}. " if h else
                "No holdout for the champion. ")
             + f"Selection so far: {n_trials} trials (every setting in every lab report, plus the rejected LightGBM model).",
             "", "| Challenger | Decision | Lab return | PF | Reasons |", "|---|---|---:|---:|---|"]
    for d in decisions:
        lines.append(f"| {d['challenger']} | {d['decision']} | {d['return_pct']:+.1f}% | {d['profit_factor']} | "
                     f"{'; '.join(d['reasons']) or 'cleared every rule'} |")
    lines += ["", "Production strategy unchanged. Promotion needs 30 days in shadow and the user's approval.", "", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "" if path.exists() else "# Experiments: champion-challenger decisions (written by bot/experiments.py)\n\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(head + "\n".join(lines))


def has_decision(path: Path) -> bool:
    """True when the log holds at least one promote-or-reject row."""
    return path.exists() and bool(ROW.search(path.read_text(encoding="utf-8")))


def main() -> None:
    rep = ROOT / "reports"
    load = lambda n: json.loads((rep / f"{n}.json").read_text())  # noqa: E731
    base, stress, holdout = load("lab_spot_policy_mp2"), load("lab_policy_fee_0.005"), load("holdout_2021_2022")
    decisions = decide(base, stress, holdout, champion="ensemble")
    write_log(decisions, rep / "experiments.md", "ensemble", base, stress, holdout, count_lab_trials(rep, extra=1))
    for d in decisions:
        print(f"{d['challenger']:12s} {d['decision']}: {'; '.join(d['reasons']) or 'cleared every rule'}")


if __name__ == "__main__":
    main()
