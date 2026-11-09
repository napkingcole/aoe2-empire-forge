#!/usr/bin/env python3
"""Test mod for "+ Add Unit" (added_lines.py), 2026-11-09.
One civ over the Franks' full tree (the Spearman line ON, so the vanilla
upgrades have something to ride), built through build_all like any mod.

  QA Lines (over Britons)
    Barracks  "Guard" line from the Spearman: Feudal -> Castle -> Imperial.
              Guard 70 HP (carried to every tier); Elite Guard attack 9.
              Pikeman / Halberdier also upgrade it (the AI's way up).
    Stable    Knight line, Castle -> Imperial, wearing the Savar's look;
              a custom card gives this line only +20 HP.
    Archery   Longbowman line, Feudal -> Castle, wearing the Chu Ko Nu's
              look (the Elite wears the Elite Chu Ko Nu's).
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

LINES = [
    {"id": 1, "building": 12, "base": SPEARMAN,
     "tiers": [{"age": 2, "name": "Guard", "edits": {"hp": 70}},
               {"age": 3},
               {"age": 4, "edits": {"attack": 9}}]},
    {"id": 2, "building": 101, "base": KNIGHT, "appearance": SAVAR,
     "tiers": [{"age": 3}, {"age": 4}]},
    {"id": 3, "building": 87, "base": LONGBOWMAN, "appearance": CHU_KO_NU,
     "tiers": [{"age": 2}, {"age": 3}]},
]

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
        tree=tree_from("FRANKS.json"),
        added_lines=LINES,
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
