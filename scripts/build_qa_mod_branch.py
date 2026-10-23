#!/usr/bin/env python3
"""One test mod for everything on fix/issues-78-80-81-86 that needs the game
(see ignore/qa_branch/CHECKLIST.md).  Built through build_all like any mod.

  QA Range     (over Britons)  Fire Archer wearing the Chu Ko Nu's look, moved to
                               the Archery Range by Ambuscade (#81); eco bonus 105
                               (#80: Crop Rotation, Caravan); -50% accuracy on
                               archers (#86); William Wallace as hero (new heroes)
  QA Bandits   (over Franks)   Bandit (scenario UU, 100 food — the fixed "full"
                               cost path, so population) wearing the Teutonic
                               Knight's look; generated Elite
  QA Qizilbash (over Goths)    Qizilbash Warrior: its real Elite, the 800/700
                               Elite upgrade, its icon in the civ picker (#55)

Also writes QA_Retired.civbuilder.json — not in the mod: open it in the wizard
for the retired-cards notice (#78) and a retired UU.  Expected numbers are read
from the same build code on the same DAT (expected.json).

    venv/bin/python scripts/build_qa_mod_branch.py     # writes ignore/qa_branch/
"""
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_all                                            # noqa: E402
import dat_reader                                           # noqa: E402
from civ_schema import FORMAT_KEY, to_draft                 # noqa: E402
from dat_reader import find_game_dat, load_dat              # noqa: E402

OUT = ROOT / "ignore" / "qa_branch"
CHU_KO_NU, TEUTONIC_KNIGHT, WALLACE = 73, 25, 432


def tree_from(civ_file: str) -> dict:
    data = json.loads((dat_reader.find_civtechtrees(find_game_dat()) / civ_file).read_text(encoding="utf-8"))
    out = {"units": [], "buildings": [], "techs": []}
    for sec in ("civ_techs_units", "civ_techs_buildings"):
        for n in data[sec]:
            key = {"Unit": "units", "Building": "buildings", "Tech": "techs"}.get(n.get("Use Type"))
            if key and n.get("Node Status") != "NotAvailable" and n["Node ID"] not in out[key]:
                out[key].append(n["Node ID"])
    return out


def preset(idx, tier):
    return {"mode": "vanilla", "vanilla_km_idx": idx, "name": "", "description": "",
            "effects": [{"id": idx, "multiplier": 1, "tier": tier}]}


def civ(alias, tagline, **kw):
    base = {"format": FORMAT_KEY, "schema_version": 2, "alias": alias, "tagline": tagline,
            "architecture": 2, "language": 0, "bonuses": [], "team_bonuses": [], "custom_bonuses": [],
            "custom_team_bonuses": [], "button_moves": [], "free_techs": [], "unit_overrides": [],
            "castle": -1, "wonder": -1}
    base.update(kw)
    return base


B = lambda *ids: [{"id": i, "multiplier": 1} for i in ids]                   # noqa: E731

QA = [
    ("britons", civ(
        "QA Range", "Range",
        share_description="Branch test: Ambuscade, Fire Archer in Chu Ko Nu's look, eco 105, -50% archer accuracy, William Wallace.",
        unique_unit={"km_idx": 84, "name": "", "description": "", "appearance": CHU_KO_NU},  # Fire Archer
        castle_ut=preset(68, "castle"),                            # Ambuscade
        imperial_ut=preset(0, "imperial"),                         # Garland Wars (anything)
        bonuses=B(105),
        # -50 (not +30) so misses are obvious: +30 only topped archers up to
        # 100%, which the user couldn't judge by eye (round 1, 2026-10-23).
        custom_bonuses=[{"targets": [{"type": "group", "id": "archers"}],
                         "effects": [{"attr": "accuracy", "op": "add", "value": -50}]}],
        hero_unit={"base_unit_id": WALLACE, "name": "William Wallace", "description": "", "overrides": {}, "flags": {}},
        # The Britons don't get Crop Rotation in current DE (their tree marks it
        # NotAvailable), so the first QA round never saw it at all: add it.
        tree={**tree_from("BRITONS.json"),
              "techs": tree_from("BRITONS.json")["techs"] + [12]},
    )),
    ("franks", civ(
        "QA Bandits", "Bandits",
        share_description="Branch test: Bandit (100 food, population) in the Teutonic Knight's look, generated Elite.",
        unique_unit={"km_idx": 110, "name": "", "description": "", "appearance": TEUTONIC_KNIGHT},
        castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree_from("FRANKS.json"),
    )),
    ("goths", civ(
        "QA Qizilbash", "Qizilbash",
        share_description="Branch test: Qizilbash Warrior, its real Elite, the 800 food / 700 gold upgrade, civ picker icon.",
        unique_unit={"km_idx": 103, "name": "", "description": ""},
        castle_ut=preset(12, "castle"), imperial_ut=preset(0, "imperial"),
        tree=tree_from("GOTHS.json"),
    )),
]

