#!/usr/bin/env python3
"""A civ built after other civs comes out the same as the civ built alone.

build_all builds every civ of a mod on one DAT, and a later civ reads other
slots as SOURCES: the Britons as its template, a vanilla civ for its
architecture, castle, wonder and monk skin.  Reading those after an earlier
civ replaced the slot read the custom civ instead: a plain civ built after a
Britons-slot civ with card 330 came out with its big farms, and Unhinged
Empires (Wololo Warlords in the Britons slot, built first) moved later civs'
train buttons.  civ_appender._original_civs keeps the vanilla civ for every
slot it overwrites.

The comparison covers the units both builds have; an earlier civ's custom
unique unit is appended to every civ, so the later civ has two more, disabled.

    venv/bin/python tests/test_civ_build_order.py
"""
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat           # noqa: E402

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

import civ_appender as ca                                # noqa: E402


def civ(alias, bonuses=(), architecture=2, castle=-1, wonder=-1, monk_skin=-1):
    return {"alias": alias, "tagline": "", "architecture": architecture, "language": 0,
            "castle": castle, "wonder": wonder, "monk_skin": monk_skin,
            "bonuses": [list(bonuses), [], [], [], []], "tree": [[], [], []]}


def build(steps):
    """apply_civ each (civ_def, slot) in order on a fresh DAT; the DAT."""
    dat = load_dat(str(dat_path))
    with contextlib.redirect_stdout(io.StringIO()):
        for cd, slot in steps:
            ca.apply_civ(dat, cd, target_slot=slot)
    return dat


def _sig(unit):
    """A unit's repr without 0-value attack entries.

    A team bonus that changes an attack class puts a 0 entry for it on every
    civ (_add_missing_attack_classes: allies are any civ), so a civ built after
    one with such a team bonus carries entries a civ built alone lacks.  They
    add no damage, which is why vanilla units carry them too.
    """
    if unit is None or unit.type_50 is None:
        return repr(unit)
    keep = unit.type_50.attacks
    unit.type_50.attacks = [x for x in keep if x.amount != 0]
    try:
        return repr(unit)
    finally:
        unit.type_50.attacks = keep


def differences(a, b, slot):
    """Units of `slot` that differ between two builds (over the units both have)."""
    ua, ub = a.civs[slot].units, b.civs[slot].units
    out = [ca.unit_label(b, slot, i) for i, (x, y) in enumerate(zip(ua, ub)) if _sig(x) != _sig(y)]
    for field in ("icon_set", "resources"):
        if repr(getattr(a.civs[slot], field)) != repr(getattr(b.civs[slot], field)):
            out.append(f"civ.{field}")
    return out


def same_as_alone(label, earlier, later, slot):
    alone = build([(later, slot)])
    after = build([(earlier, 1), (later, slot)])
    diff = differences(alone, after, slot)
    check(label, not diff, f"{len(diff)} differ: {diff[:8]}")
    return after


# A direct unit edit on the Britons-slot civ: card 330's farm size.
same_as_alone("a plain civ built after a Britons-slot civ with card 330 has vanilla farms",
              civ("Leaker", [[330, 1]]), civ("Plain"), 2)

# Architecture: Western European copies from the Britons slot (_ARCH_REP_CIVS).
same_as_alone("Western European architecture is the Britons' as shipped, not the civ that took the slot",
              civ("Meso", architecture=5), civ("West", architecture=2), 3)

# Castle, wonder and monk skin taken from a slot an earlier civ replaced.
same_as_alone("a castle, wonder and monk skin from a replaced slot are the vanilla civ's",
              civ("Taker", architecture=5, castle=4, wonder=4, monk_skin=15),
              civ("Borrower", castle=0, wonder=0, monk_skin=1), 4)

# The real case: Unhinged Empires builds Wololo Warlords into the Britons first.
P = Path.home() / "Sites/aoe2/civs"
if (P / "01_Wololo Warlords.json").exists():
    load = lambda n: json.loads((P / n).read_text(encoding="utf-8"))     # noqa: E731
    after = same_as_alone("Unhinged's Stormriders built after Wololo Warlords = built alone",
                          load("01_Wololo Warlords.json"), load("02_Stormriders.json"), 2)
    lengths = {len(c.units) for c in after.civs}
    check("every civ still has the same number of units (custom UUs reached the kept originals too)",
          len(lengths) == 1, sorted(lengths))
else:
    print("  skip  Unhinged Empires civs not found")

print("\nAll checks passed." if not failures else f"\n{failures} check(s) FAILED.")
sys.exit(1 if failures else 0)
