#!/usr/bin/env python3
"""Test mod for the Dock's button 8 (2026-11-12): a tree Turtle Ship or Caravel
keeps the demolition line beside it, one of them on page 2, instead of
dropping it as KM's cards 50/69 did.  All three civs use the Spanish tree,
which has the whole demolition line.

  QA Caravel (over Britons)  Caravel on button 8; demolition line on page 2
  QA Both    (over Franks)   Turtle Ship on button 8; Caravel and demolition line on page 2
  QA Swap    (over Goths)    Caravel, but the Button Layout picker gives the
                             demolition line page 1: the Caravel goes to page 2

    venv/bin/python scripts/build_qa_mod_dock.py   # writes ignore/qa_dock/
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
from retired_cards import TREE_VERSION                      # noqa: E402

OUT = ROOT / "ignore" / "qa_dock"
CONQUISTADOR, DOCK = 13, 45
TURTLE, ELITE_TURTLE, CARAVEL, ELITE_CARAVEL, DEMO_SHIP = 831, 832, 1004, 1006, 527


def dock_tree(*extra):
    t = tree_from("SPANISH.json")
    t["units"] += list(extra)
    return t


def qa(alias, tagline, desc, tree, **kw):
    return civ(alias, tagline, share_description=desc, tree_version=TREE_VERSION,
               unique_unit={"km_idx": CONQUISTADOR, "name": "", "description": ""},
               castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"), tree=tree, **kw)


QA = [
    ("britons", qa("QA Caravel", "Caravel", "Test: Caravel on Dock button 8, demolition ships on page 2.",
                   dock_tree(CARAVEL, ELITE_CARAVEL))),
    ("franks", qa("QA Both", "Both", "Test: Turtle Ship on button 8; Caravel and demolition ships on page 2.",
                  dock_tree(TURTLE, ELITE_TURTLE, CARAVEL, ELITE_CARAVEL))),
    ("goths", qa("QA Swap", "Swap", "Test: the Button Layout picker keeps the demolition ships on page 1.",
                 dock_tree(CARAVEL, ELITE_CARAVEL),
                 button_moves=[{"building": DOCK, "button": 8, "page_one": DEMO_SHIP}])),
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
    cfg.write_text(json.dumps({"mod_name": "QA Dock", "prefix": "qa_dock", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_dock.zip")
    print(f"\nWrote {OUT / 'qa_dock.zip'}.")


if __name__ == "__main__":
    main()
