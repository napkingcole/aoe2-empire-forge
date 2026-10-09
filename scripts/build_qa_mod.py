#!/usr/bin/env python3
"""One test mod for every 2.6.0 fix that needs the game (see ignore/qa_2_6_0/CHECKLIST.md).

Three civs, built through build_all like any mod:

  QA Elephants  (over Britons)  elephant cards 303/79/83/292/208 + Howdah, Royal
                                Battle Elephant, Sannahya, melee Charge Attack,
                                Elite upgrade cost, UT research time, hero
                                button, Galleon/Gillnets prerequisites, female
                                Monk skin + British voice
  QA Mapuche    (over Franks)   #61 Settlement Spearmen/Skirmishers, #62 team
                                bonus owner, ranged Charge Attack, male Monk +
                                Viking voice, population limit, start/age
                                resources, population space
  QA Siege      (over Goths)    #67 range/blast/conversion, #63 unit lines,
                                #66 stray Huskarl, #62 the ally with Elite
                                Skirmishers

The civ files are saved to ignore/qa_2_6_0/ too, so View Civ can open them.

    venv/bin/python scripts/build_qa_mod.py      # writes ignore/qa_2_6_0/qa_2_6_0.zip
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_all                                            # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402

OUT = ROOT / "ignore" / "qa_2_6_0"


def tree_from(civ_file: str) -> dict:
    data = json.loads((ROOT / "CivTechTrees" / civ_file).read_text(encoding="utf-8"))
    out = {"units": [], "buildings": [], "techs": []}
    for sec in ("civ_techs_units", "civ_techs_buildings"):
        for n in data[sec]:
            key = {"Unit": "units", "Building": "buildings", "Tech": "techs"}.get(n.get("Use Type"))
            if key and n.get("Node Status") != "NotAvailable" and n["Node ID"] not in out[key]:
                out[key].append(n["Node ID"])
    return out


def edit(tree, add_units=(), add_buildings=(), add_techs=(), drop_units=(), drop_buildings=(), drop_techs=()):
    t = {k: list(v) for k, v in tree.items()}
    for key, add, drop in (("units", add_units, drop_units), ("buildings", add_buildings, drop_buildings),
                           ("techs", add_techs, drop_techs)):
        t[key] = [x for x in t[key] if x not in drop] + [x for x in add if x not in t[key]]
    return t


def ut(name, desc, effect_ids, time=30):
    return {"mode": "custom", "vanilla_km_idx": None, "name": name, "description": desc,
            "cost": {"food": 200, "wood": 0, "stone": 0, "gold": 200}, "time": time,
            "effects": [{"id": i, "multiplier": 1} for i in effect_ids]}


def card(target, *effects):
    return {"target": target, "effects": list(effects)}


def unit(uid, name, scope=None, kind="unit"):
    t = {"type": "unit", "id": uid, "name": name, "kind": kind}
    return dict(t, scope=scope) if scope else t


def eff(attr, value=None, op="add", **kw):
    e = {"attr": attr, "op": op, **kw}
    if value is not None:
        e["value"] = value
    return e


def civ(alias, tagline, **kw):
    base = {"format": FORMAT_KEY, "schema_version": 2, "alias": alias, "tagline": tagline,
            "architecture": 2, "language": 0, "bonuses": [], "team_bonuses": [], "custom_bonuses": [],
            "button_moves": [], "free_techs": [], "unit_overrides": []}
    base.update(kw)
    return base


B = lambda *ids: [{"id": i, "multiplier": 1} for i in ids]     # noqa: E731

britons = tree_from("BRITONS.json")
QA = [
    ("britons", civ(
        "QA Elephants", "Elephant",
        share_description="2.6.0 test: elephants, charge, elite cost, UT times, Howdah, hero, Galleon, monk voice.",
        monk_skin=21, language=0,                                # Incas (female) Monk, British (male) voice
        unique_unit={"km_idx": 8, "name": "", "description": "",
                     "advanced_flags": {"charge_pool": 10, "charge_rate": 0.25},
                     "elite_upgrade": {"cost": {"food": 600, "wood": 0, "stone": 0, "gold": 300}, "time": 35}},
        bonuses=B(303, 79, 83, 292, 208, 309, 454),
        castle_ut=ut("QA Castle Tech", "Researches in 30 seconds", [2]),
        imperial_ut=ut("QA Howdah", "Every elephant +1/+1 armor", [5]),
        hero_unit={"base_unit_id": 1966, "name": "QA Hero", "description": "Should train on Castle button 4"},
        # Galleon without its research (35), Gillnets without Fishing Lines (906)
        tree=edit(britons, add_units=(1132, 1134, 873, 875, 1744, 1746, 239, 558, 442),
                  add_buildings=(), add_techs=(65,), drop_techs=(35, 906)),
    )),
    ("franks", civ(
        "QA Mapuche", "Settlement",
        share_description="2.6.0 test: Settlement Spearmen, Imperial Skirmisher team bonus, ranged charge, monk voice, population, resources.",
        monk_skin=1, language=10,                                # Britons (male) Monk, Viking (female) voice
        unique_unit={"km_idx": 9, "name": "", "description": "",
                     "advanced_flags": {"charge_pool": 10, "charge_rate": 0.25}},
        bonuses=B(371),
        team_bonuses=B(35),
        custom_bonuses=[
            card({"type": "civ", "age": 103}, eff("pop_cap", 25)),
            card({"type": "civ"}, eff("resources", 100, resource="stone"), eff("resources", -200, resource="food")),
            card({"type": "civ", "age": 102}, eff("resources", 200, resource="wood")),
            card(unit(12, "Barracks", kind="building"), eff("pop_space", 10)),
            card(unit(84, "Market", kind="building"), eff("pop_space", 10)),
        ],
        tree=edit(britons, add_units=(93, 358, 359, 7, 6), add_buildings=(2556,),
                  drop_buildings=(68, 562, 584), add_techs=(197, 429, 98)),
    )),
    ("goths", civ(
        "QA Siege", "Siege",
        share_description="2.6.0 test: min range, blast radius, conversion, unit lines, stray Huskarl, team-bonus ally.",
        unique_unit={"km_idx": 3, "name": "", "description": ""},
        custom_bonuses=[
            card(unit(280, "Mangonel"), eff("min_range", -1)),
            card(unit(279, "Scorpion"), eff("no_min_range", op="set")),
            card({"type": "group", "id": "siege"}, eff("blast_radius", 0.5)),
            card({"type": "civ"}, eff("convert_time", -1), eff("convert_resist", 4)),
            card(unit(74, "Militia"), eff("melee_attack", 2)),
            card(unit(77, "Long Swordsman", scope="up"), eff("hp", 20)),
            card(unit(283, "Cavalier", scope="up"), eff("melee_armor", 2)),
        ],
        # Elite Skirmishers for the #62 ally test; the Goths' own Huskarl ticked (#66)
        tree=edit(tree_from("GOTHS.json"), add_units=(7, 6, 41, 759, 761, 280, 550, 279, 542, 283, 569),
                  add_techs=(98,)),
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
    cfg.write_text(json.dumps({"mod_name": "QA 2.6.0", "prefix": "qa_2_6_0", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_2_6_0.zip")
    print(f"\nWrote {OUT / 'qa_2_6_0.zip'} and the civ files beside it.")


if __name__ == "__main__":
    main()
