#!/usr/bin/env python3
"""Real units in the tech tree (2026-11-10): a unit only a card used to unlock
— a regional unit locked to its owner civ, a KM catalog unit, or one only a
team bonus gives — is the game's own unit when the tree holds it, built by the
same machinery its card used.

    venv/bin/python tests/test_real_units.py
"""
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


from civ_appender import KM_UNIT_CARDS, _UNLOCK_UNIT_BONUSES, get_civ_bonuses  # noqa: E402

print("=== a tree unit brings its card ===")
for bid, ids in KM_UNIT_CARDS.items():
    got = {e[0] for e in get_civ_bonuses({"tree": {"units": [ids[0]]}, "bonuses": []})}
    check(f"tree with {ids[0]} reads as card {bid}", bid in got, got)
got = {e[0] for e in get_civ_bonuses({"tree": {"units": [2569]}, "bonuses": []})}
check("...as the regional unlock cards already did (Bolas Rider → 405)", 405 in got, got)
check("no unit, no card", not {e[0] for e in get_civ_bonuses({"tree": {"units": [4]}, "bonuses": []})}
      & (set(KM_UNIT_CARDS) | set(_UNLOCK_UNIT_BONUSES)))

try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
civ_file = ROOT / "my_civs" / "19_Cannoneers.json"
if dat_path is None or not civ_file.exists():
    print("  skip  no game DAT (or my_civs/19_Cannoneers.json) found")
    print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
    sys.exit(1 if failures else 0)

from civ_overrides import apply_civ_with_overrides  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

SLOT = 1
GENITOUR, ELITE_GENITOUR, CONDOTTIERO = 1010, 1012, 882
MISSIONARY, TURTLE, CARAVEL, FLAMING_CAMEL = 775, 831, 1004, 1263
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]
draft = {
    "alias": "Real", "architecture": 2, "language": 0, "bonuses": [], "team_bonuses": [],
    "unique_unit": {"km_idx": 11},
    "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
    "imperial_ut": {"mode": "vanilla", "effects": [{"id": 12, "multiplier": 1}]},
    "tree": {"units": units + [GENITOUR, ELITE_GENITOUR, CONDOTTIERO, MISSIONARY, TURTLE, CARAVEL,
                               FLAMING_CAMEL],
             "buildings": buildings, "techs": techs},
}
dat = load_dat(str(dat_path))
out = io.StringIO()
with contextlib.redirect_stdout(out):
    r, _ = apply_civ_with_overrides(dat, _draft_to_civ_def(draft), SLOT, draft)
log = out.getvalue()
civ = dat.civs[SLOT]
tt = dat.effects[civ.tech_tree_id].effect_commands
unlocked = {int(c.a) for c in tt if c.type == 8}
disabled = {int(c.d) for c in tt if c.type == 102}

print("\n=== team-bonus units, from the tree ===")
check("Genitour and its Elite: unlocked (type=8), not disabled",
      {601, 599} <= unlocked and not {601, 599} & disabled, (sorted(unlocked & {601, 599, 522}), sorted(disabled & {601, 599})))
check("Condottiero unlocked", 522 in unlocked and 522 not in disabled)
check("the type=8 is vanilla's make-avail shape (b=12, c=-1, d=1)",
      all((int(c.b), int(c.c), c.d) == (12, -1, 1.0) for c in tt if c.type == 8 and int(c.a) in (601, 599, 522)))

print("\n=== KM catalog units, from the tree ===")
owned = {tid: t for tid, t in enumerate(dat.techs) if t.civ == SLOT}
enables = {int(c.a) for t in owned.values() if 0 <= t.effect_id < len(dat.effects)
           for c in dat.effects[t.effect_id].effect_commands if c.type == 2 and int(c.b) != 0}
for uid, name in ((MISSIONARY, "Missionary"), (TURTLE, "Turtle Ship"), (CARAVEL, "Caravel"),
                  (FLAMING_CAMEL, "Flaming Camel")):
    check(f"{name}: a tech of this civ's own enables it (the card's, copied)", uid in enables)

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
