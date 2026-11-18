#!/usr/bin/env python3
"""Custom bonuses that wait: from an age, growing each age, once a building is built.

A player asked to "age ration or prerequisite a bonus" — Archers +15% HP from
the Castle Age, Militia line +5/+10/+15 HP in Feudal/Castle/Imperial, a free
tech once a building goes up.  Each is the vanilla shape (custom_bonus.STEP_AGES):

1. **Pure** — normalisation, the increments (a ratio for percentages), the
   gates each step waits on, card text, and the team/UT refusals.
2. **Precedent** — vanilla's stepped bonuses are one tech per age gated on
   101/102/103, and each trigger building fires the marker we name.  DAT-gated.
3. **Build** — apply_civ writes one gated tech per step.  DAT-gated.

    venv/bin/python tests/test_custom_bonus_when.py
"""
import contextlib
import io
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import custom_bonus as cb                                # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


def card(target, effects, when=None, **kw):
    raw = {"targets": [target], "effects": effects, **kw}
    if when is not None:
        raw["when"] = when
    out = cb.normalize([raw])
    return out[0] if out else None


MILITIA = {"type": "unit", "id": 74, "name": "Militia"}
ARCHERS = {"type": "group", "id": "archers"}
ident = lambda uid: {uid}                                 # noqa: E731
steps_of = lambda c: cb.card_steps(c, ident)              # noqa: E731


# ── 1. Pure ───────────────────────────────────────────────────────────────────
mil = card(MILITIA, [{"attr": "hp", "op": "add", "steps": {"101": 5, "102": 10, "103": 15}}],
           when={"steps": True})
st = steps_of(mil)
check("Militia line +5/+10/+15 HP is three steps, gated on Feudal, Castle, Imperial",
      [s["reqs"] for s in st] == [[101], [102], [103]], [s["reqs"] for s in st])
check("each step adds that age's increment (+5), as vanilla's Malians armor steps do",
      [[c.d for c in s["cmds"]] for s in st] == [[5.0], [5.0], [5.0]])
check("text reads like the game's own stepped bonuses",
      cb.card_text(mil) == "Militia line: +5/+10/+15 HP in the Feudal/Castle/Imperial Age", cb.card_text(mil))
check("an older Empire Forge reads `value` as the FIRST step — weakest, not strongest",
      mil["effects"][0]["value"] == 5)

pct = card(ARCHERS, [{"attr": "hp", "op": "mul", "steps": {"101": 10, "102": 15, "103": 20}}],
           when={"steps": True})
ds = [s["cmds"][0].d for s in steps_of(pct)]
check("percent steps multiply by the ratio, so the total at Imperial is exactly +20%",
      math.isclose(math.prod(ds), 1.2) and math.isclose(ds[0], 1.1), ds)

fast = card(ARCHERS, [{"attr": "attack_speed", "op": "mul", "steps": {"102": 10, "103": 25}}],
            when={"steps": True})
ds = [s["cmds"][0].d for s in steps_of(fast)]
check("'attack 10%/25% faster' ends at reload x0.8, as 25% faster from the start would",
      math.isclose(math.prod(ds), 0.8), ds)
check("its text", cb.card_text(fast) == "Archers: attack 10%/25% faster in the Castle/Imperial Age",
      cb.card_text(fast))

start = card(MILITIA, [{"attr": "hp", "op": "add", "steps": {"0": 5, "103": 15}}], when={"steps": True})
check("a step at the start has no gate; Imperial waits for 103",
      [s["reqs"] for s in steps_of(start)] == [[], [103]])
check("...and its text names the Dark Age",
      cb.card_text(start) == "Militia line: +5/+15 HP in the Dark/Imperial Age", cb.card_text(start))

blank = card(MILITIA, [{"attr": "hp", "op": "add", "steps": {"101": 5, "102": 0, "103": 15}}],
             when={"steps": True})
check("a zero step is dropped (blank = no change), not the effect",
      blank["effects"][0]["steps"] == {"101": 5, "103": 15}, blank["effects"][0])

rep = card(MILITIA, [{"attr": "hp", "op": "add", "steps": {"0": 5, "101": 5, "102": 10, "103": 10}}],
           when={"steps": True})
check("a step that repeats the one before is dropped — '+5/+5/+10/+10' would read as four changes",
      rep["effects"][0]["steps"] == {"0": 5, "102": 10}, rep["effects"][0])

