#!/usr/bin/env python3
"""The tech tree page's "+ Add Unit" lines (added_lines.py).

Normalizer first (bad buildings, junk bases, ages that don't climb, too many
tiers), then real builds into a fresh DAT: a Spearman-based 3-tier line in the
column the disabled Spearman line left, a 2-tier Knight line, and what each
mechanism has to get right — every civ gets the units (ids line up) but only
ours can train them, the tiers share one button (quirk 3), upgrades sit one row
below, stats never fall back with an upgrade, the vanilla role upgrade also
upgrades the line (the AI's way up), cards naming the role's units reach the
line once each, the F2 nodes and the AI's unit line.  DAT-gated.

    venv/bin/python tests/test_added_lines.py
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

print("=== normalizer ===")
raw = [
    {"id": 1, "building": 12, "base": 93, "role": -295,
     "tiers": [{"age": 2, "name": " Guard\n", "edits": {"hp": 70, "name": "ignored"}},
               {"age": 3, "upgrade": {"cost": {"food": -5, "gold": "50"}, "time": 30}},
               {"age": 3},                                # not later: dropped
               {"age": 4}, {"age": 4}]},
    {"id": 1, "building": 12, "base": 93, "tiers": [{"age": 2}]},       # duplicate id
    {"id": 2, "building": 82, "base": 4, "tiers": [{"age": 2}]},        # the Castle: UU step
    {"id": 3, "building": 87, "base": "lizard", "tiers": [{"age": 2}]},
    {"id": 4, "building": 87, "base": 4, "tiers": []},
    {"id": 5, "building": 87, "base": 4, "role": 7, "tiers": [{"age": 9}, {"age": 1}]},
    "junk", None,
]
n = norm_added_lines(raw)
check("only valid lines survive", [l["id"] for l in n] == [1, 5], [l["id"] for l in n])
t = n[0]["tiers"]
check("ages must climb, at most 4 tiers", [x["age"] for x in t] == [2, 3, 4], t)
check("names cleaned; edits keep stats, not names",
      t[0]["name"] == "Guard" and t[0]["edits"] == {"hp": 70}, t[0])
check("tier 1 has no upgrade; costs clamp", "upgrade" not in t[0]
      and t[1]["upgrade"] == {"cost": {"food": 0, "wood": 0, "stone": 0, "gold": 50}, "time": 30}, t[1])
check("a role outside unitlines' range is dropped; age 9 clamps to Imperial",
      n[1]["role"] is None and [x["age"] for x in n[1]["tiers"]] == [4], n[1])
check("saves and loads", to_draft(from_draft({"added_lines": raw}))["added_lines"] == n)

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

import added_lines  # noqa: E402
from build_civ import _added_line_nodes  # noqa: E402
from civ_overrides import apply_civ_with_overrides  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

SLOT, OTHER = 1, 5
SPEAR, PIKE, HALB, KNIGHT = 93, 358, 359, 38
PIKEMAN_TECH, HALBERDIER_TECH, CAVALIER_TECH, SAVAR_TECH = 197, 429, 209, 526
SAVAR = 1813
HERO = 160                     # Richard the Lionheart (creatable.hero_mode 1)
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]
draft = {
    "alias": "Added", "architecture": 2, "language": 0,
    "bonuses": [{"id": 233, "multiplier": 1}, {"id": 101, "multiplier": 1}],   # Spearmen +25% HP, +10% speed
    # A card on one added line only: +7 HP to the Knight line we add (id 2).
    "custom_bonuses": [{"targets": [{"type": "line", "id": 2, "name": "Knight"}],
                        "effects": [{"attr": "hp", "op": "add", "value": 7}]}],
    "team_bonuses": [], "unique_unit": {"km_idx": 11},
    "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
    "imperial_ut": {"mode": "vanilla", "effects": [{"id": 12, "multiplier": 1}]},
    "tree": {"units": [u for u in units if u not in (SPEAR, PIKE, HALB)], "buildings": buildings,
             "techs": techs},
    "added_lines": [
        {"id": 1, "building": 12, "base": SPEAR,
         "tiers": [{"age": 2, "name": "Guard", "edits": {"hp": 70}},
                   {"age": 3, "upgrade": {"cost": {"food": 100, "gold": 50}, "time": 30}},
                   {"age": 4, "edits": {"attack": 9}}]},
        {"id": 2, "building": 101, "base": KNIGHT, "appearance": SAVAR,
         "description": 'Holy "warriors".', "tiers": [{"age": 3}, {"age": 4}]},
        # A hero as a base: trains like any unit, without hero status.
        {"id": 3, "building": 12, "base": HERO, "tiers": [{"age": 3}]},
    ],
}
dat = load_dat(str(dat_path))
units_before = len(dat.civs[0].units)
out = io.StringIO()
with contextlib.redirect_stdout(out):
    r, _ = apply_civ_with_overrides(dat, _draft_to_civ_def(draft), SLOT, draft)
lines = r.get("added_lines") or []
check("all three lines built", [l["id"] for l in lines] == [1, 2, 3], (lines, r["warnings"]))
guard, knights, hero = lines[0], lines[1], lines[2]
ids = guard["units"]
U = dat.civs[SLOT].units

print("\n=== units ===")
check("one new unit per tier, in every civ (ids line up)",
      ids == [units_before, units_before + 1, units_before + 2]
      and all(len(c.units) == len(dat.civs[0].units) for c in dat.civs), ids)
check("other civs have the units but nothing enables them",
      dat.civs[OTHER].units[ids[0]].enabled == 0
      and not any(t.civ == OTHER for tid in guard["techs"] for t in [dat.techs[tid]]))
check("copies of the base, under their own id",
      all(U[i].class_ == U[SPEAR].class_ and U[i].base_id == i == U[i].id for i in ids))
check("names default from tier 1's", guard["names"] == ["Guard", "Veteran Guard", "Elite Guard"]
      and knights["names"] == ["Knight", "Elite Knight"], (guard["names"], knights["names"]))
btn = guard["button"]
check("the column the disabled Spearman line left (button 2), all tiers on it",
      btn == 2 and all([(t.unit_id, t.button_id) for t in U[i].creatable.train_locations] == [(12, 2)] for i in ids),
      [[(t.unit_id, t.button_id) for t in U[i].creatable.train_locations] for i in ids])
check("a stat edit carries to later tiers; a later tier's own stands",
      [U[i].hit_points for i in ids] == [70, 70, 70]
      and U[ids[2]].type_50.displayed_attack == 9 and U[ids[0]].type_50.displayed_attack != 9,
      ([U[i].hit_points for i in ids], [U[i].type_50.displayed_attack for i in ids]))

print("\n=== techs ===")
avail, up2, up3 = (dat.techs[t] for t in guard["techs"])
check("tier 1 made available at Feudal, for this civ only",
      avail.civ == SLOT and list(avail.required_techs)[:1] == [101]
      and [(c.type, int(c.a), c.b) for c in dat.effects[avail.effect_id].effect_commands] == [(2, ids[0], 1)])
check("upgrades: own button one row below, after the age and the tier before",
      [(rl.location_id, rl.button_id) for rl in up2.research_locations] == [(12, btn + 5)]
      and list(up2.required_techs)[:2] == [102, guard["techs"][0]] and up2.required_tech_count == 2
      and list(up3.required_techs)[:2] == [103, guard["techs"][1]],
      ([(rl.location_id, rl.button_id) for rl in up2.research_locations], list(up2.required_techs)))
check("an edited upgrade cost and time are used",
      {(c.type, c.amount) for c in up2.resource_costs if c.amount} == {(0, 100), (3, 50)}
      and up2.research_locations[0].research_time == 30)
halb = dat.techs[HALBERDIER_TECH]
check("an unedited upgrade defaults to the role's vanilla upgrade (Halberdier)",
      {(c.type, c.amount) for c in up3.resource_costs if c.amount}
      == {(c.type, c.amount) for c in halb.resource_costs if c.amount}
      and up3.icon_id == halb.icon_id)
check("upgrades are EC_UPGRADE from the tier before",
      [(c.type, int(c.a), int(c.b)) for c in dat.effects[up3.effect_id].effect_commands] == [(3, ids[1], ids[2])])

print("\n=== buttons ===")
check("never the fifth column (the building's commands: rally point)",
      all(l["button"] not in (5, 10, 25, 30) and l.get("upgrade_button") not in (5, 10, 25, 30) for l in lines),
      [(l["button"], l.get("upgrade_button")) for l in lines])
check("the Stable's line takes column 3 when the civ has no camels (opt-in techs don't hold a column)",
      (1755 in units or 329 in units) or knights["button"] == 3, knights["button"])
check("an upgrade sits below its unit, never in a page's top row (the units' row)",
      all(l.get("upgrade_button") is None or (l["upgrade_button"] - 1) % 20 >= 5 for l in lines)
      and ((1755 in units or 329 in units) or knights["upgrade_button"] == knights["button"] + 5),
      [(l["button"], l.get("upgrade_button")) for l in lines])
check("an upgrade into a unit the civ lacks (Heavy Camel) holds no slot",
      added_lines._upgrades_into_absent(dat, dat.techs[236], {KNIGHT})
      and not added_lines._upgrades_into_absent(dat, dat.techs[CAVALIER_TECH], {KNIGHT}))
sav = dat.techs[knights["techs"][1]]
check("an upgrade wears the icon of the upgrade into its look (Savar)",
      sav.icon_id == dat.techs[SAVAR_TECH].icon_id, (sav.icon_id, dat.techs[SAVAR_TECH].icon_id))

print("\n=== heroes ===")
h = U[hero["units"][0]]
check("a hero's copy loses hero status; the hero keeps it",
      dat.civs[SLOT].units[HERO].creatable.hero_mode and h.creatable.hero_mode == 0,
      (dat.civs[SLOT].units[HERO].creatable.hero_mode, h.creatable.hero_mode))
check("and trains at the building like any unit",
      [(t.unit_id, t.button_id) for t in h.creatable.train_locations] == [(12, hero["button"])])

print("\n=== the AI ===")
check("role defaults to the base's line (spearman-line)", guard["role"] == -295 and knights["role"] == -287,
      (guard["role"], knights["role"]))
ours = set(ids) | set(knights["units"])
touched = [(t, c.type, int(c.a)) for t in (PIKEMAN_TECH, HALBERDIER_TECH, CAVALIER_TECH)
           for c in dat.effects[dat.techs[t].effect_id].effect_commands
           if int(c.a) in ours or (c.type == 102 and int(c.d) in guard["techs"] + knights["techs"])]
check("vanilla upgrades leave the added lines alone (in game: Pikeman upgrading Guards confused)",
      not touched, touched)
lines_doc = [{"LineID": -295, "IDChain": [SPEAR, PIKE, HALB]}, {"LineID": -287, "IDChain": [KNIGHT, 283, 569]}]
n_joined = added_lines.patch_unitline_roles(lines_doc, {SLOT: {"added_lines": lines}})
check("the units join their AI lines in unitlines.json",
      n_joined == 5 and lines_doc[0]["IDChain"] == [SPEAR, PIKE, HALB] + ids, lines_doc)

print("\n=== cards naming the role's units ===")
hp = [(int(c.a), c.d) for e in dat.effects for c in e.effect_commands
      if c.type == 5 and c.c == 0 and abs(c.d - 1.25) < 1e-6 and int(c.a) in ids + [SPEAR]]
check("Spearmen +25% HP reaches every tier, exactly once each",
      sorted(a for a, _ in hp) == sorted([SPEAR] + ids), hp)
names = [c for e in dat.effects for c in e.effect_commands if int(c.a) in ids and c.c == 50]
check("never a name command", not names)

import custom_bonus  # noqa: E402
card = custom_bonus.normalize(draft["custom_bonuses"])[0]
plus7 = {int(c.a) for e in dat.effects for c in e.effect_commands if c.type == 4 and c.c == 0 and c.d == 7}
check("a card can target one added line, and only it", plus7 == set(knights["units"]), plus7)
check("its text names the line", "Knight line" in custom_bonus.card_text(card), custom_bonus.card_text(card))
check("and it can't be a team bonus", custom_bonus.team_problem(card) is not None)

print("\n=== F2 tree and strings ===")
nodes = _added_line_nodes(dat, SLOT, lines)
g = [nd for nd in nodes if nd["Node ID"] in ids]
check("a node per tier: building, then each off the one before",
      [(nd["Node Type"], nd["Link Node Type"], nd.get("Link ID"), nd["Age ID"], nd["Building ID"]) for nd in g]
      == [("Unit", "BuildingTech", None, 2, 12), ("UnitUpgrade", "Unit", ids[0], 3, 12),
          ("UnitUpgrade", "UnitUpgrade", ids[1], 4, 12)], g)
check("nodes named from the tiers' string ids and triggered by their techs",
      [nd["Name String ID"] for nd in g] == guard["sids"] and [nd["Trigger Tech ID"] for nd in g] == guard["techs"])
us = {e["sid"]: e for e in r["bonus_results"]["extra_unit_strings"]}
ts = {e["sid"]: e for e in r["bonus_results"]["extra_tech_strings"]}
k = us.get(guard["sids"][0], {})
check("unit tooltip is the base's own, renamed, minus its Upgrades line",
      k.get("ext_text", "").startswith("Create <b>Guard<b> (<cost>)") and "<hp>" in k.get("ext_text", "")
      and "<GREY>" not in k.get("ext_text", ""), k.get("ext_text"))
kk = us.get(knights["sids"][0], {})
check("the line's own description replaces the base's, quotes escaped",
      'Holy \\"warriors\\".' in kk.get("ext_text", "") and "Heavy Cavalry" not in kk.get("ext_text", ""),
      kk.get("ext_text"))
check("upgrade button label and hover", ts.get(guard["tech_sids"][0], {}).get("label") == "Upgrade to Veteran Guard"
      and "(<cost>)" in ts.get(guard["tech_sids"][0], {}).get("hover", ""), ts.get(guard["tech_sids"][0]))

print("\n=== a line whose building is off ===")
dat3 = load_dat(str(dat_path))
no_stable = dict(draft, tree=dict(draft["tree"], buildings=[b for b in buildings if b != 101]))
with contextlib.redirect_stdout(io.StringIO()):
    r3, _ = apply_civ_with_overrides(dat3, _draft_to_civ_def(no_stable), SLOT, no_stable)
check("is not built (the page hides it too)", [l["id"] for l in r3["added_lines"]] == [1, 3],
      [l["id"] for l in r3["added_lines"]])

print("\n=== two civs in one build ===")
dat2 = load_dat(str(dat_path))
with contextlib.redirect_stdout(io.StringIO()):
    r1, _ = apply_civ_with_overrides(dat2, _draft_to_civ_def(draft), SLOT, draft)
    r2, _ = apply_civ_with_overrides(dat2, _draft_to_civ_def(draft), OTHER, draft)
a, b = r1["added_lines"][0]["units"], r2["added_lines"][0]["units"]
check("each civ gets its own units, every civ's list the same length",
      not set(a) & set(b) and len({len(c.units) for c in dat2.civs}) == 1, (a, b))
check("each civ's string ids are its own", not set(r1["added_lines"][0]["sids"]) & set(r2["added_lines"][0]["sids"]))

print("\n=== the picker's catalog ===")
from civ_appender import _string_table  # noqa: E402
names, chron = _string_table(), added_lines.chronicles_strings()
cat = {r["id"]: r for r in added_lines.unit_catalog(
    dat2, dat_path, lambda u: names.get(u.language_dll_name) or chron.get(u.language_dll_name))}
group = lambda uid: (cat.get(uid) or {}).get("group")      # noqa: E731
check("standard / regional / unique / chronicles / scenario / hero",
      (group(KNIGHT), group(1132), group(SAVAR), group(2110), group(299), group(HERO))
      == ("standard", "regional", "unique", "chronicles", "scenario", "hero"),
      (group(KNIGHT), group(1132), group(SAVAR), group(2110), group(299), group(HERO)))
check("a unit no civ's tree has is still offered (War Dog, Ninja: scenario)",
      group(2612) == "scenario" and group(1145) == "scenario", (group(2612), group(1145)))
check("Chronicles units are named from the game's own strings", (cat.get(2110) or {}).get("name") == "Hoplite")
check("military only: no Villager, no Trade Cart, no animals",
      not ({83, 128, 594} & set(cat)), sorted({83, 128, 594} & set(cat)))
check("one per name", len({r["name"].casefold() for r in cat.values()}) == len(cat))

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
