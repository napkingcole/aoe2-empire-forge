#!/usr/bin/env python3
"""Monks heal from range: tech 407 'Monk Ranged Heal' stays on.  DAT-gated.

407 is an auto-fire civ=-1 tech that sets heal range (resource 90) to 4.  Only
the Teutons disable it, because their own bonus (tech 347, card 11) sets 8 and
407 could overwrite it.  The tech-tree sweep took every tech some vanilla civ
disables as a candidate, 407 is no editor node, so every custom civ with a tree
disabled it and its Monks walked up to heal (players' report, 2026-10-25).

    venv/bin/python tests/test_monk_heal_range.py
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

RANGED_HEAL, HEAL_RANGE = 407, 90
dat = load_dat(str(dat_path))
check("tech 407 is still the heal-range default (resource 90 = 4)",
      [(c.type, c.a, c.d) for c in dat.effects[dat.techs[RANGED_HEAL].effect_id].effect_commands]
      == [(1, HEAL_RANGE, 4.0)])

# A small real tree: an empty one leaves the civ's tree alone and proves nothing.
TREE = [[83, 4, 74, 93, 125], [109, 12, 87, 104, 70], [22]]


def disabled(slot):
    tt = dat.effects[dat.civs[slot].tech_tree_id].effect_commands
    return {int(c.d) for c in tt if c.type == 102}


for slot, bonuses in ((5, []), (6, [[11, 1]])):
    civ_def = {"alias": f"Heal Probe {slot}", "description": "", "architecture": 2,
               "language": 0, "wonder": -1, "castle": -1,
               "bonuses": [bonuses, [], [], [], []], "tree": TREE}
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ_def, target_slot=slot)

check("a custom civ keeps Monk Ranged Heal", RANGED_HEAL not in disabled(5))
check("with card 11 (heal range 8) it is still disabled, as for the Teutons",
      RANGED_HEAL in disabled(6))
check("the Teutons are untouched", RANGED_HEAL in disabled(4))

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
