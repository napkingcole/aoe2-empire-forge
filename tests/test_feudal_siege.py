#!/usr/bin/env python3
"""Card 99: Siege Workshop and Battering Ram in the Feudal Age.  DAT-gated.

Also cards 316 (Fortified Church) and 109 (Donjon), which had the same flaw.

The card copies the Cumans' techs 295/705/706, but the techs that make the
Siege Workshop (149), Battering Ram (162) and Capped Ram (96) available are
global and name the originals, which only the Cumans can fire — so the card did
nothing (#109).  The Workshop and Ram are now unlocked by techs of the civ's own;
the Capped Ram and the Castle Age building count go through alt-prereq gates.

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


def own_unlock(slot, unit):
    """This civ's own tech that enables `unit`, with its prerequisites."""
    for t in dat.techs:
        if t.civ == slot and t.name.startswith("EF Feudal") and t.effect_id >= 0 and any(
                c.type == 2 and int(c.a) == unit and int(c.b) == 1
                for c in dat.effects[t.effect_id].effect_commands):
            return t
    return None


print("=== card 99 alone ===")
res = build(1, [99])
check("applies with no warnings", not res.get("warnings") and not res["bonus_results"]["skipped"],
      (res.get("warnings"), res["bonus_results"]["skipped"]))
# Round 1 went through gates, and in game no Feudal Siege Workshop appeared
# (2026-10-31).  The Workshop and Ram are now this civ's own unlocks.
ws = own_unlock(1, 49)
check("the Siege Workshop has a Feudal unlock of this civ's own, needing a Blacksmith (668)",
      ws is not None and set(ws.required_techs) - {-1} == {FEUDAL, 668} and ws.required_tech_count == 2,
      ws and list(ws.required_techs))
ram = own_unlock(1, 1258)
check("the Battering Ram has a Feudal unlock of this civ's own",
      ram is not None and set(ram.required_techs) - {-1} == {FEUDAL}, ram and list(ram.required_techs))
check("and it enables only the Ram (no Cuman cavalry speed)",
      ram is not None and len(dat.effects[ram.effect_id].effect_commands) == 1)
for dep, what, wants in ((CAPPED_RAM, "Capped Ram", 706),
                         (CASTLE_COUNT, "Siege Workshop counting toward Castle Age", 295)):
    own = routes(dat, dep, 1)
    check(f"{what} ({dep}) can be reached through this civ's copy of {wants}",
          any(dat.techs[t].name == dat.techs[wants].name for t in own),
          [dat.techs[t].name for t in own])

print("\n=== a second civ in the same DAT ===")
build(2, [99])
check("it gets its own unlocks", own_unlock(2, 49) is not None and own_unlock(2, 1258) is not None)
for dep in (CAPPED_RAM, CASTLE_COUNT):
    check(f"{dep} reaches both civs' routes, from one gate",
          routes(dat, dep, 1) and routes(dat, dep, 2)
          and sum(dat.techs[r].name.startswith(_ALT_GATE_PREFIX)
                  for r in dat.techs[dep].required_techs if r >= 0) == 1)

print("\n=== a tree without rams keeps them out ===")
with contextlib.redirect_stdout(io.StringIO()):
    apply_civ(dat, {"alias": "NoRams", "team_bonuses": [], "bonuses": [{"id": 99, "multiplier": 1}],
                    "tree": {"units": [74, 4], "buildings": [49, 103, 12, 87], "techs": []}},
              target_slot=3)
check("no Ram unlock when the tree leaves the Ram out", own_unlock(3, 1258) is None)
check("the Siege Workshop still comes", own_unlock(3, 49) is not None)

print("\n=== the same shape on other cards: their copies reach the techs that need them ===")
# 316 Fortified Church: arrows (931, 943-947) and Imperial armour (942) want the
# Georgian 930; 109 Donjon: Arrowslits (610, 611) want the Sicilian 775.
for slot, card, original, dependents in ((4, 316, 930, (931, 942, 943, 944, 945, 946, 947)),
                                         (5, 109, 775, (610, 611))):
    build(slot, [card])
    for dep in dependents:
        own = routes(dat, dep, slot)
        check(f"card {card}: {dat.techs[dep].name} ({dep}) takes this civ's copy of {original}",
              any(dat.techs[t].name == dat.techs[original].name for t in own),
              [dat.techs[t].name for t in own])

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
