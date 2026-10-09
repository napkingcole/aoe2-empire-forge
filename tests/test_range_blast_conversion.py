#!/usr/bin/env python3
"""Custom bonuses: minimum range, blast radius, conversion (#67).  DAT-gated.

  minimum range   attribute 20, per unit, only units that have one; an ADD,
                  clamped so a unit never goes below 0.  "No minimum range"
                  is Andean Sling's SET to 0.
  blast radius    attribute 22, per unit, only units with a blast attack
                  (level not 3 "targeted unit only") — the Trebuchet counts at
                  width 0, as Warwolf widens it.  ADDs, so cards stack.
  conversion      Civilization effects: your Monks' monk-seconds, resources
                  176/177 (Inquisition -1/-1); resistance to enemy Monks,
                  178/179 (Faith +4/+4).

    venv/bin/python tests/test_range_blast_conversion.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import custom_bonus as cb                                   # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

from civ_appender import apply_civ                          # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402
dat = load_dat(str(dat_path))
MANGONEL, TREB, BOMBARD, SCORPION, ARCHER, SKIRM, WAR_ELE = 280, 42, 36, 279, 4, 7, 239


def cards(target, *effs):
    return cb.normalize([{"target": target, "effects": list(effs)}])


def built(slot, cs):
    """{(unit or resource, attr/res field): [(type, d), ...]} from the custom techs."""
    civ = {"format": FORMAT_KEY, "alias": f"RBC {slot}", "architecture": 2, "language": 0,
           "bonuses": [], "custom_bonuses": cs,
           "tree": {"units": [83, 280, 42, 36, 279, 4, 7, 239, 125], "buildings": [49, 87, 12, 82, 104, 109, 70],
                    "techs": [101, 102, 103]}}
    n = len(dat.techs)
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ, target_slot=slot)
    out = {}
    for t in dat.techs[n:]:
        if t.civ == slot and t.name == "C-Bonus, Custom":
            for c in dat.effects[t.effect_id].effect_commands:
                key = (int(c.a), int(c.c)) if c.type in (0, 4, 5) else (int(c.a), "res")
                out.setdefault(key, []).append((c.type, round(c.d, 3)))
    return out


SIEGE = {"type": "group", "id": "siege"}
print("=== minimum range ===")
got = built(5, cards(SIEGE, {"attr": "min_range", "op": "add", "value": -1}))
check("Mangonel 3 -> ADD -1", got.get((MANGONEL, 20)) == [(4, -1.0)], f"{got.get((MANGONEL, 20))}")
check("Bombard Cannon 5 -> ADD -1", got.get((BOMBARD, 20)) == [(4, -1.0)])
got = built(6, cards({"type": "group", "id": "archery_units"}, {"attr": "min_range", "op": "add", "value": -3}))
check("Skirmisher (1) -3 is clamped to -1", got.get((SKIRM, 20)) == [(4, -1.0)], f"{got.get((SKIRM, 20))}")
check("Archer (no minimum range) gets nothing", (ARCHER, 20) not in got)
got = built(7, cards(SIEGE, {"attr": "no_min_range", "op": "set"}))
check("no minimum range: SET 0, as Andean Sling", got.get((MANGONEL, 20)) == [(0, 0.0)], f"{got.get((MANGONEL, 20))}")
check("card text", cb.card_text(cards(SIEGE, {"attr": "min_range", "op": "add", "value": -1})[0])
      == "Siege weapons: -1 minimum range")

print("\n=== blast radius ===")
got = built(8, cards(SIEGE, {"attr": "blast_radius", "op": "add", "value": 0.5},))
check("Mangonel +0.5", got.get((MANGONEL, 22)) == [(4, 0.5)], f"{got.get((MANGONEL, 22))}")
check("Trebuchet (width 0, but it splashes) +0.5, as Warwolf", got.get((TREB, 22)) == [(4, 0.5)])
check("Scorpion (targeted only) gets nothing", (SCORPION, 22) not in got)
both = cards(SIEGE, {"attr": "blast_radius", "op": "add", "value": 0.5}) \
    + cards(SIEGE, {"attr": "blast_radius", "op": "add", "value": 1})
got = built(9, both)
check("two cards stack (+0.5 and +1)", sorted(got.get((MANGONEL, 22), [])) == [(4, 0.5), (4, 1.0)],
      f"{got.get((MANGONEL, 22))}")

print("\n=== conversion ===")
got = built(10, cards({"type": "civ"}, {"attr": "convert_time", "op": "add", "value": -1}))
check("faster Monks: 176 and 177 -1, as Inquisition", got.get((176, "res")) == [(1, -1.0)]
      and got.get((177, "res")) == [(1, -1.0)], f"{got}")
check("text", cb.card_text(cards({"type": "civ"}, {"attr": "convert_time", "op": "add", "value": -1})[0])
      == "Monks convert 1 second faster")
got = built(11, cards({"type": "civ"}, {"attr": "convert_resist", "op": "add", "value": 4}))
check("resistance: 178 and 179 +4, as Faith", got.get((178, "res")) == [(1, 4.0)]
      and got.get((179, "res")) == [(1, 4.0)], f"{got}")
check("negative resistance is refused",
      not cards({"type": "civ"}, {"attr": "convert_resist", "op": "add", "value": -2}))

print("\n=== the vanilla precedents ===")
def effect_res(name):
    e = next(e for e in dat.effects if e.name == name)
    return {(c.type, int(c.a)) for c in e.effect_commands}
check("Inquisition writes 176 and 177", {(1, 176), (1, 177)} <= effect_res("Inquisition"))
check("Faith writes 178 and 179", {(1, 178), (1, 179)} <= effect_res("Faith"))

print("\n=== offered where they mean something ===")
allowed = cb.allowed_attrs(dat, [(f"unit:{u}", "unit", u) for u in (MANGONEL, TREB, SCORPION, ARCHER, SKIRM)])
for uid, has, lacks in ((MANGONEL, {"min_range", "no_min_range", "blast_radius"}, set()),
                        (TREB, {"min_range", "blast_radius"}, set()),
                        (SCORPION, {"min_range"}, {"blast_radius"}),
                        (SKIRM, {"min_range"}, {"blast_radius"}),
                        (ARCHER, set(), {"min_range", "no_min_range", "blast_radius"})):
    a = set(allowed[f"unit:{uid}"])
    check(f"unit {uid}: offers {sorted(has)}, not {sorted(lacks)}", has <= a and not (lacks & a), f"{sorted(a)}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
