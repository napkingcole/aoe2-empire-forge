#!/usr/bin/env python3
"""Tech-tree side panel edits: unit_edits and tech_edits (civ_overrides).

Normalizer first (the QA engineer's bar: 0, -1, huge, a lizard), then a real
build into a fresh DAT pinning each mechanism: cost and train time flow down
the upgrade line, stats stay per tier, every form of a unit is written (all
villagers, a building's age variants, both Trebuchet forms), bonus damage adds
and removes attack classes, and tech edits become multiply ghosts in one
civ-owned tech.  DAT-gated.

    venv/bin/python tests/test_tree_edits.py
"""
import contextlib
import copy
import io
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


from civ_schema import FORMAT_KEY, from_draft, norm_tech_edits, norm_unit_edits, to_draft  # noqa: E402

print("=== normalizer ===")
n = norm_unit_edits({
    "38":     {"hp": 0, "attack": -1, "melee": 99999999999, "range": "lizard",
               "reload": float("nan"), "cost": {"food": -5, "gold": "60", "wood": None},
               "bonus": {"15": 5, "4": 99, "x": 3, "8": -2}},
    "-3":     {"hp": 10},
    "lizard": {"hp": 10},
    "74":     "not a dict",
    "93":     {},
})
k = n.get("38", {})
check("hp 0 clamps to 1", k.get("hp") == 1, k.get("hp"))
check("negative attack clamps to 0", k.get("attack") == 0, k.get("attack"))
check("99999999999 armour clamps to the 16-bit field", k.get("melee") == 32767, k.get("melee"))
check("negative armour is allowed (the Dark Age House has -2)",
      norm_unit_edits({"70": {"melee": -2}}) == {"70": {"melee": -2}})
check("a lizard and NaN are dropped, not guessed", "range" not in k and "reload" not in k, k)
check("cost: negatives and None read as 0, strings as numbers",
      k.get("cost") == {"food": 0, "wood": 0, "stone": 0, "gold": 60}, k.get("cost"))
check("bonus: class 4 (the unit's own attack) and junk dropped; negative is 0 (remove)",
      k.get("bonus") == {"15": 5, "8": 0}, k.get("bonus"))
check("negative / non-numeric / non-dict / empty entries dropped", set(n) == {"38"}, sorted(n))
t = norm_tech_edits({"265": {"cost": {"food": 100, "gold": 0}, "time": -4}, "x": {"time": 5}})
check("tech edit: cost kept, negative time clamps to 0",
      t == {"265": {"cost": {"food": 100, "wood": 0, "stone": 0, "gold": 0}, "time": 0}}, t)
round_trip = to_draft(from_draft({"unit_edits": {"38": {"hp": 150}}, "tech_edits": {"265": {"time": 30}}}))
check("unit_edits and tech_edits survive save and load",
      round_trip["unit_edits"] == {"38": {"hp": 150}} and round_trip["tech_edits"] == {"265": {"time": 30}},
      (round_trip.get("unit_edits"), round_trip.get("tech_edits")))

print("\n=== cost flow down a line ===")
from civ_overrides import _flow_down                                   # noqa: E402
# The Paladin tech upgrades both the Knight and the Cavalier to Paladin.
LINE = {38: {283, 569}, 283: {569, 1813}}
check("Knight's cost reaches Cavalier, Paladin and Savar",
      _flow_down(LINE, {38: "k"}) == {38: "k", 283: "k", 569: "k", 1813: "k"})
check("with the Cavalier edited too, the Paladin takes the Cavalier's (latest, not nearest)",
      _flow_down(LINE, {38: "k", 283: "c"}) == {38: "k", 283: "c", 569: "c", 1813: "c"},
      _flow_down(LINE, {38: "k", 283: "c"}))
check("a later tier's own edit wins", _flow_down(LINE, {38: "k", 569: "p"})[569] == "p")
check("nothing flows upward", 38 not in _flow_down(LINE, {283: "c"}))

