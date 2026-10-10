#!/usr/bin/env python3
"""The Donjon gets every tower bonus the Keep gets — unique techs and bonus cards.

Bonus cards reach towers through their class (52), the Donjon's class too, but a
unique tech is copied from a vanilla tech that names Watch Tower, Guard Tower and
Keep one by one: Yasama, Eupseong, Great Wall, Stronghold and Detinets left the
Donjon out (reported 2026-10-10).  civ_appender._donjon_like_keep copies each
Keep stat change onto the Donjon.  Sweeps every UT effect and every civ bonus
card: a stat change on the Keep must have a Donjon counterpart.  DAT-gated, ~20s.

    venv/bin/python tests/test_donjon_towers.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat              # noqa: E402

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

import bonus_catalog as bc                                   # noqa: E402
from civ_appender import (DONJON_UNIT, KEEP_UNIT, _KM_CASTLE_UT_TECHS,   # noqa: E402
                          _KM_IMP_UT_TECHS, _build_ut_effect_cmds)

dat = load_dat(dat_path)
STAT = (0, 4, 5)


def missing(cmds) -> list:
    """Keep stat changes with no Donjon change of the same type and attribute."""
    keep = [(c.type, int(c.c)) for c in cmds if c.type in STAT and int(c.a) == KEEP_UNIT]
    don = {(c.type, int(c.c)) for c in cmds if c.type in STAT and int(c.a) == DONJON_UNIT}
    return [k for k in keep if k not in don]


reached = 0
for label, lookup in (("castle", _KM_CASTLE_UT_TECHS), ("imperial", _KM_IMP_UT_TECHS)):
    bad = {}
    for km_id in sorted(lookup):
        cmds, _, _ = _build_ut_effect_cmds(dat, [[km_id, 1]], label, lookup)
        if any(c.type in STAT and int(c.a) == KEEP_UNIT for c in cmds):
            reached += 1
        if missing(cmds):
            bad[km_id] = missing(cmds)
    check(f"every {label} UT effect that changes the Keep changes the Donjon too", not bad, bad)
check("the sweep saw the tower UTs (Yasama, Eupseong, Great Wall, ...)", reached >= 5, reached)

# Yasama: the Keep's +2 arrows (attributes 102 and 107) on the Donjon
yasama = next(k for k, t in _KM_CASTLE_UT_TECHS.items() if t == 484)
cmds, _, _ = _build_ut_effect_cmds(dat, [[yasama, 1]], "castle", _KM_CASTLE_UT_TECHS)
check("Yasama gives the Donjon its extra arrows",
      {(4, 102), (4, 107)} <= {(c.type, int(c.c)) for c in cmds if int(c.a) == DONJON_UNIT})
# Svan Towers already names the Donjon: not doubled
svan = next(k for k, t in _KM_CASTLE_UT_TECHS.items() if t == 923)
cmds, _, _ = _build_ut_effect_cmds(dat, [[svan, 1]], "castle", _KM_CASTLE_UT_TECHS)
check("Svan Towers, which names the Donjon itself, is not doubled",
      sum(1 for c in cmds if int(c.a) == DONJON_UNIT) == 1)

# Civ bonus cards: built from vanilla techs and our own command lists
bad = {}
for bid in bc._load()["civ"]:
    cmds = []
    for t in bc.civ_bonus_techs(int(bid)):
        e = dat.techs[t].effect_id
        if 0 <= e < len(dat.effects):
            cmds += list(dat.effects[e].effect_commands)
    if missing(cmds):
        bad[bid] = missing(cmds)
check("no civ bonus card changes the Keep without the Donjon", not bad, bad)

print()
if failures:
    print(f"{failures} check(s) FAILED")
    sys.exit(1)
print("All checks passed.")
