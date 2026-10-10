#!/usr/bin/env python3
"""Custom bonuses can target a whole unit line, or a unit and up (#63).

A unit target with no scope is its whole upgrade line, alternates included —
the Militia line reaches the Legionary, the Knight line the Savar.  That is
what every card meant before #63, so saved cards keep it.  scope "up" is the
unit and the upgrades after it: "Long Swordsman and up" covers Two-Handed,
Champion and Legionary, never Militia or Man-at-Arms.

The first part is pure; the rest builds real civs and needs the game DAT.

    venv/bin/python tests/test_unit_line_targets.py
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


EFF = [{"attr": "melee_attack", "op": "add", "value": 2}]


def card(**target):
    return cb.normalize([{"target": {"type": "unit", "kind": "unit", **target}, "effects": EFF}])[0]


print("=== cards ===")
line = card(id=74, name="Militia")
up = card(id=77, name="Long Swordsman", scope="up")
top = card(id=567, name="Champion", scope="up", top=True)
check("no scope stays a whole-line card", "scope" not in line["target"])
check("scope 'up' survives normalize", up["target"].get("scope") == "up")
check("a bogus scope is dropped", "scope" not in card(id=74, name="M", scope="sideways")["target"])
check("buildings never take a scope",
      "scope" not in cb.normalize([{"target": {"type": "unit", "kind": "building", "id": 68, "name": "Mill",
                                               "scope": "up"}, "effects": [{"attr": "hp", "op": "add", "value": 50}]}])[0]["target"])
check("line card reads 'Militia line: ...'", cb.card_text(line).startswith("Militia line:"), cb.card_text(line))
check("'up' card reads 'Long Swordsman and up: ...'", cb.card_text(up).startswith("Long Swordsman and up:"),
      cb.card_text(up))
check("a top unit reads just its name", cb.card_text(top).startswith("Champion:"), cb.card_text(top))

try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
if dat_path is None:
    print("  skip  no game DAT found — build checks need it")
    print("\nFAIL" if failures else "\nPASS", f"({failures} failure(s))")
    sys.exit(1 if failures else 0)

from civ_appender import apply_civ                          # noqa: E402
from civ_schema import FORMAT_KEY                           # noqa: E402
dat = load_dat(str(dat_path))


def touched(slot, c):
    """Unit ids the civ's custom-bonus tech gives +melee attack to."""
    civ = {"format": FORMAT_KEY, "alias": f"Lines {slot}", "architecture": 2, "language": 0,
           "bonuses": [], "custom_bonuses": [c],
           "tree": {"units": [83, 74, 75, 77, 473, 567], "buildings": [12, 109, 70],
                    "techs": [101, 102, 103]}}
    n = len(dat.techs)
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ, target_slot=slot)
    return {int(ec.a) for t in dat.techs[n:] if t.civ == slot and 0 <= t.effect_id < len(dat.effects)
            for ec in dat.effects[t.effect_id].effect_commands if ec.type == 4 and int(ec.c) == 9}


print("\n=== what each card reaches ===")
got = touched(5, line)
check("Militia line: all six, Legionary included", {74, 75, 77, 473, 567, 1793} <= got, f"{sorted(got)}")
got = touched(6, up)
check("Long Swordsman and up: Two-Handed, Champion, Legionary and itself",
      {77, 473, 567, 1793} <= got, f"{sorted(got)}")
check("...but not Militia or Man-at-Arms", not ({74, 75} & got), f"{sorted(got)}")
got = touched(7, top)
check("Champion (top): just the Champion", got == {567}, f"{sorted(got)}")
got = touched(8, card(id=283, name="Cavalier", scope="up"))
check("Cavalier and up: Paladin and Savar, not the Knight", {283, 569, 1813} <= got and 38 not in got,
      f"{sorted(got)}")
legacy = {"target": {"type": "unit", "id": 77, "name": "Long Swordsman", "kind": "unit"}, "effects": EFF}
got = touched(9, cb.normalize([legacy])[0])
check("a pre-#63 card on Long Swordsman still covers the whole line", {74, 75} <= got, f"{sorted(got)}")

print("\n=== the catalog's line tiles ===")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
A._DAT_OBJ_CACHE[str(dat_path)] = dat
A._CB_ALLOWED_CACHE.clear()
cat = A.app.test_client().get("/api/builder/custom-bonus/catalog").get_json()
lines = {ln["name"]: ln for ln in cat.get("lines", [])}
for name, must, bldg in (("Militia line", "Legionary", 12), ("Knight line", "Savar", 101),
                         ("Scout Cavalry line", "Winged Hussar", 101), ("Camel Rider line", "Camel Scout", 101),
                         ("Galley line", "Galleon", 45), ("Spearman line", "Halberdier", 12)):
    ln = lines.get(name)
    check(f"{name} at building {bldg} includes {must}", ln and ln["building"] == bldg and must in ln["members"],
          f"{ln}")
check("members are listed in upgrade order", lines["Galley line"]["members"][:2] == ["Galley", "War Galley"],
      f"{lines['Galley line']['members']}")
check("every line has its own effect list", all(f"line:{ln['id']}" in cat["allowed"] for ln in cat["lines"]))
tops = {u["name"]: u["top"] for u in cat["units"]}
check("Champion is a top unit, Long Swordsman is not", tops.get("Champion") and not tops.get("Long Swordsman"))

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
