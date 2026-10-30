#!/usr/bin/env python3
"""Card 99: Siege Workshop and Battering Ram in the Feudal Age.  DAT-gated.

The card copies the Cumans' techs 295/705/706, but the techs that make the
Siege Workshop (149), Battering Ram (162) and Capped Ram (96) available are
global and name the originals, which only the Cumans can fire — so the card did
nothing (#109).  The Ram's Feudal route is tech 711, the Cumans' cavalry speed
bonus, so it gets an empty trigger of its own rather than a copy of 711.

    venv/bin/python tests/test_feudal_siege.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat     # noqa: E402
from civ_appender import _ALT_GATE_PREFIX, apply_civ  # noqa: E402

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
    print("SKIP: no game DAT found")
    sys.exit(0)
dat = load_dat(dat_path)

FEUDAL, CASTLE, IMPERIAL = 101, 102, 103
SIEGE_WORKSHOP, RAM, CAPPED_RAM, CASTLE_COUNT = 149, 162, 96, 1218


def routes(dat, dependent, civ_index):
    """The civ-owned techs that can satisfy `dependent` through an alt gate."""
    out = []
    for r in dat.techs[dependent].required_techs:
        if r >= 0 and dat.techs[r].name.startswith(_ALT_GATE_PREFIX):
            out += [m for m in dat.techs[r].required_techs
                    if m >= 0 and dat.techs[m].civ == civ_index]
    return out


def build(slot, bonuses):
    with contextlib.redirect_stdout(io.StringIO()):
        return apply_civ(dat, {"alias": f"Siege{slot}", "team_bonuses": [],
                               "bonuses": [{"id": b, "multiplier": 1} for b in bonuses]},
                         target_slot=slot)


print("=== card 99 alone ===")
res = build(1, [99])
check("applies with no warnings", not res.get("warnings") and not res["bonus_results"]["skipped"],
      (res.get("warnings"), res["bonus_results"]["skipped"]))
for dep, what, wants in ((SIEGE_WORKSHOP, "Siege Workshop", 705), (CAPPED_RAM, "Capped Ram", 706),
                         (CASTLE_COUNT, "Siege Workshop counting toward Castle Age", 295)):
    own = routes(dat, dep, 1)
    check(f"{what} ({dep}) can be reached through this civ's copy of {wants}",
          any(dat.techs[t].name == dat.techs[wants].name for t in own),
          [dat.techs[t].name for t in own])
ram = routes(dat, RAM, 1)
check("the Battering Ram (162) has a Feudal route of this civ's own",
      len(ram) == 1 and list(dat.techs[ram[0]].required_techs)[:1] == [FEUDAL], ram)
check("and that route carries no effect (no Cuman cavalry speed)",
      ram and dat.techs[ram[0]].effect_id == -1)

print("\n=== a second civ in the same DAT ===")
build(2, [99])
for dep in (SIEGE_WORKSHOP, RAM, CAPPED_RAM, CASTLE_COUNT):
    check(f"{dep} reaches both civs' routes, from one gate",
          routes(dat, dep, 1) and routes(dat, dep, 2)
          and sum(dat.techs[r].name.startswith(_ALT_GATE_PREFIX)
                  for r in dat.techs[dep].required_techs if r >= 0) == 1)

print("\n=== card 97 (the cavalry speed that copies 711) gives no early Ram ===")
build(3, [97])
check("a civ with only card 97 has no Feudal Ram route", not routes(dat, RAM, 3), routes(dat, RAM, 3))

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
