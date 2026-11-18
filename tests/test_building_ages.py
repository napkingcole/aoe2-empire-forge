#!/usr/bin/env python3
"""Buildings available an age earlier, from the tree's "Available from" (#122).

The Cumans have their Siege Workshop in the Feudal Age; any building with a
make-available tech can now move the same way (civ_overrides._apply_age_moves,
the Armenians' shape: a civ-owned trigger at the earlier age in a spare slot of
the tech's requirements).  A regional building (the Feitoria) moves its civ's
own copy at build time (the Feitoria and Caravanserai aren't tree buildings,
so they have no panel to move them from).  The F2 tree draws the building in
its new age.  DAT-gated.

    venv/bin/python tests/test_building_ages.py
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

from civ_overrides import apply_civ_with_overrides, enabling_tech  # noqa: E402
from retired_cards import TREE_VERSION  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

SLOT = 1
WORKSHOP, UNIVERSITY, MONASTERY = 49, 209, 104
FEUDAL = 101
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]
dat = load_dat(str(dat_path))
draft = {"tree_version": TREE_VERSION, "alias": "Early", "architecture": 2, "language": 0,
         "bonuses": [], "team_bonuses": [], "unique_unit": {"km_idx": 2},
         "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
         "imperial_ut": {"mode": "vanilla", "effects": [{"id": 4, "multiplier": 1}]},
         "tree": {"units": units, "buildings": buildings, "techs": techs},
         "unit_edits": {str(WORKSHOP): {"age": 2}, str(UNIVERSITY): {"age": 2}, str(MONASTERY): {"age": 2}}}
with contextlib.redirect_stdout(io.StringIO()):
    r, _ = apply_civ_with_overrides(dat, _draft_to_civ_def(draft), SLOT, draft)


def earlier(building, age):
    """The building's enabling tech now has a civ-owned trigger at `age`."""
    tid = enabling_tech(dat, SLOT, building)
    if tid is None:
        return None
    trig = [q for q in dat.techs[tid].required_techs if q >= 0 and dat.techs[q].civ == SLOT
            and "(earlier)" in dat.techs[q].name]
    return bool(trig) and age in dat.techs[trig[0]].required_techs


check("Siege Workshop in the Feudal Age, as the Cumans'", earlier(WORKSHOP, FEUDAL), r["warnings"])
check("University in the Feudal Age", earlier(UNIVERSITY, FEUDAL), r["warnings"])
check("Monastery in the Feudal Age", earlier(MONASTERY, FEUDAL), r["warnings"])
check("recorded as buildings, for the F2 tree",
      {k: v for k, v in r.get("age_moves", {}).items() if k.startswith("Building:")}
      == {f"Building:{WORKSHOP}": 2, f"Building:{UNIVERSITY}": 2, f"Building:{MONASTERY}": 2}, r.get("age_moves"))

ct = Path(dat_path).parent / "CivTechTrees"
bj = next((p for p in ct.glob("*.json") if p.stem.lower() == "britons"), None) if ct.exists() else None
if bj is not None:
    from build_civ import _patch_per_civ_techtree
    with contextlib.redirect_stdout(io.StringIO()):
        out = json.loads(_patch_per_civ_techtree(bj, _draft_to_civ_def(draft), dat, SLOT, civ_result=r))
    ages = {n["Node ID"]: n["Age ID"] for n in out["civ_techs_buildings"] if n["Node ID"] in (WORKSHOP, UNIVERSITY, MONASTERY)}
    check("the F2 tree draws them in the Feudal Age", ages == {WORKSHOP: 2, UNIVERSITY: 2, MONASTERY: 2}, ages)

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
