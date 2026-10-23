#!/usr/bin/env python3
"""Monastery skin: the Monastery's look, chosen apart from the architecture.  DAT-gated.

Like the Monk, the Monastery's art is per civ, not per architecture set (Goths
and Teutons share one; Mongols, Huns, Cumans and Khitans build a shrine).
Five units carry it: the Monastery 104, its age versions 30-32 and its rubble
1421 — which the architecture pass never copied, so a custom civ's Monastery
always fell to Britons rubble.

    venv/bin/python tests/test_monastery_skin.py
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

from civ_appender import (MONASTERY_SKIN_OPTIONS, _MONASTERY_RUBBLE,  # noqa: E402
                          _MONASTERY_SKIN_UNITS, apply_civ)
from civ_schema import FORMAT_KEY, from_draft, to_draft      # noqa: E402
from wizard_build import _draft_to_civ_def                    # noqa: E402

dat = load_dat(str(dat_path))
CHRONICLES = {"Achaemenids", "Athenians", "Spartans", "Macedonians", "Thracians", "Puru"}
look = lambda civ: tuple(civ.units[u].standing_graphic[0] for u in (*_MONASTERY_SKIN_UNITS, _MONASTERY_RUBBLE))  # noqa: E731

print("=== the options ===")
heads = {}
for i, c in enumerate(dat.civs[1:], 1):
    heads.setdefault(c.units[104].standing_graphic[0], []).append(c.name)
offered = [dat.civs[o["value"]].units[104].standing_graphic[0] for o in MONASTERY_SKIN_OPTIONS]
check("each option is a different Monastery", len(set(offered)) == len(offered))
uncovered = [names for g, names in heads.items() if g not in offered and not set(names) <= CHRONICLES]
check("every Monastery in the game is offered (Chronicles' aside)", not uncovered, uncovered)

print("\n=== a build ===")


def build(slot, **kw):
    civ = {"format": FORMAT_KEY, "alias": "Monastery Probe", "language": 0, "bonuses": [],
           "tree": {"units": [83], "buildings": [109, 104], "techs": [101, 102, 103]}, **kw}
    d = load_dat(str(dat_path))
    with contextlib.redirect_stdout(io.StringIO()):
        r = apply_civ(d, _draft_to_civ_def(to_draft(civ)), target_slot=slot)
    return d, d.civs[r["civ_index"]]


d, civ = build(1, architecture=2, monastery_skin_building=12)
check("Western European architecture, the Steppe shrine: all five units are the Mongols'",
      look(civ) == look(d._ef_original_civs.get(12, d.civs[12])), (look(civ), look(d.civs[12])))
d, civ = build(1, architecture=5)
aztecs = d.civs[15]
check("no choice: the architecture's own Monastery, rubble included (Mesoamerican = Aztecs')",
      look(civ) == look(aztecs), (look(civ), look(aztecs)))

draft = to_draft({"format": FORMAT_KEY, "alias": "X", "monastery_skin_building": 3})
check("the choice round-trips the civ file", from_draft(draft).get("monastery_skin_building") == 3)

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
