#!/usr/bin/env python3
"""Test mod for unit rename + the infantry-vs-villagers fix (2026-11-09).
One civ over the Franks' full tree, built through build_all like any mod.

  QA Token (over Britons): renamed upgrade buttons show "(<cost>)", and
  tree-page renames: Footman (Militia), Sergeant (Man-at-Arms), Holy Knight
                            / Holy Paladin, Siege Engine (Trebuchet, packed
                            and unpacked), Abbot (Monk, and the relic-carrying
                            Monk), Peasant (both Villagers); card 203 at x25,
                            so infantry get +25 attack vs villagers per age
                            from Feudal and should one-shot them

    venv/bin/python scripts/build_qa_mod_rename.py   # writes ignore/qa_rename/
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

OUT = ROOT / "ignore" / "qa_rename"
CONQUISTADOR = 13
RENAMES = {74: "Footman", 75: "Sergeant", 38: "Holy Knight", 569: "Holy Paladin",
           331: "Siege Engine", 125: "Abbot", 83: "Peasant"}

def renamed_civ(alias, tagline, how):
    return civ(
        alias, tagline,
        share_description=f"Test: renamed Militia, Man-at-Arms, Knight, Paladin, Trebuchet, Monk and "
                          f"Villager; upgrade buttons show their cost {how}; infantry one-shot villagers.",
        unique_unit={"km_idx": CONQUISTADOR, "name": "", "description": ""},
        bonuses=[{"id": 203, "multiplier": 25}],
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree_from("FRANKS.json"),
        unit_edits={str(u): {"name": n} for u, n in RENAMES.items()},
    )


QA = [
    ("britons", renamed_civ("QA Token", "Token", "through the game's <cost> token")),
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
    cfg.write_text(json.dumps({"mod_name": "QA Rename", "prefix": "qa_rename", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_rename.zip")
    print(f"\nWrote {OUT / 'qa_rename.zip'}.")


if __name__ == "__main__":
    main()
