#!/usr/bin/env python3
"""The unique unit's bonus damage and armour classes, per tier, and armour
classes on the tech tree (feedback on 2.8.0-preview.1).

The tree page could edit a unit's bonus damage, but the UU is not on the tree,
so the UU tab gained the same rows: overrides.bonus_base / bonus_elite =
{class: amount}, written by civ_overrides._apply_uu_overrides through the same
write_bonus_attacks the tree uses.  Armour classes (armour_base / armour_elite,
and a tree edit's "armour") are {class: amount | "immune"}: 0 is a real value
(the full bonus), "immune" removes the class, and a tree edit reaches every
form of the unit (a packed Trebuchet takes the same bonuses).  Both schema
doors must keep the maps.

    venv/bin/python tests/test_uu_class_overrides.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from civ_schema import from_draft, norm_unit_edits, norm_uu_overrides, to_draft   # noqa: E402

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

arm = norm_uu_overrides({"armour_base": {"8": 0, "1": "immune", "3": 5, "27": -2, "30": "junk"}})
check("armour keeps 0, negatives and immune; drops 3/4 and junk",
      arm.get("armour_base") == {"8": 0, "1": "immune", "27": -2}, f"{arm}")
ue = norm_unit_edits({"38": {"armour": {"8": 10, "4": 3}}})
check("a tree edit keeps its armour map", ue == {"38": {"armour": {"8": 10}}}, f"{ue}")

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

    # Armour: the Cataphract's Cavalry armour is 12 (16 Elite) in the game.
    arm = lambda uid: {a.class_: a.amount for a in units[uid].type_50.armours}   # noqa: E731
    abefore = {BASE: arm(BASE), ELITE: arm(ELITE)}
    draft = {"unique_unit": {"km_idx": 6, "overrides": {"armour_base": {"8": 0, "1": 3},
                                                         "armour_elite": {"8": "immune"}}}}
    with contextlib.redirect_stdout(io.StringIO()):
        _apply_uu_overrides(dat, slot, {"unit_id": BASE, "elite_id": ELITE}, draft)
    b, e = arm(BASE), arm(ELITE)
    check("Cataphract: Cavalry armour set to 0 (a value, not removed)",
          abefore[BASE].get(8) == 12 and b.get(8) == 0, f"{abefore[BASE]} -> {b}")
    check("Cataphract: gains Infantry armour 3", b.get(1) == 3, f"{b}")
    check("Cataphract: melee and pierce armour untouched",
          (b.get(4), b.get(3)) == (abefore[BASE].get(4), abefore[BASE].get(3)), f"{b}")
    check("Elite Cataphract: immune removes the Cavalry class", 8 not in e, f"{e}")

    # The tree: a Trebuchet's armour edit reaches its packed form too.
    from civ_overrides import _apply_unit_edits, unit_forms   # noqa: E402
    TREB = 331                                               # the trained (packed) node; 42 unpacked
    forms = unit_forms(dat, units, TREB)
    with contextlib.redirect_stdout(io.StringIO()):
        _apply_unit_edits(dat, slot, {"unit_edits": {str(TREB): {"armour": {"8": 7, "20": "immune"}}}})
    got = {f: {a.class_: a.amount for a in units[f].type_50.armours} for f in forms if units[f].type_50}
    check("the Trebuchet has a packed form", len(forms) > 1, f"{forms}")
    check("every Trebuchet form takes Cavalry armour 7 and loses Siege Weapons",
          all(a.get(8) == 7 and 20 not in a for a in got.values()), f"{got}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
