#!/usr/bin/env python3
"""A custom bonus that makes buildings generate a resource, as the Feitoria does.  DAT-gated.

A player asked for it (2026-10-24).  The Feitoria generates with action-151
tasks, each scaled by a civ resource (205-208).  Generate tasks only run when
they're on civ 0, in unit_headers and on every civ's unit, so the task can't
belong to one civ: the card's buildings get a task on every civ, scaled by a
resource of their own, and the card adds its rate to that resource for its
own civ only.  Saved and read back.  The per-minute scale is not measured.

    venv/bin/python tests/test_trickle_bonus.py
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat      # noqa: E402
from dat_lazy import save_bytes                     # noqa: E402
import civ_appender as ca                           # noqa: E402
import custom_bonus as cb                           # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)
dat = load_dat(str(dat_path))

print("the rate resources")
check("every one is 0 for every civ in this game",
      all(c.resources[r] == 0 for c in dat.civs for r in ca._TRICKLE_RESOURCES))
check("...and no effect uses one",
      not any(int(c.a) in ca._TRICKLE_RESOURCES for e in dat.effects for c in e.effect_commands if c.type in (1, 6, 11)))

print("the card")
BARRACKS = {"type": "unit", "id": 12, "kind": "building", "name": "Barracks"}
card = {"targets": [BARRACKS], "effects": [{"attr": "trickle", "op": "add", "value": 10, "resource": "gold"}]}
norm = cb.normalize([card])
check("kept, with its resource", norm and norm[0]["effects"][0]["resource"] == "gold")
check("its text", cb.card_text(norm[0]) == "Barracks: generate 10 gold per minute", cb.card_text(norm[0]))
GROWING = {**card, "when": {"steps": True},
           "effects": [{"attr": "trickle", "op": "add", "resource": "gold", "steps": {"0": 10, "102": 30}}]}
g = cb.normalize([GROWING])
check("a growing card keeps it (#117: it was stripped, so the card did nothing)",
      g and g[0]["effects"] and g[0]["effects"][0].get("steps") == {"0": 10, "102": 30}, g)
check("a trickle must name its resource",
      not cb.normalize([{**card, "effects": [{"attr": "trickle", "op": "add", "value": 10}]}]))

print("the build")
feitoria_before = [(t.resource_out, t.resource_multiplier, t.work_value_1)
                   for t in dat.civs[0].units[1021].bird.tasks if t.action_type == 151]
FORAGERS = {"type": "job", "id": "forager"}
JOB_CARD = {"targets": [FORAGERS], "effects": [{"attr": "trickle", "op": "add", "value": 2, "resource": "wood"}]}
j = cb.normalize([JOB_CARD])
check("a villager job takes it (#113)", j and j[0]["effects"][0]["resource"] == "wood", j)
check("its text", j and cb.card_text(j[0]) == "Foragers: generate 2 wood per minute", j and cb.card_text(j[0]))
offered = cb.allowed_attrs(dat, [("building:12", "building", 12)])
check("offered to foragers and lumberjacks, a building, not to builders or repairers",
      "trickle" in offered["job:forager"] and "trickle" in offered["job:lumberjack"]
      and "trickle" in offered["building:12"]
      and "trickle" not in offered["job:builder"] and "trickle" not in offered["job:repairer"],
      {k: "trickle" in v for k, v in offered.items() if k.startswith("job:") or k == "building:12"})
puru = ca._generate_template(dat, ca._STONE_MINER)
check("the template: the Puru stone miner's generate task, scaled by 512",
      puru is not None and puru.resource_multiplier == 512, puru and puru.resource_multiplier)

SLOT, SLOT2, PLAIN, GROW, JOB = 5, 6, 7, 8, 9
for slot, cards in ((SLOT, [card]),
                    (SLOT2, [{**card, "effects": [{"attr": "trickle", "op": "add", "value": 25, "resource": "gold"}]}]),
                    (PLAIN, []),
                    (GROW, [GROWING]),
                    (JOB, [JOB_CARD])):
    civ_def = {"alias": f"Trickle {slot}", "tagline": "", "architecture": 1, "language": 0, "wonder": -1,
               "castle": -1, "bonuses": [[], [], [], [], []], "tree": [[], [], []], "custom_bonuses": cards}
    with contextlib.redirect_stdout(io.StringIO()):
        ca.apply_civ(dat, civ_def, target_slot=slot)

reg = dat._ef_trickle
barracks = [k for k in reg if 12 in k[0]]
check("one rate resource for Barracks gold, shared by both civs", len(barracks) == 1, reg)
rate_res = reg[barracks[0]]
check("...covering every Barracks copy", {12, 20, 132, 498} <= barracks[0][0], sorted(barracks[0][0]))
forage = [k for k in reg if k[0] == frozenset({120, 354})]
check("the foragers have one of their own, for wood", len(forage) == 1 and forage[0][1] == 1, reg)
job_res = reg[forage[0]] if forage else None
check("...a different resource from the Barracks'", job_res is not None and job_res != rate_res)


def card_cmds(slot):
    t = next(t for t in dat.techs if t.civ == slot and t.name == "C-Bonus, Custom")
    return [(c.type, int(c.a), int(c.b), c.d) for c in dat.effects[t.effect_id].effect_commands]


check("slot 5's card adds 10 to it", card_cmds(SLOT) == [(1, rate_res, 1, 10.0)], card_cmds(SLOT))
check("slot 6's adds 25", card_cmds(SLOT2) == [(1, rate_res, 1, 25.0)], card_cmds(SLOT2))
grow = sorted(([(c.type, int(c.a), int(c.b), c.d) for c in dat.effects[t.effect_id].effect_commands],
               [q for q in t.required_techs if q >= 0])
              for t in dat.techs if t.civ == GROW and t.name.startswith("C-Bonus, Custom") and t.effect_id >= 0)
check("the growing card adds 10 from the start, then 20 more in the Castle Age",
      grow == [([(1, rate_res, 1, 10.0)], []), ([(1, rate_res, 1, 20.0)], [102])], grow)

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "empires2_x2_p1.dat"
    out.write_bytes(save_bytes(dat))
    back = load_dat(str(out))

print("read back from the saved DAT")


def gen(tasks):
    return [(t.resource_out, t.resource_multiplier, round(t.work_value_1 * 60, 6))
            for t in tasks or () if t.action_type == 151]


want = [(3, rate_res, 1.0)]
for uid in (12, 20, 132, 498):
    check(f"Barracks {uid}: the task in unit_headers", gen(back.unit_headers[uid].task_list) == want,
          gen(back.unit_headers[uid].task_list))
    bad = [i for i, c in enumerate(back.civs) if gen(c.units[uid].bird.tasks) != want]
    check(f"Barracks {uid}: ...and on every civ, civ 0 included", not bad, bad[:5])
ids = [t.id for t in back.civs[SLOT].units[12].bird.tasks]
check("task ids stay sequential", ids == list(range(len(ids))), ids)
check("only our civs raise the rate: everyone starts at 0",
      all(c.resources[rate_res] == 0 for c in back.civs))
feitoria_after = [(t.resource_out, t.resource_multiplier, t.work_value_1)
                  for t in back.civs[0].units[1021].bird.tasks if t.action_type == 151]
check("the Feitoria is untouched", feitoria_after == feitoria_before, feitoria_after)

check("the forager card adds 2 to its resource", card_cmds(JOB) == [(1, job_res, 1, 2.0)], card_cmds(JOB))
for uid in (120, 354):
    for where, tasks in (("civ 0", back.civs[0].units[uid].bird.tasks),
                         (f"civ {JOB}", back.civs[JOB].units[uid].bird.tasks),
                         ("unit_headers", back.unit_headers[uid].task_list)):
        gathers = {(t.class_id, t.unit_id) for t in tasks if t.action_type == 5 and t.resource_in >= 0}
        made = {(t.class_id, t.unit_id) for t in tasks if t.action_type == 151 and t.resource_multiplier == job_res}
        check(f"forager {uid}, {where}: a wood task per thing it forages {sorted(gathers)}",
              gathers and made == gathers and all(
                  (t.resource_out, round(t.work_value_1 * 60, 6), t.gather_type, t.auto_search_targets)
                  == (1, 1.0, puru.gather_type, puru.auto_search_targets)
                  for t in tasks if t.action_type == 151 and t.resource_multiplier == job_res),
              f"gathers {sorted(gathers)}, made {sorted(made)}")
check("the Puru stone miner is untouched", ca._generate_template(back, ca._STONE_MINER).resource_multiplier == 512)

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
