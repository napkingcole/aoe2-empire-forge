#!/usr/bin/env python3
"""A KM civ must not lose techs KM's builder could never tick.  DAT-gated.

The tree sweep reads a node's absence as "the user unticked it" (CLAUDE.md
quirk 15).  KM trees predate some nodes, so their absence carries no intent.
Two of them cost every imported civ real units: Galleon (35) — a bare button
since the naval rework, with the upgrade itself in auto-fire tech 911 that
requires it, as does Fast Fire Ship (246) — and Fishing Lines (906), which
Gillnets now requires.  Found building Unhinged Empires on 2026-09-28.

The same gap exists outside KM: the editor hangs the Galleon off the War
Galley, never off tech 35, so an Empire Forge tree can tick the unit and not
the research.  The upload route built that literally while the wizard route
(KM-shaped by then) did not — the uberdudes drift in test_route_roundtrip.  The
fix is general: a ticked node keeps its unticked prerequisites in any format
(2026-10-08), so both shapes run through the same checks here.

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
from civ_schema import FORMAT_KEY, is_empireforge, is_km_format   # noqa: E402

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

# Galleon, Fire/Fast Fire Ship and Gillnets, none of the techs KM could not
# express — once as KM wrote it, once as the editor saves it.
UNITS, BUILDINGS, TECHS = [13, 539, 21, 442, 529, 532, 83], [45, 68, 109, 199], [65, 101, 102, 103]
km = {
    "alias": "KM Gap Probe", "description": "", "architecture": 2, "language": 0,
    "wonder": -1, "castle": -1,
    "bonuses": [[], [], [], [], []],
    "tree": [UNITS, BUILDINGS, TECHS],
}
ef = {
    "format": FORMAT_KEY, "alias": "EF Gap Probe", "architecture": 2, "language": 0,
    "bonuses": [],
    "tree": {"units": UNITS, "buildings": BUILDINGS, "techs": TECHS},
}
check("KM fixture is KM format", is_km_format(km))
check("EF fixture is Empire Forge format", is_empireforge(ef))
check("fixture has Galleon, Fast Fire Ship and Gillnets but not their prerequisites",
      442 in UNITS and 532 in UNITS and 65 in TECHS and 35 not in TECHS and 906 not in TECHS)

dat = load_dat(str(dat_path))
SLOT = 1


def disabled_for(civ):
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ, target_slot=SLOT)
    tt = dat.effects[dat.civs[SLOT].tech_tree_id].effect_commands
    return {int(c.d) for c in tt if c.type == 102}


for label, civ in (("KM", km), ("EF", ef)):
    disabled = disabled_for(civ)
    for tid, name in [(35, "Galleon"), (911, "Galleon upgrade"),
                      (246, "Fast Fire Ship"), (906, "Fishing Lines"),
                      (65, "Gillnets")]:
        check(f"{label}: {name} ({tid}) is not disabled", tid not in disabled)

# The other direction: an untick with nothing ticked depending on it still
# means "off", and a prerequisite reached only through some other civ's path
# stays off.  Champion 567 has two producers — vanilla 264, and Chronicles'
# own 1174 behind shadow tech 1138 — and only the first one is the civ's.
plain = {**ef, "tree": {"units": [13, 539, 21, 74, 75, 77, 473, 567, 83],
                        "buildings": [12, 45, 109], "techs": [101, 102, 103, 207, 264]}}
disabled = disabled_for(plain)
check("EF without a Galleon: Galleon (35) is still disabled", 35 in disabled)
check("EF with Champions: Paphos Shadow Tech (1138) is still disabled", 1138 in disabled)

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
