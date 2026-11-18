#!/usr/bin/env python3
"""Card 81, "No buildings required to advance ages or unlock buildings" (#126).

The Khmer requirement (tech 638) is one OR-option in seven techs: the three age
gates and the Mill, Barracks/Donjon, Blacksmith and Farms nodes.  The card used
to reach only the age gates, so a Barracks was still needed for the Stable and
Range; and it wrote straight into those techs' six slots, so the fourth civ in
a mod with the card stopped the build.  Every civ's copy of 638 must now satisfy
all seven, however many civs take it.  DAT-gated.

    venv/bin/python tests/test_khmer_card.py
"""
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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
civ_file = ROOT / "my_civs" / "19_Cannoneers.json"
if dat_path is None or not civ_file.exists():
    print("  skip  no game DAT (or my_civs/19_Cannoneers.json) found")
    sys.exit(0)

from civ_overrides import apply_civ_with_overrides  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

KHMER_REQ = 638
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]
dat = load_dat(str(dat_path))
dependents = [i for i, t in enumerate(dat.techs) if KHMER_REQ in t.required_techs]
check("the game links the Khmer requirement into seven techs", len(dependents) == 7, dependents)


def satisfiers(tid, seen=None):
    """Techs that satisfy `tid`'s requirement as one OR-option, through gates."""
    seen = seen or set()
    out = set()
    for r in dat.techs[tid].required_techs:
        if r < 0 or r in seen:
            continue
        seen.add(r)
        out.add(r)
        if dat.techs[r].name.startswith("EF alt-prereq gate"):
            out |= satisfiers(r, seen)
    return out


SLOTS = (1, 2, 3, 4, 5)
copies = {}
for slot in SLOTS:
    draft = {"alias": f"Khmerish {slot}", "architecture": 2, "language": 0,
             "bonuses": [{"id": 81, "multiplier": 1}], "team_bonuses": [],
             "unique_unit": {"km_idx": 2},
             "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
             "imperial_ut": {"mode": "vanilla", "effects": [{"id": 4, "multiplier": 1}]},
             "tree": {"units": units, "buildings": buildings, "techs": techs}}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            apply_civ_with_overrides(dat, _draft_to_civ_def(draft), slot, draft)
    except RuntimeError as e:
        check(f"civ {slot} with the card builds", False, e)
        break
    copies[slot] = next((i for i, t in enumerate(dat.techs)
                         if t.name == "C-Bonus, No building requirement" and t.civ == slot), None)
check("five civs in one mod take the card", len(copies) == len(SLOTS) and None not in copies.values(),
      copies)

names = {d: dat.techs[d].name for d in dependents}
for d in dependents:
    sat = satisfiers(d)
    missing = [s for s, c in copies.items() if c not in sat]
    check(f"every civ's copy opens {names[d]}", not missing, f"missing for civs {missing}")
    check(f"...and the Khmer keep theirs ({names[d]})", KHMER_REQ in dat.techs[d].required_techs)

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
