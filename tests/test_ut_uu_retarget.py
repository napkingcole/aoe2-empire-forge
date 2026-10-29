#!/usr/bin/env python3
"""A unique tech that names another civ's unique unit is retargeted onto ours,
but never twice onto one unit.  DAT-gated.

Zealotry gives +20 HP to each camel, the Camel Archer and the Mameluke among
them.  The Mameluke's commands are retargeted to the civ's own unique unit, so
a Camel Archer civ got +20 as itself and +20 as the Mameluke: +40 (#99, found
in the stats preview, and real in the DAT).

    venv/bin/python tests/test_ut_uu_retarget.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dat_reader import find_game_dat, load_dat          # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f"\n       {extra}"))
    failures += not cond


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

from civ_overrides import apply_civ_with_overrides     # noqa: E402
from civ_schema import to_draft                         # noqa: E402
from wizard_build import _draft_to_civ_def              # noqa: E402
from build_qa_mod_branch import civ, preset             # noqa: E402

CAMEL_ARCHER, LONGBOWMAN, ZEALOTRY = 26, 0, 48
dat = load_dat(str(dat_path))


def hp_adds(slot, km_idx):
    c = civ(f"Retarget {slot}", "R", unique_unit={"km_idx": km_idx, "name": "", "description": ""},
            castle_ut=preset(ZEALOTRY, "castle"), imperial_ut=preset(0, "imperial"))
    with contextlib.redirect_stdout(io.StringIO()):
        r, info = apply_civ_with_overrides(dat, _draft_to_civ_def(to_draft(c)), slot)
    cmds = dat.effects[dat.techs[r["castle_ut_tech_id"]].effect_id].effect_commands
    return [[c.d for c in cmds if c.type == 4 and int(c.a) == uid and int(c.c) == 0]
            for uid in (info["unit_id"], info["elite_id"])]


check("Zealotry gives the Camel Archer +20 HP once, both tiers (#99)",
      hp_adds(5, CAMEL_ARCHER) == [[20.0], [20.0]], hp_adds(5, CAMEL_ARCHER))
check("another unique unit still gets the Mameluke's +20 HP",
      hp_adds(6, LONGBOWMAN) == [[20.0], [20.0]], hp_adds(6, LONGBOWMAN))

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
