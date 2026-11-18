#!/usr/bin/env python3
"""The waypoint flag (#87).

Resource 73, "Waypoint Sprite Graphic ID", holds each civ's rally flag
(Britons 9466, Franks 9467...).  Every custom civ is built from the Britons
template, so every one flew the Britons' flag.  Now the flag is the one
picked, or the architecture's civ's (as the Monk defaults), and the identity
scene can draw it.  DAT-gated.

    venv/bin/python tests/test_waypoint_flag.py
"""
import contextlib
import io
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


from civ_schema import from_draft, to_draft  # noqa: E402

check("saves and loads", to_draft(from_draft({"waypoint_flag": 11})).get("waypoint_flag") == 11)

try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(1 if failures else 0)

import civ_appender as ca  # noqa: E402
import game_sprites  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

FLAG = 73
VIKINGS, TEUTONS = 11, 4
dat = load_dat(str(dat_path))
vik, teu, brit = (int(dat.civs[i].resources[FLAG]) for i in (VIKINGS, TEUTONS, 1))
check("the game gives each civ its own", len({vik, teu, brit}) == 3, (vik, teu, brit))


def build(slot, **extra):
    d = {"alias": "Flag", "architecture": 1, "language": 0, "bonuses": [], "team_bonuses": [],
         "unique_unit": {"km_idx": 2}, **extra}
    with contextlib.redirect_stdout(io.StringIO()):
        ca.apply_civ(dat, _draft_to_civ_def(d), target_slot=slot)
    return int(dat.civs[slot].resources[FLAG])


check("a picked flag: the Vikings'", build(5, waypoint_flag=VIKINGS) == vik)
arch = ca._ARCH_REP_CIVS[0]          # architecture 1, Central European: the Goths
want = int(ca._original_civ(dat, arch).resources[FLAG]) if isinstance(arch, int) else None
got = build(6)
check("none picked: the architecture's civ's, not always the Britons'",
      want is not None and got == want, (got, want, arch))
check("the identity scene can draw a civ's flag",
      game_sprites._scene_graphic(dat, "waypoint_flag", TEUTONS)[0] == teu)

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