two = card(ARCHERS, [{"attr": "hp", "op": "add", "steps": {"101": 5}},
                     {"attr": "range", "op": "add", "steps": {"103": 1}}], when={"steps": True})
check("effects can step on different ages: one step per age that changes something",
      [s["reqs"] for s in steps_of(two)] == [[101], [103]])

castle = card(ARCHERS, [{"attr": "hp", "op": "mul", "value": 15}], when={"age": 102})
check("from the Castle Age: one step gated on 102",
      [s["reqs"] for s in steps_of(castle)] == [[102]])
check("...reading 'from the Castle Age'",
      cb.card_text(castle) == "Archers: +15% HP from the Castle Age", cb.card_text(castle))

loom = card({"type": "tech", "id": 22, "name": "Loom"}, [{"attr": "free", "op": "set"}],
            when={"building": 68})
check("free Loom once a Mill is built: gated on the Mill's marker (110)",
      [s["reqs"] for s in steps_of(loom)] == [[110]])
check("...reading 'once a Mill is built'",
      cb.card_text(loom) == "Loom: free and instant once a Mill is built", cb.card_text(loom))
both = card(ARCHERS, [{"attr": "hp", "op": "mul", "value": 15}], when={"age": 102, "building": 87})
check("an age AND a building: both prerequisites (a tech needs every one)",
      [s["reqs"] for s in steps_of(both)] == [[102, 132]])
check("...and 'an' before a vowel",
      cb.card_text(both) == "Archers: +15% HP from the Castle Age, once an Archery Range is built",
      cb.card_text(both))
grow_b = card(MILITIA, [{"attr": "hp", "op": "add", "steps": {"101": 5, "102": 10}}],
              when={"steps": True, "building": 12})
check("a growing card with a building: every step waits for it",
      [s["reqs"] for s in steps_of(grow_b)] == [[101, 122], [102, 122]])
check("the build's own marker wins over vanilla's",
      [s["reqs"] for s in cb.card_steps(loom, ident, lambda k, a: 999 if k == "trigger" else
                                        {22} if k == "techs" else {})] == [[999]])

free_step = card(MILITIA, [{"attr": "hp", "op": "add", "steps": {"102": 10, "103": 20}}],
                 when={"steps": True})
check("a plain card is unchanged: one step, no gate",
      [s["reqs"] for s in steps_of(card(MILITIA, [{"attr": "hp", "op": "add", "value": 5}]))] == [[]])
check("an ungated card stores no `when`",
      "when" not in card(MILITIA, [{"attr": "hp", "op": "add", "value": 5}]))
check("a junk building id is dropped, not the card",
      card(ARCHERS, [{"attr": "hp", "op": "add", "value": 5}], when={"building": 70}).get("when") is None)
check("a card marked growing whose effects have no steps reads as from the start",
      steps_of(card(MILITIA, [{"attr": "hp", "op": "add", "value": 5}], when={"steps": True}))[0]["reqs"] == [])

# Civilization cards: the age moves to `when`, and a building gates the grants.
old_civ = cb.normalize([{"target": {"type": "civ", "id": "civ", "age": 103},
                         "effects": [{"attr": "pop_cap", "op": "add", "value": 25}]}])[0]
check("a Civilization card saved before gating keeps its age, now in `when`",
      old_civ.get("when") == {"age": 103} and old_civ["targets"][0].get("age") == 103, old_civ)
check("...and still builds the same gated tech", [s["reqs"] for s in steps_of(old_civ)] == [[103]])
wood = card({"type": "civ", "id": "civ"}, [{"attr": "resources", "op": "add", "value": 200, "resource": "wood"}],
            when={"building": 562})
check("+200 wood once a Lumber Camp is built: a gated grant, not the Town Center start path",
      [s["reqs"] for s in steps_of(wood)] == [[258]] and steps_of(wood)[0]["cmds"][0].a == 1)
check("...reading '+200 wood once a Lumber Camp is built'",
      cb.card_text(wood) == "+200 wood once a Lumber Camp is built", cb.card_text(wood))
check("Civilization cards don't grow each age",
      "steps" not in (card({"type": "civ", "id": "civ"},
                           [{"attr": "pop_cap", "op": "add", "value": 5}], when={"steps": True}).get("when") or {}))

