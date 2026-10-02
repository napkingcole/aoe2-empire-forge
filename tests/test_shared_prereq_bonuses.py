#!/usr/bin/env python3
"""Bonuses that re-point a shared tech's prerequisites must work for EVERY civ
in a mod, not just the first few.  DAT-gated.

282 (Winged Hussar), 360 (Castle Age Heavy Cav Archer) and 105 (eco upgrades one
age earlier) copy a civ-gated trigger for our civ and thread the copy back into
the global tech that named the original (CLAUDE.md quirk 9).  That global tech
has six required_techs slots and is shared by every civ in the mod.  Writing each
civ's copy straight into it spent one slot per civ: Winged Hussar (786) has two
spare, so the third civ with 282 got nothing — the copied trigger had already
disabled its Hussar.  Found building Unhinged Empires (12 civs) on 2026-09-28,
where Budget Bois lost the Hussar and Stompy Bois lost bonus 105.

The fix routes every copy through one OR-gate per trigger.  This builds more
civs than any tech has slots and checks, by evaluating the prerequisite graph,
that each one can still reach the dependents.

    venv/bin/python tests/test_shared_prereq_bonuses.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat      # noqa: E402
from civ_appender import apply_civ                  # noqa: E402

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
# A real KM tree (Unhinged Empires' Wololo Warlords), so the Hussar, Cavalry
# Archer and eco upgrades are not simply unticked.
TREE = [
    [13, 17, 21, 74, 545, 539, 331, 125, 83, 128, 474, 39, 5, 6, 7, 492, 24, 4, 567, 473, 77, 75, 359, 358, 93, 1903, 1901, 441, 546, 448, 569, 283, 38, 548, 422, 1258, 1907, 1904, 36, 1942, 691, 420, 1795, 528, 527, 1104, 442, 1372, 1370, 440],
    [12, 45, 49, 50, 68, 70, 72, 79, 82, 84, 87, 101, 103, 104, 109, 199, 209, 276, 562, 584, 598, 621, 792, 236, 235, 234, 155, 117, 487],
    [22, 101, 102, 103, 408, 47, 436, 437, 875, 215, 602, 435, 39, 219, 212, 211, 201, 200, 199, 75, 68, 67, 80, 82, 81, 77, 76, 74, 375, 374, 373, 65, 51, 50, 64, 377, 63, 140, 608, 93, 194, 322, 380, 54, 379, 321, 315, 233, 230, 45, 46, 438, 319, 316, 441, 439, 231, 252, 280, 8, 249, 213, 182, 55, 279, 278, 221, 203, 202, 17, 23, 15, 12, 13, 14, 48],
]
SLOTS = list(range(1, 9))      # 8 civs: more than any tech has free slots
for slot in SLOTS:
    civ_def = {
        "alias": f"Prereq Probe {slot}", "description": "", "architecture": 2,
        "language": 0, "wonder": -1, "castle": -1,
        "bonuses": [[[282, 1], [360, 1], [105, 1]], [], [], [], []],
        "tree": TREE,
    }
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        apply_civ(dat, civ_def, target_slot=slot)
    check(f"civ {slot}: no prerequisite slot ran out",
          "no free required_techs slot" not in buf.getvalue(),
          [l for l in buf.getvalue().splitlines() if "no free" in l])

def fires_for(civ_index: int, ages: set[int]):
    """Can this civ satisfy a tech's prerequisites having reached only `ages`?
    Researchable techs are assumed researched; type=102 disables are honoured."""
    tt = dat.effects[dat.civs[civ_index].tech_tree_id].effect_commands
    disabled = {int(c.d) for c in tt if c.type == 102}
    memo: dict[int, bool] = {}

    def ok(tid: int) -> bool:
        if tid in (101, 102, 103):
            return tid in ages
        if tid in memo:
            return memo[tid]
        memo[tid] = False                      # cycle guard
        t = dat.techs[tid]
        if t.civ not in (-1, civ_index) or tid in disabled:
            return False
        met = sum(1 for r in t.required_techs if r != -1 and ok(r))
        memo[tid] = met >= t.required_tech_count
        return memo[tid]
    return ok


# tech -> (name, the ages the bonus says it needs; the vanilla route needs one more)
FEUDAL, CASTLE, IMPERIAL = {101}, {101, 102}, {101, 102, 103}
DEPENDENTS = {
    786: ("Winged Hussar (282)", IMPERIAL),
    218: ("Heavy Cavalry Archer in Castle Age (360)", CASTLE),
    13:  ("Heavy Plow in Feudal (105)", FEUDAL),
    203: ("Bow Saw in Feudal (105)", FEUDAL),
    182: ("Gold Shaft Mining in Feudal (105)", FEUDAL),
    65:  ("Gillnets in Feudal (105)", FEUDAL),
}
print()
for slot in SLOTS:
    lost = [name for tid, (name, ages) in DEPENDENTS.items()
            if not fires_for(slot, ages)(tid)]
    check(f"civ {slot} reaches all shared dependents", not lost,
          f"unreachable: {lost}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
