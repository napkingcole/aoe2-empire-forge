#!/usr/bin/env python3
"""Custom bonus auras (#103).  DAT-gated past the first section.

An aura is the game's own: action-155 tasks on the source — one per class or
unit it reaches — switched on by Combat Ability (attribute 63) bit 32.  The
Caravanserai and Centurion ship with the bit; Thracians and Delian League SET
it from a tech, which is how the card's tech switches ours on, so an age, a
building or a unique tech gates it for free.  Each stat's value is written the
way the game's own auras write it (custom_bonus.AURA_STATS).

    venv/bin/python tests/test_aura_bonus.py
"""
import contextlib
import io
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import custom_bonus as cb                           # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


TC = {"type": "unit", "id": 109, "kind": "building", "name": "Town Center"}
AURA = {"attr": "aura", "op": "add", "value": 15, "stat": "work_rate", "affects": "villagers", "range": 8}


def card(effects, target=TC, **kw):
    out = cb.normalize([{"targets": [target], "effects": effects, **kw}])
    return out[0] if out else None


print("=== the card ===")
c = card([AURA])
check("kept as typed", c and c["effects"][0] == AURA, c and c["effects"])
check("its text", c and cb.card_text(c) == "Town Center: gives nearby Villagers +15% work rate (range 8)",
      c and cb.card_text(c))
check("an unknown stat is dropped", card([{**AURA, "stat": "luck"}]) is None)
check("an unknown group is dropped", card([{**AURA, "affects": "dragons"}]) is None)
check("a villager job can be reached", card([{**AURA, "affects": "job:lumberjack"}]) is not None)
check("range is kept to 1-20", card([{**AURA, "range": 99}])["effects"][0]["range"] == 20)
check("the amount is capped per stat", card([{**AURA, "stat": "attack", "value": 500}])["effects"][0]["value"] == 20)
check("a negative amount is refused", card([{**AURA, "value": -10}]) is None)
check("no team bonus: allies' buildings don't carry the tasks", bool(cb.team_problem(c)))
check("a unique tech can hold one", cb.ut_problem(c) is None, cb.ut_problem(c))
check("not per relic: the card has nothing left", card([AURA], when={"relics": 4}) is None)
grow = card([AURA, {"attr": "hp", "op": "add", "steps": {"0": 10, "102": 20}}], when={"steps": True})
check("on a growing card it comes with the first step",
      grow and any(e["attr"] == "aura" and "steps" not in e for e in grow["effects"]), grow)

print("\n=== values, as the game writes them ===")
v = cb.aura_task_value
check("speed +20% -> 1.2 multiply (Caravanserai)", v("speed", 20) == (1.2, True))
check("work rate +15% -> 0.15 multiply (Thracian Castle)", v("work_rate", 15) == (0.15, True))
check("attack speed +10% -> 1-1/1.1 multiply (Cao Cao, campaign)",
      math.isclose(v("attack_speed", 10)[0], 0.0909091, abs_tol=1e-6) and v("attack_speed", 10)[1])
check("regeneration 30 HP/min -> 30 (Stronghold)", v("regen", 30) == (30.0, False))

from dat_reader import find_game_dat, load_dat     # noqa: E402

dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(1 if failures else 0)
import civ_appender as ca                          # noqa: E402
from dat_lazy import save_bytes                    # noqa: E402

dat = load_dat(str(dat_path))
c0 = dat.civs[0].units


def auras(uid, civ=0):
    return [t for t in c0[uid].bird.tasks if t.action_type == 155] if civ == 0 else \
        [t for t in dat.civs[civ].units[uid].bird.tasks if t.action_type == 155]


print("\n=== the precedents ===")
cara = {(int(t.search_wait_time), round(t.work_value_1, 4), t.combat_level_flag, t.class_id) for t in auras(1754)}
check("Caravanserai: Trade Carts (class 19) x1.2 speed, multiply + range shown",
      (5, 1.2, 5, 19) in cara and int(c0[1754].type_50.break_off_combat) & 32, cara)
thrace = {(int(t.search_wait_time), round(t.work_value_1, 4)) for t in auras(2418)}
check("Thracian Castle: work rate 0.15", (13, 0.15) in thrace, thrace)
cao = {(int(t.search_wait_time), round(t.work_value_1, 4)) for t in auras(2052)}
check("Cao Cao (campaign): attack speed 0.0909", (10, 0.0909) in cao, cao)
thr = next(e for e in dat.effects if e.name == "Thracians Static Bonuses")
check("Thracians switch theirs on with an EC_SET of 63 = 34",
      any(c.type == 0 and int(c.c) == 63 and c.d == 34.0 for c in thr.effect_commands))


