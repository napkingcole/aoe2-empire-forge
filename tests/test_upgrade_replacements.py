#!/usr/bin/env python3
"""The Legionary and Savar replace the upgrade they share a button with.  DAT-gated.

Legionary and Two-Handed Swordsman are both Barracks button 6, Savar and Paladin
both Stable button 7, and the game shows one.  The cards (and the tree nodes
that derive them) unlocked the replacement but never switched off the vanilla
upgrade, so players got Two-Handed Swordsman and Champion (#91).  The Romans
and Persians switch theirs off with 895 and 527.

    venv/bin/python tests/test_upgrade_replacements.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dat_reader import find_game_dat, load_dat         # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f"\n       {extra}"))
    failures += not cond


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

import fu_stats                                         # noqa: E402
from civ_overrides import apply_civ_with_overrides     # noqa: E402
from civ_schema import to_draft                         # noqa: E402
from wizard_build import _draft_to_civ_def              # noqa: E402
from build_qa_mod_branch import B, civ, preset, tree_from   # noqa: E402

dat = load_dat(str(dat_path))
TREE = tree_from("FRANKS.json")                         # full Militia and Knight lines
CASES = [  # (how, bonuses, extra tree units, line base, replacement, vanilla upgrade techs)
    ("Legionary card", B(416), [], 74, 1793, {217, 264}),
    ("Legionary tree node", [], [1793], 74, 1793, {217, 264}),
    ("Savar card", B(417), [], 38, 1813, {265}),
]
for slot, (how, bonuses, extra, base, want, vanilla) in enumerate(CASES, start=5):
    c = civ(f"Replace {slot}", "R", unique_unit={"km_idx": 0, "name": "", "description": ""},
            bonuses=bonuses, castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
            tree={**TREE, "units": TREE["units"] + extra})
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ_with_overrides(dat, _draft_to_civ_def(to_draft(c)), slot)
    sim = fu_stats.Simulation(dat, slot)
    check(f"{how}: the line ends as {want}", sim.final_unit(base) == want, sim.final_unit(base))
    check(f"{how}: the vanilla upgrade it shares a button with is gone",
          not vanilla & set(sim.techs), sorted(vanilla & set(sim.techs)))

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
