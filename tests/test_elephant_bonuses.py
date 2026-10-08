#!/usr/bin/env python3
"""Elephant bonuses reach every elephant.  DAT-gated.

Card 303 "Elephant units +1/+1P armor" copies vanilla tech 640, the Khmer bonus,
which only touches the Battle Elephant line.  The card says elephant units, and
the user chose all of them (issue #60), so _apply_elephant_armour gives the
other lines the same packed-armour commands, scaled by the same multiplier.

The checks sum what the civ's own techs add to attribute 8 per unit and armour
class, so they compare the copy and the extension on equal terms, and a line
the extension drops shows up as a mismatch against the Battle Elephant.

    venv/bin/python tests/test_elephant_bonuses.py
"""
import contextlib
import io
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat              # noqa: E402
from civ_appender import apply_civ, _ELEPHANT_UNITS, EC_ADD  # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)
dat = load_dat(str(dat_path))

# Every trainable unit with elephant armour class 5, heroes aside, must be on
# the list — the Sannahya was missing until #60.
HEROES = {930, 1071, 1106, 1162, 1165, 1166, 1297, 2436, 2472}
class5 = {uid for uid, u in enumerate(dat.civs[1].units)
          if u is not None and u.type_50 and u.creatable
          and any(a.class_ == 5 for a in (u.type_50.armours or []))} - HEROES
check("every class-5 elephant is in _ELEPHANT_UNITS", class5 <= set(_ELEPHANT_UNITS),
      f"missing {sorted(class5 - set(_ELEPHANT_UNITS))}")


def armour_gain(slot):
    """unit -> {armour class: total added} from this civ's own techs."""
    gain = defaultdict(lambda: defaultdict(int))
    for t in dat.techs:
        if t.civ != slot or not 0 <= t.effect_id < len(dat.effects):
            continue
        for c in dat.effects[t.effect_id].effect_commands:
            if c.type == EC_ADD and int(c.c) == 8 and c.a in _ELEPHANT_UNITS:
                packed = int(c.d)
                gain[int(c.a)][packed >> 8] += packed & 0xFF
    return gain


for slot, mult in ((5, 1), (6, 2)):
    civ = {"format": FORMAT_KEY, "alias": f"Elephants x{mult}", "architecture": 2,
           "language": 0, "bonuses": [{"id": 303, "multiplier": mult}],
           "tree": {"units": [83, 1132, 1134, 239, 558, 873, 875], "buildings": [101, 109, 70],
                    "techs": [101, 102, 103]}}
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ, target_slot=slot)
    gain = armour_gain(slot)
    want = {4: mult, 3: mult}
    check(f"x{mult}: Battle Elephant keeps vanilla's +{mult}/+{mult}",
          dict(gain[1132]) == want, f"{dict(gain[1132])}")
    wrong = {uid: dict(gain[uid]) for uid in _ELEPHANT_UNITS if dict(gain[uid]) != want}
    check(f"x{mult}: every elephant gets +{mult}/+{mult}", not wrong, f"{wrong}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
