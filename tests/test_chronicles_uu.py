#!/usr/bin/env python3
"""The six Chronicles Castle units build as a civ's unique unit.

They were unlock cards (447-450, 452, 453); since 2026-10-10 they are UU picks
(_KM_UU_TECHS 97-102) and the cards are retired.  For each unit: this civ owns
a copy of its make-avail and elite techs, the unit trains at the Castle, and the
unit and its Elite upgrade are named (their own names live in the Chronicles
string table, which a normal match may not load).  A civ that still carries the
old card AND picks the same unit gets one copy, not two; the retired cards are
off the picker but still build.  Renaming one gives it this civ's own strings.
DAT-gated, ~3 min.

    venv/bin/python tests/test_chronicles_uu.py
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat              # noqa: E402

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

import build_all                                            # noqa: E402
from bonus_names import DEPRECATED_BONUSES                  # noqa: E402
from civ_appender import (_CHRONICLES_UU_CARDS, _KM_UU_NAMES,   # noqa: E402
                          _KM_UU_TECHS, _UNLOCK_UNIT_BONUSES)

CASTLE = 82


def civ(km_idx, name="", bonuses=()):
    return {"format": "empireforge_v2", "schema_version": 2, "alias": "Chron Probe",
            "tagline": "", "description": "", "architecture": 1, "language": 0,
            "bonuses": [{"id": b, "multiplier": 1} for b in bonuses], "team_bonuses": [],
            "custom_bonuses": [],
            "unique_unit": {"km_idx": km_idx, "vanilla_id": None, "name": name,
                            "description": "", "overrides": {}, "advanced_flags": {}},
            "tree": {"units": [], "buildings": [], "techs": []},
            "unit_overrides": [], "button_moves": [], "free_techs": []}


def build(c):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "c.json").write_text(json.dumps(c), encoding="utf-8")
        (tmp / "cfg.json").write_text(json.dumps(
            {"mod_name": "C", "civs": [{"json": str(tmp / "c.json"), "replace": "Britons"}]}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            build_all.build_mod(tmp / "cfg.json", dat_path, tmp / "out.zip")
        outer = zipfile.ZipFile(tmp / "out.zip")
        dz = zipfile.ZipFile(io.BytesIO(outer.read(next(n for n in outer.namelist() if n.endswith("-data.zip")))))
        uz = zipfile.ZipFile(io.BytesIO(outer.read(next(n for n in outer.namelist() if n.endswith("-ui.zip")))))
        (tmp / "m.dat").write_bytes(dz.read(next(n for n in dz.namelist() if n.endswith(".dat"))))
        sp = next(n for n in uz.namelist() if n.endswith("key-value-modded-strings-utf8.txt") and "/en/" in n)
        s = {int(m.group(1)): m.group(2) for ln in uz.read(sp).decode("utf-8").splitlines()
             if (m := re.match(r'^(\d+)\s+"(.*)"$', ln.strip()))}
        return load_dat(str(tmp / "m.dat")), s


def owned_copies(dat, slot, unit_id):
    """This civ's techs that enable unit_id (its make-avail copies)."""
    out = []
    for tid, t in enumerate(dat.techs):
        if t.civ == slot and 0 <= t.effect_id < len(dat.effects):
            if any(c.type == 2 and int(c.a) == unit_id and int(c.b) != 0
                   for c in dat.effects[t.effect_id].effect_commands):
                out.append(tid)
    return out


def elite_copy(dat, slot, unit_id, elite_id):
    for tid, t in enumerate(dat.techs):
        if t.civ == slot and 0 <= t.effect_id < len(dat.effects):
            if any(c.type == 3 and int(c.a) == unit_id and int(c.b) == elite_id
                   for c in dat.effects[t.effect_id].effect_commands):
                return t
    return None


check("the six cards are retired from the picker",
      all(b in DEPRECATED_BONUSES for b in _CHRONICLES_UU_CARDS.values()))
check("the Barracks/Stable/Range Chronicles units stay cards",
      not {451, 454, 455, 456} & set(DEPRECATED_BONUSES))

for km_idx, card in sorted(_CHRONICLES_UU_CARDS.items()):
    name = _KM_UU_NAMES[km_idx]
    uid, eid = _UNLOCK_UNIT_BONUSES[card]["units"]
    dat, s = build(civ(km_idx))
    u = dat.civs[1].units[uid]
    check(f"{name}: this civ owns a make-avail copy", len(owned_copies(dat, 1, uid)) == 1,
          owned_copies(dat, 1, uid))
    check(f"{name}: trains at the Castle",
          any(tl.unit_id == CASTLE for tl in u.creatable.train_locations))
    check(f"{name}: named in game", name in s.get(u.language_dll_name, ""),
          (u.language_dll_name, s.get(u.language_dll_name)))
    et = elite_copy(dat, 1, uid, eid)
    check(f"{name}: the Elite upgrade is named 'Elite {name}'",
          et is not None and s.get(et.language_dll_name) == f"Elite {name}",
          et and (et.language_dll_name, s.get(et.language_dll_name)))

# An old civ with the card AND the same unit picked: one copy
uid = _UNLOCK_UNIT_BONUSES[447]["units"][0]
dat, s = build(civ(97, bonuses=(447,)))
check("Immortal picked AND card 447 carried: one make-avail copy, not two",
      len(owned_copies(dat, 1, uid)) == 1, owned_copies(dat, 1, uid))
# A retired card still builds for a civ that carries it
dat, s = build(civ(0, bonuses=(448,)))
check("a civ still carrying retired card 448 gets the Strategos",
      len(owned_copies(dat, 1, _UNLOCK_UNIT_BONUSES[448]["units"][0])) == 1)
# Renamed: this civ's own strings
dat, s = build(civ(100, name="Royal Guard"))
u = dat.civs[1].units[_UNLOCK_UNIT_BONUSES[450]["units"][0]]
check("a renamed Companion Cavalry is named 'Royal Guard'",
      s.get(u.language_dll_name) == "Royal Guard", s.get(u.language_dll_name))

# The Sannahya card (Stable, stays a card): Battle Elephant HP, the user's call
dat, s = build(civ(0, bonuses=(454,)))
check("the Sannāhya has 250 HP and the Elite 300 (it ships at 300/400)",
      (dat.civs[1].units[2390].hit_points, dat.civs[1].units[2391].hit_points) == (250, 300),
      (dat.civs[1].units[2390].hit_points, dat.civs[1].units[2391].hit_points))

print()
if failures:
    print(f"{failures} check(s) FAILED")
    sys.exit(1)
print("All checks passed.")
