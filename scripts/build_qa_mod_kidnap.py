#!/usr/bin/env python3
"""Probe mod: does the KM Headhunter kidnap villagers?  Built through build_all.

  QA Kidnap     (over Britons)  Headhunter with the Scythian Scout's kidnap task
  QA Kidnap 95  (over Franks)   the same, and the civ starts with resource 95
                                "Enable PTWC / Kidnap / Loot" at 1

The UGC guide says kidnapping is switched on by resource 95, whose value 1 also
lets the Town Center be packed up.  Nothing in the shipped code sets it; the
second civ is here only to tell whether it is needed.  Both civs have the full
tree of their slot, so their Monks also retest ranged healing (tech 407).

    venv/bin/python scripts/build_qa_mod_kidnap.py      # writes ignore/qa_kidnap/
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_all                                            # noqa: E402
import civ_overrides                                        # noqa: E402
from build_qa_mod_branch import civ, preset, tree_from      # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402

OUT = ROOT / "ignore" / "qa_kidnap"
HEADHUNTER, KIDNAP_RESOURCE = 63, 95

QA = [
    ("britons", civ("QA Kidnap", "Kidnap",
                    share_description="Probe: Headhunter kidnaps villagers.",
                    unique_unit={"km_idx": HEADHUNTER, "name": "", "description": ""},
                    castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
                    tree=tree_from("BRITONS.json"))),
    ("franks", civ("QA Kidnap 95", "Kidnap 95",
                   share_description="Probe: Headhunter kidnaps villagers, resource 95 on.",
                   unique_unit={"km_idx": HEADHUNTER, "name": "", "description": ""},
                   castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
                   tree=tree_from("FRANKS.json"))),
]

# Probe only: the second civ starts with resource 95 = 1.
_apply = civ_overrides.apply_civ_with_overrides


def _with_resource_95(dat, civ_def, slot, *a, **kw):
    out = _apply(dat, civ_def, slot, *a, **kw)
    if civ_def.get("alias") == "QA Kidnap 95":
        dat.civs[out[0]["civ_index"]].resources[KIDNAP_RESOURCE] = 1.0
        print("       PROBE: resource 95 = 1 (kidnap / loot / Town Center packing)")
    return out


build_all.apply_civ_with_overrides = _with_resource_95


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
    cfg.write_text(json.dumps({"mod_name": "QA Kidnap", "prefix": "qa_kidnap", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_kidnap.zip")
    print(f"\nWrote {OUT / 'qa_kidnap.zip'}.")


if __name__ == "__main__":
    main()
