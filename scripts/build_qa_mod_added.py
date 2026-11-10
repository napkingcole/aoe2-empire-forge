#!/usr/bin/env python3
"""Test mod for "+ Add Unit" (added_lines.py), 2026-11-09.
One civ over the Franks' full tree (the Spearman line ON, so the vanilla
upgrades have something to ride), built through build_all like any mod.

  QA Lines (over Britons)
    Barracks  "Guard" line from the Spearman: Feudal -> Castle -> Imperial.
              Guard 70 HP (carried to every tier); Elite Guard attack 9.
    Stable    Knight line, Castle -> Imperial, wearing the Savar's look;
              a custom card gives this line only +20 HP.
    Archery   Longbowman line, Feudal -> Castle, wearing the Chu Ko Nu's
              look (the Elite wears the Elite Chu Ko Nu's).
    Barracks  Hoplite line (Chronicles), Castle -> Imperial.            [round 2]
    Stable    "Lionheart": Richard the Lionheart as a plain unit, Castle:
              no gold border, no regeneration, convertible.             [round 2]
    Barracks  "Elite Champion" after the Champion, attack 16 (beside it).   [round 3]
    Archery   "Imperial Skirmisher" after the Elite Skirmisher, 45 HP.     [round 3]
    Stable    Paladin upgrade gives a Savar copy, named Savar.             [round 3]
    Earlier   Knight in Feudal, Pikeman in Feudal, Gold Mining in Dark.    [round 3]
    Stable    Battle Elephant line ON; "Royal Battle Elephant" after the Elite,
              the suggested one: 330 HP, 15 attack, 4 pierce, 1200f/1000g.  [round 5]
    Siege WS  "Houfnice" after the Bombard Cannon, the game's own price.   [round 5]
    Castle    Trebuchet wearing the Palintonon look (Athenians), named so. [round 5]
    Cards     Spearmen +25% HP (233) also reaches the Guard line.

    venv/bin/python scripts/build_qa_mod_added.py   # writes ignore/qa_added/
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_all                                            # noqa: E402
from build_qa_mod_branch import civ, preset, tree_from      # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402

OUT = ROOT / "ignore" / "qa_added"
SPEARMAN, KNIGHT, LONGBOWMAN = 93, 38, 8
SAVAR, CHU_KO_NU = 1813, 73
CONQUISTADOR = 13
HOPLITE, RICHARD = 2110, 160          # Chronicles; a hero (Richard the Lionheart)
CHAMPION, ELITE_SKIRM, PALADIN, PIKEMAN, GOLD_MINING = 567, 6, 569, 358, 55
BATTLE_ELEPHANT, ELITE_BATTLE_ELEPHANT, BOMBARD, HOUFNICE, TREB_PACKED = 1132, 1134, 36, 1709, 331

LINES = [
    {"id": 1, "building": 12, "base": SPEARMAN,
     "tiers": [{"age": 2, "name": "Guard", "edits": {"hp": 70}},
               {"age": 3},
               {"age": 4, "edits": {"attack": 9}}]},
    {"id": 2, "building": 101, "base": KNIGHT, "appearance": SAVAR,
     "tiers": [{"age": 3}, {"age": 4}, {"age": 4}]},          # round 4: two Imperial tiers
    {"id": 3, "building": 87, "base": LONGBOWMAN, "appearance": CHU_KO_NU,
     "tiers": [{"age": 2}, {"age": 3}]},
    # Round 2: a Chronicles unit and a hero as bases.
    {"id": 4, "building": 12, "base": HOPLITE, "tiers": [{"age": 3}, {"age": 4}]},
    {"id": 5, "building": 101, "base": RICHARD, "tiers": [{"age": 3, "name": "Lionheart"}]},
    # Round 3: extend, replace.
    {"id": 6, "building": 12, "base": CHAMPION, "from": CHAMPION,
     "tiers": [{"age": 4, "edits": {"attack": 16}}]},
    {"id": 7, "building": 87, "base": ELITE_SKIRM, "from": ELITE_SKIRM,
     "tiers": [{"age": 4, "edits": {"hp": 45}}]},
    {"id": 8, "building": 101, "base": SAVAR, "replaces": PALADIN, "tiers": [{"age": 4}]},
    # Round 5: suggested upgrades, as the picker fills them in.
    {"id": 9, "building": 101, "base": ELITE_BATTLE_ELEPHANT, "from": ELITE_BATTLE_ELEPHANT,
     "tiers": [{"age": 4, "name": "Royal Battle Elephant", "edits": {"hp": 330, "attack": 15, "pierce": 4},
                "upgrade": {"cost": {"food": 1200, "gold": 1000}, "time": 200}}]},
    {"id": 10, "building": 49, "base": HOUFNICE, "from": BOMBARD,
     "tiers": [{"age": 4, "upgrade": {"cost": {"food": 1100, "gold": 800}, "time": 140}}]},
]

TREE = tree_from("FRANKS.json")
TREE["units"] += [BATTLE_ELEPHANT, ELITE_BATTLE_ELEPHANT]

QA = [
    ("britons", civ(
        "QA Lines", "Lines",
        share_description="Test: added lines at the Barracks (Guard), Stable (Knight, Savar look) "
                          "and Archery Range (Longbowman, Chu Ko Nu look).",
        unique_unit={"km_idx": CONQUISTADOR, "name": "", "description": ""},
        bonuses=[{"id": 233, "multiplier": 1}],
        custom_bonuses=[{"targets": [{"type": "line", "id": 2, "name": "Knight"}],
                         "effects": [{"attr": "hp", "op": "add", "value": 20}]}],
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=TREE,
        added_lines=LINES,
        # Round 3: available earlier.
        unit_edits={str(KNIGHT): {"age": 2}, str(PIKEMAN): {"age": 2},
                    # Round 5: a look.
                    str(TREB_PACKED): {"name": "Palintonon", "skin": "Athenians"}},
        tech_edits={str(GOLD_MINING): {"age": 1}},
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
    cfg.write_text(json.dumps({"mod_name": "QA Lines", "prefix": "qa_added", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_added.zip")
    print(f"\nWrote {OUT / 'qa_added.zip'}.")


if __name__ == "__main__":
    main()
