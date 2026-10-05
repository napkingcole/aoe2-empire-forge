#!/usr/bin/env python3
"""The Chronicles-derived cards (civ 441-445, team 87-90) reach the built DAT.

Chronicles civs can't be picked outside their own game mode, but their bonus
techs and effects live in the shared DAT, and the portable ones use only
standard units, techs and ages.  Each card here is checked where it lands, not
in the catalog.  DAT-gated.

    venv/bin/python tests/test_chronicles_bonuses.py
"""
import contextlib
import json
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dat_reader import find_game_dat, load_dat     # noqa: E402
from civ_appender import apply_civ, EC_UPGRADE     # noqa: E402

failures = 0


def dispatched_handler_ids() -> set[int]:
    import re
    src = (Path(__file__).resolve().parent.parent / "civ_appender.py").read_text()
    start = src.index("def _create_bonus_handler")
    body = src[start:src.index("\ndef ", start + 10)]
    return {int(x) for m in re.finditer(r"if bonus_id (?:==|in) ([^:]+):", body)
            for x in re.findall(r"\d+", m.group(1))}


def check(label, ok, detail=""):
    global failures
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        failures += 1
        if detail:
            print(f"       {detail}")


# A handler-only bonus the picker doesn't know about is never offered: one was
# built and tested, and still missing from the catalog until this was added.
from civ_appender import HANDLED_BONUS_IDS          # noqa: E402
check("every bonus _create_bonus_handler dispatches is in HANDLED_BONUS_IDS",
      dispatched_handler_ids() <= HANDLED_BONUS_IDS,
      sorted(dispatched_handler_ids() - HANDLED_BONUS_IDS))

SLOT = 1
dat = load_dat(find_game_dat())
n_techs = len(dat.techs)
with contextlib.redirect_stdout(io.StringIO()):
    res = apply_civ(dat, {"alias": "ChronProbe",
                          "bonuses": [{"id": b, "multiplier": 1} for b in range(441, 446)],
                          "team_bonuses": [{"id": t, "multiplier": 1} for t in range(87, 91)]},
                    target_slot=SLOT)

mine = [(i, dat.techs[i]) for i in range(n_techs, len(dat.techs)) if dat.techs[i].civ == SLOT]
cmds = [c for _, t in mine if 0 <= t.effect_id < len(dat.effects)
        for c in dat.effects[t.effect_id].effect_commands]

check("all five civ cards apply, none skipped",
      res["bonus_results"]["applied"] >= 5 and not res["bonus_results"]["skipped"],
      (res["bonus_results"]["applied"], res["bonus_results"]["skipped"]))
check("no warnings", not res.get("warnings"), res.get("warnings"))

# 441 / 444 — civ-gated Macedonian / Thracian techs copied to this civ (quirk 9).
names = {t.name for _, t in mine}
check("441: the three cavalry-armor techs are this civ's own copies",
      sum("for Cavalry, Macedonian" in n for n in names) == 3, sorted(names))
check("444: both skirmisher-regen steps are this civ's own copies",
      sum("Skirmishers regen" in n for n in names) == 2)

# 442 / 443 / 445 — ec_list cards.
check("442: siege +1 pierce armor (class 3) on all four siege classes",
      {int(c.b) for c in cmds if c.type == 4 and int(c.c) == 8 and int(c.d) == 3 * 256 + 1} >= {13, 51, 54, 55})
check("443: seven Stable techs research 50% faster (mode 2)",
      sum(1 for c in cmds if c.type == 103 and int(c.c) == 2 and int(c.a) in
          (435, 39, 254, 428, 209, 265, 236)) == 7)
stone = [t for _, t in mine if any(c.type == 6 and int(c.a) == 512
                                   for c in dat.effects[t.effect_id].effect_commands)]
check("445: resource 512 switched on, then raised by Stone Mining and Stone Shaft Mining",
      any(c.type == 1 and int(c.a) == 512 for c in cmds)
      and sorted(t.required_techs[0] for t in stone) == [278, 279])

# Team bonuses — all merged into the civ's team-bonus effect.
tb = dat.effects[dat.civs[SLOT].team_bonus_id].effect_commands
check("T87: releases the global Fortified Outpost tech (1269 cost and time)",
      {(c.type, int(c.a)) for c in tb} >= {(101, 1269), (103, 1269)})
