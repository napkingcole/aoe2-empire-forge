#!/usr/bin/env python3
"""Scorpion techs and bonuses reach the Heavy and Imperial Scorpion.  DAT-gated.

#92: Chemistry, Rocketry, Ballistas, Double Crossbow and the gold discount name
the Scorpion and Heavy Scorpion by id, so our Imperial Scorpion (1179, bonus
308) got none of them.  And card 271 "Scorpions train 50% faster" named unit
541, a projectile, instead of the Heavy Scorpion 542 (KM's list).

    venv/bin/python tests/test_imperial_scorpion_techs.py
"""
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dat_reader import find_game_dat, load_dat        # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f"\n       {extra}"))
    failures += not cond


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

from civ_appender import apply_civ                    # noqa: E402

HEAVY, IMPERIAL = 542, 1179
CHEMISTRY, ROCKETRY, BALLISTAS, DOUBLE_CROSSBOW, CHEAP_SCORPIONS = 47, 52, 883, 623, 892
dat = load_dat(str(dat_path))


def build(slot, bonuses):
    civ_def = {"alias": f"Scorpion Probe {slot}", "description": "", "architecture": 2, "language": 0,
               "wonder": -1, "castle": -1, "bonuses": [[[b, 1] for b in bonuses], [], [], [], []],
               "tree": [[], [], []]}
    with contextlib.redirect_stdout(io.StringIO()):
        return apply_civ(dat, civ_def, target_slot=slot)


def shape(tid, uid):
    return sorted((c.type, int(c.c), round(c.d, 4)) for c in dat.effects[dat.techs[tid].effect_id].effect_commands
                  if int(c.a) == uid and c.type in (0, 4, 5))


build(5, [308, 271])
for tid, name in ((CHEMISTRY, "Chemistry"), (ROCKETRY, "Rocketry"), (BALLISTAS, "Ballistas"),
                  (DOUBLE_CROSSBOW, "Double Crossbow"), (CHEAP_SCORPIONS, "cheaper scorpions")):
    check(f"{name} gives the Imperial Scorpion what it gives the Heavy Scorpion",
          shape(tid, HEAVY) and shape(tid, IMPERIAL) == shape(tid, HEAVY), (shape(tid, HEAVY), shape(tid, IMPERIAL)))

train = [t for t, x in enumerate(dat.techs) if x.civ == 5 and x.effect_id >= 0
         and any(c.type == 5 and int(c.c) == 101 and int(c.a) == 279 for c in dat.effects[x.effect_id].effect_commands)]
check("card 271 speeds up Heavy and Imperial Scorpion training too (#92)",
      len(train) == 1 and all(shape(train[0], u) == shape(train[0], 279) for u in (HEAVY, IMPERIAL)),
      [(u, shape(train[0], u)) for u in (279, HEAVY, IMPERIAL)] if train else train)
check("card 271 no longer touches the projectile 541",
      not any(int(c.a) == 541 for c in dat.effects[dat.techs[train[0]].effect_id].effect_commands) if train else False)

n = len(dat.effects[dat.techs[CHEMISTRY].effect_id].effect_commands)
build(6, [308])
check("a second Imperial Scorpion civ adds nothing twice",
      len(dat.effects[dat.techs[CHEMISTRY].effect_id].effect_commands) == n)

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
