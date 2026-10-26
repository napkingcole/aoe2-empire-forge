#!/usr/bin/env python3
"""Wooden Castles, a Castle unique tech (preset 69).  DAT-gated.

The user's idea after the Slavs' Detinets (2026-10-24): on research every
Castle, built and to come, becomes a Wooden Fort costing 300 stone + 500 wood,
keeping the Castle's HP, arrows and build time.  No vanilla tech does it, so it
is built (civ_appender._UT_BUILT): a copy of this civ's Castle wearing the Fort,
and EC_UPGRADE 82 -> that copy — the Thracians' own bonus upgrades their Castle
the same way (82 -> 2418), and units still train at "82" after it, as after any
age-up's building upgrade.  Saved and read back.

    venv/bin/python tests/test_wooden_castles_ut.py
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
WOODEN = ca._WOODEN_CASTLE_UT

print("the preset")
check("offered in the Castle pool, built here (no vanilla source)",
      ("castle", WOODEN) in ca._UT_BUILT and ca.ut_source_tech(WOODEN, "castle") is None)
check("this game can (it has the 4x4 Wooden Fort)", ca._UT_BUILT[("castle", WOODEN)]["available"](dat))
import build_all                                    # noqa: E402
check("named", build_all._UNIQUE_CASTLE_STRINGS[WOODEN].startswith("Wooden Castles"))
import bonus_names                                  # noqa: E402
check("not listed as unsupported", WOODEN not in {u["id"] for u in bonus_names.unsupported_unique_techs(True)})

n_units = len(dat.civs[0].units)
SLOT, SLOT2, PLAIN = 5, 6, 7
castle_pick = {SLOT: -1, SLOT2: [c.name for c in dat.civs].index("Japanese") - 1, PLAIN: -1}
res = {}
for slot, ut in ((SLOT, [[WOODEN, 1]]), (SLOT2, [[WOODEN, 1]]), (PLAIN, [])):
    civ_def = {"alias": f"Wooden UT {slot}", "description": "", "architecture": 2, "language": 0,
               "wonder": -1, "castle": castle_pick[slot], "bonuses": [[], [3], ut, [], []],
               "tree": [[4], [82, 109], []]}
    with contextlib.redirect_stdout(io.StringIO()):
        res[slot] = ca.apply_civ(dat, civ_def, target_slot=slot)

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "empires2_x2_p1.dat"
    out.write_bytes(save_bytes(dat))
    back = load_dat(str(out))

new = getattr(dat, "_ef_wooden_castle_unit", None)
print("the Wooden Castle unit (read back from the saved DAT)")
check("one new unit, appended to every civ, shared by both civs that took the tech",
      new == n_units and all(len(c.units) == len(back.civs[0].units) for c in back.civs), (new, n_units))
fort = back.civs[0].units[ca._WOODEN_FORT]
for slot in (SLOT, SLOT2):
    w, c = back.civs[slot].units[new], back.civs[slot].units[82]
    check(f"slot {slot}: wears the Wooden Fort", (w.standing_graphic, w.dying_graphic, w.undead_graphic,
          w.dead_unit_id, w.building.snow_graphic_id) == (fort.standing_graphic, fort.dying_graphic,
          fort.undead_graphic, fort.dead_unit_id, fort.building.snow_graphic_id))
    check(f"slot {slot}: costs 300 stone + 500 wood",
          [(r.type, r.amount) for r in w.creatable.resource_costs if r.flag][:2] == [(2, 300), (1, 500)])
    check(f"slot {slot}: keeps this civ's Castle HP, arrows, build time and button",
          (w.hit_points, w.type_50.displayed_attack, [(t.unit_id, t.button_id, t.train_time) for t in w.creatable.train_locations])
          == (c.hit_points, c.type_50.displayed_attack, [(t.unit_id, t.button_id, t.train_time) for t in c.creatable.train_locations]))
    check(f"slot {slot}: is its own unit, named as the Castle", (w.id, w.base_id, w.copy_id) == (new, new, new)
          and w.language_dll_name == c.language_dll_name)


def ut_cmds(slot):
    tid = res[slot]["castle_ut_tech_id"]
    return [(c.type, int(c.a), int(c.b)) for c in back.effects[back.techs[tid].effect_id].effect_commands]


print("the tech")
for slot in (SLOT, SLOT2):
    check(f"slot {slot}: upgrades the Castle into it, and does nothing else",
          ut_cmds(slot) == [(3, 82, new)], ut_cmds(slot))
check("a civ without it keeps its stone Castle", back.civs[PLAIN].units[82].standing_graphic != fort.standing_graphic)

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
