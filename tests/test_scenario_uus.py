#!/usr/bin/env python3
"""Scenario units as unique units (km 103-124); KM's custom ones offered beside them.  DAT-gated.

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
check("twenty-two scenario units, 103-124", sorted(kcu.SCENARIO_UUS) == list(range(103, 125)))
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

print("\n=== KM's custom units are offered; a scenario unit of the same name wins ===")
# 2026-10-22 all 36 KM custom units left the picker; 2026-10-24 they came back
# (players build civs on them — the Headhunter, the Jaridah).  Retired are only
# those whose game unit the picker already offers under the same name.
from civ_schema import RETIRED_UUS                                # noqa: E402
import app as webapp                                              # noqa: E402
scenario_names = {name for name, _, _ in kcu.SCENARIO_UUS.values()}
km = {i for i, p in kcu.PRESETS.items() if p["mode"] != "scenario"}
check("retired = exactly the KM units a scenario unit shares a name with",
      RETIRED_UUS == {i for i in km if kcu.PRESETS[i]["name"] in scenario_names},
      sorted(RETIRED_UUS))
check("...seven of them", len(RETIRED_UUS) == 7, len(RETIRED_UUS))
with webapp.app.test_request_context("/api/builder/uu/catalog"):
    entries = webapp._uu_catalog_entries()
check("the picker marks only those retired", all(e["retired"] == (e["km_idx"] in RETIRED_UUS) for e in entries))
check("...offers the other 29 KM units", km - RETIRED_UUS <= {e["km_idx"] for e in entries if not e["retired"]},
      sorted(km - RETIRED_UUS - {e["km_idx"] for e in entries}))
check("...and offers every scenario unit", {e["km_idx"] for e in entries if e["scenario"]} == set(kcu.SCENARIO_UUS))
from civ_appender import apply_civ                                # noqa: E402
for idx, what in ((63, "a KM unit (Headhunter)"), (42, "a retired one (KM's Ninja)")):
    old = {"format": FORMAT_KEY, "alias": "Wololo Probe", "architecture": 2, "language": 0, "bonuses": [],
           "unique_unit": {"km_idx": idx},
           "tree": {"units": [83], "buildings": [109, 82], "techs": [101, 102, 103]}}
    with contextlib.redirect_stdout(io.StringIO()):
        r = apply_civ(dat, old, target_slot=4)
    check(f"a civ with {what} builds it",
          r.get("uu_id", -1) >= 0 and r.get("km_uu_make_avail_tech_id", -1) >= 0, {k: r.get(k) for k in ("uu_id", "elite_uu_id")})

print("\n=== the civ's own UU keeps Castle button 1 ===")
# QA 2026-10-23: QA Qizilbash copied the Goths' tree, Huskarl node and all.
# Castle button 1 then had two lines; the lower unit id won page 1, so the
# Huskarl (41) kept it and the Qizilbash (a new unit, 2700s) went to page 2.
# It only showed with earlier civs in the same build, as in the QA mod: this
# is that mod's three civs, with the game's own Britons/Franks/Goths trees.
from build_civ import _find_civ_slot                                # noqa: E402
from dat_reader import find_civtechtrees                            # noqa: E402
from wizard_build import _draft_to_civ_def as _to_civ_def           # noqa: E402
from civ_schema import to_draft as _to_draft                        # noqa: E402


def game_tree(civ_file):
    data = json.loads((find_civtechtrees(dat_path) / civ_file).read_text(encoding="utf-8"))
    out = {"units": [], "buildings": [], "techs": []}
    for sec in ("civ_techs_units", "civ_techs_buildings"):
        for n in data[sec]:
            key = {"Unit": "units", "Building": "buildings", "Tech": "techs"}.get(n.get("Use Type"))
            if key and n.get("Node Status") != "NotAvailable" and n["Node ID"] not in out[key]:
                out[key].append(n["Node ID"])
    return out


def qa(alias, km, tree_file, ut, look=None):
    uu = {"km_idx": km, "name": "", "description": ""}
    if look is not None:
        uu["appearance"] = look
    return {"format": FORMAT_KEY, "alias": alias, "architecture": 2, "language": 0, "bonuses": [],
            "unique_unit": uu, "tree": game_tree(tree_file),
            "castle_ut": {"mode": "vanilla", "vanilla_km_idx": ut, "effects": [{"id": ut, "multiplier": 1, "tier": "castle"}]},
            "imperial_ut": {"mode": "vanilla", "vanilla_km_idx": 0, "effects": [{"id": 0, "multiplier": 1, "tier": "imperial"}]}}


fresh = load_dat(str(dat_path))
with contextlib.redirect_stdout(io.StringIO()):
    for alias, km, tree_file, ut, look, civ in (("QA Range", 84, "BRITONS.json", 68, 73, "britons"),
                                               ("QA Bandits", 110, "FRANKS.json", 2, 25, "franks"),
                                               ("QA Qizilbash", 103, "GOTHS.json", 12, None, "goths")):
        r = apply_civ(fresh, _to_civ_def(_to_draft(qa(alias, km, tree_file, ut, look))),
                      target_slot=_find_civ_slot(fresh, civ))
dat = fresh
units = dat.civs[r["civ_index"]].units
slot = [(t.unit_id, t.button_id) for t in units[r["uu_id"]].creatable.train_locations]
check("the Qizilbash trains on Castle button 1, page 1", (82, 1) in slot, slot)

# Same QA round: Anarchy trained Huskarls at the Barracks.  Replacing the Goths
# had set their Anarchy to civ 99, and the UT copy read that instead of the
# Goths — _src_civ_uu_ids(99) then answered with the Britons' Longbowman, the
# first civ replaced, so the Huskarl was never swapped for the Qizilbash.
ut_cmds = dat.effects[dat.techs[r["castle_ut_tech_id"]].effect_id].effect_commands
named = {int(c.a) for c in ut_cmds if c.type in (0, 2)}
check("Anarchy moves the Qizilbash to the Barracks, not the Huskarl",
      {r["uu_id"], r["elite_uu_id"]} <= named and not named & {41, 555}, sorted(named))

print("\n=== the greyed later-age buttons are the new civ's ===")
# futuravailableunits.json is keyed by civ NAME: the Goths' entry put a greyed
# Huskarl on Castle button 1 through the Dark and Feudal Ages (QA 2026-10-23).
tree = game_tree("GOTHS.json")
tree["units"] = [u for u in tree["units"] if u != 440]                 # no Petard
civ = qa("Future Probe", 103, "GOTHS.json", 12)
civ["tree"] = tree
with contextlib.redirect_stdout(io.StringIO()):
    blob = build_wizard_mod(to_draft(civ), str(dat_path), "Goths")
outer = zipfile.ZipFile(io.BytesIO(blob))
dz = zipfile.ZipFile(io.BytesIO(outer.read(next(n for n in outer.namelist() if n.endswith("-data.zip")))))
future = json.loads(dz.read("resources/_common/dat/futuravailableunits.json"))
civs = json.loads(dz.read("resources/_common/dat/civilizations.json"))["civilization_list"]
goths = next(c for c in civs if c["internal_name"] == "Goths")
castle = next(b for b in future["Goths"]["Buildings"] if b["ID"] == 82)
units = {u["ID"] for u in castle["Units"]}
techs = {t["ID"] for t in castle["Techs"]}
check("the Castle shows the Qizilbash and its Elite, not the Huskarl",
      {goths["unique_unit_id"], goths["elite_unique_unit_id"]} <= units and not units & {41, 555}, sorted(units))
check("...and this civ's UTs and Elite upgrade, not Anarchy, Perfusion or Elite Huskarl",
      {goths["unique_tech_id_1"], goths["unique_tech_id_2"], goths["unique_unit_upgrade_id"]} <= techs
      and not techs & {16, 457, 365}, sorted(techs))
check("a unit the tree took away is no greyed button (Petard)", 440 not in units, sorted(units))
check("other civs are the game's own", future["Britons"] == json.loads(
    (dat_path.parent / "futuravailableunits.json").read_text(encoding="utf-8"))["Britons"])

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
