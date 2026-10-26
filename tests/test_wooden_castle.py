#!/usr/bin/env python3
"""Card 460, Wooden Castles: the civ's Castle is the campaign Wooden Fort.  DAT-gated.

The user's design (2026-10-24): the Wooden Fort's look (unit 2600, scenario
only, added with the Mapuche/Tupi/Muisca DLC) on the civ's own Castle (82),
which costs 300 stone + 500 wood instead of 650 stone, has 3000 HP instead of
4800, builds in 175 s instead of 200, and keeps the Castle's arrows.  It stays
unit 82, so everything that names the Castle still finds it.

It edits unit data rather than writing effect commands, so this saves the DAT
and reads it back: a change the lazy loader didn't write out would pass in
memory and do nothing in game.

    venv/bin/python tests/test_wooden_castle.py
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat      # noqa: E402
from dat_lazy import save_bytes                     # noqa: E402
from civ_appender import apply_civ, HANDLED_BONUS_IDS   # noqa: E402
import bonus_names                                  # noqa: E402

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

print("the card is offered")
check("460 is handled and named", 460 in HANDLED_BONUS_IDS
      and 460 not in {b["id"] for b in bonus_names.unsupported_bonuses()})

dat = load_dat(str(dat_path))
fort = dat.civs[0].units[2600]
check("unit 2600 is the Wooden Fort, a 4x4 like the Castle",
      fort is not None and fort.name == "WOODENFORT" and fort.clearance_size == dat.civs[1].units[82].clearance_size)
castle_civ0 = (dat.civs[1].units[82].hit_points, dat.civs[1].units[82].standing_graphic)

# Not slot 1: apply_civ clones the Britons there as its template.  The second
# probe picks the Franks' castle explicitly: the card must win over the pick.
SLOT, SLOT_PICKED, SLOT_PLAIN = 5, 6, 7
for slot, bonuses, castle in ((SLOT, [[460, 1]], -1), (SLOT_PICKED, [[460, 1]], 1), (SLOT_PLAIN, [], -1)):
    civ_def = {"alias": f"Wooden Probe {slot}", "description": "", "architecture": 2,
               "language": 0, "wonder": -1, "castle": castle,
               "bonuses": [bonuses, [], [], [], []], "tree": [[], [], []]}
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ_def, target_slot=slot)

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "empires2_x2_p1.dat"
    out.write_bytes(save_bytes(dat))
    back = load_dat(str(out))

fort = back.civs[0].units[2600]
plain = back.civs[SLOT_PLAIN].units[82]
for slot, what in ((SLOT, "architecture's castle"), (SLOT_PICKED, "picked castle")):
    print(f"460 over the {what} (read back from the saved DAT)")
    c = back.civs[slot].units[82]
    check("wears the Wooden Fort: standing, destroyed, rubble",
          (c.standing_graphic, c.dying_graphic, c.undead_graphic, c.dead_unit_id)
          == (fort.standing_graphic, fort.dying_graphic, fort.undead_graphic, fort.dead_unit_id))
    check("...damaged, snow and garrisoned",
          [d.graphic_id for d in c.damage_graphics] == [d.graphic_id for d in fort.damage_graphics]
          and c.building.snow_graphic_id == fort.building.snow_graphic_id
          and c.creatable.garrison_graphic == fort.creatable.garrison_graphic)
    check("3000 HP", c.hit_points == 3000, c.hit_points)
    costs = [(r.type, r.amount, r.flag) for r in c.creatable.resource_costs]
    check("costs 300 stone + 500 wood, nothing else", costs[:2] == [(2, 300, 1), (1, 500, 1)]
          and all(r.flag == 0 or r.amount == 0 for r in c.creatable.resource_costs[2:]), costs)
    check("builds in 175 s", [t.train_time for t in c.creatable.train_locations] == [175])
    check("still built by the Villager on the Castle's button",
          [(t.unit_id, t.button_id) for t in c.creatable.train_locations]
          == [(t.unit_id, t.button_id) for t in plain.creatable.train_locations])
    check("keeps the Castle's arrows, range and garrison",
          (c.type_50.displayed_attack, c.type_50.max_range, c.type_50.reload_time, c.garrison_capacity,
           [(a.class_, a.amount) for a in c.type_50.attacks])
          == (plain.type_50.displayed_attack, plain.type_50.max_range, plain.type_50.reload_time,
              plain.garrison_capacity, [(a.class_, a.amount) for a in plain.type_50.attacks]))
    check("keeps the Castle's icon and name", (c.icon_id, c.language_dll_name) == (plain.icon_id, plain.language_dll_name))

print("other civs")
check("a civ without the card keeps a stone Castle", plain.hit_points == 4800
      and plain.standing_graphic != fort.standing_graphic)
check("the Britons' Castle is untouched", (back.civs[1].units[82].hit_points, back.civs[1].units[82].standing_graphic)
      == castle_civ0)

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