# The official upgrade is per building: researched at one Outpost, it upgrades
# that Outpost (c=2).  A civ-wide c=-1 card was tried and withdrawn in-game
# (2026-10-03) — it sat beside this button and did a different job.
fort = dat.techs[1270]
check("T87: tech 1270 is researched at the Outpost and upgrades only that one (c=2)",
      fort.research_locations[0].location_id == 598
      and [(int(c.a), int(c.b), int(c.c)) for c in dat.effects[fort.effect_id].effect_commands
           if c.type == EC_UPGRADE] == [(598, 2415, 2)])
check("no civ-owned Outpost upgrade is created", not any(
      t.name == "Fortified Outposts" for _, t in mine))
barracks = [int(c.a) for c in tb if c.type == 103 and int(c.c) == 1]
check("T88: 13 Barracks techs research faster, none of them Chronicles-only",
      len(barracks) == 13 and not {1137, 1173, 1174} & set(barracks), barracks)
check("T89: buildings +3 line of sight",
      any(c.type == 4 and int(c.b) == 3 and int(c.c) == 1 and c.d == 3 for c in tb))
check("T90: trade carts +15% speed",
      any(c.type == 5 and int(c.b) == 19 and int(c.c) == 5 for c in tb))

# ── Chronicles unique units (unlock cards 447-454) ───────────────────────────
from civ_appender import _UNLOCK_UNIT_BONUSES, CHRONICLES_SIDS   # noqa: E402

UNITS = [b for b, spec in _UNLOCK_UNIT_BONUSES.items() if spec.get("chronicles")]
check("ten Chronicles unit cards", UNITS == list(range(447, 457)), UNITS)
check("every Chronicles string id is distinct",
      len(set(CHRONICLES_SIDS.values())) == len(CHRONICLES_SIDS) == 36, len(CHRONICLES_SIDS))

# One card per civ: six of these train at the Castle and share the UU button,
# so a civ can only fit a couple (both pages of the Castle are one slot each).
written: set[str] = set()
for b, SLOT2 in zip(UNITS, range(2, 2 + len(UNITS))):
    n2 = len(dat.techs)
    with contextlib.redirect_stdout(io.StringIO()):
        res2 = apply_civ(dat, {"alias": "ChronUnits", "bonuses": [{"id": b, "multiplier": 1}],
                               "team_bonuses": []}, target_slot=SLOT2)
    written |= {e["name"] for e in res2["bonus_results"].get("extra_unit_strings", [])}
    check(f"{b}: applies with no warnings",
          res2["bonus_results"]["applied"] >= 1 and not res2["bonus_results"]["skipped"]
          and not res2.get("warnings"), (res2["bonus_results"]["skipped"], res2.get("warnings")))
    mine2 = {t.name: (i, t) for i, t in enumerate(dat.techs) if i >= n2 and t.civ == SLOT2}
    spec = _UNLOCK_UNIT_BONUSES[b]
    src_make, src_elite = (dat.techs[t] for t in spec["techs"])
    make = mine2.get(src_make.name)
    elite = mine2.get(src_elite.name)
    check(f"{b} {spec['name']}: make-avail and elite techs are this civ's own copies",
          make is not None and elite is not None)
    if make and elite:
        check(f"{b} {spec['name']}: unlocks in the standard Castle Age, elite in the standard Imperial Age",
              102 in make[1].required_techs and 103 in elite[1].required_techs)
        check(f"{b} {spec['name']}: elite upgrade button carries our own name string",
              elite[1].language_dll_name == CHRONICLES_SIDS[("tech", spec["techs"][1])])
    units = dat.civs[SLOT2].units
    check(f"{b} {spec['name']}: every form carries our own name string",
          all(units[u].language_dll_name == CHRONICLES_SIDS[("unit", u)] for u in spec["names"]))
from civ_appender import unit_label                  # noqa: E402
check("logs and warnings name a renamed unit by its name, not a campaign line",
      unit_label(dat, 9, 2390) == "2390 (Sannāhya)", unit_label(dat, 9, 2390))
check("unit names reach the strings writer (incl. the macron in Sannāhya)",
      {"Immortal (Melee)", "Immortal (Ranged)", "Strategos", "Sannāhya", "Elite Sannāhya"} <= written,
      sorted(written)[:12])

