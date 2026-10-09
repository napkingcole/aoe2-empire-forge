#!/usr/bin/env python3
"""In-game probe: does EC_RESOURCE b=-1 written straight onto GOLD trickle?

Nothing in vanilla (or in our tested code) does this — b=-1 sets special
trickle-RATE resources (Vineyards 236, Paper Money 266) that the engine pays
out through gatherers.  Before offering a "+X gold per minute" custom bonus,
this builds one throwaway mod to find out.  The product code is untouched:
the probe tech is added by wrapping build_all's apply_civ for this run only.

    venv/bin/python scripts/probe_trickle.py            # writes ignore/probe_trickle.zip

In game: install both mods, play the civ "Trickle Probe" (it replaces the
Britons) in a Dark Age skirmish, and watch gold with no gold miners.

  gold rises ~1 per second from the start  -> the mechanism works; build the card
  gold stays put                           -> it doesn't; the idea stays off
  anything else (a one-off +1, a crash)    -> report it as seen

The probe tech is repeatable (CLAUDE.md quirk 1), like every trickle tech.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_all                                            # noqa: E402
from civ_appender import _add_auto_fire_tech, EC_RESOURCE   # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402
from genieutils.effect import EffectCommand                 # noqa: E402

GOLD, RATE = 3, 1.0          # 1 gold per second if b=-1 means "per second"

PROBE_CIV = {
    "format": FORMAT_KEY, "schema_version": 2, "alias": "Trickle Probe",
    "tagline": "Test civ: gold should rise by itself", "description": "",
    "architecture": 2, "language": 0, "bonuses": [], "team_bonuses": [],
    "unique_unit": {"km_idx": 0},
}
# A realistic tree, borrowed from a saved civ: a tiny one unticks so much that
# the tech-tree effect passes the ~189-command crash limit.  No bonuses, so
# nothing but the probe moves gold.
PROBE_CIV["tree"] = json.loads((ROOT / "uberdudes.civbuilder.json").read_text(encoding="utf-8"))["tree"]

_real_apply_civ = build_all.apply_civ


def _apply_civ_with_probe(dat, civ_def, target_slot, *args, **kwargs):
    result = _real_apply_civ(dat, civ_def, target_slot=target_slot, *args, **kwargs)
    if civ_def.get("alias") == PROBE_CIV["alias"]:
        tid = _add_auto_fire_tech(dat, target_slot,
                                  [EffectCommand(type=EC_RESOURCE, a=GOLD, b=-1, c=-1, d=RATE)],
                                  name="PROBE gold trickle")
        print(f"  PROBE: tech {tid} adds EC_RESOURCE gold b=-1 d={RATE} (repeatable={dat.techs[tid].repeatable})")
    return result


def main() -> None:
    dat_path = find_game_dat()
    if dat_path is None:
        sys.exit("No game DAT found.")
    out = ROOT / "ignore" / "probe_trickle.zip"
    with tempfile.TemporaryDirectory() as tmp:
        civ_file = Path(tmp) / "trickle_probe.json"
        civ_file.write_text(json.dumps(PROBE_CIV), encoding="utf-8")
        cfg = Path(tmp) / "probe.json"
        cfg.write_text(json.dumps({"mod_name": "Trickle Probe", "prefix": "trickle_probe",
                                   "civs": [{"json": str(civ_file), "replace": "britons"}]}),
                       encoding="utf-8")
        build_all.apply_civ = _apply_civ_with_probe
        try:
            build_all.build_mod(cfg, Path(dat_path), out)
        finally:
            build_all.apply_civ = _real_apply_civ
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
