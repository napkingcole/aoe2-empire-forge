#!/usr/bin/env python3
"""The unique unit's bonus damage, per tier (feedback on 2.8.0-preview.1).

The tree page could edit a unit's bonus damage, but the UU is not on the tree,
so the UU tab gained the same rows: overrides.bonus_base / bonus_elite =
{class: amount}, written by civ_overrides._apply_uu_overrides through the same
write_bonus_attacks the tree uses.  Both schema doors must keep the maps.

    venv/bin/python tests/test_uu_class_overrides.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from civ_schema import from_draft, to_draft, norm_uu_overrides   # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


# ── Schema: the maps survive both doors, cleaned ─────────────────────────────
raw = {"hp_base": 120, "bonus_base": {"1": 20, "8": "5", "4": 9, "x": 3, "15": -2},
       "bonus_elite": {}, "attack_elite": None}
clean = norm_uu_overrides(raw)
check("bonus_base keeps real classes as ints; a negative clamps to 0 (removed), as on the tree",
      clean.get("bonus_base") == {"1": 20, "8": 5, "15": 0},
      f"{clean.get('bonus_base')}")
check("an empty tier map is dropped", "bonus_elite" not in clean, f"{clean}")
check("plain stats pass through, nulls dropped", clean.get("hp_base") == 120 and "attack_elite" not in clean)

saved = {"format": "empireforge_v2", "schema_version": 2, "alias": "Bonus Probe",
         "unique_unit": {"km_idx": 6, "overrides": {"bonus_base": {"1": 20}, "bonus_elite": {"1": 0, "8": 7}}}}
d = to_draft(saved)
check("to_draft keeps the bonus maps",
      d["unique_unit"]["overrides"] == {"bonus_base": {"1": 20}, "bonus_elite": {"1": 0, "8": 7}},
      f"{d['unique_unit'].get('overrides')}")
back = from_draft(d)
check("from_draft writes them back out", back["unique_unit"]["overrides"] == d["unique_unit"]["overrides"],
      f"{back['unique_unit']['overrides']}")

# ── Build: the Cataphract's bonuses, per tier ────────────────────────────────
from dat_reader import find_game_dat, load_dat              # noqa: E402
from civ_overrides import _apply_uu_overrides               # noqa: E402

dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
else:
    dat = load_dat(str(dat_path))
    slot = 7
    units = dat.civs[slot].units
    BASE, ELITE = 40, 553                                    # Cataphract, Elite Cataphract
    atk = lambda uid: {a.class_: a.amount for a in units[uid].type_50.attacks}   # noqa: E731
    before = {BASE: atk(BASE), ELITE: atk(ELITE)}
    draft = {"unique_unit": {"km_idx": 6, "overrides": {"bonus_base": {"1": 20, "8": 4},
                                                         "bonus_elite": {"1": 0}}}}
    with contextlib.redirect_stdout(io.StringIO()):
        _apply_uu_overrides(dat, slot, {"unit_id": BASE, "elite_id": ELITE}, draft)
    b, e = atk(BASE), atk(ELITE)
    check("Cataphract: +20 vs infantry (was +13)", before[BASE].get(1) == 13 and b.get(1) == 20, f"{b}")
    check("Cataphract: gains +4 vs cavalry", b.get(8) == 4, f"{b}")
    check("Cataphract: melee attack untouched", b.get(4) == before[BASE].get(4), f"{b}")
    check("Elite Cataphract: the infantry bonus is removed", 1 not in e, f"{e}")
    check("Elite Cataphract: the base tier's new class doesn't leak to it",
          e.get(8, 0) == before[ELITE].get(8, 0), f"{e}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