# ── Hoplite / Scythian: global techs rebuilt with standard prerequisites ─────
CHRONICLES_ONLY = {1138, 1267, 113, 115, 1335}       # Paphos, Spartan helper, dup ages, empty trigger
for b in (455, 456):
    spec = _UNLOCK_UNIT_BONUSES[b]
    slot = 2 + UNITS.index(b)
    own = [t for t in dat.techs if t.civ == slot and t.name in {dat.techs[x].name for x in spec["techs"]}]
    reqs = {r for t in own for r in t.required_techs if r >= 0}
    check(f"{b} {spec['name']}: both techs are civ-owned copies", len(own) == 2, [t.name for t in own])
    check(f"{b} {spec['name']}: no Chronicles-only prerequisite survives",
          not reqs & CHRONICLES_ONLY, sorted(reqs))
    make = next((t for t in own if all(l.location_id == -1 for l in t.research_locations)), None)
    check(f"{b} {spec['name']}: the unlock fires on its own — no cost gate",
          make is not None and not [r for r in make.resource_costs if r.type >= 0 and r.amount > 0])

slot = 2 + UNITS.index(456)
scy = next(t for t in dat.techs if t.civ == slot and t.name.startswith("Functional Enable Scythian"))
check("456: the unlock hides the Cavalry Archer, as in the game",
      any(c.type == 2 and int(c.a) == 39 and int(c.b) == 0
          for c in dat.effects[scy.effect_id].effect_commands))
from civ_appender import _tree_unit_ids               # noqa: E402
tree = {"tree": {"units": [4, 39, 474, 2485, 2486], "buildings": [87], "techs": []}}
check("456: picking it takes the Cavalry Archer line out of the tree",
      _tree_unit_ids(tree) == {4, 2485, 2486}, sorted(_tree_unit_ids(tree)))

import tempfile                                          # noqa: E402
from build_civ import _patch_per_civ_techtree, _find_civ_techtrees_folder   # noqa: E402
folder = _find_civ_techtrees_folder(find_game_dat())
if folder and (folder / "ATHENIANS.json").exists():
    out = json.loads(_patch_per_civ_techtree(
        folder / "BRITONS.json",
        {"tree": {"units": [4, 39, 474, 2485, 2486, 2110, 2111], "buildings": [12, 87, 101], "techs": [39]},
         "bonuses": []}, dat=dat, slot=slot))
    units = {n["Node ID"]: n for n in out["civ_techs_units"] if n.get("Use Type") == "Unit"}
    check("F2: Cavalry Archer / Heavy Cav Archer nodes became the Scythian ones",
          2485 in units and 2486 in units and 39 not in units and 474 not in units, sorted(units)[:12])
    check("F2: the Elite Scythian node links to the Scythian",
          units.get(2486, {}).get("Link ID") == 2485)
    check("F2: Husbandry (also Node ID 39, a tech) is untouched",
          any(n.get("Node ID") == 39 and n.get("Use Type") == "Tech" for n in out["civ_techs_units"]))
    check("F2: Hoplite and Elite Hoplite nodes are injected",
          2110 in units and 2111 in units)
else:
    print("  skip  F2 checks: no CivTechTrees folder with the Chronicles civs")

# Hoplite beside the Phalangite: one of them moves to page 2 of the Barracks,
# and its elite upgrade goes with it.  The planner used to copy the ORIGINAL
# global Elite Hoplite too (prerequisites it can never meet) — inert, but junk.
with contextlib.redirect_stdout(io.StringIO()):
    res3 = apply_civ(dat, {"alias": "Barracks Pair", "bonuses": [{"id": 451, "multiplier": 1},
                                                                  {"id": 455, "multiplier": 1}],
                           "team_bonuses": [],
                           "tree": {"units": [74, 2110, 2111, 2384, 2385], "buildings": [12], "techs": []}},
                    target_slot=12)
elites = [t for t in dat.techs if t.civ == 12 and t.name == "Elite Hoplite"]
# (A five-unit tree makes the sweep disable nearly everything, so the tree
# effect itself runs long here — only the button warning is the point.)
check("Hoplite + Phalangite: both trainable (no full-Barracks warning)",
      not [w for w in res3.get("warnings", []) if "can't be trained" in w], res3.get("warnings"))
check("exactly one Elite Hoplite, and it has standard prerequisites only",
      len(elites) == 1 and not {r for r in elites[0].required_techs if r >= 0} & CHRONICLES_ONLY,
      [[r for r in t.required_techs if r >= 0] for t in elites])

