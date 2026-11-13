#!/usr/bin/env python3
"""A replacement with later tiers (feedback on 2.8.0-preview.1).

A player wanted a Heavy Pikeman between the Pikeman and the Halberdier.
Inserting a tier into a vanilla line would mean copying the shared Halberdier
upgrade and taking it from the AI, so instead: replace the Halberdier with a
Heavy Pikeman (the vanilla upgrade 429 stays, a hidden tech after it gives
ours) and give that replacement a later tier of our own, a custom Halberdier.
"Available from" on the replaced unit moves 429 an age earlier, the way the
Armenians' own bonus does.  DAT-gated.

    venv/bin/python tests/test_replacement_tiers.py
"""
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


from civ_schema import from_draft, norm_added_lines, to_draft  # noqa: E402

PIKE, HALB, CAVALIER, PALADIN = 358, 359, 283, 569
HALBERDIER_TECH, CASTLE_AGE, IMPERIAL_AGE = 429, 102, 103
LINES = [
    {"id": 1, "building": 12, "base": PIKE, "replaces": HALB,
     "tiers": [{"age": 3, "name": "Heavy Pikeman", "edits": {"hp": 70}},
               {"age": 4, "name": "Halberdier", "edits": {"attack": 8},
                "upgrade": {"cost": {"food": 300, "gold": 600}, "time": 50}}]},
    # The Cavalier still upgrades into the Paladin: no tier after it.
    {"id": 2, "building": 101, "base": 38, "replaces": CAVALIER,
     "tiers": [{"age": 4, "name": "Lancer"}, {"age": 4}]},
]

print("=== schema ===")
n = norm_added_lines(LINES)
check("a replacement keeps its later tiers", [len(l["tiers"]) for l in n] == [2, 2], n)
check("a later tier keeps its own upgrade", n[0]["tiers"][1].get("upgrade", {}).get("time") == 50, n[0]["tiers"][1])
check("saves and loads", to_draft(from_draft({"added_lines": LINES}))["added_lines"] == n)

try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
civ_file = ROOT / "my_civs" / "19_Cannoneers.json"
if dat_path is None or not civ_file.exists():
    print("  skip  no game DAT (or my_civs/19_Cannoneers.json) found")
    print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
    sys.exit(1 if failures else 0)

from build_civ import _added_line_nodes  # noqa: E402
from civ_overrides import apply_civ_with_overrides  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

print("=== build ===")
SLOT = 1
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]
draft = {
    "alias": "Pikes", "architecture": 2, "language": 0, "bonuses": [], "team_bonuses": [],
    "unique_unit": {"km_idx": 11},
    "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
    "imperial_ut": {"mode": "vanilla", "effects": [{"id": 12, "multiplier": 1}]},
    "tree": {"units": units, "buildings": buildings, "techs": techs},
    "unit_edits": {str(HALB): {"age": 3}},                   # the Halberdier upgrade in Castle
    "tech_edits": {str(HALBERDIER_TECH): {"cost": {"food": 150, "gold": 100}}},
    "added_lines": LINES,
}
dat = load_dat(str(dat_path))
with contextlib.redirect_stdout(io.StringIO()):
    r, _ = apply_civ_with_overrides(dat, _draft_to_civ_def(draft), SLOT, draft)
lines = {l["id"]: l for l in r.get("added_lines") or []}
pk = lines.get(1)
check("the Heavy Pikeman line is built with both tiers", pk and len(pk["units"]) == 2, pk)
if pk:
    heavy, halb = pk["units"]
    h1, rename, up = pk["techs"]
    eff = lambda t: dat.effects[dat.techs[t].effect_id].effect_commands          # noqa: E731
    check("the hidden tech waits on the vanilla Halberdier upgrade",
          HALBERDIER_TECH in dat.techs[h1].required_techs, dat.techs[h1].required_techs)
    check("...and turns Halberdiers into Heavy Pikemen",
          any(c.type == 3 and int(c.a) == HALB and int(c.b) == heavy for c in eff(h1)))
    t = dat.techs[up]
    check("our Halberdier upgrade waits on the hidden tech and the Imperial Age",
          h1 in t.required_techs and IMPERIAL_AGE in t.required_techs and t.required_tech_count == 2,
          (t.required_techs, t.required_tech_count))
    check("...upgrades the Heavy Pikeman into ours",
          any(c.type == 3 and int(c.a) == heavy and int(c.b) == halb for c in eff(up)))
    check("...is civ-owned, researched at the Barracks, on its own button",
          t.civ == SLOT and any(rl.location_id == 12 and rl.button_id == pk["upgrade_button"]
                                for rl in t.research_locations) and pk["upgrade_button"] != pk["button"],
          (t.civ, [(rl.location_id, rl.button_id) for rl in t.research_locations], pk["button"]))
    check("...at its own price", {rc.type: rc.amount for rc in t.resource_costs if rc.amount > 0} == {0: 300, 3: 600},
          [(rc.type, rc.amount) for rc in t.resource_costs])
    us = dat.civs[SLOT].units
    check("both tiers share the Halberdier's train button",
          us[heavy].creatable.train_locations[0].button_id == us[halb].creatable.train_locations[0].button_id
          == pk["button"])
    check("stats carry: the Halberdier keeps the Heavy Pikeman's HP and adds its attack",
          us[heavy].hit_points == 70 and us[halb].hit_points == 70 and us[halb].type_50.displayed_attack == 8,
          (us[heavy].hit_points, us[halb].hit_points, us[halb].type_50.displayed_attack))
    moved = r.get("age_moves") or {}
    check("Available from moves the Halberdier upgrade to the Castle Age",
          any(v == 3 for v in moved.values()), moved)
    scale = [(int(c.b), round(c.d, 3)) for e in dat.effects if e.name == "Tech tree edits"
             for c in e.effect_commands if c.type == 101 and int(c.a) == HALBERDIER_TECH and int(c.c) == 2]
    check("the replaced unit's upgrade takes the price set on the replacement's panel",
          sorted(scale) == [(0, round(150 / 300, 3)), (3, round(100 / 600, 3))], scale)
    nodes = _added_line_nodes(dat, SLOT, [pk])
    check("one F2 node, for the later tier, hung off the vanilla Halberdier node",
          len(nodes) == 1 and nodes[0]["Node ID"] == halb and nodes[0]["Link ID"] == HALB
          and nodes[0]["Trigger Tech ID"] == up, nodes)
cv = lines.get(2)
check("a replaced unit that still upgrades keeps only its first tier, with a warning",
      cv and len(cv["units"]) == 1 and any("can't take more tiers" in w for w in r["warnings"]),
      (cv, r["warnings"]))

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
