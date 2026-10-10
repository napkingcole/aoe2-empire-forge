#!/usr/bin/env python3
"""Custom bonuses can give buildings population space (#64).  DAT-gated.

Population space is attribute 21, the amount of a building's first resource
storage — vanilla's "Houses +5 pop".  It only means population when that slot
is population, so the card is written per building, never class-wide: a Farm's
first slot is its food, and "+5" there would be five food per farm.  Walls and
gates are left out (the user's call: every segment would become a house), and
an empty slot (Market, Blacksmith, ...) is turned into a population slot on the
civ's own building.

    venv/bin/python tests/test_pop_space_bonus.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import custom_bonus as cb                                   # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

from civ_appender import apply_civ                          # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402
dat = load_dat(str(dat_path))
BARRACKS, MARKET, HOUSE, FARM, PALISADE, GATE, OUTPOST = 12, 84, 70, 50, 72, 487, 598
template_market = dat.civs[1].units[MARKET].resource_storages[0].type


def card(target, value=10):
    return cb.normalize([{"target": target, "effects": [{"attr": "pop_space", "op": "add", "value": value}]}])[0]


def build(slot, c):
    """(units given +pop, class-wide pop commands, the civ's unit table)."""
    civ = {"format": FORMAT_KEY, "alias": f"Pop space {slot}", "architecture": 2, "language": 0,
           "bonuses": [], "custom_bonuses": [c],
           "tree": {"units": [83], "buildings": [12, 84, 70, 109, 68], "techs": [101, 102, 103]}}
    n = len(dat.techs)
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ, target_slot=slot)
    cmds = [ec for t in dat.techs[n:] if t.civ == slot and 0 <= t.effect_id < len(dat.effects)
            for ec in dat.effects[t.effect_id].effect_commands if ec.type == 4 and int(ec.c) == 21]
    return {int(ec.a) for ec in cmds if ec.a >= 0}, [ec for ec in cmds if ec.a < 0], dat.civs[slot].units


print("=== a building that already holds population ===")
got, wide, units = build(5, card({"type": "unit", "id": BARRACKS, "kind": "building", "name": "Barracks"}))
check("Barracks +10: the Barracks gets attribute 21 +10", BARRACKS in got, f"{sorted(got)}")
check("...as population (slot type 4)", units[BARRACKS].resource_storages[0].type == 4)
check("card text", cb.card_text(card({"type": "unit", "id": BARRACKS, "kind": "building",
                                      "name": "Barracks"})) == "Barracks: +10 population space")

print("\n=== a building with an empty slot ===")
got, wide, units = build(6, card({"type": "unit", "id": MARKET, "kind": "building", "name": "Market"}))
check("Market +10: the Market gets attribute 21 +10", MARKET in got, f"{sorted(got)}")
check("...and its empty first slot became population", units[MARKET].resource_storages[0].type == 4,
      f"{units[MARKET].resource_storages[0]}")
check("...on this civ only: the template Market is untouched",
      dat.civs[1].units[MARKET].resource_storages[0].type == template_market == -1)

print("\n=== All buildings ===")
got, wide, units = build(7, card({"type": "group", "id": "buildings"}, 5))
check("no class-wide command (it would reach Farms)", not wide, f"{len(wide)} class-wide")
check("Houses, Barracks and the Market get it", {HOUSE, BARRACKS, MARKET} <= got, f"{sorted(got)[:20]}")
check("Farms, Outposts, palisades and gates do not", not ({FARM, OUTPOST, PALISADE, GATE} & got),
      f"{sorted({FARM, OUTPOST, PALISADE, GATE} & got)}")
check("the Farm still stores food, not population", units[FARM].resource_storages[0].type == 0)

print("\n=== offered where it means something ===")
allowed = cb.allowed_attrs(dat, [("building:12", "building", BARRACKS), ("building:50", "building", FARM),
                                  ("building:84", "building", MARKET), ("building:72", "building", PALISADE)])
for key, want in (("building:12", True), ("building:84", True), ("building:50", False),
                  ("building:72", False), ("group:walls", False), ("group:buildings", True)):
    check(f"{key}: population space {'offered' if want else 'not offered'}",
          ("pop_space" in allowed[key]) == want, f"{allowed[key]}")
check("not offered on units", "pop_space" not in allowed.get("group:infantry", []))
check("negative amounts are refused",
      not cb.normalize([{"target": {"type": "group", "id": "buildings"},
                         "effects": [{"attr": "pop_space", "op": "add", "value": -5}]}]))

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
