#!/usr/bin/env python3
"""A KM civ must not lose techs KM's builder could never tick.  DAT-gated.

The tree sweep reads a node's absence as "the user unticked it" (CLAUDE.md
quirk 15).  KM trees predate some nodes, so their absence carries no intent.
Two of them cost every imported civ real units: Galleon (35) — a bare button
since the naval rework, with the upgrade itself in auto-fire tech 911 that
requires it, as does Fast Fire Ship (246) — and Fishing Lines (906), which
Gillnets now requires.  Found building Unhinged Empires on 2026-09-28.

    venv/bin/python tests/test_km_import_gaps.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat      # noqa: E402
from civ_appender import apply_civ                  # noqa: E402
from civ_schema import is_km_format                 # noqa: E402

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

# Minimal KM civ: Galleon, Fire/Fast Fire Ship and Gillnets, none of the techs
# KM could not express.
civ = {
    "alias": "KM Gap Probe", "description": "", "architecture": 2, "language": 0,
    "wonder": -1, "castle": -1,
    "bonuses": [[], [], [], [], []],
    "tree": [[13, 539, 21, 442, 529, 532, 83], [45, 68, 109, 199], [65, 101, 102, 103]],
}
check("fixture is KM format", is_km_format(civ))
check("fixture has Galleon, Fast Fire Ship and Gillnets but not the techs KM lacked",
      442 in civ["tree"][0] and 532 in civ["tree"][0] and 65 in civ["tree"][2]
      and 35 not in civ["tree"][2] and 906 not in civ["tree"][2])

dat = load_dat(str(dat_path))
SLOT = 1
with contextlib.redirect_stdout(io.StringIO()):
    apply_civ(dat, civ, target_slot=SLOT)
tt = dat.effects[dat.civs[SLOT].tech_tree_id].effect_commands
disabled = {int(c.d) for c in tt if c.type == 102}

for tid, name in [(35, "Galleon"), (911, "Galleon upgrade"),
                  (246, "Fast Fire Ship"), (906, "Fishing Lines"),
                  (65, "Gillnets")]:
    check(f"{name} ({tid}) is not disabled", tid not in disabled)

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
