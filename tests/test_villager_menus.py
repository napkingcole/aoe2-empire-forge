#!/usr/bin/env python3
"""The villager's build menus are not pages (#129).

The economic and military menus reuse button numbers (the Lumber Camp and the
Siege Workshop are both on 4; interface_kind tells them apart), so the button
resolver must leave the villager alone.  It treated card 99's Siege Workshop
as a clash with the Mule Cart and moved the Mule Cart to "page 2", button 21,
where a villager has no button: the reporter's Mule Carts couldn't be built.
Replays the reporter's civ (Mountain Clans: Mule Cart, card 99).  DAT-gated.

    venv/bin/python tests/test_villager_menus.py
"""
import contextlib
import io
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
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
civ_file = ROOT / "my_civs" / "19_Cannoneers.json"
if dat_path is None or not civ_file.exists():
    print("  skip  no game DAT (or my_civs/19_Cannoneers.json) found")
    sys.exit(0)

from civ_overrides import apply_civ_with_overrides  # noqa: E402
from retired_cards import TREE_VERSION  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

BUILDER, MULE_CART, LUMBER, MINING, WORKSHOP = 118, 1808, 562, 584, 49
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]
dat = load_dat(str(dat_path))
draft = {"tree_version": TREE_VERSION, "alias": "Mountain Clans", "architecture": 2, "language": 0,
         "bonuses": [{"id": 99, "multiplier": 1}],     # Siege Workshop and Battering Ram in Feudal
         "team_bonuses": [], "unique_unit": {"km_idx": 2},
         "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
         "imperial_ut": {"mode": "vanilla", "effects": [{"id": 4, "multiplier": 1}]},
         "tree": {"units": units, "techs": techs,
                  "buildings": [b for b in buildings if b not in (LUMBER, MINING)] + [MULE_CART, WORKSHOP]}}
with contextlib.redirect_stdout(io.StringIO()):
    r, _ = apply_civ_with_overrides(dat, _draft_to_civ_def(draft), 1, draft)
mule = dat.civs[1].units[MULE_CART]
locs = [(t.unit_id, t.button_id) for t in mule.creatable.train_locations]
check("the Mule Cart stays on the villager's button 4", locs == [(BUILDER, 4)], locs)
check("...with no page move reported for the villager",
      not any(e.get("building") == BUILDER for e in r.get("button_layout") or []), r.get("button_layout"))
ws = [(t.unit_id, t.button_id) for t in dat.civs[1].units[WORKSHOP].creatable.train_locations]
check("the Siege Workshop keeps its own 4, on the military menu", ws == [(BUILDER, 4)], ws)

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
