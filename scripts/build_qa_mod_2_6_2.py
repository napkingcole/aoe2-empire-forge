#!/usr/bin/env python3
"""One test mod for everything unreleased since v2.6.1 that needs the game
(see ignore/qa_2_6_2/CHECKLIST.md).  Built through build_all like any mod.

  QA Horde    (over Franks)   Mangudai + Anarchy + Perfusion + mounted +20% HP
                              (stats-preview checks), Longship tree node with
                              the Demolition line kept, Mesoamerican castle
  QA Gates    (over Poles)    gated cards (age / growing / once built, Folwark
                              as the Mill), cards 247 and 221, Thracian 458/459,
                              Thalassocracy, Timurid Siegecraft on a melee UU,
                              the FRANKISH castle asked for after QA Horde took
                              the Franks' slot (build order), custom team card
  QA Library  (over Goths)    custom Castle UT made of library cards, Flemish
                              Revolution, a multi-target card, a start-resources
                              card, an OLD save's card 51 (Longship, no demo)

    venv/bin/python scripts/build_qa_mod_2_6_2.py     # writes ignore/qa_2_6_2/qa_2_6_2.zip
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_all                                            # noqa: E402
import dat_reader                                           # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402

OUT = ROOT / "ignore" / "qa_2_6_2"


def tree_from(civ_file: str) -> dict:
    data = json.loads((dat_reader.find_civtechtrees(dat_reader.find_game_dat()) / civ_file).read_text(encoding="utf-8"))
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


def preset(idx, tier):
    """A vanilla UT preset (build_all._UNIQUE_*_STRINGS index)."""
    return {"mode": "vanilla", "vanilla_km_idx": idx, "name": "", "description": "",
            "effects": [{"id": idx, "multiplier": 1, "tier": tier}]}


def card(targets, effects, when=None, text=""):
    c = {"targets": targets if isinstance(targets, list) else [targets], "effects": effects}
    if when:
        c["when"] = when
    if text:
        c["text"] = text
    return c


G = lambda gid: {"type": "group", "id": gid}                                   # noqa: E731
UNIT = lambda uid, name: {"type": "unit", "id": uid, "name": name, "kind": "unit"}  # noqa: E731
BLD = lambda uid, name: {"type": "unit", "id": uid, "name": name, "kind": "building"}  # noqa: E731
CIV = {"type": "civ", "id": "civ"}
B = lambda *ids: [{"id": i, "multiplier": 1} for i in ids]                   # noqa: E731


def civ(alias, tagline, **kw):
    base = {"format": FORMAT_KEY, "schema_version": 2, "alias": alias, "tagline": tagline,
            "architecture": 2, "language": 0, "bonuses": [], "team_bonuses": [], "custom_bonuses": [],
            "custom_team_bonuses": [], "button_moves": [], "free_techs": [], "unit_overrides": [],
            "castle": -1, "wonder": -1}
    base.update(kw)
    return base


STABLE = (448, 546, 441, 38, 283, 569, 39, 474)
LONGSHIP, DEMO = (250, 533), (1104, 527, 528)

QA = [
    ("franks", civ(
        "QA Horde", "Horde",
        share_description="2.6.2 test: stats preview (Mangudai, Anarchy, Perfusion), Longship node + demo, Mesoamerican castle.",
        architecture=5,                                            # Mesoamerican: its castle is unmistakable
        unique_unit={"km_idx": 11, "name": "", "description": ""},  # Mangudai
        castle_ut=preset(12, "castle"),                            # Anarchy
        imperial_ut=preset(12, "imperial"),                        # Perfusion
        bonuses=B(4),                                              # mounted units +20% HP from Feudal
        tree=edit(tree_from("MONGOLS.json"), add_units=STABLE + LONGSHIP + DEMO,
                  add_techs=(435, 39)),
    )),
    ("poles", civ(
        "QA Gates", "Gates",
        share_description="2.6.2 test: gated cards, Folwark Mill trigger, cards 247/221, Thracian 458/459, Thalassocracy, Siegecraft, Frankish castle.",
        castle=1, wonder=1,                                        # the FRANKS' castle and wonder (KM index 1)
        unique_unit={"km_idx": 3, "name": "", "description": ""},  # Teutonic Knight (melee)
        castle_ut=preset(22, "castle"),                            # Thalassocracy: Docks -> Harbors
        imperial_ut=preset(32, "imperial"),                        # Timurid Siegecraft: trebuchets +2 range
        # 459 at x4 (+60%) so the aura is unmistakable in a gather test
        bonuses=B(247, 221, 458) + [{"id": 459, "multiplier": 4}],
        custom_bonuses=[
            card(UNIT(74, "Militia"), [{"attr": "hp", "op": "add", "steps": {"101": 5, "102": 10, "103": 15}}],
                 when={"steps": True}),
            card(G("archers"), [{"attr": "hp", "op": "mul", "value": 15}], when={"age": 102}),
            card({"type": "tech", "id": 22, "name": "Loom"}, [{"attr": "free", "op": "set"}],
                 when={"building": 68, "building_name": "Mill"}),
            card(CIV, [{"attr": "resources", "op": "add", "value": 200, "resource": "wood"}],
                 when={"building": 562, "building_name": "Lumber Camp"}),
        ],
        custom_team_bonuses=[
            card([G("cavalry"), G("cavalry_archers")], [{"attr": "los", "op": "add", "value": 2}]),
        ],
        tree=edit(tree_from("POLES.json"), add_units=(7, 6, 4, 24, 492, 93, 358, 359, 331, 42),
                  add_techs=(436, 437)),
    )),
    ("goths", civ(
        "QA Library", "Library",
        share_description="2.6.2 test: library cards in a Castle UT, Flemish Revolution, multi-target card, start stone, old card 51.",
        unique_unit={"km_idx": 49, "name": "", "description": ""},  # Amazon Archer (KM-custom UU)
        castle_ut={"mode": "custom", "vanilla_km_idx": None, "name": "QA Smithy", "description": "Blacksmith techs -20% cost",
                   "cost": {"food": 200, "wood": 0, "stone": 0, "gold": 200}, "time": 30, "effects": [],
                   "custom_bonuses": [card([G("techs_blacksmith")], [{"attr": "tech_cost", "op": "mul", "value": -20}])]},
        imperial_ut=preset(4, "imperial"),                         # Flemish Revolution
        bonuses=B(51),                                             # an OLD save's Longboats card
        custom_bonuses=[
            card([G("archers"), BLD(82, "Castle")], [{"attr": "range", "op": "add", "value": 1}]),
            card(CIV, [{"attr": "resources", "op": "add", "value": 100, "resource": "stone"}]),
        ],
        tree=edit(tree_from("GOTHS.json"), add_units=DEMO + (4, 24, 492, 545, 539, 21, 442)),
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
    cfg.write_text(json.dumps({"mod_name": "QA 2.6.2", "prefix": "qa_2_6_2", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_2_6_2.zip")
    print(f"\nWrote {OUT / 'qa_2_6_2.zip'} and the civ files beside it.")


if __name__ == "__main__":
    main()
