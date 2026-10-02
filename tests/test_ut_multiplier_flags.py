#!/usr/bin/env python3
"""Every unique tech that offers a multiplier must have something to scale.

Gothikon offered x2..x10 and did nothing at any of them (reported in-game
2026-10-02): its effect is all EC_SET, which _scale_ec_for_multiplier leaves
alone on purpose — scaling a SET would set a different value, not more of the
effect.  A multiplier that does nothing is a card that lies, so this sweeps
every Castle/Imperial UT preset: if x3 changes no command, the preset must be
flagged `multiplier: false` in static/data/ut_overrides.json.  DAT-gated.

    venv/bin/python tests/test_ut_multiplier_flags.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat            # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

import civ_appender as ca                                  # noqa: E402

dat = load_dat(str(dat_path))
overrides = json.loads((ROOT / "static/data/ut_overrides.json").read_text(encoding="utf-8"))

# Nothing pending: Bimaristan, Coiled Serpent Array and Ordo Cavalry were held
# here until the user confirmed (2026-10-02) they can't scale either.
PENDING: set[tuple[str, int]] = set()

offenders = []
for kind, table in (("castle", ca._KM_CASTLE_UT_TECHS), ("imperial", ca._KM_IMP_UT_TECHS)):
    for slot, tid in sorted(table.items()):
        if tid is None or not (0 <= tid < len(dat.techs)) or dat.techs[tid].effect_id < 0:
            continue
        cmds = dat.effects[dat.techs[tid].effect_id].effect_commands
        scales = any((s.d, s.c) != (c.d, c.c)
                     for c in cmds for s in [ca._scale_ec_for_multiplier(c, 3)])
        flagged = (overrides.get(kind, {}).get(str(slot)) or {}).get("multiplier") is False
        if not scales and not flagged and (kind, slot) not in PENDING:
            offenders.append(f"{kind} {slot} ({dat.techs[tid].name})")

check("every UT whose multiplier changes nothing is flagged multiplier:false",
      not offenders, "; ".join(offenders))
check("Gothikon (imperial 63) is flagged",
      (overrides["imperial"].get("63") or {}).get("multiplier") is False)

print()
if failures:
    print(f"{failures} check(s) FAILED")
    sys.exit(1)
print("All checks passed.")
