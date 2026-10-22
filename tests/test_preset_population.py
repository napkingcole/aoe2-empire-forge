#!/usr/bin/env python3
"""Every custom unique unit costs population, and its stated cost.  DAT-gated.

km_custom_uu._apply_unit_cost's "full" mode wrote the spendable costs and then
blanked every slot after them — population included (CLAUDE.md quirk 14: a
unit has three cost slots, one usually population).  So the 28 presets with a
full cost (Gendarme, Hetaireia, …) trained for no population (found
2026-10-22; inferred from the DAT, not seen in-game).  The Headhunter's KM
post-cost hack then wrote over the slot population moved to.

    venv/bin/python tests/test_preset_population.py
"""
import contextlib
import io
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

import km_custom_uu as kcu                                    # noqa: E402
from civ_appender import apply_civ                            # noqa: E402
from civ_schema import FORMAT_KEY                             # noqa: E402

dat = load_dat(str(dat_path))
built = {}
for idx in sorted(kcu.PRESETS):
    civ = {"format": FORMAT_KEY, "alias": f"Pop {idx}", "architecture": 2, "language": 0,
           "bonuses": [], "unique_unit": {"km_idx": idx},
           "tree": {"units": [83], "buildings": [109, 82], "techs": [101, 102, 103]}}
    with contextlib.redirect_stdout(io.StringIO()):
        r = apply_civ(dat, civ, target_slot=3)
    units = dat.civs[r["civ_index"]].units
    built[idx] = [[(c.type, c.amount, c.flag) for c in units[u].creatable.resource_costs]
                  for u in (r["uu_id"], r["elite_uu_id"])]

print("=== population ===")
no_pop = [kcu.PRESETS[i]["name"] for i, tiers in built.items()
          if not all(any(t == 4 and a > 0 for t, a, _ in costs) for costs in tiers)]
check(f"all {len(built)} custom UUs and their Elites cost population", not no_pop, no_pop)

print("\n=== stated costs ===")
def spend(costs):
    return {t: a for t, a, f in costs if t in (0, 1, 2, 3) and a > 0}
check("Gendarme (a full cost): 95 food 85 gold", spend(built[52][0]) == {0: 95, 3: 85}, built[52][0])
check("Headhunter keeps 75 gold and KM's zero-food entry, beside population",
      built[63][0] == [(3, 75, 1), (4, 1, 0), (0, 0, 1)], built[63][0])
check("Bandit: 100 food (was the game's 300)", spend(built[110][0]) == {0: 100}, built[110][0])
check("Cobra Car: 200 food 200 gold (was free)", spend(built[115][0]) == {0: 200, 3: 200}, built[115][0])
check("...on the Elite too", spend(built[115][1]) == {0: 200, 3: 200}, built[115][1])

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
