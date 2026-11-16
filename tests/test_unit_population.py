#!/usr/bin/env python3
"""A unit's population, set on the tech tree (#121).

Written as the game's own units have it: resource storage 4 (Population
Headroom) at -N and 11 (Current Population) at +N, and population in the
cost at ceil(N), the room needed to train it — the Karambit Warrior takes 0.5
(cost 1), the Sannahya 2.  Buildings that house others (storage 4 positive)
have none to set.  DAT-gated.

    venv/bin/python tests/test_unit_population.py
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


from civ_schema import norm_unit_edits  # noqa: E402

print("=== schema ===")
check("keeps a population, half steps included",
      norm_unit_edits({"38": {"pop": "2"}, "4": {"pop": 0.5}}) == {"38": {"pop": 2.0}, "4": {"pop": 0.5}},
      norm_unit_edits({"38": {"pop": "2"}, "4": {"pop": 0.5}}))
check("never below 0", norm_unit_edits({"38": {"pop": -1}}) == {"38": {"pop": 0.0}})

try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
civ_file = ROOT / "my_civs" / "19_Cannoneers.json"
if dat_path is None or not civ_file.exists():
    print("  skip  no game DAT (or my_civs/19_Cannoneers.json) found")
    print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
    sys.exit(1 if failures else 0)

from civ_overrides import apply_civ_with_overrides, read_unit_stats  # noqa: E402
from retired_cards import TREE_VERSION  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

SLOT = 1
KNIGHT, ARCHER, MULE_CART, CASTLE, TREB, TREB_PACKED = 38, 4, 1808, 82, 42, 331
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]
dat = load_dat(str(dat_path))
check("the game's own: the Knight takes 1, the Mule Cart 0, the Castle houses (none to set)",
      read_unit_stats(dat.civs[SLOT].units[KNIGHT]).get("pop") == 1.0
      and read_unit_stats(dat.civs[SLOT].units[MULE_CART]).get("pop") == 0.0
      and "pop" not in read_unit_stats(dat.civs[SLOT].units[CASTLE]))
draft = {"tree_version": TREE_VERSION, "alias": "Pop", "architecture": 2, "language": 0,
         "bonuses": [], "team_bonuses": [],
         "unique_unit": {"km_idx": 2, "overrides": {"pop_base": 3, "pop_elite": 0.5}},
         "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
         "imperial_ut": {"mode": "vanilla", "effects": [{"id": 4, "multiplier": 1}]},
         "tree": {"units": units + [MULE_CART], "buildings": buildings, "techs": techs},
         "unit_edits": {str(KNIGHT): {"pop": 2}, str(ARCHER): {"pop": 0.5}, str(MULE_CART): {"pop": 1},
                        str(CASTLE): {"pop": 3}, str(TREB_PACKED): {"pop": 2}}}
with contextlib.redirect_stdout(io.StringIO()):
    r, _ = apply_civ_with_overrides(dat, _draft_to_civ_def(draft), SLOT, draft)
us = dat.civs[SLOT].units


def pop(u):
    st = {s.type: (s.amount, s.flag) for s in u.resource_storages if s.type in (4, 11)}
    cost = [(c.amount, c.flag) for c in (u.creatable.resource_costs if u.creatable else ()) if c.type == 4]
    return st, cost


print("=== the build ===")
check("Knight takes 2, as the Sannahya: storage -2/+2, room for 2 to train",
      pop(us[KNIGHT]) == ({4: (-2.0, 2), 11: (2.0, 2)}, [(2, 0)]), pop(us[KNIGHT]))
check("...and keeps its food and gold", {c.type: c.amount for c in us[KNIGHT].creatable.resource_costs
                                         if c.type in (0, 3)} == {0: 60, 3: 75})
check("Archer takes 0.5, as the Karambit Warrior: room for 1 to train",
      pop(us[ARCHER]) == ({4: (-0.5, 2), 11: (0.5, 2)}, [(1, 0)]), pop(us[ARCHER]))
check("the Mule Cart, which took none, takes 1: storage and a population cost added",
      pop(us[MULE_CART]) == ({4: (-1.0, 2), 11: (1.0, 2)}, [(1, 0)]), pop(us[MULE_CART]))
check("the Castle houses others, so it's left alone",
      pop(us[CASTLE]) == pop(dat.civs[0].units[CASTLE]), pop(us[CASTLE]))
check("the Trebuchet's other form takes the same", pop(us[TREB]) == pop(us[TREB_PACKED])
      and pop(us[TREB])[0][11][0] == 2.0, (pop(us[TREB]), pop(us[TREB_PACKED])))
check("the unique unit's panel: Huskarl 3, Elite Huskarl 0.5",
      pop(us[r["uu_id"]])[0][11][0] == 3.0 and pop(us[r["elite_uu_id"]])[0][11][0] == 0.5,
      (pop(us[r["uu_id"]]), pop(us[r["elite_uu_id"]])))
check("other civs keep the game's", pop(dat.civs[2].units[KNIGHT])[0][11][0] == 1.0)

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
