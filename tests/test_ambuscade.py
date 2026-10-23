#!/usr/bin/env python3
"""Ambuscade (Castle UT 68): the unique unit trains at the Archery Range.  DAT-gated.

Issue #81, the third of Anarchy (Barracks) and Marauders (Stable).  No vanilla
tech does it, so the preset copies Marauders (483) with the attr-42 building
rewritten to the Archery Range.  Archery Range button 4 belongs to the Hand
Cannoneer, so the unit's dormant slot is button 10, empty for every civ.

    venv/bin/python tests/test_ambuscade.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat      # noqa: E402
from civ_appender import apply_civ                  # noqa: E402

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
AMBUSCADE, MARAUDERS_TECH = 68, 483
RANGE, STABLE, BUTTON, HOTKEY = 87, 101, 10, 16176


def cmds_of(tid):
    return [(c.type, int(c.a), int(c.b), int(c.c), c.d)
            for c in dat.effects[dat.techs[tid].effect_id].effect_commands]


marauders_before = cmds_of(MARAUDERS_TECH)
civ_def = {
    "alias": "Ambuscade Probe", "description": "", "architecture": 2,
    "language": 0, "wonder": -1, "castle": -1,
    "bonuses": [[], [3], [[AMBUSCADE, 1]], [], []],
    "tree": [[4, 5, 7], [RANGE, 109], []],      # Hand Cannoneer keeps button 4
}
with contextlib.redirect_stdout(io.StringIO()):
    res = apply_civ(dat, civ_def, target_slot=1)
uu, elite = res["uu_id"], res["elite_uu_id"]

print("Ambuscade's effect")
ut = cmds_of(res["castle_ut_tech_id"])
to_range = {c[1] for c in ut if c[0] == 0 and c[3] == 42 and c[4] == RANGE}
check("points our unique unit and its elite at the Archery Range",
      {uu, elite} <= to_range, str(ut))
check("never names the Stable", not any(c[3] == 42 and c[4] == STABLE for c in ut), str(ut))
check("never the Tarkan it was copied from (755/757)",
      not any(c[1] in (755, 757) for c in ut), str(ut))
check("enables our unique unit", any(c[0] == 2 and c[1] == uu and c[2] == 1 for c in ut), str(ut))

print("the dormant train slot")
for uid in (uu, elite):
    tls = dat.civs[1].units[uid].creatable.train_locations
    dyn = [(tl.button_id, tl.hot_key_id) for tl in tls if tl.unit_id == -1]
    check(f"unit {uid} has a (-1, button {BUTTON}) slot after the Castle's",
          len(tls) > 1 and tls[1].unit_id == -1 and dyn == [(BUTTON, HOTKEY)], str(dyn))
hc = [tl.button_id for tl in dat.civs[1].units[5].creatable.train_locations if tl.unit_id == RANGE]
check("the Hand Cannoneer keeps Archery Range button 4", hc == [4], str(hc))

print("Marauders itself is untouched")
check("tech 483 still points at the Stable", cmds_of(MARAUDERS_TECH) == marauders_before,
      str(cmds_of(MARAUDERS_TECH)))

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
