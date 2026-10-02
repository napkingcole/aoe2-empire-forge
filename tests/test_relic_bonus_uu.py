#!/usr/bin/env python3
"""Bonus 102's relic attack reaches the civ's own Unique Unit (issue #48).

"Each garrisoned relic gives +1 attack to Knights and Unique Unit" copies the
Lithuanian techs 699-702, which name the Leitis (1234/1236) by id and add
MELEE attack.  A custom civ's UU got nothing, and a ranged UU like the Mangudai
would have ignored a melee bonus even if it had been retargeted.  DAT-gated.

    venv/bin/python tests/test_relic_bonus_uu.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dat_reader import find_game_dat, load_dat     # noqa: E402
from civ_appender import apply_civ                 # noqa: E402

failures = 0


def check(label, ok, detail=""):
    global failures
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        failures += 1
        if detail:
            print(f"       {detail}")


MANGUDAI, ELITE_MANGUDAI, LEITIS, ELITE_LEITIS = 11, 561, 1234, 1236
PIERCE, MELEE = 3, 4

dat = load_dat(find_game_dat())
n_before = len(dat.techs)
apply_civ(dat, {"alias": "RelicProbe", "bonuses": [{"id": 102, "multiplier": 1}],
                "team_bonuses": [], "unique_unit": {"km_idx": 11}}, target_slot=1)

relic = [dat.techs[i] for i in range(n_before, len(dat.techs))
         if dat.techs[i].civ == 1 and "Relic +1 cav attack" in dat.techs[i].name]
cmds = [c for t in relic for c in dat.effects[t.effect_id].effect_commands
        if c.type == 4 and int(c.c) == 9]
by_unit = {}
for c in cmds:
    by_unit.setdefault(int(c.a), []).append(int(c.d))

check("the four relic steps were copied for the civ", len(relic) == 4, [t.name for t in relic])
check("no command still targets the Leitis",
      not ({LEITIS, ELITE_LEITIS} & by_unit.keys()), sorted(by_unit))
check("Mangudai and Elite Mangudai get one step per relic",
      len(by_unit.get(MANGUDAI, [])) == 4 and len(by_unit.get(ELITE_MANGUDAI, [])) == 4,
      {u: len(v) for u, v in by_unit.items()})
check("the Mangudai's bonus is PIERCE attack (+1), the class it deals",
      all(d == PIERCE * 256 + 1 for u in (MANGUDAI, ELITE_MANGUDAI) for d in by_unit.get(u, [])),
      {u: by_unit.get(u) for u in (MANGUDAI, ELITE_MANGUDAI)})
check("Knights keep their melee +1",
      by_unit.get(38) and all(d == MELEE * 256 + 1 for d in by_unit[38]), by_unit.get(38))

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
