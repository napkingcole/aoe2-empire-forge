#!/usr/bin/env python3
"""Elephant bonuses reach every elephant.  DAT-gated.

DE wrote several elephant bonuses for one line: card 303 (+1/+1 armour), 79
(+10% speed) and 83 (-25%/-35% cost) touch only the Battle Elephant; 292
(bonus-damage and conversion resistance) misses our Royal Battle Elephant and
the Sannahya; the Howdah UT covers Battle and War Elephants.  The cards say
elephant units (79: melee elephant units), and the user chose all of them
(issue #60, 2026-10-08), so _ELEPHANT_EXTENSIONS copies each template's
per-unit commands onto the units it leaves out.

Each check sums what the civ's own techs do to a unit — per attribute, command
type and age gate — and compares every elephant in the card's set with the
Battle Elephant, which every template covers.  A dropped line, a lost age gate
or a multiplier applied to only some lines all show up as a mismatch.

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
from civ_appender import (apply_civ, _ELEPHANT_UNITS, _MELEE_ELEPHANT_UNITS,  # noqa: E402
                          EC_ADD, EC_MULTIPLY, EC_SET)
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
ranged = {u for u in _ELEPHANT_UNITS if dat.civs[1].units[u].type_50.max_range > 0}
check("melee elephants are exactly the range-0 ones",
      set(_MELEE_ELEPHANT_UNITS) == set(_ELEPHANT_UNITS) - ranged,
      f"ranged={sorted(ranged)}")


def summary(slot):
    """unit -> {(attr, type, age): combined value} over this civ's own techs."""
    out = defaultdict(dict)
    for t in dat.techs:
        if t.civ != slot or not 0 <= t.effect_id < len(dat.effects):
            continue
        age = next((r for r in t.required_techs if r in (101, 102, 103)), -1)
        for c in dat.effects[t.effect_id].effect_commands:
            if c.type not in (EC_SET, EC_ADD, EC_MULTIPLY) or c.a not in _ELEPHANT_UNITS:
                continue
            s = out[int(c.a)]
            if c.type == EC_ADD and int(c.c) in (8, 9):          # packed: per class
                key = (int(c.c), EC_ADD, age, int(c.d) >> 8)
                s[key] = s.get(key, 0) + (int(c.d) & 0xFF)
            elif c.type == EC_ADD:
                key = (int(c.c), EC_ADD, age)
                s[key] = round(s.get(key, 0) + c.d, 4)
            elif c.type == EC_MULTIPLY:
                key = (int(c.c), EC_MULTIPLY, age)
                s[key] = round(s.get(key, 1) * c.d, 4)
            else:
                s[(int(c.c), EC_SET, age)] = round(c.d, 4)
    return out


TREE = {"units": [83, 1132, 1134, 239, 558, 873, 875], "buildings": [101, 109, 70],
        "techs": [101, 102, 103]}
CASES = [(303, "+1/+1 armour", _ELEPHANT_UNITS), (79, "+10% speed", _MELEE_ELEPHANT_UNITS),
         (83, "cost -25%/-35%", _ELEPHANT_UNITS), (292, "resistance", _ELEPHANT_UNITS)]
slot = 4
for bonus, what, units in CASES:
    for mult in (1, 2):
        slot += 1
        civ = {"format": FORMAT_KEY, "alias": f"E{bonus}x{mult}", "architecture": 2,
               "language": 0, "bonuses": [{"id": bonus, "multiplier": mult}], "tree": TREE}
        with contextlib.redirect_stdout(io.StringIO()):
            apply_civ(dat, civ, target_slot=slot)
        got = summary(slot)
        ref = got[1132]
        wrong = sorted(u for u in units if got[u] != ref)
        check(f"card {bonus} {what} x{mult}: every elephant matches the Battle Elephant",
              ref and not wrong, f"ref={ref} wrong={wrong} e.g. {got[wrong[0]] if wrong else ''}")
        if bonus == 79:
            extra = sorted(u for u in _ELEPHANT_UNITS if u not in units and got[u])
            check("card 79 leaves the ranged elephants alone", not extra, f"{extra}")

# Howdah is an Imperial UT, so its commands join the UT's own effect.
slot += 1
km = {"alias": "Howdah", "description": "", "architecture": 2, "language": 0,
      "wonder": -1, "castle": -1, "bonuses": [[], [], [], [[5, 1]], []],
      "tree": [TREE["units"], TREE["buildings"], TREE["techs"]]}
with contextlib.redirect_stdout(io.StringIO()):
    apply_civ(dat, km, target_slot=slot)
got = summary(slot)
wrong = sorted(u for u in _ELEPHANT_UNITS if got[u] != got[1132])
check("Howdah: every elephant matches the Battle Elephant", got[1132] and not wrong,
      f"ref={got[1132]} wrong={wrong}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
