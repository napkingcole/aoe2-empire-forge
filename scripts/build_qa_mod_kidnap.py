#!/usr/bin/env python3
"""Probe mod: does the KM Headhunter kidnap villagers?  Built through build_all.

Round 1 (kidnap task after the attack, with and without resource 95) only
attacked villagers, 2026-10-25.  Round 2: First only attacked, Twin kidnapped,
so the twin is now the only path and both civs build it (the mode switch below
is inert; a3cff91 has the "first" mode).  Round 2 was:

  QA Kidnap First  (over Britons)  the kidnap task ahead of the attack
  QA Kidnap Twin   (over Franks)   KM's way: a second form with no attack and
                                   the kidnap task, in the same task-swap group

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
import km_custom_uu                                         # noqa: E402
from build_qa_mod_branch import civ, preset, tree_from      # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402

OUT = ROOT / "ignore" / "qa_kidnap"
HEADHUNTER = 63

QA = [
    ("britons", civ("QA Kidnap First", "Kidnap First",
                    share_description="Probe: kidnap task ahead of the attack.",
                    unique_unit={"km_idx": HEADHUNTER, "name": "", "description": ""},
                    castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
                    tree=tree_from("BRITONS.json"))),
    ("franks", civ("QA Kidnap Twin", "Kidnap Twin",
                   share_description="Probe: KM's swappable kidnapper form.",
                   unique_unit={"km_idx": HEADHUNTER, "name": "", "description": ""},
                   castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
                   tree=tree_from("FRANKS.json"))),
]

# Probe only: each civ picks the kidnap mode as it is built.
_apply = civ_overrides.apply_civ_with_overrides
MODES = {"QA Kidnap First": "first", "QA Kidnap Twin": "twin"}


def _with_mode(dat, civ_def, slot, *a, **kw):
    spec = km_custom_uu.PRESETS[HEADHUNTER]["extra"]["kidnap"]
    spec["mode"] = MODES[civ_def["alias"]]
    print(f"       PROBE: kidnap mode {spec['mode']}")
    try:
        return _apply(dat, civ_def, slot, *a, **kw)
    finally:
        spec.pop("mode")


build_all.apply_civ_with_overrides = _with_mode


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
