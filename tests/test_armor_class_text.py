#!/usr/bin/env python3
"""Every armour card grants the armour class its text names.

Armour (attribute 8) packs class * 256 + amount into d: class 3 is pierce,
class 4 is melee.  Bonus 55 "Stable units +1P armor" carried d=1025 — class 4,
melee — and players got melee armour from a pierce card (issue #47).  This
sweeps every civ and team card whose text names one class, so the same slip
anywhere else fails here.  No DAT needed.

    venv/bin/python tests/test_armor_class_text.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bonus_catalog import civ_bonus_ec_list, team_bonus_ec_list   # noqa: E402

PIERCE, MELEE = 3, 4
failures = 0
checked = 0


def classes_named(text: str) -> set[int]:
    t = text.lower()
    named = set()
    if re.search(r"\d+p armou?r|pierce armou?r|/\+?\d+p\b", t):
        named.add(PIERCE)
    if re.search(r"melee armou?r|\+\d+/\+?\d+p", t):
        named.add(MELEE)
    return named


def sweep(kind, names, ec_list_of):
    global failures, checked
    for key, text in names.items():
        named = classes_named(text)
        if not named:
            continue
        granted = {int(ec["D"]) >> 8
                   for group in ec_list_of(int(key)) for ec in group["ecs"]
                   if ec["C"] == 8 and ec["type"] in (0, 4, 5) and ec["D"] >= 256}
        if not granted:
            continue                      # delivered by a vanilla tech, not our data
        checked += 1
        if not granted <= named:
            failures += 1
            print(f"  FAIL {kind} {key} {text!r}: grants class {sorted(granted)}, "
                  f"text names {sorted(named)}")


sweep("civ", json.loads((ROOT / "bonus_names.json").read_text(encoding="utf-8")), civ_bonus_ec_list)
sweep("team", json.loads((ROOT / "team_bonus_names.json").read_text(encoding="utf-8")), team_bonus_ec_list)

print(f"  {checked} armour cards checked")
if checked < 5:
    failures += 1
    print("  FAIL the sweep matched too few cards to mean anything")
print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
