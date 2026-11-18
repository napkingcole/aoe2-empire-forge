#!/usr/bin/env python3
"""Test mod for feature/feedback-2.8: everything since 2.8.0-preview.1.

  QA Castle (over Britons): the Castle and its neighbours.
    UU        Konnik, +10 vs infantry (Elite +20); Castle UT Anarchy
    2nd UU    Serjeant, renamed "Castellan", Elite at 600F/300G 30s
    Hero      Liu Bei (to Castle page 2)
    Buildings Krepost and Donjon, from their cards (93, 109) as a player gets them
    Barracks  Halberdier replaced: Heavy Spearman (Castle), then a custom
              Halberdier (Imperial) in the Halberdier's look;
              Halberdier upgrade at 150F/100G
    Castle    Elite Petard after the Petard
    Units     Knight takes 2 population, anti-cavalry armour 10; Archer 0.5
    Cards     Loom instant; Gold Mining free; Builders build 100% faster
    Look      Spartan voices; the Vikings' waypoint flag

  QA Built (over Franks): lines, looks and cards.
    Castle    a built unique unit: Super Mangonel, 3 tiers; Krepost (card 93);
              Castle UT Anarchy; "unique units +50 HP"
    Stable    Winged Hussar, then a Magyar Huszar tier; Camel Riders, no Camel Scout
    Range     Elite Hand Cannoneer tier; card 52 (gunpowder -20%)
    Buildings Siege Workshop and University in the Feudal Age
    Cards     Town Centers +30 gold/min, +30 more each age; Archers +20 HP once a Tower
              stands, Militia line +20 HP once an Outpost stands
    Looks     the Spearman line and the rams as the Achaemenids'

  QA Mule (over Goths): cards a player reported.
    Mule Cart (a building, in place of the camps; 1 population) with card 99;
    cards 81, 105, and 345 with 86 (free Lumber Camp)

  QA Settle (over Teutons): the Settlement and an Italian ally.
    Card 371; Halberdier replaced by a Heavy Spearman; a Shotel Warrior line
    at the Barracks (an Italian ally's Condottiero keeps button 3); card 345
    with 110 (free farm upgrades; apart from 105, which it would hide)

    venv/bin/python scripts/build_qa_mod_28.py   # writes ignore/qa_28/
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_all                                            # noqa: E402
from build_qa_mod_branch import B, civ, preset, tree_from   # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402
from retired_cards import TREE_VERSION                      # noqa: E402

OUT = ROOT / "ignore" / "qa_28"
KONNIK, SERJEANT = 31, 36                                    # km indices
LIU_BEI = 1966
KREPOST, DONJON, SETTLEMENT = 1251, 1665, 2556
SPEAR, PIKE, HALB, HALB_TECH = 93, 358, 359, 429
KNIGHT, ARCHER, PETARD, MANGONEL = 38, 4, 440, 280
HUSSAR, WINGED_HUSSAR, MAGYAR_HUSZAR = 441, 1707, 869
CAMEL_RIDER, HEAVY_CAMEL, CAMEL_SCOUT = 329, 330, 1755
HAND_CANNONEER, MULE_CART, SHOTEL = 5, 1808, 1016
RAMS = (1258, 422, 548)
WORKSHOP, UNIVERSITY = 49, 209
LOOM, GOLD_MINING, CROP_ROTATION = 22, 55, 12
VIKINGS = 11


def anarchy(name):
    return {"mode": "custom", "name": name, "description": "Unique units train at the Barracks.",
            "cost": {"food": 300, "gold": 200}, "time": 40, "effects": [{"id": 12, "multiplier": 1}]}


def tree(add_units=(), drop_units=(), add_buildings=(), add_techs=()):
    t = tree_from("SPANISH.json")
    t["units"] = [u for u in t["units"] if u not in drop_units] + [u for u in add_units if u not in t["units"]]
    t["buildings"] += [b for b in add_buildings if b not in t["buildings"]]
    t["techs"] += [x for x in add_techs if x not in t["techs"]]
    return t


def card(cid, targets, effects, when=None):
    c = {"id": cid, "targets": targets, "effects": effects}
    if when is not None:
        c["when"] = when
    return c


QA = [
    ("britons", civ(
        "QA Castle", "Castle",
        share_description="Test: two unique units, Liu Bei, Krepost and Donjon, a Heavy Spearman, population.",
        tree_version=TREE_VERSION, language=47, waypoint_flag=VIKINGS,
        unique_unit={"km_idx": KONNIK, "name": "", "description": "",
                     "overrides": {"bonus_base": {"1": 10}, "bonus_elite": {"1": 20}}},
        second_uu={"km_idx": SERJEANT, "name": "Castellan", "description": "A test second unique unit.",
                   "elite_upgrade": {"cost": {"food": 600, "gold": 300}, "time": 30}},
        hero_unit={"base_unit_id": LIU_BEI, "name": "", "description": "", "overrides": {}, "flags": {}},
        bonuses=B(93, 109),
        castle_ut=anarchy("Castle Anarchy"), imperial_ut=preset(0, "imperial"),
        tree=tree(),
        unit_edits={str(KNIGHT): {"pop": 2, "armour": {"8": 10}}, str(ARCHER): {"pop": 0.5},
                    str(HALB): {"age": 3}},          # the Heavy Spearman (the Halberdier's place) in Castle
        tech_edits={str(HALB_TECH): {"cost": {"food": 150, "gold": 100}}},
        added_lines=[
            {"id": 1, "building": 12, "base": PIKE, "replaces": HALB,
             "tiers": [{"age": 3, "name": "Heavy Spearman", "edits": {"hp": 70}},
                       {"age": 4, "name": "Halberdier", "edits": {"attack": 8}, "appearance": HALB,
                        "upgrade": {"cost": {"food": 300, "gold": 600}, "time": 50}}]},
            {"id": 2, "building": 82, "base": PETARD, "from": PETARD, "tiers": [{"age": 4, "name": "Elite Petard"}]},
        ],
        custom_bonuses=[
            card("qa-loom", [{"type": "tech", "id": LOOM, "name": "Loom"}], [{"attr": "instant", "op": "set"}]),
            card("qa-gold", [{"type": "tech", "id": GOLD_MINING, "name": "Gold Mining"}], [{"attr": "free", "op": "set"}]),
            card("qa-build", [{"type": "job", "id": "builder"}], [{"attr": "work_rate", "op": "mul", "value": 100}]),
        ],
    )),
    ("franks", civ(
        "QA Built", "Built",
        share_description="Test: a built unique unit, tiers after the Winged Hussar and Hand Cannoneer, Feudal buildings, cards.",
        tree_version=TREE_VERSION,
        unique_unit={"km_idx": KONNIK, "name": "", "description": ""},
        bonuses=B(93, 52),
        castle_ut=anarchy("Built Anarchy"), imperial_ut=preset(0, "imperial"),
        tree=tree(add_units=(WINGED_HUSSAR, CAMEL_RIDER, HEAVY_CAMEL), drop_units=(HUSSAR, CAMEL_SCOUT)),
        unit_edits={str(WORKSHOP): {"age": 2}, str(UNIVERSITY): {"age": 2},
                    **{str(u): {"skin": "Achaemenids"} for u in (SPEAR, PIKE, HALB, *RAMS)}},
        added_lines=[
            {"id": 1, "building": 82, "base": MANGONEL,
             "tiers": [{"age": 3, "name": "Super Mangonel"}, {"age": 3, "name": "Veteran Mangonel"}, {"age": 4, "name": "Elite Mangonel"}]},
            {"id": 2, "building": 101, "base": MAGYAR_HUSZAR, "from": WINGED_HUSSAR,
             "tiers": [{"age": 4, "name": "Magyar Huszar"}]},
            {"id": 3, "building": 87, "base": HAND_CANNONEER, "from": HAND_CANNONEER,
             "tiers": [{"age": 4, "name": "Elite Hand Cannoneer"}]},
        ],
        custom_bonuses=[
            card("qa-uu", [{"type": "group", "id": "unique_unit"}], [{"attr": "hp", "op": "add", "value": 50}]),
            card("qa-tc", [{"type": "unit", "id": 109, "kind": "building", "name": "Town Center"}],
                 [{"attr": "trickle", "op": "add", "resource": "gold",
                   "steps": {"0": 30, "101": 60, "102": 90, "103": 120}}], when={"steps": True}),
            card("qa-tower", [{"type": "group", "id": "archers"}], [{"attr": "hp", "op": "add", "value": 20}],
                 when={"building": 79}),
            card("qa-outpost", [{"type": "unit", "id": 74, "name": "Militia"}], [{"attr": "hp", "op": "add", "value": 20}],
                 when={"building": 598}),
        ],
    )),
    ("goths", civ(
        "QA Mule", "Mule",
        share_description="Test: Mule Carts with Feudal siege, Khmer buildings, Burgundian eco, Wei villagers.",
        tree_version=TREE_VERSION, architecture=5,       # Mesoamerican: the Aztecs' waypoint flag by default
        unique_unit={"km_idx": KONNIK, "name": "", "description": ""},
        bonuses=B(99, 81, 105, 345, 86),
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree(add_buildings=(MULE_CART,), add_techs=(CROP_ROTATION,)),   # the Spanish lack Crop Rotation
        unit_edits={str(MULE_CART): {"pop": 1}},
    )),
    ("teutons", civ(
        "QA Settle", "Settle",
        share_description="Test: Spearmen at the Settlement, a line beside an Italian ally's Condottiero.",
        tree_version=TREE_VERSION,
        unique_unit={"km_idx": KONNIK, "name": "", "description": ""},
        bonuses=B(371, 345, 110),
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree(add_buildings=(SETTLEMENT,), add_techs=(CROP_ROTATION,)),
        added_lines=[
            {"id": 1, "building": 12, "base": PIKE, "replaces": HALB, "tiers": [{"age": 4, "name": "Heavy Spearman"}]},
            {"id": 2, "building": 12, "base": SHOTEL, "tiers": [{"age": 3}, {"age": 4}]},
        ],
    )),
]


def main() -> None:
    dat_path = find_game_dat()
    if dat_path is None:
        sys.exit("No game DAT found.")
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for replace, c in QA:
        f = OUT / f"{c['alias'].replace(' ', '_')}.civbuilder.json"
        f.write_text(json.dumps(c, indent=2) + "\n", encoding="utf-8")
        entries.append({"json": str(f), "replace": replace})
    cfg = OUT / "qa_mod_config.json"
    cfg.write_text(json.dumps({"mod_name": "QA 2.8", "prefix": "qa_28", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_28.zip")
    print(f"\nWrote {OUT / 'qa_28.zip'}.")


if __name__ == "__main__":
    main()
