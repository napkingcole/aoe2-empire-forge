#!/usr/bin/env python3
"""A unique unit's attack speed and range edits reach the unit itself.  DAT-gated.

Each has a real field and a displayed one.  The override wrote only the
displayed reload, so a Conquistador set to 2 still attacked every 2.9 s and the
stats page said 2.9 (#104), and a Heavy Pikeman stayed at 3 (#98).  The KM
presets with an attack speed (Xolotl Warrior, Cuahchiqueh, Photonman,
Maillotins) had the same bug.  Range wrote only the real field, so the tooltip
kept the old range.

    venv/bin/python tests/test_uu_reload_override.py
"""
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dat_reader import find_game_dat, load_dat          # noqa: E402
from civ_overrides import apply_civ_with_overrides     # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f"\n       {extra}"))
    failures += not cond


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)
dat = load_dat(str(dat_path))


def build(slot, km_idx, overrides):
    civ_def = {"alias": f"Reload Probe {slot}", "description": "", "architecture": 2,
               "language": 0, "wonder": -1, "castle": -1,
               "bonuses": [[], [km_idx], [], [], []], "tree": [[], [], []],
               "unique_unit": {"km_idx": km_idx, "name": "", "description": "", "overrides": overrides}}
    with contextlib.redirect_stdout(io.StringIO()):
        _, info = apply_civ_with_overrides(dat, civ_def, slot)
    cu = dat.civs[slot].units
    return cu[info["unit_id"]].type_50, cu[info["elite_id"]].type_50


def stats(t):
    return (round(t.reload_time, 2), round(t.displayed_reload_time, 2),
            round(t.max_range, 2), round(t.displayed_range, 2))


for slot, km, name, ov, want in (
        (5, 13, "Conquistador", {"reload_base": 2, "reload_elite": 1.5, "range_base": 7, "range_elite": 8},
         ((2, 2, 7, 7), (1.5, 1.5, 8, 8))),
        (6, 109, "Heavy Pikeman", {"reload_base": 2, "reload_elite": 2}, None)):
    base, elite = build(slot, km, ov)
    if want is None:
        check(f"{name}: attacks every 2 s, shown as 2 s (#98)",
              stats(base)[:2] == stats(elite)[:2] == (2, 2), (stats(base), stats(elite)))
    else:
        check(f"{name}: reload and range edits are real and shown (#104)",
              (stats(base), stats(elite)) == want, (stats(base), stats(elite)))

base, elite = build(7, 40, {})
check("KM preset Xolotl Warrior attacks at 0.9 / 0.8 s",
      stats(base)[:2] == (0.9, 0.9) and stats(elite)[:2] == (0.8, 0.8), (stats(base), stats(elite)))
base, _ = build(8, 44, {})
check("KM preset Photonman: 5.5 s, range 8, both real and shown",
      stats(base) == (5.5, 5.5, 8, 8), stats(base))

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
