#!/usr/bin/env python3
"""Camel Riders without Camel Scouts (#110).

"Make Camels Available" (235) enables the Camel Scout at the Castle Age and
860 turns it straight into the Camel Rider: that is how every vanilla camel
civ but the Gurjaras (858, Feudal Camel Scouts) has camels.  A tree with the
Rider line and no Scout must keep 235: the sweep used to switch it off as the
Scout's make-avail, beside the tree's own unlock of it.  DAT-gated.

    venv/bin/python tests/test_camel_riders.py
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
from retired_cards import TREE_VERSION  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

SCOUT, RIDER, HEAVY = 1755, 329, 330
MAKE_CAMELS, FEUDAL_SCOUTS = 235, 858
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]


def build(tree_units):
    dat = load_dat(str(dat_path))
    draft = {"tree_version": TREE_VERSION, "alias": "Camels", "architecture": 2, "language": 0,
             "bonuses": [], "team_bonuses": [], "unique_unit": {"km_idx": 2},
             "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
             "imperial_ut": {"mode": "vanilla", "effects": [{"id": 4, "multiplier": 1}]},
             "tree": {"units": tree_units, "buildings": buildings, "techs": techs}}
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ_with_overrides(dat, _draft_to_civ_def(draft), 1, draft)
    tt = dat.effects[dat.civs[1].tech_tree_id].effect_commands
    return ({int(c.a) for c in tt if c.type == 8}, {int(c.d) for c in tt if c.type == 102})


base = [u for u in units if u not in (SCOUT, RIDER, HEAVY)]
on, off = build(base + [RIDER, HEAVY])
check("Riders without Scouts: Make Camels Available is unlocked", MAKE_CAMELS in on)
check("...and not also switched off", MAKE_CAMELS not in off)
check("...and no Feudal Camel Scouts (the Gurjaras' 858 stays theirs)", FEUDAL_SCOUTS not in on)
on, off = build(base)
check("no camels at all: Make Camels Available is switched off", MAKE_CAMELS in off and MAKE_CAMELS not in on,
      (MAKE_CAMELS in on, MAKE_CAMELS in off))

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
