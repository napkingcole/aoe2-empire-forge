#!/usr/bin/env python3
"""A Monk skin speaks with a voice of its own gender (#58).  DAT-gated.

A civ's Monk voice has one gender, the voice civ's: 13 civs' vanilla Monks are
women (they select with priestess sound 597), and their Monk lines are female
recordings; everyone else's are male.  A skin of the other gender used to keep
the clone's Monk lines, so a female Monk spoke British in a man's voice.  Now it
takes the villager lines of its own gender in the same language — the Jadwiga
precedent — and a skin that matches its voice civ is left alone.

    venv/bin/python tests/test_monk_voice.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat              # noqa: E402
from civ_appender import apply_civ, _PRIESTESS_SELECT        # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)
dat = load_dat(str(dat_path))
idx = {c.name: i for i, c in enumerate(dat.civs)}
BRITONS, INCAS, MAPUCHE = idx["British"], idx["Incas"], idx["Mapuche"]

female = {c.name for c in dat.civs if c.units[125] is not None
          and c.units[125].selection_sound == _PRIESTESS_SELECT}
check("Incas and Mapuche Monks are female, Britons' male",
      {"Incas", "Mapuche"} <= female and "British" not in female, f"{sorted(female)}")

MONK = dat.civs[1].units[125]
SOUNDS = {"monk": (MONK.selection_sound, MONK.bird.move_sound),
          "male villager": (dat.civs[1].units[83].selection_sound,
                            dat.civs[1].units[83].bird.move_sound),
          "female villager": (dat.civs[1].units[293].selection_sound,
                              dat.civs[1].units[293].bird.move_sound)}


def sounds(slot, uid):
    u = dat.civs[slot].units[uid]
    return u.selection_sound, u.bird.move_sound


# (label, monk skin civ, voice civ, target slot, expected voice)
CASES = [
    ("female skin, male voice (the report)", INCAS, BRITONS, 5, "female villager"),
    ("male skin, female voice",              BRITONS, MAPUCHE, 6, "male villager"),
    ("female skin, female voice",            INCAS, MAPUCHE, 7, "monk"),
    ("male skin, male voice",                BRITONS, BRITONS, 8, "monk"),
    # The voice civ's own slot: read after the overwrite it would be the
    # Britons clone, a male Monk, and the female skin would go unmatched.
    ("replacing the voice civ's own slot",   INCAS, MAPUCHE, MAPUCHE, "monk"),
    ("...and with a male skin",              BRITONS, MAPUCHE, MAPUCHE, "male villager"),
]
for label, skin, voice, slot, want in CASES:
    civ = {"format": FORMAT_KEY, "alias": label[:20], "architecture": 2,
           "language": voice - 1, "monk_skin": skin, "bonuses": [],
           "tree": {"units": [83, 125], "buildings": [104, 109, 70], "techs": [101, 102, 103]}}
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ, target_slot=slot)
    for uid in (125, 286):
        got = sounds(slot, uid)
        check(f"{label}: unit {uid} speaks with the {want} lines", got == SOUNDS[want],
              f"got {got}, {want} is {SOUNDS[want]}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
