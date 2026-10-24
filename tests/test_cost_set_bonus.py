#!/usr/bin/env python3
"""A custom bonus that replaces what a unit costs (Corvinian Army style).  DAT-gated.

A player asked for it (2026-10-24).  The game's own do it in one order:
Corvinian Army sets the Magyar Huszar's gold cost to 0, then its food to 80;
Hussite Reforms sets the Monk's gold to 0, then its food to 100.  The card
"cost, replaced" names one resource per effect, at most two; the build zeroes
every resource it doesn't name first, then sets the named ones, on every unit
of the line.

    venv/bin/python tests/test_cost_set_bonus.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat      # noqa: E402
import civ_appender as ca                           # noqa: E402
import custom_bonus as cb                           # noqa: E402
import fu_stats                                     # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


print("the vanilla precedent")
dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)
dat = load_dat(str(dat_path))
for name, want in (("Corvinian Army", [(0, 105, 0.0), (0, 103, 80.0)]), ("Hussite Reforms", [(0, 105, 0.0), (0, 103, 100.0)])):
    e = next(e for e in dat.effects if e.name == name)
    got = [(c.type, int(c.c), c.d) for c in e.effect_commands if 103 <= int(c.c) <= 106]
    check(f"{name}: zero the old resource, then set the new", got[:1] == want[:1] and want[1] in got, got)

print("the card")
raw = {"targets": [{"type": "unit", "id": 74, "name": "Militia"}],
       "effects": [{"attr": "cost_set", "op": "set", "value": 60, "resource": "food"},
                   {"attr": "cost_set", "op": "set", "value": 20, "resource": "wood"},
                   {"attr": "cost_set", "op": "set", "value": 5, "resource": "stone"}]}
card = cb.normalize([raw])[0]
check("at most two resources (a third is dropped)", [e["resource"] for e in card["effects"]] == ["food", "wood"])
check("its text", cb.card_text(card) == "Militia line: costs 60 food + 20 wood", cb.card_text(card))
check("a replaced cost must name its resource",
      not cb.normalize([{**raw, "effects": [{"attr": "cost_set", "op": "set", "value": 60}]}]))
check("...and doesn't grow each age",
      not cb.normalize([{**raw, "when": {"steps": True},
                         "effects": [{"attr": "cost_set", "op": "set", "value": 60, "resource": "food",
                                      "steps": {"0": 60}}]}]))
allowed = cb.allowed_attrs(dat, [("unit:74", "unit", 74), ("building:70", "building", 70)])
check("offered on a unit that costs something", "cost_set" in allowed["unit:74"])

print("the build")
civ_def = {"alias": "Cost Probe", "tagline": "", "architecture": 1, "language": 0, "wonder": -1,
           "castle": -1, "bonuses": [[], [], [], [], []], "tree": [[], [], []], "custom_bonuses": [raw]}
SLOT = 5
with contextlib.redirect_stdout(io.StringIO()):
    ca.apply_civ(dat, civ_def, target_slot=SLOT)
tech = next(t for t in dat.techs if t.civ == SLOT and t.name == "C-Bonus, Custom")
cmds = [(c.type, int(c.a), int(c.c), c.d) for c in dat.effects[tech.effect_id].effect_commands]
line = {74, 75, 77, 473, 567}
for uid in line:
    mine = [(t, c, d) for t, a, c, d in cmds if a == uid]
    check(f"unit {uid}: gold and stone to 0, then food 60 and wood 20",
          mine == [(0, 105, 0.0), (0, 106, 0.0), (0, 103, 60.0), (0, 104, 20.0)], mine)

sim = fu_stats.Simulation(dat, SLOT)
champ = sim.units[567]
costs = sorted((r.type, r.amount) for r in champ.creatable.resource_costs if r.flag == 1 and r.type in (0, 1, 2, 3) and r.amount)
check("the stats preview reads the Champion as 60 food + 20 wood", costs == [(0, 60), (1, 20)], costs)

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
