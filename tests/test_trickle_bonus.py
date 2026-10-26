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
check("a trickle must name its resource",
      not cb.normalize([{**card, "effects": [{"attr": "trickle", "op": "add", "value": 10}]}]))

print("the build")
feitoria_before = [(t.resource_out, t.resource_multiplier, t.work_value_1)
                   for t in dat.civs[0].units[1021].bird.tasks if t.action_type == 151]
SLOT, SLOT2, PLAIN = 5, 6, 7
for slot, cards in ((SLOT, [card]),
                    (SLOT2, [{**card, "effects": [{"attr": "trickle", "op": "add", "value": 25, "resource": "gold"}]}]),
                    (PLAIN, [])):
    civ_def = {"alias": f"Trickle {slot}", "tagline": "", "architecture": 1, "language": 0, "wonder": -1,
               "castle": -1, "bonuses": [[], [], [], [], []], "tree": [[], [], []], "custom_bonuses": cards}
    with contextlib.redirect_stdout(io.StringIO()):
        ca.apply_civ(dat, civ_def, target_slot=slot)

reg = dat._ef_trickle
check("one rate resource for Barracks gold, shared by both civs", len(reg) == 1, reg)
rate_res = next(iter(reg.values()))
check("...covering every Barracks copy", {12, 20, 132, 498} <= next(iter(reg))[0], sorted(next(iter(reg))[0]))


def card_cmds(slot):
    t = next(t for t in dat.techs if t.civ == slot and t.name == "C-Bonus, Custom")
    return [(c.type, int(c.a), int(c.b), c.d) for c in dat.effects[t.effect_id].effect_commands]


check("slot 5's card adds 10 to it", card_cmds(SLOT) == [(1, rate_res, 1, 10.0)], card_cmds(SLOT))
check("slot 6's adds 25", card_cmds(SLOT2) == [(1, rate_res, 1, 25.0)], card_cmds(SLOT2))

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

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
