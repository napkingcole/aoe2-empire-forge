#!/usr/bin/env python3
"""A destroyed building leaves its own architecture's rubble.  DAT-gated.

Every building's rubble is a separate unit (its dead_unit_id, class 14 — or 11
for a few Dark Age ones) with per-civ art.  The architecture pass copied the
buildings but never followed them to their rubble, so every custom civ left the
Western European template's rubble (2026-10-24; the Monastery's, 1421, was the
one instance found and fixed in 2.7.0).  The Castle's and the Wonder's rubble
follow the Castle and Wonder picks.  Saved and read back.

    venv/bin/python tests/test_building_rubble.py
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
from civ_appender import apply_civ, _ARCH_REP_CIVS, _ARCH_BUILDING_CLASSES   # noqa: E402
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


RUBBLE_CLASSES = {11, 14}


def look(u):
    return (u.standing_graphic, u.dying_graphic, u.undead_graphic)


# (label, architecture value, castle pick, wonder pick, slot) — picks are KM
# indices (DAT civ - 1).
EAST_ASIAN, AFRICAN = 3, 9
CASES = [("East Asian", EAST_ASIAN, idx["Mayan"] - 1, idx["Tupi"] - 1, 30),
         ("African", AFRICAN, -1, -1, 31)]
for label, arch, castle, wonder, slot in CASES:
    civ = {"format": FORMAT_KEY, "alias": label, "architecture": arch, "language": 0,
           "castle": castle, "wonder": wonder, "bonuses": [],
           "tree": {"units": [83], "buildings": [109, 70, 12, 82], "techs": [101, 102, 103]}}
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ, target_slot=slot)

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "empires2_x2_p1.dat"
    out.write_bytes(save_bytes(dat))
    back = load_dat(str(out))
britons = back.civs[1].units

for label, arch, castle, wonder, slot in CASES:
    print(f"{label} architecture (read back from the saved DAT)")
    rep = back.civs[_ARCH_REP_CIVS[arch - 1]].units
    ours = back.civs[slot].units
    wrong, differs = [], 0
    for b, u in enumerate(rep):
        if u is None or u.class_ not in _ARCH_BUILDING_CLASSES or b in (82, 276) or b == 104 or b in (30, 31, 32):
            continue
        d = u.dead_unit_id
        if not 0 <= d < len(rep) or rep[d] is None or rep[d].class_ not in RUBBLE_CLASSES:
            continue
        # The Castle's and Wonder's rubble follow their picks (checked below),
        # also where another building shares it (the Thracian Fort, 1430).
        if d in (rep[82].dead_unit_id, rep[276].dead_unit_id):
            continue
        differs += look(rep[d]) != look(britons[d])
        if look(ours[d]) != look(rep[d]):
            wrong.append((b, d, rep[d].name))
    check(f"every building leaves {label} rubble ({differs} of them differ from Western European)",
          not wrong and differs > 0, wrong[:8])
    for b, name, pick in ((82, "Castle", castle), (276, "Wonder", wonder)):
        src = back.civs[pick + 1 if pick >= 0 else _ARCH_REP_CIVS[arch - 1]].units
        d = src[b].dead_unit_id
        check(f"the {name} leaves the {name.lower()} source's rubble",
              look(ours[d]) == look(src[d]) and look(src[d]) != look(britons[d]))

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