# ── Palintonon (457): the Chronicles skin of the Trebuchet, +15% attack ─────
from civ_appender import CHRONICLES_SIDS as _SIDS        # noqa: E402
athenians = next(c for c in dat.civs if c.name == "Athenians")
with contextlib.redirect_stdout(io.StringIO()):
    res4 = apply_civ(dat, {"alias": "Palintonon", "bonuses": [{"id": 457, "multiplier": 1}],
                           "team_bonuses": []}, target_slot=13)
mine4 = dat.civs[13].units
check("457: applies with no warnings", not res4.get("warnings"), res4.get("warnings"))
for uid in (42, 331):
    check(f"457: unit {uid} wears the Athenian art (standing, attack, icon)",
          mine4[uid].standing_graphic == athenians.units[uid].standing_graphic
          and mine4[uid].icon_id == athenians.units[uid].icon_id
          and mine4[uid].type_50.attack_graphic == athenians.units[uid].type_50.attack_graphic)
    check(f"457: unit {uid} is named with our own string",
          mine4[uid].language_dll_name == _SIDS[("unit", uid)])
check("457: stats are untouched (same attack entries as the Trebuchet)",
      [(a.class_, a.amount) for a in mine4[42].type_50.attacks]
      == [(a.class_, a.amount) for a in dat.civs[1].units[42].type_50.attacks])
boost = [c for t in dat.techs if t.civ == 13 and t.name == "C-Bonus, Palintonon attack"
         for c in dat.effects[t.effect_id].effect_commands]
check("457: +15% on each attack entry of the UNPACKED unit only",
      sorted((int(c.a), int(c.d) >> 8, int(c.d) & 255) for c in boost) == [(42, 3, 115), (42, 11, 115)],
      [(int(c.a), int(c.d) >> 8, int(c.d) & 255) for c in boost])
check("457: another civ's Trebuchet keeps its own art",
      dat.civs[2].units[42].standing_graphic != athenians.units[42].standing_graphic)

# ── Hero on Castle button 4, so the Trebuchet keeps button 2 ────────────────
from civ_overrides import _apply_hero_unit              # noqa: E402
LIU_BEI = 1966
for label, uu, slot in (("with a Castle UU", 11, 14), ("with a Crusader Knight UU (also button 4)", 39, 15)):
    hero_civ = {"alias": "Hero", "bonuses": [], "team_bonuses": [], "unique_unit": {"km_idx": uu},
                "hero_unit": {"base_unit_id": LIU_BEI, "name": "Probe Hero"},
                "tree": {"units": [4, 38, 42, 331, 440], "buildings": [82, 12, 101, 87], "techs": []}}
    with contextlib.redirect_stdout(io.StringIO()):
        hres = apply_civ(dat, hero_civ, target_slot=slot)
        _apply_hero_unit(dat, slot, hero_civ)
    u = dat.civs[slot].units
    hero_btn = u[LIU_BEI].creatable.train_locations[0].button_id
    treb_btn = u[331].creatable.train_locations[0].button_id
    check(f"hero {label}: the Trebuchet keeps Castle button 2", treb_btn == 2, treb_btn)
    check(f"hero {label}: the hero is on button 4, or moved to page 2 by the planner",
          hero_btn == 4 or 21 <= hero_btn <= 35, hero_btn)
    tt = dat.effects[dat.civs[slot].tech_tree_id].effect_commands
    check(f"hero {label}: the Trebuchet's Imperial unlock (tech 256) is not disabled",
          not any(c.type == 102 and int(c.d) == 256 for c in tt))
    check(f"hero {label}: nothing is left untrainable",
          not [w for w in hres.get("warnings", []) if "can't be trained" in w], hres.get("warnings"))

# EC_ENABLE with b=-1 also shows a unit (27 vanilla commands use it).  Every
# "is this an enable?" check used to demand b == 1, so these units — and the
# Saxon Hearth Troop, whose make-avail is b=-1 too — were invisible to them.
from build_civ import _uu_actual_unit_id              # noqa: E402
# (Immortal rather than the Hearth Troop: the Hearth Troop is Viking Sagas
# content, absent from the pre-DLC DAT the release-only pass runs against.)
check("a b=-1 make-avail resolves to its unit (Immortal 1114 -> 2101), not the tech id",
      _uu_actual_unit_id(dat, 1114) == 2101, _uu_actual_unit_id(dat, 1114))

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