RETIRED = civ(                                              # opened in the wizard, not built
    "QA Retired", "Retired",
    share_description="Branch test (wizard only): retired cards 245 and 324, and the retired Hetaireia UU.",
    unique_unit={"km_idx": 51, "name": "", "description": ""},
    bonuses=B(245, 324, 4),
    tree=tree_from("GOTHS.json"),
)


def expected(dat_path: Path) -> dict:
    """The numbers to look for, from apply_civ on a fresh copy of the DAT —
    the same code the mod was built with."""
    from civ_appender import apply_civ
    from wizard_build import _draft_to_civ_def
    import fu_stats                                         # noqa: F401  (keeps the stats code honest)
    res = {0: "food", 1: "wood", 2: "stone", 3: "gold"}

    def cost(costs):
        return {res[c.type]: int(c.amount) for c in costs if c.type in res and c.amount > 0}

    def pop(costs):
        return int(sum(c.amount for c in costs if c.type == 4))

    out = {}
    for slot, (_, c) in zip((1, 2, 3), QA):
        dat = load_dat(str(dat_path))
        with contextlib.redirect_stdout(io.StringIO()):
            r = apply_civ(dat, _draft_to_civ_def(to_draft(c)), target_slot=slot)
        units = dat.civs[r["civ_index"]].units

        def unit(uid):
            u = units[uid]
            return {"hp": u.hit_points, "attack": u.type_50.displayed_attack,
                    "melee_armor": u.type_50.displayed_melee_armour,
                    "pierce_armor": u.creatable.displayed_pierce_armour,
                    "range": u.type_50.max_range, "reload": round(u.type_50.reload_time, 2),
                    "speed": round(u.speed, 2), "accuracy": u.type_50.accuracy_percent,
                    "cost": cost(u.creatable.resource_costs), "population": pop(u.creatable.resource_costs),
                    "standing_graphic": u.standing_graphic[0]}

        def tech(tid):
            t = dat.techs[tid]
            return {"cost": cost(t.resource_costs),
                    "time": next((loc.research_time for loc in t.research_locations if loc.location_id >= 0), None)}

        e = {"uu": unit(r["uu_id"]), "elite": unit(r["elite_uu_id"]),
             "elite_upgrade": tech(r["km_uu_elite_tech_id"]) if r.get("km_uu_elite_tech_id", -1) >= 0 else None,
             "castle_ut": tech(r["castle_ut_tech_id"])}
        if c["alias"] == "QA Range":
            e["crop_rotation"] = tech(12)
            e["caravan"] = tech(48)
            e["accuracy"] = {n: units[i].type_50.accuracy_percent for i, n in
                             ((4, "Archer"), (24, "Crossbowman"), (492, "Arbalester"))}
            e["look_source"] = {"chu_ko_nu_standing_graphic": dat.civs[0].units[CHU_KO_NU].standing_graphic[0]}
            h = units[WALLACE]
            e["hero"] = {"hp": h.hit_points, "cost": cost(h.creatable.resource_costs),
                         "train_buttons": [(t.unit_id, t.button_id) for t in h.creatable.train_locations]}
        if c["alias"] == "QA Bandits":
            e["look_source"] = {"teutonic_knight_standing_graphic": dat.civs[0].units[TEUTONIC_KNIGHT].standing_graphic[0]}
        out[c["alias"]] = e
    return out


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
    (OUT / "QA_Retired.civbuilder.json").write_text(json.dumps(RETIRED, indent=2) + "\n", encoding="utf-8")
    cfg = OUT / "qa_mod_config.json"
    cfg.write_text(json.dumps({"mod_name": "QA Branch", "prefix": "qa_branch", "civs": entries}, indent=2),
                   encoding="utf-8")
    build_all.build_mod(cfg, Path(dat_path), OUT / "qa_branch.zip")
    exp = expected(Path(dat_path))
    (OUT / "expected.json").write_text(json.dumps(exp, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT / 'qa_branch.zip'}, the civ files and expected.json.")


if __name__ == "__main__":
    main()
