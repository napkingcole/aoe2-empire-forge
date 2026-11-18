#!/usr/bin/env python3
"""Test mod for the 2026-11-18 work on feature/feedback-2.8 (after qa_28).

  QA Arrows (over Britons): shooting, reach, bonus damage.
    UU        Longbowman (ranged) and a second, Huskarl (melee) whose attack
              ignores armor
    Cards     unique units +2 projectiles (the Huskarl gets none)
              Cavalry archers +2 projectiles (no second projectile of their own)
              Towers +2 projectiles (as Yasama)
              Spearman line +1 melee reach
              Archer line +4 bonus damage vs Spearmen
              Militia line -10 bonus damage vs Cavalry (a penalty)
              Spearman line +100% bonus damage vs Cavalry
              Skirmisher line +4 bonus damage vs Cavalry (a class they lack)
    Civ bonus 461 (Trebuchets +35% accuracy)

  QA Charge (over Franks): defensive charges, relics, villagers.
    UU        Teutonic Knight: Defensive Charge, one melee hit, every 20 s
    2nd UU    Konnik: Defensive Charge, dodges projectiles, every 4 s
    Civ bonus 462 (Bloodlines, Scout line upgrades -50% food),
              463 (Bombard Tower, Elite Cannon Galleon -50%)
    Cards     Knight line +1 melee attack per relic (up to 4)
              Foragers generate 30 wood per minute
              Lumberjacks generate 30 gold per minute

  QA Aura (over Goths): auras.
    Cards     Town Center: nearby Villagers +50% work rate (range 8)
              Castle: nearby military +120 HP regeneration/min (range 8)
              Barracks: nearby infantry +30% speed (range 8), from the Castle Age
              Unique unit: nearby archers +3 pierce armor (range 6)
    Castle UT a card only: Blacksmith gives nearby military +2 attack (range 8)
    Buildings Siege Workshop and University in the Feudal Age

    venv/bin/python scripts/build_qa_mod_29.py   # writes ignore/qa_29/
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

OUT = ROOT / "ignore" / "qa_29"
LONGBOW, HUSKARL, TEUTONIC, KONNIK = 0, 2, 3, 31            # km indices
ARCHER, MILITIA, SPEAR, SKIRM, KNIGHT = 4, 74, 93, 7, 38
WORKSHOP, UNIVERSITY = 49, 209


def tree():
    return tree_from("SPANISH.json")


def card(cid, targets, effects, when=None):
    c = {"id": cid, "targets": targets, "effects": effects}
    if when is not None:
        c["when"] = when
    return c


def unit(uid, name):
    return {"type": "unit", "id": uid, "name": name}


def building(uid, name):
    return {"type": "unit", "id": uid, "kind": "building", "name": name}


def group(gid):
    return {"type": "group", "id": gid}


def aura(stat, value, affects, rng=8):
    return {"attr": "aura", "op": "add", "value": value, "stat": stat, "affects": affects, "range": rng}


def bonus_damage(value, cls, op="add"):
    return {"attr": "bonus_damage", "op": op, "value": value, "class": cls}


QA = [
    ("britons", civ(
        "QA Arrows", "Arrows",
        share_description="Test: extra projectiles, melee reach, bonus damage, an armor-ignoring Huskarl.",
        tree_version=TREE_VERSION,
        unique_unit={"km_idx": LONGBOW, "name": "", "description": ""},
        second_uu={"km_idx": HUSKARL, "name": "", "description": "",
                   "advanced_flags": {"ignores_armor": True}},
        bonuses=B(461),
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree(),
        custom_bonuses=[
            card("qa-uu-proj", [group("unique_unit")], [{"attr": "projectiles", "op": "add", "value": 2}]),
            card("qa-ca-proj", [group("cavalry_archers")], [{"attr": "projectiles", "op": "add", "value": 2}]),
            card("qa-tower-proj", [group("towers")], [{"attr": "projectiles", "op": "add", "value": 2}]),
            card("qa-reach", [unit(SPEAR, "Spearman")], [{"attr": "reach", "op": "add", "value": 1}]),
            card("qa-bd-archer", [unit(ARCHER, "Archer")], [bonus_damage(4, 27)]),
            card("qa-bd-militia", [unit(MILITIA, "Militia")], [bonus_damage(-10, 8)]),
            card("qa-bd-spear", [unit(SPEAR, "Spearman")], [bonus_damage(100, 8, "mul")]),
            card("qa-bd-skirm", [unit(SKIRM, "Skirmisher")], [bonus_damage(4, 8)]),
        ],
    )),
    ("franks", civ(
        "QA Charge", "Charge",
        share_description="Test: defensive charges, per-relic attack, villagers that generate resources.",
        tree_version=TREE_VERSION,
        unique_unit={"km_idx": TEUTONIC, "name": "", "description": "",
                     "advanced_flags": {"defense_charge": "melee", "defense_recharge": 20}},
        second_uu={"km_idx": KONNIK, "name": "", "description": "",
                   "advanced_flags": {"defense_charge": "ranged", "defense_recharge": 4}},
        bonuses=B(462, 463),
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree(),
        custom_bonuses=[
            card("qa-relic", [unit(KNIGHT, "Knight")], [{"attr": "melee_attack", "op": "add", "value": 1}],
                 when={"relics": 4}),
            card("qa-forage", [{"type": "job", "id": "forager"}],
                 [{"attr": "trickle", "op": "add", "value": 30, "resource": "wood"}]),
            card("qa-chop", [{"type": "job", "id": "lumberjack"}],
                 [{"attr": "trickle", "op": "add", "value": 30, "resource": "gold"}]),
        ],
    )),
    ("goths", civ(
        "QA Aura", "Aura",
        share_description="Test: auras on a Town Center, Castle, Barracks, the unique unit and in a unique tech.",
        tree_version=TREE_VERSION,
        unique_unit={"km_idx": HUSKARL, "name": "", "description": ""},
        bonuses=B(),
        castle_ut={"mode": "custom", "name": "Forge Aura", "description": "Blacksmiths inspire nearby soldiers.",
                   "cost": {"food": 200, "gold": 200}, "time": 30, "effects": [],
                   "custom_bonuses": [card("qa-ut-aura", [building(103, "Blacksmith")],
                                           [aura("attack", 2, "military")])]},
        imperial_ut=preset(0, "imperial"),
        tree=tree(),
        unit_edits={str(WORKSHOP): {"age": 2}, str(UNIVERSITY): {"age": 2}},
        custom_bonuses=[
            card("qa-tc-aura", [building(109, "Town Center")], [aura("work_rate", 50, "villagers")]),
            card("qa-castle-aura", [building(82, "Castle")], [aura("regen", 120, "military")]),
            card("qa-barracks-aura", [building(12, "Barracks")], [aura("speed", 30, "infantry")],
                 when={"age": 102}),
            card("qa-uu-aura", [group("unique_unit")], [aura("pierce_armor", 3, "archers", 6)]),
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
    cfg.write_text(json.dumps({"mod_name": "QA 2.9", "prefix": "qa_29", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_29.zip")
    print(f"\nWrote {OUT / 'qa_29.zip'}.")


if __name__ == "__main__":
    main()
