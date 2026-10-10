#!/usr/bin/env python3
"""In-game probe: does a blast radius card make a Castle / Fortified Church splash?

The custom bonus picker offers "blast radius" on anything with an attack whose
blast level is not 3 ("hits only its target").  The Fortified Church, Castle,
Keep and Krepost are level 0 at width 0 — the Trebuchet's setting before Warwolf
widens it — so a card should make their arrows splash, friendly units included.
That is inferred from Warwolf, never seen; this mod checks it.

    venv/bin/python scripts/probe_blast.py          # writes ignore/probe_blast.zip

Civ "Blast Probe" (over Britons, Britons tree + Keep, card 316 "Fortified church
replaces monastery" — the only way a custom civ gets one), two cards at the maximum:
  Monasteries          +5 blast radius   -> only the Fortified Church (the Monastery has no attack)
  Defensive buildings  +5 blast radius   -> Castle, Keep, Krepost; NOT the Watch / Guard Tower (level 3)

In game (cheats on): build a Fortified Church, a Castle, a Keep and a Guard Tower;
send a clump of enemy units — and park some of your own beside them.
  arrows from the Church / Castle / Keep hit a whole clump  -> the effect is real (keep it)
  ...and your own units nearby take damage too              -> level 0 friendly fire, as expected
  the Guard Tower hits one unit at a time                   -> the comparison
  nothing splashes                                          -> remove blast radius from these
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_all                                            # noqa: E402
from civ_appender import _add_auto_fire_tech, EC_ADD        # noqa: E402
from genieutils.effect import EffectCommand                 # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402


def tree_from(civ_file: str) -> dict:
    data = json.loads((ROOT / "CivTechTrees" / civ_file).read_text(encoding="utf-8"))
    out = {"units": [], "buildings": [], "techs": []}
    for sec in ("civ_techs_units", "civ_techs_buildings"):
        for n in data[sec]:
            key = {"Unit": "units", "Building": "buildings", "Tech": "techs"}.get(n.get("Use Type"))
            if key and n.get("Node Status") != "NotAvailable" and n["Node ID"] not in out[key]:
                out[key].append(n["Node ID"])
    return out


# Round 2 (2026-10-10): the card's +5 on 1806 did not show on a built church.
# Card 316 makes the church by UPGRADING the Monastery (104 -> 1806, tech 1512),
# which fires before the card's tech — so the theory is the engine copied 1806
# into the Monastery before the +5 landed.  This writes +5 straight onto the
# Monastery (and its old entries 30-32) as well; if the church shows it now,
# building cards must also hit the pre-upgrade unit.
_real_apply_civ = build_all.apply_civ


def _apply_civ_with_probe(dat, civ_def, target_slot, *args, **kwargs):
    result = _real_apply_civ(dat, civ_def, target_slot=target_slot, *args, **kwargs)
    if civ_def.get("alias") == "Blast Probe":
        tid = _add_auto_fire_tech(dat, target_slot,
                                  [EffectCommand(type=EC_ADD, a=u, b=-1, c=22, d=5.0) for u in (104, 30, 31, 32)],
                                  name="PROBE Monastery blast")
        print(f"  PROBE: tech {tid} adds +5 blast width to the Monastery (104, 30-32)")
    return result


def main() -> None:
    build_all.apply_civ = _apply_civ_with_probe
    dat_path = find_game_dat()
    if dat_path is None:
        sys.exit("No game DAT found.")
    tree = tree_from("BRITONS.json")
    for b in (79, 234, 235, 82):
        if b not in tree["buildings"]:
            tree["buildings"].append(b)
    for t in (140, 63):                       # Guard Tower, Keep upgrades
        if t not in tree["techs"]:
            tree["techs"].append(t)
    blast = [{"attr": "blast_radius", "op": "add", "value": 5}]
    civ = {"format": FORMAT_KEY, "schema_version": 2, "alias": "Blast Probe",
           "tagline": "Test civ: splashing arrows", "description": "",
           "architecture": 2, "language": 0, "bonuses": [{"id": 316, "multiplier": 1}], "team_bonuses": [],
           "unique_unit": {"km_idx": 0},
           "custom_bonuses": [
               {"target": {"type": "group", "id": "churches"}, "effects": blast},
               {"target": {"type": "group", "id": "defensive"}, "effects": blast},
           ],
           "tree": tree}
    out = ROOT / "ignore" / "probe_blast.zip"
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "blast.json"
        f.write_text(json.dumps(civ), encoding="utf-8")
        cfg = Path(tmp) / "cfg.json"
        cfg.write_text(json.dumps({"mod_name": "Blast Probe", "prefix": "blast_probe",
                                   "civs": [{"json": str(f), "replace": "britons"}]}), encoding="utf-8")
        build_all.build_mod(cfg, Path(dat_path), out)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
