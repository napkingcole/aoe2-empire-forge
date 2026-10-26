#!/usr/bin/env python3
"""The custom-bonus composer offers only effects that do something.  DAT-gated.

Effects used to be filtered by target kind alone, so every unit was offered
every unit effect: garrison space on Villagers (a user spotted it), range on a
Champion, carry capacity on a Knight.  custom_bonus.allowed_attrs narrows each
target to the effects whose stat some unit it reaches has in the DAT, and the
catalog endpoint hands that to the composer once the DAT is loaded.

    venv/bin/python tests/test_custom_bonus_targets.py
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
dat = load_dat(str(dat_path))

UNITS = {38: "Knight", 567: "Champion", 4: "Archer", 35: "Battering Ram", 125: "Monk",
         13: "Fishing Ship", 128: "Trade Cart", 545: "Transport Ship"}
BUILDINGS = {68: "Mill", 82: "Castle"}
entries = ([(f"unit:{u}", "unit", u) for u in UNITS]
           + [(f"building:{b}", "building", b) for b in BUILDINGS])
allowed = {k: set(v) for k, v in cb.allowed_attrs(dat, entries).items()}

print("=== effects that need a stat the target lacks are not offered ===")
EXPECT = [
    # (target, has, lacks)
    ("group:villagers", {"work_rate", "carry", "hp"}, {"garrison"}),
    ("unit:38",  {"melee_attack", "attack_speed", "speed"}, {"range", "pierce_attack", "carry", "garrison", "work_rate"}),
    ("unit:567", {"melee_attack"}, {"range", "pierce_attack"}),
    ("unit:4",   {"range", "pierce_attack", "attack_speed"}, {"melee_attack", "garrison", "carry"}),
    ("unit:35",  {"garrison", "melee_attack"}, {"range", "carry"}),
    ("unit:125", {"work_rate", "hp"}, {"attack_speed", "melee_attack", "pierce_attack", "carry"}),
    ("unit:13",  {"carry", "work_rate"}, {"garrison", "melee_attack"}),
    ("unit:128", {"carry"}, {"attack_speed", "melee_attack", "range"}),
    ("unit:545", {"garrison", "speed"}, {"attack_speed", "range", "carry"}),
    ("building:68", {"hp", "build_speed"}, {"pierce_attack", "attack_speed", "range", "garrison"}),
    ("building:82", {"garrison", "pierce_attack", "range", "attack_speed"}, set()),
    ("group:monks", {"work_rate"}, {"attack_speed", "melee_attack", "pierce_attack"}),
]
for key, has, lacks in EXPECT:
    got = allowed.get(key, set())
    check(f"{key}: offers {sorted(has)}", has <= got, f"missing {sorted(has - got)}")
    if lacks:
        check(f"{key}: not {sorted(lacks)}", not (lacks & got), f"still {sorted(lacks & got)}")

unit_kind = {k for k, a in cb.ATTRS.items() if "unit" in a["kinds"]}
check("the per-civ Unique unit group is not narrowed", allowed["group:unique_unit"] == unit_kind,
      f"{sorted(unit_kind - allowed['group:unique_unit'])}")
check("every offered effect is one its kind allows",
      all(set(v) <= {k for k, a in cb.ATTRS.items() if a["kinds"]} for v in allowed.values()))

print("\n=== Farms and Monasteries groups (2026-10-10) ===")
fm = cb.allowed_attrs(dat, [("building:50", "building", 50), ("building:276", "building", 276)])
check("a Farms and Fish Traps group covers Farm, Fish Trap, Rice Farm and Pasture",
      {50, 199, 1187, 1889} <= set(cb.GROUPS["farms"]["buildings"]))
check("...but not the Pasture's animals (class 49 holds the Argali and Ibex)",
      not {1899, 1900} & set(cb.GROUPS["farms"]["buildings"]))
check("farms are never offered population space or blast radius",
      not {"pop_space", "blast_radius"} & set(fm["group:farms"] + fm["building:50"]), fm["group:farms"])
check("a Monasteries group covers the Monastery and the Fortified Church",
      {104, 1806} == set(cb.GROUPS["churches"]["buildings"]))
fc = cb.allowed_attrs(dat, [("building:1806", "building", 1806), ("building:82", "building", 82)])
check("the Fortified Church is not offered blast radius (it did not show in game); the Castle is",
      "blast_radius" not in fc["building:1806"] + fc["group:churches"]
      and "blast_radius" in fc["building:82"])
check("a Wonder (no attack) is not offered blast radius",
      "blast_radius" not in fm["building:276"], fm["building:276"])

print("\n=== building work rate: train and research faster (2026-10-24) ===")
# Attribute 13 on a building is its training and research speed: Conscription,
# Chivalry, Perfusion and the Goths'/Huns'/Britons' team bonuses all write it on
# every age form of the building.  Offered where something trains or researches.
wr = cb.allowed_attrs(dat, [(f"building:{b}", "building", b) for b in (12, 84, 68, 70, 50)])
check("Barracks, Market and Mill are offered work rate",
      all("work_rate" in wr[f"building:{b}"] for b in (12, 84, 68)))
check("a House and a Farm are not (nothing trains or researches there)",
      not any("work_rate" in wr[f"building:{b}"] for b in (70, 50)))
check("...nor the Farms group", "work_rate" not in wr["group:farms"])
check("Military buildings are", "work_rate" in wr["group:military_buildings"])
from civ_appender import _custom_bonus_resolver                    # noqa: E402
line_of, resolve = _custom_bonus_resolver(dat, 1, {})
card = {"targets": [{"type": "unit", "id": 12, "kind": "building", "name": "Barracks"}],
        "effects": [{"attr": "work_rate", "op": "mul", "value": 20}]}
cmds = cb.card_commands(card, line_of, resolve)
vanilla = {int(c.a) for c in dat.effects[405].effect_commands if c.type == 5 and int(c.c) == 13}  # Goths team bonus
check("the card multiplies attribute 13 by 1.2 on every Barracks the Goths' team bonus names",
      {int(c.a) for c in cmds if c.type == 5 and int(c.c) == 13 and abs(c.d - 1.2) < 1e-6} >= vanilla
      and vanilla, (sorted(vanilla), [(c.type, c.a, c.c, c.d) for c in cmds]))
check("its text says what it does", cb.card_text(card) == "Barracks: train and research 20% faster", cb.card_text(card))

print("\n=== the catalog endpoint ===")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
c = A.app.test_client()
A._DAT_OBJ_CACHE.pop(str(dat_path), None)
A._CB_ALLOWED_CACHE.clear()
A._DAT_LOADING.add(str(dat_path))          # pretend a load is in flight
cold = c.get("/api/builder/custom-bonus/catalog").get_json()
check("DAT not loaded yet: says pending and offers everything",
      cold.get("allowed_pending") is True and "allowed" not in cold)
A._DAT_LOADING.discard(str(dat_path))
A._DAT_OBJ_CACHE[str(dat_path)] = dat
warm = c.get("/api/builder/custom-bonus/catalog").get_json()
got = warm.get("allowed") or {}
check("DAT loaded: an allowed list for every unit and building in the picker",
      all(f"unit:{u['id']}" in got for u in warm["units"])
      and all(f"building:{b['id']}" in got for b in warm["buildings"]))
check("...and Villagers are not offered garrison space",
      "garrison" not in got.get("group:villagers", ["garrison"]))

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
