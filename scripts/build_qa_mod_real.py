#!/usr/bin/env python3
"""Test mod for the unlock cards' retirement into the tree (feature/real-unit-add,
2026-11-11): the game's own units from the "+", replacements, Looks, the hero
panel, the siege ship in the tree, and an old civ converted at build.

  QA Real (over Britons): a civ made the new way, everything in its tree.
    Range     Genitour + Elite (a team-bonus unit, now a tree unit)
    Barracks  Condottiero (team-bonus unit); Temple Guard + Elite (also at
              the Monastery, as the game has it)
    Workshop  Flaming Camel (KM catalog unit)
    Dock      Caravel + Elite (KM catalog unit); the Dragon Ship in the Fast
              Fire Ship's place; the Dromon in the Cannon Galleon's place
    Stable    Savar in the Paladin's place; Winged Hussar in the Hussar's
    Looks     Knight wears the Crusader Knight; Trebuchet is the Palintonon
    Hero      Liu Bei (hero panel)

  QA Legacy (over Franks): a civ saved the old way, converted at build.
    Cards     456 Scythian Horse Archer, 416 Legionary, 43 Missionary,
              405 Bolas Rider, 309 Royal Battle Elephant
    Picker    long_range_ship "lou_chuan" (the Siege Ship picker's choice)

    venv/bin/python scripts/build_qa_mod_real.py   # writes ignore/qa_real/
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

OUT = ROOT / "ignore" / "qa_real"
CONQUISTADOR = 13
KNIGHT, CRUSADER_KNIGHT, TREB_PACKED = 38, 1723, 331
PALADIN, SAVAR, HUSSAR, WINGED_HUSSAR = 569, 1813, 441, 1707
FAST_FIRE_SHIP, DRAGON_SHIP = 532, 1302
CANNON_GALLEON, ELITE_CANNON_GALLEON, DROMON = 420, 691, 1795
GENITOUR, ELITE_GENITOUR, CONDOTTIERO = 1010, 1012, 882
TEMPLE_GUARD, ELITE_TEMPLE_GUARD, FLAMING_CAMEL = 2586, 2587, 1263
CARAVEL, ELITE_CARAVEL = 1004, 1006
LIU_BEI = 1966
BATTLE_ELEPHANT, ELITE_BATTLE_ELEPHANT = 1132, 1134

real_tree = tree_from("SPANISH.json")          # has the Paladin, Hussar, Fast Fire Ship, Cannon Galleon line
gone = {PALADIN, HUSSAR, FAST_FIRE_SHIP, CANNON_GALLEON, ELITE_CANNON_GALLEON}
real_tree["units"] = [u for u in real_tree["units"] if u not in gone] + [
    SAVAR, WINGED_HUSSAR, DRAGON_SHIP, DROMON, GENITOUR, ELITE_GENITOUR, CONDOTTIERO,
    TEMPLE_GUARD, ELITE_TEMPLE_GUARD, FLAMING_CAMEL, CARAVEL, ELITE_CARAVEL]

legacy_tree = tree_from("SARACENS.json")       # has the Cavalry Archer, Champion, Elite Cannon Galleon
legacy_tree["units"] += [BATTLE_ELEPHANT, ELITE_BATTLE_ELEPHANT]

QA = [
    ("britons", civ(
        "QA Real", "Real",
        share_description="Test: the game's own units from the tree, replacements, Looks, Liu Bei, the Dromon.",
        tree_version=TREE_VERSION,
        unique_unit={"km_idx": CONQUISTADOR, "name": "", "description": ""},
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=real_tree,
        unit_edits={str(KNIGHT): {"appearance": CRUSADER_KNIGHT},
                    str(TREB_PACKED): {"name": "Palintonon", "skin": "Athenians"}},
        hero_unit={"base_unit_id": LIU_BEI, "name": "", "description": "", "overrides": {}, "flags": {}},
    )),
    ("franks", civ(
        "QA Legacy", "Legacy",
        share_description="Test: an old civ with unlock cards and the Siege Ship picker, converted at build.",
        unique_unit={"km_idx": CONQUISTADOR, "name": "", "description": ""},
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        bonuses=B(456, 416, 43, 405, 309),
        long_range_ship="lou_chuan", long_range_ship_elite=True,
        tree=legacy_tree,
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
    cfg.write_text(json.dumps({"mod_name": "QA Real", "prefix": "qa_real", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_real.zip")
    print(f"\nWrote {OUT / 'qa_real.zip'}.")


if __name__ == "__main__":
    main()
