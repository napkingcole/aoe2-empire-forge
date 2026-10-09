#!/usr/bin/env python3
"""A civ can set its Elite unique-unit upgrade's cost and research time (#68).

unique_unit.elite_upgrade = {cost: {food, wood, stone, gold}, time}; zero means
"keep the game's", as for the UT cost.  _override_ut_costs writes it onto
km_uu_elite_tech_id — the civ's own copy of the upgrade, so the original that
other civs research is untouched.  Both civ shapes reach it: the upload route
passes the saved file, the wizard route the draft.  DAT-gated.

    venv/bin/python tests/test_elite_upgrade_cost.py
"""
import contextlib
import copy
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from civ_schema import FORMAT_KEY, to_draft                 # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

from civ_appender import apply_civ, _KM_UU_TECHS            # noqa: E402
from civ_overrides import _override_ut_costs                # noqa: E402

dat = load_dat(str(dat_path))
RES = {0: "food", 1: "wood", 2: "stone", 3: "gold"}


def cost_time(tech):
    cost = {RES[c.type]: c.amount for c in tech.resource_costs if c.type in RES and c.amount > 0}
    time = next(l.research_time for l in tech.research_locations if l.location_id >= 0)
    return cost, time


def build(slot, uu, elite_upgrade, shape):
    civ = {"format": FORMAT_KEY, "alias": f"Elite {slot}", "architecture": 2, "language": 0,
           "bonuses": [], "unique_unit": {**uu, **({"elite_upgrade": elite_upgrade} if elite_upgrade else {})},
           "tree": {"units": [83, 74, 4, 38], "buildings": [12, 87, 101, 82, 109, 70],
                    "techs": [101, 102, 103]}}
    src = civ if shape == "upload" else to_draft(civ)
    with contextlib.redirect_stdout(io.StringIO()):
        result = apply_civ(dat, copy.deepcopy(civ), target_slot=slot)
        _override_ut_costs(dat, result, src)
    return dat.techs[result["km_uu_elite_tech_id"]], result["km_uu_elite_tech_id"]


TK_ELITE = _KM_UU_TECHS[3][1]
vanilla = cost_time(dat.techs[TK_ELITE])
WANT = {"cost": {"food": 600, "wood": 0, "stone": 0, "gold": 300}, "time": 35}

print("=== Teutonic Knight (vanilla UU) ===")
for slot, shape in ((5, "upload"), (6, "wizard")):
    tech, tid = build(slot, {"km_idx": 3}, WANT, shape)
    check(f"{shape}: the civ's own copy, not the original {TK_ELITE}", tid != TK_ELITE, f"tid={tid}")
    check(f"{shape}: cost and time as set", cost_time(tech) == ({"food": 600, "gold": 300}, 35),
          f"{cost_time(tech)}")
check("the original upgrade other civs research is unchanged",
      cost_time(dat.techs[TK_ELITE]) == vanilla, f"{cost_time(dat.techs[TK_ELITE])} vs {vanilla}")

tech, _ = build(7, {"km_idx": 3}, None, "upload")
check("no elite_upgrade keeps the game's cost and time", cost_time(tech) == vanilla, f"{cost_time(tech)}")
tech, _ = build(8, {"km_idx": 3}, {"cost": {"food": 0}, "time": 0}, "upload")
check("an all-zero elite_upgrade also keeps them", cost_time(tech) == vanilla, f"{cost_time(tech)}")
tech, _ = build(9, {"km_idx": 3}, {"time": 20}, "wizard")
check("time alone keeps the game's cost", cost_time(tech) == (vanilla[0], 20), f"{cost_time(tech)}")

print("\n=== a KM-custom UU ===")
custom = next(i for i in range(60, 200) if i not in _KM_UU_TECHS)
tech, _ = build(10, {"km_idx": custom}, WANT, "upload")
check(f"KM-custom UU {custom}: cost and time as set", cost_time(tech) == ({"food": 600, "gold": 300}, 35),
      f"{cost_time(tech)}")

# The UT research time had the same field to get wrong: it was written to a
# tech-level `research_time` genieutils' Tech doesn't have, so it never reached
# the DAT.  Checked here against the real Tech, not a stand-in.
print("\n=== a custom UT research time reaches the DAT ===")
ut_civ = {"format": FORMAT_KEY, "alias": "UT time", "architecture": 2, "language": 0,
          "bonuses": [], "unique_unit": {"km_idx": 3},
          "castle_ut": {"mode": "custom", "name": "T", "cost": {"food": 1}, "time": 77, "effects": [{"id": 1, "multiplier": 1}]},
          "tree": {"units": [83], "buildings": [82, 109, 70], "techs": [101, 102, 103]}}
with contextlib.redirect_stdout(io.StringIO()):
    r = apply_civ(dat, copy.deepcopy(ut_civ), target_slot=11)
    _override_ut_costs(dat, r, ut_civ)
check("Castle UT research time is 77 at its research location",
      cost_time(dat.techs[r["castle_ut_tech_id"]])[1] == 77,
      f"{cost_time(dat.techs[r['castle_ut_tech_id']])}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
