#!/usr/bin/env python3
"""A unique unit can wear another unit's look, keeping its own stats.  DAT-gated.

The Appearance choice (2026-10-22, the user's design): the art — animations,
death, icon, corpse, selection box, an archer's arrow point — comes from a hero
or another unit; stats, cost, hitbox, projectile and voice stay the UU's.
Only a look of the same kind (infantry, foot archers, cavalry, cavalry
archers) and size (selection box within 0.05: an elephant's is 0.6 to a
horse's 0.4, though their collision radii match) is allowed.

    venv/bin/python tests/test_uu_appearance.py
"""
import contextlib
import io
import sys
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

import civ_appender as ca                                   # noqa: E402
from civ_schema import FORMAT_KEY, from_draft, to_draft     # noqa: E402
from wizard_build import _draft_to_civ_def                  # noqa: E402

dat = load_dat(str(dat_path))
G = dat.civs[0].units
QIZILBASH, ATTILA, WAR_ELEPHANT, LONGBOWMAN = 1817, 777, 239, 8

print("=== who may wear what ===")
check("Qizilbash may wear Attila (cavalry, same size)", ca.appearance_ok(G[ATTILA], G[QIZILBASH]))
check("...but not a War Elephant (cavalry, bigger art)", not ca.appearance_ok(G[WAR_ELEPHANT], G[QIZILBASH]))
check("...nor a Longbowman (another kind)", not ca.appearance_ok(G[LONGBOWMAN], G[QIZILBASH]))


def build(look, slot):
    draft = {"alias": f"Look {slot}", "architecture": 2, "language": 0, "bonuses": [],
             "unique_unit": {"km_idx": 103, "appearance": look},
             "tree": {"units": [83], "buildings": [109, 82], "techs": [101, 102, 103]}}
    civ_def = _draft_to_civ_def(draft)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = ca.apply_civ(dat, civ_def, target_slot=slot)
    return r, buf.getvalue()


def look(u):
    return (u.standing_graphic, u.dying_graphic, u.icon_id, u.dead_unit_id,
            u.dead_fish.walking_graphic, u.type_50.attack_graphic, u.outline_size_x)


def stats(u):
    return (u.hit_points, u.speed, u.type_50.displayed_attack, u.collision_size_x,
            [(c.type, c.amount) for c in u.creatable.resource_costs])


print("\n=== a build: the Qizilbash wearing Attila ===")
r, log = build(ATTILA, 5)
units = dat.civs[r["civ_index"]].units
for uid, tier in ((r["uu_id"], "UU"), (r["elite_uu_id"], "Elite")):
    check(f"{tier} wears Attila's look", look(units[uid]) == look(G[ATTILA]), look(units[uid]))
plain, _ = build(None, 6)
plain_units = dat.civs[plain["civ_index"]].units
check("...with the stats, cost and hitbox it has without a look",
      stats(units[r["uu_id"]]) == stats(plain_units[plain["uu_id"]]))
check("...and the Elite's too", stats(units[r["elite_uu_id"]]) == stats(plain_units[plain["elite_uu_id"]]))

print("\n=== a look that doesn't fit is refused ===")
r, log = build(WAR_ELEPHANT, 7)
units = dat.civs[r["civ_index"]].units
check("the UU keeps its own look", look(units[r["uu_id"]]) == look(plain_units[plain["uu_id"]]))
check("...and the build says why", "doesn't fit" in log and any("appearance" in w for w in r.get("warnings", [])),
      [l for l in log.splitlines() if "appearance" in l.lower()][:2])

print("\n=== QA 2026-10-23: a second attack, and the look's Elite ===")
FIRE_ARCHER_KM, CHU_KO_NU, ELITE_CHU_KO_NU = 84, 73, 559
check("the Chu Ko Nu's Elite is found by its game name", ca.look_elite(dat, CHU_KO_NU) == ELITE_CHU_KO_NU)
check("...and a hero has none", ca.look_elite(dat, ATTILA) is None)
draft = {"alias": "Look FA", "architecture": 2, "language": 0, "bonuses": [],
         "unique_unit": {"km_idx": FIRE_ARCHER_KM, "appearance": CHU_KO_NU},
         "tree": {"units": [83], "buildings": [109, 82], "techs": [101, 102, 103]}}
with contextlib.redirect_stdout(io.StringIO()):
    r = ca.apply_civ(dat, _draft_to_civ_def(draft), target_slot=8)
units = dat.civs[r["civ_index"]].units
fa = units[r["uu_id"]]
# The Fire Archer's volley at buildings is a charge attack with its own art;
# it kept the Fire Archer's while everything else was the Chu Ko Nu's.
check("the second attack plays the look's attack, not the Fire Archer's",
      fa.creatable.special_graphic == G[CHU_KO_NU].type_50.attack_graphic,
      (fa.creatable.special_graphic, G[CHU_KO_NU].type_50.attack_graphic))
check("the Elite Fire Archer wears the Elite Chu Ko Nu",
      look(units[r["elite_uu_id"]]) == look(G[ELITE_CHU_KO_NU]))
check("...and the base Fire Archer the Chu Ko Nu", look(fa) == look(G[CHU_KO_NU]))

print("\n=== the choice survives saving and loading ===")
schema = from_draft({"unique_unit": {"km_idx": 103, "appearance": ATTILA}})
check("from_draft keeps it", schema["unique_unit"].get("appearance") == ATTILA, schema["unique_unit"])
check("to_draft keeps it", to_draft(schema)["unique_unit"].get("appearance") == ATTILA)
check("the wizard hands it to the build",
      _draft_to_civ_def({"unique_unit": {"km_idx": 103, "appearance": ATTILA}})["unique_unit"]["appearance"] == ATTILA)

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