try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
if dat_path is None:
    print("  skip  no game DAT found")
    print()
    print("FAIL" if failures else "PASS", f"({failures} failure(s))")
    sys.exit(1 if failures else 0)

from civ_overrides import apply_civ_with_overrides, unit_forms  # noqa: E402
from wizard_build import _draft_to_civ_def                       # noqa: E402

dat = load_dat(str(dat_path))
SLOT = next(i for i, c in enumerate(dat.civs) if c.name == "Goths")
KNIGHT, CAVALIER, PALADIN = 38, 283, 569
VILLAGER, VILLAGER_F, BUILDER = 83, 293, 118
BARRACKS, BARRACKS_F, BARRACKS_C, BARRACKS_I = 12, 498, 132, 20
TREB_PACKED, TREB = 331, 42
PALADIN_TECH = 265
ARCHERS = 15
before = {u: copy.deepcopy(dat.civs[SLOT].units[u]) for u in (TREB_PACKED, TREB)}

tree = {"units": [74, 75, 77, 473, 567, 4, 24, 492, KNIGHT, CAVALIER, PALADIN, 448, 546, 441, 331, 83],
        "buildings": [12, 87, 101, 82, 109, 70, 68, 562, 584],
        "techs": [222, 207, 217, 264, 100, 237, 209, PALADIN_TECH, 254, 428, 22, 101, 102, 103]}
draft = to_draft({
    "format": FORMAT_KEY, "alias": "Tree Edits", "architecture": 2, "language": 0,
    "bonuses": [], "unique_unit": {"km_idx": 3},
    "castle_ut": {"mode": "vanilla", "effects": [{"id": 0, "multiplier": 1}]},
    "imperial_ut": {"mode": "vanilla", "effects": [{"id": 0, "multiplier": 1}]},
    "tree": tree,
    "unit_edits": {
        str(KNIGHT):    {"hp": 150, "cost": {"wood": 70, "gold": 50}, "train": 20,
                         "bonus": {str(ARCHERS): 6}},
        str(PALADIN):   {"cost": {"food": 100}},
        str(VILLAGER):  {"hp": 40, "melee": 2},
        str(BARRACKS):  {"hp": 2000},
        str(TREB_PACKED): {"hp": 300, "attack": 999},
    },
    "tech_edits": {
        str(PALADIN_TECH): {"cost": {"food": 100, "gold": 0, "stone": 50}, "time": 85},
    },
})
civ_def = _draft_to_civ_def(draft)
n_effects, n_techs = len(dat.effects), len(dat.techs)
with contextlib.redirect_stdout(io.StringIO()):
    result, _ = apply_civ_with_overrides(dat, civ_def, SLOT, draft)
units = dat.civs[SLOT].units


def cost(uid):
    return {rc.type: rc.amount for rc in units[uid].creatable.resource_costs if rc.type in (0, 1, 2, 3)}


print("\n=== unit edits ===")
check("Knight costs 70 wood + 50 gold, food gone", cost(KNIGHT) == {1: 70, 3: 50}, cost(KNIGHT))
check("the Knight's cost flows to the Cavalier", cost(CAVALIER) == {1: 70, 3: 50}, cost(CAVALIER))
check("the Paladin's own cost wins over the Knight's", cost(PALADIN) == {0: 100}, cost(PALADIN))
check("a Villager cost never reaches the Flemish Militia (Flemish Revolution changes class)",
      1663 not in __import__("civ_overrides").upgrade_successors(dat).get(VILLAGER, set()))
check("population slot preserved",
      any(rc.type == 4 for rc in units[KNIGHT].creatable.resource_costs))
check("train time flows down the line (Knight, Cavalier, Paladin)",
      all(tl.train_time == 20 for u in (KNIGHT, CAVALIER, PALADIN)
          for tl in units[u].creatable.train_locations))
