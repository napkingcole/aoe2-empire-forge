#!/usr/bin/env python3
"""The tree panel's upgrade numbers: one build, filtered, equals a real build.

The side panel builds a civ once per set of cards with every tree tech and
building switched on (app._tree_steps_build), tags each step with the tree tech
it comes from, and drops the steps of techs the live tree has off, unless a
ticked node needs that tech (the build keeps it: civ_appender Step 3b').  This
pins that the filtered steps are exactly what a build of that tree produces,
unit by unit, for trees aimed at the prerequisite rule: Chemistry with Hand
Cannoneers ticked, Gillnets without Fishing Lines, the Dock's Galleon tech,
Iron Casting without Forging.  DAT-gated, ~2 minutes.

    venv/bin/python tests/test_tree_steps_filter.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


try:
    from dat_reader import find_game_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
civ_file = ROOT / "my_civs" / "19_Cannoneers.json"
if dat_path is None or not civ_file.exists():
    print("  skip  no game DAT (or my_civs/19_Cannoneers.json) found")
    print("\nPASS (0 failure(s))")
    sys.exit(0)

import app  # noqa: E402

units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]
TREE = {"units": units, "buildings": buildings, "techs": techs}
DRAFT = {"alias": "Steps filter", "architecture": 2, "language": 0,
         "bonuses": [{"id": 101, "multiplier": 1}, {"id": 133, "multiplier": 1}],
         "team_bonuses": [{"id": 2, "multiplier": 1}],
         "unique_unit": {"km_idx": 11},
         "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
         "imperial_ut": {"mode": "vanilla", "effects": [{"id": 12, "multiplier": 1}]},
         "tree": TREE}
check("the sample tree has Hand Cannoneers and Chemistry", 5 in units and 47 in techs)


def without(*ids):
    return dict(TREE, techs=[t for t in TREE["techs"] if t not in ids])


def sig(steps):
    return [(s["key"], s["op"], round(s["v"], 4), s["source"]) for s in steps]


basis, _ = app._tree_steps_split(DRAFT)
once = app._tree_steps_build(basis, TREE, str(dat_path))
check("steps carry the tree tech they come from",
      any(s["node"] == 435 for steps in once["steps"].values() for s in steps))
check("a Hand Cannoneer needs Chemistry", 47 in once["needs"].get("u5", []))

for label, tree in [
    ("as saved", TREE),
    ("Chemistry off, Hand Cannoneers on", without(47)),
    ("Bloodlines, Forging line, armour off", without(435, 67, 68, 75, 74, 76, 77, 80, 81, 82)),
    ("Fishing Lines, Dock 35, Forging off", without(906, 35, 67)),
]:
    real = app._tree_steps_build(basis, tree, str(dat_path), exact=True)
    on = set(tree["techs"])
    for t in tree["techs"]:
        on |= set(once["needs"].get(f"t{t}", []))
    for u in tree["units"] + tree["buildings"]:
        on |= set(once["needs"].get(f"u{u}", []))
    differ = [uid for uid in set(once["steps"]) | set(real["steps"])
              if sig([s for s in once["steps"].get(uid, []) if not s["node"] or s["node"] in on])
              != sig(real["steps"].get(uid, []))]
    check(f"filtered = real build: {label}", not differ, f"{len(differ)} units differ, e.g. {differ[:5]}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