def build(slot, cards):
    civ = {"alias": f"Aura {slot}", "tagline": "", "architecture": 1, "language": 0, "wonder": -1,
           "castle": -1, "bonuses": [[], [], [], [], []], "tree": [[], [], []], "custom_bonuses": cards}
    with contextlib.redirect_stdout(io.StringIO()):
        ca.apply_civ(dat, civ, target_slot=slot)
    return [t for t in dat.techs if t.civ == slot and t.name == "C-Bonus, Custom"]


print("\n=== the build ===")
SLOT, OTHER = 5, 6
other_before = len(auras(109, OTHER))
techs = build(SLOT, [c, card([{**AURA, "stat": "regen", "value": 20, "affects": "military", "range": 6}])])
tc = dat.civs[SLOT].units[109]
mine = auras(109, SLOT)
check("the Town Center's own dormant auras (+15 HP/min) are gone from this civ's copy",
      not any(int(t.search_wait_time) == 109 and t.work_value_1 == 15.0 for t in mine), len(mine))
wr = [t for t in mine if int(t.search_wait_time) == 13]
check("one work-rate task, on the Villager class, 0.15, range 8, multiply + shown, own units",
      [(t.class_id, t.unit_id, round(t.work_value_1, 4), t.work_range, t.combat_level_flag, t.target_diplomacy)
       for t in wr] == [(4, -1, 0.15, 8.0, 5, 1)],
      [(t.class_id, t.unit_id, t.work_value_1, t.work_range, t.combat_level_flag, t.target_diplomacy) for t in wr])
mil_classes = set(cb.GROUPS["military"].get("classes", ()))
rg = {t.class_id for t in mine if int(t.search_wait_time) == 109 and t.class_id >= 0}
check("the second card kept the first's: a regen task per military class, 20 HP/min, no multiply",
      rg == mil_classes and all(t.work_value_1 == 20.0 and t.combat_level_flag == 4
                                for t in mine if int(t.search_wait_time) == 109), (sorted(rg), sorted(mil_classes)))
ids = [t.id for t in tc.bird.tasks]
check("task ids stay sequential", ids == list(range(len(ids))), ids)
check("another civ's Town Center is untouched", len(auras(109, OTHER)) == other_before)
sets = [(int(cmd.a), cmd.type, cmd.d) for t in techs for cmd in dat.effects[t.effect_id].effect_commands
        if int(cmd.c) == 63 and cmd.type in (0, 4)]
check("the card switches it on: ADD 32 to 63 on every Town Center copy, once each (two cards)",
      (109, 4, 32.0) in sets and {71, 141, 142} <= {a for a, _, _ in sets}
      and len(sets) == len({a for a, _, _ in sets}) and all(t == 4 for _, t, _ in sets), sets)
check("...and nowhere in the unit itself, so a gate can hold it back",
      not int(tc.type_50.break_off_combat) & 32)

dat2 = load_dat(str(dat_path))
dat, keep = dat2, dat
techs = build(SLOT, [card([AURA], when={"age": 102})])
check("from the Castle Age: the switch waits on 102",
      any(102 in t.required_techs and any(cmd.type == 4 and int(cmd.c) == 63
                                          for cmd in dat.effects[t.effect_id].effect_commands) for t in techs))

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "empires2_x2_p1.dat"
    out.write_bytes(save_bytes(dat))
    back = load_dat(str(out))
saved = [(t.class_id, round(t.work_value_1, 4), int(t.search_wait_time))
         for t in back.civs[SLOT].units[109].bird.tasks if t.action_type == 155]
check("survives saving the DAT", saved == [(4, 0.15, 13)], saved)

# An aura and extra projectiles on one unit: both bits, neither wiping the other.
dat = load_dat(str(dat_path))
TOWER = {"type": "group", "id": "towers"}
techs = build(SLOT, [card([{"attr": "projectiles", "op": "add", "value": 2}], target=TOWER),
                     card([{**AURA, "stat": "regen", "value": 30, "affects": "military"}], target=TOWER)])
bits = sorted(cmd.d for t in techs for cmd in dat.effects[t.effect_id].effect_commands
              if int(cmd.a) == 79 and int(cmd.c) == 63 and cmd.type == 4)
check("a Watch Tower with both cards: ADD 32 (aura) only — towers fire one after another, no volley bit",
      bits == [32.0], bits)

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
