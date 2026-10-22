#!/usr/bin/env python3
"""Scenario units as unique units (km 103-117).  DAT-gated.

km_custom_uu.SCENARIO_UUS offers fifteen units the scenario editor can place
but no civ trains: the UU is the game's own unit as it stands, the Elite is the
game's own where one exists (Qizilbash, War Dog), else scenario_elite() — DE's
typical elite step, measured over its 65 unique units and agreed with the user:
HP +15% (nearest 5, at least +5); melee +2 attack +1 pierce armour; ranged +1
attack +1 range; no attack (Priests) +1 range only.  The Elite upgrade costs
800 food / 700 gold and takes 45 s.

    venv/bin/python tests/test_scenario_uus.py
"""
import contextlib
import io
import json
import sys
import zipfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat              # noqa: E402

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

import km_custom_uu as kcu                                    # noqa: E402
from civ_appender import _KM_UU_NAMES, _KM_UU_TECHS          # noqa: E402

dat = load_dat(str(dat_path))
U = dat.civs[0].units


def stats(u):
    t = u.type_50
    return {"hp": u.hit_points, "attack": t.displayed_attack, "ma": t.displayed_melee_armour,
            "pa": u.creatable.displayed_pierce_armour, "range": t.max_range, "los": u.line_of_sight}


def elite_of(uid):
    e = deepcopy(U[uid])
    kcu.scenario_elite(e)
    return stats(U[uid]), stats(e)


print("=== the table ===")
check("fifteen scenario units, 103-117", sorted(kcu.SCENARIO_UUS) == list(range(103, 118)))
check("none collides with a vanilla or KM index",
      not set(kcu.SCENARIO_UUS) & (set(_KM_UU_TECHS) | set(range(0, 103))))
check("every one is named for the picker", all(_KM_UU_NAMES.get(i) == n for i, (n, _, _) in kcu.SCENARIO_UUS.items()))
check("every one is a PRESETS entry in scenario mode",
      all(kcu.PRESETS[i]["mode"] == "scenario" for i in kcu.SCENARIO_UUS))
check("names match the game's", all(
    U[b] is not None and _KM_UU_NAMES[i] for i, (_, b, _) in kcu.SCENARIO_UUS.items()))

print("\n=== scenario_elite ===")
b, e = elite_of(1)                                            # Imperial Legionary, melee
check("melee: HP +15% to the nearest 5 (75 -> 85)", e["hp"] == 85, e)
check("melee: +2 attack, +1 pierce armour, melee armour unchanged",
      (e["attack"] - b["attack"], e["pa"] - b["pa"], e["ma"] - b["ma"]) == (2, 1, 0), (b, e))
b, e = elite_of(1222)                                         # Sharkatzor, ranged
check("ranged: +1 attack, +1 range and line of sight, armour unchanged",
      (e["attack"] - b["attack"], e["range"] - b["range"], e["los"] - b["los"], e["pa"] - b["pa"]) == (1, 1, 1, 0),
      (b, e))
b, e = elite_of(1023)                                         # Priest, no attack
check("no attack: +1 range only — never an attack it lacks",
      (e["attack"], e["range"] - b["range"]) == (0, 1), (b, e))
check("small HP still gains at least 5 (Priest 30 -> 35)", e["hp"] == 35, e)

print("\n=== a build ===")
from wizard_build import build_wizard_mod                     # noqa: E402
from civ_schema import FORMAT_KEY, to_draft                    # noqa: E402
CIV = {"format": FORMAT_KEY, "alias": "Scenario Probe", "architecture": 2, "language": 0,
       "bonuses": [], "unique_unit": {"km_idx": 103},
       "tree": {"units": [83, 4, 74], "buildings": [109, 82, 12], "techs": [101, 102, 103]}}
with contextlib.redirect_stdout(io.StringIO()):
    blob = build_wizard_mod(to_draft(CIV), str(dat_path), "Britons")
outer = zipfile.ZipFile(io.BytesIO(blob))
dz = zipfile.ZipFile(io.BytesIO(outer.read(next(n for n in outer.namelist() if n.endswith("-data.zip")))))
uz = zipfile.ZipFile(io.BytesIO(outer.read(next(n for n in outer.namelist() if n.endswith("-ui.zip")))))

civs = json.loads(dz.read("resources/_common/dat/civilizations.json"))["civilization_list"]
britons = civs[1]
icon = f"{U[1817].icon_id:03d}_50730.png"
check("the civ picker shows the Qizilbash's own icon",
      britons.get("unique_unit_image_paths") == [f"/resources/uniticons/{icon}"], britons.get("unique_unit_image_paths"))
check("...and the UI mod ships that icon, made from the game's",
      f"resources/_common/wpfg/resources/uniticons/{icon}" in uz.namelist())
# (Icons already in our bundled uniticons/ — the Heavy Pikeman's 136, which KM's
# Swiss Pikeman uses — ship in every mod anyway.)
others = [n for n in uz.namelist() if n.endswith("_50730.png")
          and n.split("/")[-1] in {f"{U[b].icon_id:03d}_50730.png" for i, (_, b, _) in kcu.SCENARIO_UUS.items() if i != 103}
          and not (ROOT / "uniticons" / n.split("/")[-1]).exists()]
check("but not the other scenario units' icons", not others, others[:3])

strings = uz.read(next(n for n in uz.namelist() if n.endswith("key-value-modded-strings-utf8.txt") and "/en/" in n)).decode()
check("the UU and its Elite are named", '"Qizilbash Warrior"' in strings and "Elite Qizilbash Warrior" in strings)

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