# Per relic (#112): the Lithuanians' "+1 attack per relic", techs 699-702.
KNIGHTS = {"type": "unit", "id": 38, "name": "Knight"}
rel = card(KNIGHTS, [{"attr": "melee_attack", "op": "add", "value": 1}], when={"relics": 4, "age": 102, "building": 68})
check("per relic is a gate of its own: no age, no building on top", rel["when"] == {"relics": 4}, rel["when"])
st = steps_of(rel)
check("four steps, each the whole effect (+1 attack)",
      len(st) == 4 and all([c.d for c in s["cmds"]] == [1025.0] for s in st), [[c.d for c in s["cmds"]] for s in st])
check("step k costs k relics", [s["relics"] for s in st] == [1, 2, 3, 4])
check("the first waits on the Dark Age and a Monastery (107), the rest on the Dark Age and the step before",
      [s["reqs"] for s in st] == [[104, 107], [104], [104], [104]] and [s["after"] for s in st] == [None, 0, 1, 2],
      [(s["reqs"], s["after"]) for s in st])
check("its text", cb.card_text(rel) == "Knight line: +1 melee attack per relic in a Monastery (up to 4)", cb.card_text(rel))
check("capped at RELIC_MAX", card(KNIGHTS, [{"attr": "hp", "op": "add", "value": 5}],
                                  when={"relics": 99})["when"] == {"relics": cb.RELIC_MAX})
check("not on a Civilization card", "relics" not in (card({"type": "civ", "id": "civ"},
      [{"attr": "pop_cap", "op": "add", "value": 5}], when={"relics": 4}).get("when") or {}))
check("a per-relic card can't be a team bonus or go in a unique tech",
      bool(cb.team_problem(rel)) and bool(cb.ut_problem(rel)))

check("a gated card can't be a team bonus", bool(cb.team_problem(castle)))
check("a gated card can't go in a unique tech", bool(cb.ut_problem(loom)))
check("an ungated card still can", cb.team_problem(card(ARCHERS, [{"attr": "hp", "op": "add", "value": 5}])) is None)


# ── 2 & 3. DAT-gated ──────────────────────────────────────────────────────────
from dat_reader import find_game_dat, load_dat          # noqa: E402

dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found — precedent and build checks skipped")
    sys.exit(1 if failures else 0)

import civ_appender as ca                                # noqa: E402

dat = load_dat(str(dat_path))

for name in ("C-Bonus, +2% arc HP feudal", "C-Bonus, inf +1 armor castle"):
    t = next((t for t in dat.techs if t.name == name), None)
    check(f"vanilla precedent {name!r} is an auto-fire tech gated on an age",
          t is not None and set(t.required_techs) & {101, 102, 103}
          and t.research_locations and t.research_locations[0].location_id == -1)

units = dat.civs[1].units
for bid, (label, marker) in cb.TRIGGER_BUILDINGS.items():
    if marker is None:
        continue                    # made by the build (MADE_TRIGGERS), checked below
    u = units[bid] if bid < len(units) else None
    got = u.building.tech_id if u is not None and u.building is not None else None
    t = dat.techs[marker] if got == marker else None
    check(f"{label} ({bid}) fires marker {marker}, which has no prerequisites",
          t is not None and t.civ == -1 and all(r < 0 for r in t.required_techs), f"fires {got}")


def civ_def(cards, buildings=()):
    return {"alias": "When Probe", "tagline": "", "architecture": 1, "language": 0,
            "wonder": -1, "castle": -1, "bonuses": [[], [], [], [], []],
            "tree": [[], list(buildings), []], "custom_bonuses": cards}


slot = 7
cards = [mil, loom]
with contextlib.redirect_stdout(io.StringIO()):
    res = ca.apply_civ(dat, civ_def(cards), target_slot=slot)
ours = [t for t in dat.techs if t.civ == slot and t.name == "C-Bonus, Custom"]
reqs = sorted(tuple(r for r in t.required_techs if r >= 0) for t in ours)
check("the build writes one gated tech per step: Feudal, Castle, Imperial, the Mill",
      reqs == [(101,), (102,), (103,), (110,)], reqs)
check("...each needing all of its prerequisites",
      all(t.required_tech_count == len([r for r in t.required_techs if r >= 0]) for t in ours))
check("apply_civ counts each card once", res["bonus_results"].get("custom_applied") == 2,
      res["bonus_results"].get("custom_applied"))

dat = load_dat(str(dat_path))
warns: list = []
with contextlib.redirect_stdout(io.StringIO()):
    res = ca.apply_civ(dat, civ_def([card(ARCHERS, [{"attr": "hp", "op": "add", "value": 5}],
                                          when={"building": 1251})], buildings=[12, 68]), target_slot=slot)
