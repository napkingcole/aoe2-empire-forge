#!/usr/bin/env python3
"""Test mod for fix/issue-108 (2026-10-30).  Built through build_all like any mod.

  QA Scythian (over Britons)  #108 Scythian Horse Archer card 456 beside the
                              Gurjaras' Elephant Archer: it takes the Archery
                              Range button, the Elephant Archer goes to page 2
  QA Classes  (over Franks)   card 243 x4 (Skirmishers vs infantry), 253 (foot
                              archers vs villagers), 256 (Scouts vs stone
                              defences), 254 (gunpowder vs camels), 213
                              (Mangonels cut trees)
  QA Siege    (over Goths)    #109 card 99 (Feudal Siege Workshop and Ram), 316
                              (Fortified Church arrow and armour upgrades), 109
                              (Arrowslits reach the Donjon); Svan Towers

    venv/bin/python scripts/build_qa_mod_108.py   # writes ignore/qa_108/
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

OUT = ROOT / "ignore" / "qa_108"
CAMEL_ARCHER = 26

QA = [
    ("britons", civ(
        "QA Scythian", "Scythian",
        share_description="Test: the Scythian Horse Archer card beside the Elephant Archer.",
        unique_unit={"km_idx": CAMEL_ARCHER, "name": "", "description": ""},
        bonuses=B(456), team_bonuses=B(3),
        castle_ut=preset(0, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree_from("GURJARAS.json"),                    # Elephant Archer, Cavalry Archer
    )),
    ("franks", civ(
        "QA Classes", "Classes",
        share_description="Test: bonus attack vs infantry, villagers, stone defences and camels; Mangonels cut trees.",
        unique_unit={"km_idx": CAMEL_ARCHER, "name": "", "description": ""},
        bonuses=[{"id": 243, "multiplier": 4}, *B(253, 256, 254, 213)], team_bonuses=B(3),
        castle_ut=preset(0, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree_from("SPANISH.json"),                     # Skirmisher, Archer, Scout, Hand Cannoneer, Mangonel
    )),
    ("goths", civ(
        "QA Siege", "Siege",
        share_description="Test: Feudal Siege Workshop and Ram, Fortified Church arrows, Arrowslits on the Donjon.",
        unique_unit={"km_idx": CAMEL_ARCHER, "name": "", "description": ""},
        bonuses=B(99, 316, 109, 24, 44, 175), team_bonuses=B(3),   # 24/44/175: start resources
        castle_ut=preset(52, "castle"),                     # Svan Towers: +2 church arrows
        imperial_ut=preset(0, "imperial"),
        tree=tree_from("BRITONS.json"),                     # Siege Workshop, rams, Monastery, Arrowslits
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
    cfg.write_text(json.dumps({"mod_name": "QA 108", "prefix": "qa_108", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_108.zip")
    print(f"\nWrote {OUT / 'qa_108.zip'}.")


if __name__ == "__main__":
    main()
