#!/usr/bin/env python3
"""Test mod for the bugfix pass on fix/issues-91-104 (2026-10-29).
Built through build_all like any mod.

  QA Reload  (over Britons)  #104 Conquistador with reload 2 / 1.5 and range
                             7 / 8; #92 Imperial Scorpion (308) + card 271;
                             #96 NO team bonus, so the civ panel must show
                             text and "Team Bonus: None"
  QA Zealot  (over Franks)   #99 Camel Archer + Zealotry; #91 Legionary (416)
                             and Savar (417) cards over the Franks' full lines
  QA Tusk    (over Goths)    #97 Tusk Swords with the Armored and Siege
                             Elephant; #93 Shu siege speed (336) with Cannon
                             Galleons; #104 the Xolotl Warrior preset's speed

    venv/bin/python scripts/build_qa_mod_bugfix.py   # writes ignore/qa_bugfix/
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

OUT = ROOT / "ignore" / "qa_bugfix"
CONQUISTADOR, CAMEL_ARCHER, XOLOTL = 13, 26, 40
ZEALOTRY, TUSK_SWORDS = 48, 18
KHMER = tree_from("KHMER.json")                 # elephants, scorpions, Cannon Galleons

QA = [
    ("britons", civ(
        "QA Reload", "Reload",
        share_description="Test: Conquistador attacks every 2 s (Elite 1.5 s), range 7 (8); Imperial Scorpion gets the scorpion techs; no team bonus.",
        unique_unit={"km_idx": CONQUISTADOR, "name": "", "description": "",
                     "overrides": {"reload_base": 2, "reload_elite": 1.5, "range_base": 7, "range_elite": 8}},
        bonuses=B(308, 271),
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=KHMER,
    )),
    ("franks", civ(
        "QA Zealot", "Zealot",
        share_description="Test: Zealotry gives the Camel Archer +20 HP once; Legionary and Savar replace Two-Handed Swordsman and Paladin.",
        unique_unit={"km_idx": CAMEL_ARCHER, "name": "", "description": ""},
        bonuses=B(416, 417), team_bonuses=B(3),
        castle_ut=preset(ZEALOTRY, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree_from("FRANKS.json"),                      # full Militia and Knight lines
    )),
    ("goths", civ(
        "QA Tusk", "Tusk",
        share_description="Test: Tusk Swords reaches every melee elephant; Cannon Galleons move faster with the Shu siege bonus; Xolotl Warrior attack speed.",
        unique_unit={"km_idx": XOLOTL, "name": "", "description": ""},
        bonuses=B(336), team_bonuses=B(3),
        castle_ut=preset(TUSK_SWORDS, "castle"), imperial_ut=preset(0, "imperial"),
        tree={**KHMER, "units": KHMER["units"] + [1744, 1746]},   # Armored / Siege Elephant
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
    cfg.write_text(json.dumps({"mod_name": "QA Bugfix", "prefix": "qa_bugfix", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_bugfix.zip")
    print(f"\nWrote {OUT / 'qa_bugfix.zip'}.")


if __name__ == "__main__":
    main()
