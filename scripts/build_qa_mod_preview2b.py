#!/usr/bin/env python3
"""Test mod for the 2026-10-26 fixes on feature/km-unretire-wooden-castle.
Built through build_all like any mod.

  QA Cost Start   (over Britons)  Headhunter (Elite carries 1); a civ card
                                  making the Knight line 30 wood + 30 gold from
                                  the start; a Castle Age card making Monks 80
                                  wood (the Monk has a spare slot, so it works)
  QA Cost Castle  (over Franks)   the reported case: a Castle UT making Knights
                                  30 wood + 10 stone, which can't work mid-game
                                  and must leave them at 60 food + 75 gold (the
                                  build warns); Wooden Castles (card 460)

Both civs check the new loading-screen tips (IDS_CIVTIPS_1_* / _2_*).

    venv/bin/python scripts/build_qa_mod_preview2b.py   # writes ignore/qa_preview2b/
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

OUT = ROOT / "ignore" / "qa_preview2b"
HEADHUNTER = 63
KNIGHT = {"type": "unit", "id": 38, "name": "Knight", "kind": "unit"}
MONK = {"type": "unit", "id": 125, "name": "Monk", "kind": "unit"}


def cost(**res):
    return [{"attr": "cost_set", "op": "set", "value": v, "resource": r} for r, v in res.items()]


QA = [
    ("britons", civ(
        "QA Cost Start", "Cost Start",
        share_description="Test: Knight line 30 wood + 30 gold from the start; Monks 80 wood from the Castle Age; Elite Headhunter carries 1.",
        unique_unit={"km_idx": HEADHUNTER, "name": "", "description": ""},
        custom_bonuses=[{"targets": [KNIGHT], "effects": cost(wood=30, gold=30)},
                        {"targets": [MONK], "when": {"age": 102}, "effects": cost(wood=80)}],
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree_from("FRANKS.json"),                      # the full Knight line
    )),
    ("franks", civ(
        "QA Cost Castle", "Cost Castle",
        share_description="Test: a Castle UT setting Knights to 30 wood + 10 stone is skipped (Knights keep 60 food + 75 gold); Wooden Castles.",
        unique_unit={"km_idx": 103, "name": "", "description": ""},
        bonuses=B(460),
        castle_ut={"mode": "custom", "vanilla_km_idx": None, "name": "Logistica",
                   "description": "Knight line: costs 30 wood + 10 stone",
                   "cost": {"food": 800, "wood": 0, "stone": 0, "gold": 600}, "time": 50,
                   "effects": [{"id": 3, "multiplier": 1, "tier": "castle"}],
                   "custom_bonuses": [{"targets": [KNIGHT], "effects": cost(wood=30, stone=10)}]},
        imperial_ut=preset(0, "imperial"),
        tree=tree_from("FRANKS.json"),
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
    cfg.write_text(json.dumps({"mod_name": "QA Preview 2b", "prefix": "qa_preview2b", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_preview2b.zip")
    print(f"\nWrote {OUT / 'qa_preview2b.zip'}.")


if __name__ == "__main__":
    main()
