#!/usr/bin/env python3
"""The scenario editor's Priest and Pagan Priest as Monk looks.  DAT-gated.

A player asked for them (2026-10-24).  A Monk look is three units: the Monk
(125), its corpse (134) and the Monk carrying a relic (286).  Both priests have
all three — Priest 1023 / corpse 1024 / relic 1025, Pagan Priest 1940 / 1024 /
1941 — and the Monk's 30-task layout, so the heal and convert graphics line up.
The value is the priest's unit id (civ_appender.SCENARIO_MONK_SKINS).  Saved
and read back: a field the lazy DAT writer missed would pass in memory only.

    venv/bin/python tests/test_scenario_monk_skins.py
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat                    # noqa: E402
from dat_lazy import save_bytes                                   # noqa: E402
from civ_appender import (apply_civ, MONK_SKIN_OPTIONS, SCENARIO_MONK_SKINS,   # noqa: E402
                          monk_skin_units)
from civ_schema import FORMAT_KEY                                 # noqa: E402

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
dat = load_dat(str(dat_path))
idx = {c.name: i for i, c in enumerate(dat.civs)}

print("the options")
check("Priest and Pagan Priest are offered", {1023, 1940} <= {o["value"] for o in MONK_SKIN_OPTIONS})
check("...as unit ids no civ index can reach", all(v >= len(dat.civs) for v in SCENARIO_MONK_SKINS))
for v, name in ((1023, "PRIEST"), (1940, "PGPRIEST")):
    got = monk_skin_units(dat, v)
    check(f"{name}: Monk, corpse and relic carrier are in this game",
          got is not None and got[0].name == name and [u.class_ for u in got] == [18, 11, 43])
    check(f"{name}: the Monk's task layout, action for action",
          [t.action_type for t in got[0].bird.tasks] == [t.action_type for t in dat.civs[1].units[125].bird.tasks])
check("an unknown value is no skin", monk_skin_units(dat, 999) is None and monk_skin_units(dat, "x") is None)

# (label, skin, voice civ, slot).  Mapuche Monks are female: a male priest
# speaking Mapuche takes the male villager lines, as a Briton Monk would.
CASES = [("Priest", 1023, idx["British"], 5), ("Pagan Priest", 1940, idx["Mapuche"], 6)]
for label, skin, voice, slot in CASES:
    civ = {"format": FORMAT_KEY, "alias": label, "architecture": 2,
           "language": voice - 1, "monk_skin": skin, "bonuses": [],
           "tree": {"units": [83, 125], "buildings": [104, 109, 70], "techs": [101, 102, 103]}}
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ, target_slot=slot)

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "empires2_x2_p1.dat"
    out.write_bytes(save_bytes(dat))
    back = load_dat(str(out))

for label, skin, voice, slot in CASES:
    print(f"{label} (read back from the saved DAT)")
    src = monk_skin_units(back, skin)
    for uid, s in zip((125, 134, 286), src):
        d = back.civs[slot].units[uid]
        check(f"unit {uid} wears {s.name}: standing, dying, decay",
              (d.standing_graphic, d.dying_graphic, d.undead_graphic)
              == (s.standing_graphic, s.dying_graphic, s.undead_graphic))
    m, s = back.civs[slot].units[125], src[0]
    check("the Monk walks, converts and heals in it, with its button icon",
          m.dead_fish.walking_graphic == s.dead_fish.walking_graphic
          and m.type_50.attack_graphic == s.type_50.attack_graphic
          and [t.proceeding_graphic_id for t in m.bird.tasks] == [t.proceeding_graphic_id for t in s.bird.tasks]
          and m.icon_id == s.icon_id)
    check("...and keeps the Monk's own stats", m.hit_points == back.civs[1].units[125].hit_points)
male_villager = back.civs[1].units[83].selection_sound
check("a (male) priest speaking Mapuche uses the male villager lines",
      back.civs[6].units[125].selection_sound == male_villager)

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
