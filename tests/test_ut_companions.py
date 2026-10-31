#!/usr/bin/env python3
"""A preset UT's vanilla companion techs fire for our copy of it.  DAT-gated.

Many unique techs have a second half that waits for the UT and an ordinary
upgrade: Svan Towers + Chemistry, the Thalassocracy arrow techs, Greek Fire,
Citadels, Rocketry and Ming-Kuang Armor + Chemistry, Kshatriyas + Supplies.
They name the vanilla UT, and ours is a new tech, so none fired: Svan Towers
gave the Fortified Church nothing (seen in game 2026-10-31).  Global companions
take our UT through the alt-prereq gate; civ-gated ones (Paper Money's lumber
halves, Torsion + Chemistry, Imperial Nomads) are copied for the civ.

    venv/bin/python tests/test_ut_companions.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat                    # noqa: E402
from civ_appender import (_ALT_GATE_PREFIX, _KM_CASTLE_UT_TECHS,   # noqa: E402
                          _KM_IMP_UT_TECHS, apply_civ)

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
N = len(dat.techs)


def dependents(src):
    return [i for i in range(N) if src in dat.techs[i].required_techs
            and not dat.techs[i].name.startswith("[FTT]")]


def preset(idx, tier):
    return {"mode": "vanilla", "vanilla_km_idx": idx, "name": "", "description": "",
            "effects": [{"id": idx, "multiplier": 1, "tier": tier}]}


def our_ut(slot, tier):
    return next(i for i, t in enumerate(dat.techs) if t.civ == slot
                and t.name.endswith("Castle UT" if tier == "castle" else "Imperial UT"))


def reaches(dep, slot, ut, src):
    """Can this civ's UT satisfy `dep` where it names `src`?"""
    gates = [r for r in dat.techs[dep].required_techs
             if r >= 0 and dat.techs[r].name.startswith(_ALT_GATE_PREFIX)]
    if any(ut in dat.techs[g].required_techs for g in gates):
        return True
    name = dat.techs[dep].name                    # a civ-gated companion: our own copy
    return any(t.civ == slot and t.name == name and ut in t.required_techs
               and src not in t.required_techs for t in dat.techs[N:])


cases = [(k, "castle", v) for k, v in _KM_CASTLE_UT_TECHS.items() if dependents(v)] + \
        [(k, "imperial", v) for k, v in _KM_IMP_UT_TECHS.items() if dependents(v)]
print(f"{len(cases)} presets have companions:",
      ", ".join(dat.techs[v].name for _, _, v in cases))
castles = [c for c in cases if c[1] == "castle"]
imps = [c for c in cases if c[1] == "imperial"]
for slot, (c, i) in enumerate(zip(castles + [None] * len(imps), imps + [None] * len(castles)), start=1):
    if c is None and i is None:
        break
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, {"alias": f"Comp{slot}", "bonuses": [], "team_bonuses": [],
                        "castle_ut": preset(c[0], "castle") if c else None,
                        "imperial_ut": preset(i[0], "imperial") if i else None}, target_slot=slot)
    for case in (c, i):
        if case is None:
            continue
        _, tier, src = case
        ut = our_ut(slot, tier)
        for dep in dependents(src):
            check(f"{dat.techs[src].name}: {dat.techs[dep].name} ({dep}) fires for our UT",
                  reaches(dep, slot, ut, src))

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