check("Knight HP 150, but HP stays per tier (Cavalier untouched)",
      units[KNIGHT].hit_points == 150 and units[CAVALIER].hit_points != 150,
      (units[KNIGHT].hit_points, units[CAVALIER].hit_points))
vs_archers = next((a.amount for a in units[KNIGHT].type_50.attacks if a.class_ == ARCHERS), None)
check("bonus damage adds a class the Knight lacked (+6 vs archers)", vs_archers == 6, vs_archers)

forms = unit_forms(dat, units, VILLAGER)
check("the Villager's forms include the female villager and the builder",
      {VILLAGER_F, BUILDER} <= set(forms), forms[:6])
check("every villager form has 40 HP and 2 melee armour",
      all(units[f].hit_points == 40 and units[f].type_50.displayed_melee_armour == 2 for f in forms),
      [(f, units[f].hit_points) for f in forms if units[f].hit_points != 40][:5])
# Vanilla Barracks: 1200 / 1500 / 1800 / 2100 HP by age.  Edited to 2000 in
# the Dark Age = +800 in every age, so the age progression survives.
check("a building's age variants take the same change (Barracks 2000/2300/2600/2900)",
      [units[b].hit_points for b in (BARRACKS, BARRACKS_F, BARRACKS_C, BARRACKS_I)]
      == [2000, 2300, 2600, 2900],
      [units[b].hit_points for b in (BARRACKS, BARRACKS_F, BARRACKS_C, BARRACKS_I)])
check("both Trebuchet forms take the HP", units[TREB_PACKED].hit_points == 300
      and units[TREB].hit_points == 300, (units[TREB_PACKED].hit_points, units[TREB].hit_points))
check("the unpacked Trebuchet (it fights) takes the attack",
      units[TREB].type_50.displayed_attack == 999, units[TREB].type_50.displayed_attack)

print("\n=== tech edits (ghosts) ===")
ghost = [t for t in dat.techs[n_techs:] if t.name == "Tech tree edits"]
check("one civ-owned ghost tech", len(ghost) == 1 and ghost[0].civ == SLOT,
      [(t.name, t.civ) for t in ghost])
cmds = [(c.type, c.a, c.b, c.c, round(c.d, 4)) for c in dat.effects[ghost[0].effect_id].effect_commands] if ghost else []
pal = dat.techs[PALADIN_TECH]
food = next(rc.amount for rc in pal.resource_costs if rc.type == 0)
gold = next(rc.amount for rc in pal.resource_costs if rc.type == 3)
t_now = next(rl.research_time for rl in pal.research_locations if rl.location_id >= 0)
check("Paladin food scaled to 100 by multiply (c=2)", (101, PALADIN_TECH, 0, 2, round(100 / food, 4)) in cmds, cmds)
check("Paladin gold multiplied by 0 (free of gold)", (101, PALADIN_TECH, 3, 2, 0.0) in cmds, cmds)
check("research time scaled to 85 s", (103, PALADIN_TECH, -1, 2, round(85 / t_now, 4)) in cmds, cmds)
check("stone the tech doesn't cost: no command, a warning",
      not any(c[0] == 101 and c[2] == 2 for c in cmds)
      and any("stone" in w for w in result.get("warnings", [])), result.get("warnings"))
check("the shared Paladin tech itself is untouched (other civs keep it)",
      (food, gold) == (1300, 750) or food > 100, (food, gold))
check("the ghost fires on its own (no prerequisites, auto-fire location)",
      ghost and ghost[0].required_tech_count == 0
      and [rl.location_id for rl in ghost[0].research_locations] == [-1])

print("\n=== no edits, no trace ===")
dat2 = load_dat(str(dat_path))
plain = dict(draft, unit_edits={}, tech_edits={})
with contextlib.redirect_stdout(io.StringIO()):
    apply_civ_with_overrides(dat2, _draft_to_civ_def(plain), SLOT, plain)
check("no ghost tech without tech edits", not any(t.name == "Tech tree edits" for t in dat2.techs))

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
