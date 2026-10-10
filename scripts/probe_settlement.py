#!/usr/bin/env python3
"""In-game probe for issue #69: does picking the Settlement give a Settlement?

A player reported that choosing the Settlement in the tech tree took away the
Mill, Lumber Camp and Mining Camp but never gave a Settlement.  Every build path
writes exactly what vanilla Mapuche use (type=8 on tech 1353, the camps hidden),
and the feature had never been loaded in game — so this builds one mod with
each way a civ can get the Settlement, to check in one lobby:

  Settle Native   the Mapuche template as-is              (over Britons)
  Settle Poles    the Poles template, Settlement picked   (over Franks)
  Settle Blank    the full tree, Settlement picked         (over Goths)
  Settle KM Card  a KM-format civ with legacy card 403     (over Teutons)

    venv/bin/python scripts/probe_settlement.py      # writes ignore/probe_settlement.zip

In game, for each civ in a Dark Age game: a Villager's build menu should show
the Settlement (button 2, where the Mill was) and no Mill, Lumber Camp or Mining
Camp; the Settlement should accept wood, food, gold and stone.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_all                                            # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402

CAMPS_AND_SWAPS = (68, 562, 584, 1734, 1808)


def tree_from(civ_file: str) -> dict:
    data = json.loads((ROOT / "CivTechTrees" / civ_file).read_text(encoding="utf-8"))
    out = {"units": [], "buildings": [], "techs": []}
    for sec in ("civ_techs_units", "civ_techs_buildings"):
        for n in data[sec]:
            key = {"Unit": "units", "Building": "buildings", "Tech": "techs"}.get(n.get("Use Type"))
            if key and n.get("Node Status") != "NotAvailable":
                out[key].append(n["Node ID"])
    return out


def full_tree() -> dict:
    full = json.loads((ROOT / "static/aoe2techtree/data/trees/FULL.json").read_text(encoding="utf-8"))
    out = {"units": [], "buildings": [b["node_id"] for b in full["buildings"]], "techs": []}
    for n in full["units_techs"]:
        (out["units"] if n["use_type"] == "Unit" else out["techs"]).append(n["node_id"])
    return out


def with_settlement(tree: dict) -> dict:
    """What the editor's Settlement switch saves: the Settlement in, the camps out."""
    t = {k: list(v) for k, v in tree.items()}
    t["buildings"] = [b for b in t["buildings"] if b not in CAMPS_AND_SWAPS] + [2556]
    return t


def ef(alias: str, tree: dict) -> dict:
    return {"format": FORMAT_KEY, "schema_version": 2, "alias": alias, "tagline": "Settlement test",
            "architecture": 2, "language": 0, "bonuses": [], "team_bonuses": [],
            "unique_unit": {"km_idx": 0}, "tree": tree}


def main() -> None:
    dat_path = find_game_dat()
    if dat_path is None:
        sys.exit("No game DAT found.")
    britons = tree_from("BRITONS.json")
    civs = [
        ("britons", ef("Settle Native", tree_from("MAPUCHE.json"))),
        ("franks",  ef("Settle Poles", with_settlement(tree_from("POLES.json")))),
        ("goths",   ef("Settle Blank", with_settlement(full_tree()))),
        ("teutons", {"alias": "Settle KM Card", "description": "Settlement test", "architecture": 2,
                     "language": 0, "wonder": -1, "castle": -1,
                     "bonuses": [[[403, 1]], [0], [], [], []],
                     "tree": [britons["units"], britons["buildings"], britons["techs"]]}),
    ]
    out = ROOT / "ignore" / "probe_settlement.zip"
    with tempfile.TemporaryDirectory() as tmp:
        entries = []
        for replace, civ in civs:
            f = Path(tmp) / f"{civ['alias'].replace(' ', '_')}.json"
            f.write_text(json.dumps(civ), encoding="utf-8")
            entries.append({"json": str(f), "replace": replace})
        cfg = Path(tmp) / "probe.json"
        cfg.write_text(json.dumps({"mod_name": "Settlement Probe", "prefix": "settlement_probe",
                                   "civs": entries}), encoding="utf-8")
        build_all.build_mod(cfg, Path(dat_path), out)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
