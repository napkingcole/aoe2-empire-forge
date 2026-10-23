#!/usr/bin/env python3
"""Bonus 105 moves EVERY eco upgrade it discounts one age earlier.  DAT-gated.

"Economic upgrades cost -40% food and available one age earlier" borrows the
Burgundians' route: each upgrade lists a Burgundian-gated, effectless shim tech
as an alternative prerequisite, and _apply_early_eco_shims copies those shims
for our civ.  The list of shims was hand-written and missed two — 766 (Crop
Rotation) and 759 (Caravan) — so those stayed at their normal age (issue #80).
The sweep below derives the shims from the DAT, so a missed one fails here.

    venv/bin/python tests/test_early_eco_shims.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat              # noqa: E402
from civ_appender import apply_civ, _EARLY_ECO_SHIM_TECHS   # noqa: E402
from bonus_catalog import civ_bonus_ec_list                 # noqa: E402

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

dat = load_dat(str(dat_path))
BURGUNDIANS, CROP_ROTATION, CARAVAN = 36, 12, 48
ECO = sorted({int(ec["A"]) for e in civ_bonus_ec_list(105) for ec in e["ecs"]})


def burgundian_shims(tid):
    return {r for r in dat.techs[tid].required_techs
            if r >= 0 and dat.techs[r].civ == BURGUNDIANS and dat.techs[r].effect_id == -1}


print("every discounted upgrade's Burgundian shim is in the list")
for tid in ECO:
    missing = burgundian_shims(tid) - set(_EARLY_ECO_SHIM_TECHS)
    check(f"{tid} {dat.techs[tid].name}", not missing, f"missing shim(s) {sorted(missing)}")

print("the discount matches the game's Burgundians")
# The card said -33% (x0.667) after the game had moved the Burgundians to -40%
# (x0.6); matched 2026-10-23.  Read the game's own Burgundian tech tree effect.
burg_tt = dat.effects[dat.civs[next(i for i, c in enumerate(dat.civs) if c.name == "Burgundians")].tech_tree_id]
game = {int(c.a): round(c.d, 3) for c in burg_tt.effect_commands if c.type == 101 and int(c.a) in ECO and int(c.b) == 0}
ours = {int(ec["A"]): round(ec["D"], 3) for e in civ_bonus_ec_list(105) for ec in e["ecs"]}
check("every upgrade's food multiplier is the game's", ours == game, f"ours {ours}\n       game {game}")

print("a civ with bonus 105 gets its own route to each")
civ_def = {
    "alias": "Early Eco Probe", "description": "", "architecture": 2,
    "language": 0, "wonder": -1, "castle": -1,
    "bonuses": [[[105, 1]], [], [], [], []],
    "tree": [[], [], []],
}
with contextlib.redirect_stdout(io.StringIO()):
    civ_index = apply_civ(dat, civ_def, target_slot=1)["civ_index"]


def ours(tid, depth=2):
    """A prerequisite gated to our civ, directly or through _add_alt_prereq's
    global gate tech."""
    for r in dat.techs[tid].required_techs:
        if r < 0 or r in _EARLY_ECO_SHIM_TECHS:
            continue
        if dat.techs[r].civ == civ_index or (depth > 1 and ours(r, depth - 1)):
            return True
    return False


for tid in (CROP_ROTATION, CARAVAN):
    check(f"{dat.techs[tid].name} lists a copy gated to our civ", ours(tid),
          str(list(dat.techs[tid].required_techs)))

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