check("a card waiting for a building the civ can't build warns",
      any("can't build" in w for w in res.get("warnings", [])), res.get("warnings"))
dat = load_dat(str(dat_path))
with contextlib.redirect_stdout(io.StringIO()):
    res = ca.apply_civ(dat, civ_def([card(ARCHERS, [{"attr": "hp", "op": "add", "value": 5}],
                                          when={"building": 68})], buildings=[12, 1711]), target_slot=slot)
check("a Folwark civ's 'once a Mill is built' doesn't warn — the Folwark fires the same marker",
      not any("can't build" in w for w in res.get("warnings", [])), res.get("warnings"))

# Towers and the Outpost fire no marker in the game: the build gives this civ's
# own, vanilla's "Castle built" shape (#123).
dat = load_dat(str(dat_path))
with contextlib.redirect_stdout(io.StringIO()):
    res = ca.apply_civ(dat, civ_def([card(ARCHERS, [{"attr": "hp", "op": "add", "value": 5}], when={"building": 79}),
                                     card(ARCHERS, [{"attr": "hp", "op": "add", "value": 6}], when={"building": 598})],
                                    buildings=[12, 79, 234, 235, 598]), target_slot=slot)
us = dat.civs[slot].units
tower = us[79].building.tech_id
check("a Tower card: every tower form fires one marker of this civ's",
      tower >= 0 and us[234].building.tech_id == us[235].building.tech_id == tower and dat.techs[tower].civ == slot,
      (us[79].building.tech_id, us[234].building.tech_id, us[235].building.tech_id))
check("...which nothing but building one fires (needs one of no prerequisites)",
      tower >= 0 and all(r < 0 for r in dat.techs[tower].required_techs) and dat.techs[tower].required_tech_count == 1)
outpost = us[598].building.tech_id
gates = sorted(tuple(r for r in t.required_techs if r >= 0) for t in dat.techs
               if t.civ == slot and t.name == "C-Bonus, Custom")
check("the Outpost has its own, and each card waits on its marker",
      outpost >= 0 and outpost != tower and gates == sorted([(tower,), (outpost,)]), (gates, tower, outpost))
check("...without the can't-build warning", not any("can't build" in w for w in res.get("warnings", [])),
      res.get("warnings"))
check("other civs' towers are untouched", dat.civs[2].units[79].building.tech_id == -1)

# Per relic, built — against the Lithuanians' own chain.
lith = [dat.techs[t] for t in (699, 700, 701, 702)]
check("precedent: 699-702 are auto-fire, chained, costing 1-4 relics (resource 7, flag 1)",
      [(c.type, c.amount, c.flag) for t in lith for c in t.resource_costs[:1]]
      == [(7, n, 1) for n in (1, 2, 3, 4)]
      and [[r for r in t.required_techs if r >= 0] for t in lith] == [[104, 107], [104, 699], [104, 700], [104, 701]],
      [[r for r in t.required_techs if r >= 0] for t in lith])
dat = load_dat(str(dat_path))
with contextlib.redirect_stdout(io.StringIO()):
    ca.apply_civ(dat, civ_def([rel], buildings=[12, 101, 104]), target_slot=slot)
ours = [(i, t) for i, t in enumerate(dat.techs) if t.civ == slot and t.name == "C-Bonus, Custom"]
shape = [([r for r in t.required_techs if r >= 0], [(c.type, c.amount, c.flag) for c in t.resource_costs],
          t.repeatable, [r.location_id for r in t.research_locations]) for _, t in ours]
ids = [i for i, _ in ours]
want = [([104, 107] if k == 1 else [104, ids[k - 2]], [(7, k, 1), (-1, 0, 0), (-1, 0, 0)], 1, [-1])
        for k in range(1, 5)]
check("the build writes the Lithuanian shape: four chained techs costing 1-4 relics", shape == want,
      f"{shape}\n       want {want}")
check("...each adding +1 attack to the Knight line",
      all({(38, 9, 1025.0), (283, 9, 1025.0), (569, 9, 1025.0)}
          <= {(int(c.a), int(c.c), c.d) for c in dat.effects[t.effect_id].effect_commands} for _, t in ours))

print("\nAll checks passed." if not failures else f"\n{failures} check(s) FAILED.")
sys.exit(1 if failures else 0)
