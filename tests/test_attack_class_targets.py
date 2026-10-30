#!/usr/bin/env python3
"""Every attack class a civ's effects change exists on the unit.  DAT-gated.

The engine only changes an attack class the unit already has.  Card 243
"Skirmishers +1 vs infantry" did nothing, even at x4, because no Skirmisher
has an infantry entry (reported 2026-10-30).  Vanilla units carry 0-value
entries for the classes their techs touch; the one vanilla bonus that targets
a missing class (the Varangian team bonus) creates it first with attribute
161, "Add Attack Type".  Ten cards had the same flaw.

    venv/bin/python tests/test_attack_class_targets.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat                  # noqa: E402
from civ_appender import (EC_ADD, _add_missing_attack_classes,   # noqa: E402
                          _attack_classes_added, _every_civ, apply_civ)
from genieutils.effect import EffectCommand                     # noqa: E402

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
SLOT = 1
CARDS = (206, 213, 243, 253, 254, 255, 256, 263, 268, 275)

print("=== cards that add attack vs a class the unit lacks ===")
civ_def = {"alias": "Classes", "description": "", "architecture": 2, "language": 0,
           "wonder": -1, "castle": -1,
           "bonuses": [[[243, 4], *([c, 1] for c in CARDS if c != 243)], [], [], [], []],
           "tree": [[83, 13, 74, 4, 24, 7, 6, 1155], [12, 87, 109, 70], [101, 102, 103, 98, 655]]}
with contextlib.redirect_stdout(io.StringIO()):
    apply_civ(dat, civ_def, target_slot=SLOT)
civ = dat.civs[SLOT]
own = [civ.tech_tree_id] + [t.effect_id for t in dat.techs if t.civ == SLOT]
missing = []
for uid, classes in _attack_classes_added(dat, own).items():
    unit = civ.units[uid] if uid < len(civ.units) else None
    if unit is None or unit.type_50 is None:
        continue
    have = {a.class_ for a in unit.type_50.attacks}
    missing += [(uid, unit.name, c) for c in classes - have]
check("every attack class the civ's effects change exists on the unit", not missing,
      f"{len(missing)} missing, e.g. {missing[:6]}")

skirm = {a.class_: a.amount for a in civ.units[7].type_50.attacks}
check("the Skirmisher has an infantry (class 1) entry", 1 in skirm, skirm)
check("added at 0, so the card's +4 is the whole bonus", skirm.get(1) == 0, skirm)
pierce = {a.class_: a.amount for a in dat.civs[2].units[7].type_50.attacks}
check("another civ's Skirmisher is untouched", 1 not in pierce, pierce)

print("\n=== card 213: Mangonels cut trees the way Onagers do ===")
# Trees are not combat units and have no armour, so the card's old +100 vs
# class 18 could never land.  Onagers cut trees through their blast attack
# level (1 reaches trees, the Mangonel's 2 does not).
cmds = [c for t in dat.techs if t.civ == SLOT and 0 <= t.effect_id < len(dat.effects)
        for c in dat.effects[t.effect_id].effect_commands if c.a == 280 and int(c.c) == 44]
onager = dat.civs[2].units[550].type_50.blast_attack_level
check("the card sets the Mangonel's blast attack level", len(cmds) == 1, cmds)
check(f"to the Onager's ({onager})", cmds and cmds[0].type == 0 and cmds[0].d == onager,
      [(c.type, c.d) for c in cmds])
check("and no longer adds attack vs trees",
      not any(c.a == 280 and int(c.c) == 9 and (int(c.d) >> 8) == 18
              for t in dat.techs if t.civ == SLOT and 0 <= t.effect_id < len(dat.effects)
              for c in dat.effects[t.effect_id].effect_commands))

print("\n=== team bonus classes reach every civ ===")
tb = civ.team_bonus_id
ec = EffectCommand(type=EC_ADD, a=38, b=-1, c=9, d=float((21 << 8) | 2))   # Knight +2 vs class 21
dat.effects[tb].effect_commands.append(ec)
for c in _every_civ(dat):
    k = c.units[38]
    if k is not None and k.type_50 is not None:
        k.type_50.attacks = [a for a in k.type_50.attacks if a.class_ != 21]
_add_missing_attack_classes(dat, SLOT, tb)
lacking = [c.name for c in _every_civ(dat)
           if c.units[38] is not None and 21 not in {a.class_ for a in c.units[38].type_50.attacks}]
check("an ally's Knight gets the team bonus's class too", not lacking, lacking[:5])

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
