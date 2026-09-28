#!/usr/bin/env python3
"""Colliding unit lines move to the building's second page.  DAT-gated.

A command panel is a 5x3 grid, and the engine adds page 2 by itself: buttons
21-35, arrows appearing as soon as one is used (confirmed in-game 2026-09-25,
three test mods — see project memory "Button Pages").  Before this, two lines
on one (building, button) meant only one was reachable, and the unlock cards
could only warn about it.

The invariant checked first is the whole point: for every building, no two of
the civ's lines share a button.  It fails against the old code, where Eagle
Warrior, Fire Lancer and Jian Swordsman all sat on Barracks button 4.

    venv/bin/python tests/test_button_pages.py
"""
import contextlib
import io
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat                   # noqa: E402
from civ_appender import (apply_civ, _PAGE_ONE_PRIORITY, _PAGE2_USABLE,  # noqa: E402
                          _grid_hotkeys, _upgrade_neighbours, EC_UPGRADE,
                          _allocate_tech, _resolve_button_collisions)

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


# ── The choice survives the wizard's draft -> civ_def conversion ─────────────
from wizard_build import _draft_to_civ_def                         # noqa: E402
_pick = [{"building": 12, "button": 4, "page_one": 1901}]
check("wizard drafts carry button_moves into apply_civ",
      _draft_to_civ_def({"button_moves": _pick}).get("button_moves") == _pick)

dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)
dat = load_dat(str(dat_path))

BARRACKS, RANGE, STABLE = 12, 87, 101
EAGLE, FIRE_LANCER, JIAN, IBIRAPEMA = (751, 752, 753), (1901, 1903), (1974,), (2582, 2584)
CAV_ARCHER, ELEPHANT_ARCHER, BOLAS = (39, 474), (873, 875), (2569, 2571)
KNIGHT, HEI_GUANG = (38, 283, 569), (1944, 1946)
SHRIVAMSHA, BATTLE_ELEPHANT, STEPPE_LANCER = (1751, 1753), (1132, 1134), (1370, 1372)
HUSKARL, TARKAN = (41, 555), (755, 757)
ANARCHY, MARAUDERS = 16, 483
FTT_MOVE_SHRIVAMSHA = (865, 866)
ELITE_FIRE_LANCER_TECH, AZTECS = 982, 15
# Viking Sagas: absent from the pre-DLC DAT, so its checks skip there
MOUNTED_XBOW, PARTHIAN_TACTICS, CRANEQUINS, HEAVY_MOUNTED_XBOW = (2700, 2701), 436, 1452, 1451
# Not "does unit 2700 exist": before the DLC, 2700 was "Rock 2" (internal names lie).
_mx = dat.civs[1].units[MOUNTED_XBOW[0]] if MOUNTED_XBOW[0] < len(dat.civs[1].units) else None
HAS_MOUNTED_XBOW = bool(_mx and _mx.creatable and any(
    tl.unit_id == 87 and tl.button_id == 3 for tl in _mx.creatable.train_locations))

# ── The default table names units that really share each slot ───────────────
# Guards against a patch moving a unit: a stale entry would silently stop
# deciding anything.
print("=== priority table matches the DAT ===")
vanilla = dat.civs[1].units
for (bldg, btn), ids in sorted(_PAGE_ONE_PRIORITY.items()):
    # A unit newer than this DAT is simply absent (pre-DLC run); only a unit
    # that exists and trains somewhere else is a stale entry.
    present = [u for u in ids if u < len(vanilla) and vanilla[u] is not None
               and vanilla[u].creatable is not None]
    # unit_id -1 is a dormant slot a UT points at the building in-game (Anarchy, Marauders)
    wrong = [u for u in present
             if not any(tl.unit_id in (bldg, -1) and tl.button_id == btn
                        for tl in vanilla[u].creatable.train_locations)]
    check(f"building {bldg} button {btn}: every listed line trains there", not wrong, wrong)


def unit_ids(*lines):
    return sorted({u for line in lines for u in line})


def build(slot, extra=None):
    civ_def = {
        "alias": f"Pages {slot}", "description": "", "architecture": 2, "language": 0,
        "wonder": -1, "castle": -1,
        "bonuses": [[], [], [], [], []],
        "tree": [
            unit_ids(EAGLE, FIRE_LANCER, JIAN, IBIRAPEMA, CAV_ARCHER, ELEPHANT_ARCHER,
                     BOLAS, KNIGHT, HEI_GUANG, SHRIVAMSHA, BATTLE_ELEPHANT, STEPPE_LANCER,
                     MOUNTED_XBOW if HAS_MOUNTED_XBOW else (), (4, 74, 75, 77)),
            [BARRACKS, RANGE, STABLE, 109, 70, 68, 562, 584],
            # the lines' upgrades, so there are techs to follow them
            [384, 434, ELITE_FIRE_LANCER_TECH, 218, 481, 209, 265, 1033, 631, 715,
             PARTHIAN_TACTICS]
            + ([HEAVY_MOUNTED_XBOW, CRANEQUINS] if HAS_MOUNTED_XBOW else []),
        ],
    }
    civ_def.update(extra or {})
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        result = apply_civ(dat, civ_def, target_slot=slot)
    return result, civ_def, buf.getvalue()


def slot_of(civ, uid, bldg):
    return next((tl.button_id for tl in dat.civs[civ].units[uid].creatable.train_locations
                 if tl.unit_id == bldg), None)


SLOT, SLOT_PICK = 5, 6
result, civ_def, log = build(SLOT)
result_pick, _, _ = build(SLOT_PICK, {"button_moves": [
    {"building": BARRACKS, "button": 4, "page_one": FIRE_LANCER[0]}]})

# ── No two of the civ's lines share a button ─────────────────────────────────
print("\n=== no collisions remain ===")
neighbours = _upgrade_neighbours(dat)
have = set(civ_def["tree"][0])
for civ in (SLOT, SLOT_PICK):
    by_slot = defaultdict(set)
    for uid in have:
        unit = dat.civs[civ].units[uid] if uid < len(dat.civs[civ].units) else None
        if unit is None or unit.creatable is None:      # not in this DAT (pre-DLC run)
            continue
        for tl in unit.creatable.train_locations:
            if tl.unit_id >= 0 and tl.button_id > 0:
                by_slot[(tl.unit_id, tl.button_id)].add(uid)
    clashes = []
    for slot, uids in by_slot.items():
        # joined by an upgrade = one line; anything else sharing is a clash
        lines = []
        for u in uids:
            for line in lines:
                if neighbours.get(u, set()) & line:
                    line.add(u)
                    break
            else:
                lines.append({u})
        if len(lines) > 1:
            clashes.append((slot, sorted(uids)))
    check(f"civ {civ}: every (building, button) holds one line", not clashes, clashes)

# ── Default layout ───────────────────────────────────────────────────────────
print("\n=== default: the table's first line keeps page 1 ===")
check("Eagle line stays on Barracks button 4",
      all(slot_of(SLOT, u, BARRACKS) == 4 for u in EAGLE))
fl = {slot_of(SLOT, u, BARRACKS) for u in FIRE_LANCER}
check("Fire Lancer and Elite Fire Lancer move together to one page-2 slot",
      len(fl) == 1 and fl <= _PAGE2_USABLE, fl)
for name, line, bldg in (("Jian Swordsman", JIAN, BARRACKS), ("Ibirapema", IBIRAPEMA, BARRACKS),
                         ("Elephant Archer", ELEPHANT_ARCHER, RANGE), ("Bolas Rider", BOLAS, RANGE),
                         ("Hei Guang", HEI_GUANG, STABLE)):
    got = {slot_of(SLOT, u, bldg) for u in line}
    check(f"{name} is on page 2", len(got) == 1 and got <= _PAGE2_USABLE, got)
check("Cavalry Archer and Knight lines keep page 1",
      all(slot_of(SLOT, u, RANGE) == 3 for u in CAV_ARCHER)
      and all(slot_of(SLOT, u, STABLE) == 2 for u in KNIGHT))

# ── Hotkeys mirror page 1 ────────────────────────────────────────────────────
hk_by_bldg, hk_by_pos = _grid_hotkeys(dat)
fl_slot = next(iter(fl))
want = hk_by_bldg.get((BARRACKS, fl_slot - 20), hk_by_pos.get(fl_slot - 20))
got = {tl.hot_key_id for u in FIRE_LANCER
       for tl in dat.civs[SLOT].units[u].creatable.train_locations if tl.unit_id == BARRACKS}
check("Fire Lancer takes the hotkey of the matching page-1 position", got == {want},
      f"got {got}, want {want}")

# ── The upgrade follows, on a private copy ───────────────────────────────────
print("\n=== upgrade techs follow one row down ===")
ours = [tid for tid, t in enumerate(dat.techs)
        if t.civ == SLOT and 0 <= t.effect_id < len(dat.effects)
        and any(ec.type == EC_UPGRADE and int(ec.b) == 1903
                for ec in dat.effects[t.effect_id].effect_commands)]
check("our civ owns an Elite Fire Lancer upgrade", len(ours) == 1, ours)
if ours:
    rl = dat.techs[ours[0]].research_locations[0]
    check("...at the Barracks, one row below the Fire Lancer",
          rl.location_id == BARRACKS and rl.button_id == fl_slot + 5,
          (rl.location_id, rl.button_id, fl_slot))
tt = dat.effects[dat.civs[SLOT].tech_tree_id].effect_commands
check("the shared original is disabled for our civ",
      any(ec.type == 102 and int(ec.d) == ELITE_FIRE_LANCER_TECH for ec in tt))
# Disabling alone was not enough in-game (2026-09-26): with the tree's type=8
# unlock still present, the shared Elite Battle Elephant upgrade stayed on
# page-1 button 9 and covered the Elite Steppe Lancer.
moved_originals = (ELITE_FIRE_LANCER_TECH, 631)
check("no moved original keeps its tree unlock (type=8)",
      not [ec for ec in tt if ec.type == 8 and int(ec.a) in moved_originals],
      [(int(ec.a)) for ec in tt if ec.type == 8 and int(ec.a) in moved_originals])
# Cranequins improves the Mounted Crossbowman and shares Range button 13 with
# Parthian Tactics; left behind, it hid under Parthian Tactics (in-game 2026-09-26).
if HAS_MOUNTED_XBOW:
    mx = slot_of(SLOT, MOUNTED_XBOW[0], RANGE)
    cq = [t for t in range(len(dat.techs)) if dat.techs[t].civ == SLOT
          and dat.techs[t].name == dat.techs[CRANEQUINS].name]
    check("Cranequins follows the Mounted Crossbowman, two rows down",
          len(cq) == 1 and dat.techs[cq[0]].research_locations[0].button_id == mx + 10,
          [(t, dat.techs[t].research_locations[0].button_id) for t in cq] + [("line at", mx)])
    check("Parthian Tactics keeps Range button 13",
          dat.techs[PARTHIAN_TACTICS].research_locations[0].button_id == 13
          and not any(ec.type == 102 and int(ec.d) == PARTHIAN_TACTICS for ec in tt))
    moved_originals += (HEAVY_MOUNTED_XBOW, CRANEQUINS)
    check("...and neither original Mounted Crossbowman tech stays unlocked",
          not [ec for ec in tt if ec.type == 8 and int(ec.a) in moved_originals])
check("the shared original is untouched for everyone else",
      dat.techs[ELITE_FIRE_LANCER_TECH].research_locations[0].button_id == 9)
check("a vanilla civ is untouched (Aztec Eagles on Barracks 4)",
      all(slot_of(AZTECS, u, BARRACKS) == 4 for u in EAGLE))

# ── The player's pick wins ───────────────────────────────────────────────────
print("\n=== button_moves overrides the default ===")
check("Fire Lancer keeps page 1 when picked",
      all(slot_of(SLOT_PICK, u, BARRACKS) == 4 for u in FIRE_LANCER))
eg = {slot_of(SLOT_PICK, u, BARRACKS) for u in EAGLE}
check("...and the Eagle line moves to page 2 instead", len(eg) == 1 and eg <= _PAGE2_USABLE, eg)
check("apply_civ reports the layout",
      any(e["building"] == BARRACKS and FIRE_LANCER[0] in e["units"] for e in result["button_layout"])
      and any(EAGLE[0] in e["units"] for e in result_pick["button_layout"]))

# ── DE's all-techs movers can't undo the layout ──────────────────────────────
# Seen in-game 2026-09-26: with Shrivamsha, Knights and Elite Battle Elephant,
# "[FTT] Move Shrivamsha Riders 2" put the Shrivamsha back on page-1 button 9.
print("\n=== conditional [FTT] movers are switched off ===")
for tid in FTT_MOVE_SHRIVAMSHA:
    check(f"tech {tid} ({dat.techs[tid].name}) is disabled for our civ",
          any(ec.type == 102 and int(ec.d) == tid for ec in tt))

# ── Units a UT places in a building in-game ──────────────────────────────────
# Anarchy / Marauders point a dormant (-1, button 4) train location at the
# Barracks / Stable when researched, so they clash with Eagles / Battle
# Elephants only in-game.  Give civ SLOT its own copies, as a UT pick would.
print("\n=== UT-placed units (Anarchy, Marauders) are resolved too ===")
seen: dict = {}
for tid in (ANARCHY, MARAUDERS):
    _allocate_tech(dat, tid, SLOT, seen)
with contextlib.redirect_stdout(io.StringIO()):
    _resolve_button_collisions(dat, SLOT, civ_def)
for name, line, bldg in (("Huskarl", HUSKARL, BARRACKS), ("Tarkan", TARKAN, STABLE)):
    got = {dat.civs[SLOT].units[u].creatable.train_locations[1].button_id for u in line}
    check(f"{name}'s in-game slot is on page 2", len(got) == 1 and got <= _PAGE2_USABLE, got)
check("the Eagle line still keeps Barracks button 4",
      all(slot_of(SLOT, u, BARRACKS) == 4 for u in EAGLE))

# ── A civ without clashes is left alone ──────────────────────────────────────
print("\n=== no clash, no change ===")
plain = {"alias": "Plain", "description": "", "architecture": 2, "language": 0,
         "wonder": -1, "castle": -1, "bonuses": [[], [], [], [], []],
         "tree": [[4, 74, 75, 7, 38], [BARRACKS, RANGE, STABLE, 109], []]}
with contextlib.redirect_stdout(io.StringIO()):
    plain_result = apply_civ(dat, plain, target_slot=7)
check("button_layout is empty", plain_result["button_layout"] == [], plain_result["button_layout"])

# ── The wizard's preview shows only what the civ can research ────────────────
# Reported 2026-09-27 against a real civ: the Eagle Warrior upgrade sat under
# the Fire Lancer (no Eagles in the civ), Champi upgrades under Man-at-Arms,
# Supplies (removed by DE, switched off by the Dark Age tech) on button 11, and
# the team-bonus Genitour missing while its elite upgrade showed.
print("\n=== preview: page 1 lists only what the civ can research ===")
from civ_appender import button_layout_preview                    # noqa: E402
preview_def = {
    "alias": "Preview", "description": "", "architecture": 2, "language": 0,
    "wonder": -1, "castle": -1,
    "bonuses": [[], [], [], [], [[1, 1]]],                   # team bonus 1: Genitour
    "tree": [[4, 24, 492, 7, 6, 74, 75, 77, 473, 567, 93, 358, 359, *FIRE_LANCER,
              *JIAN, *CAV_ARCHER, *BOLAS, 1962, 279, 542],
             [BARRACKS, RANGE, 49], [875]],                   # Gambesons ticked
}
PREVIEW_TECHS = {875}


def cell_names(building, button, page=0):
    for b in button_layout_preview(dat, preview_def, PREVIEW_TECHS):
        if b["building"] == building:
            first = 1 if page == 0 else 21
            cell = b["pages"][page][button - first]
            return [i["name"] for i in cell.get("items", [])]
    return None


under_lancer = cell_names(BARRACKS, 9)
check("under the Fire Lancer: its own upgrade, and no Eagle upgrade",
      under_lancer == ["Elite Fire Lancer"], under_lancer)
CHAMPI_NAMES = {"Champi Warrior", "Elite Champi Warrior", "Champi Runner", "Champi Scout (Make avail)"}
check("no Champi techs under Man-at-Arms",
      not CHAMPI_NAMES & set(cell_names(BARRACKS, 6) or []), cell_names(BARRACKS, 6))
check("no Chronicles copies of Two-Handed Swordsman / Champion",
      (cell_names(BARRACKS, 6) or []).count("Champion") == 1, cell_names(BARRACKS, 6))
check("Supplies is gone; Gambesons leads button 11",
      (cell_names(BARRACKS, 11) or [])[:1] == ["Gambesons"], cell_names(BARRACKS, 11))
check("the team-bonus Genitour is on Archery Range button 9",
      cell_names(RANGE, 9) == ["Genitour"], cell_names(RANGE, 9))
check("no Elite Elephant Archer on button 8 for a civ without Elephant Archers",
      "Elite Elephant Archer" not in (cell_names(RANGE, 8) or []), cell_names(RANGE, 8))

# ── Another civ's unique units in the tree don't count ───────────────────────
# A full wizard tree lists every vanilla UU (the editor has a node for each),
# but their techs are civ-gated, so the civ can't train them.  Counting them put
# ~50 lines on Castle button 1 and warned that the Castle was full for every
# one (reported 2026-09-28, a real civ with one KM UU).
print("\n=== other civs' UUs in the tree are not the civ's ===")
CASTLE = 82
castle_units = sorted(uid for uid, u in enumerate(dat.civs[1].units)
                      if u is not None and u.creatable is not None
                      and any(tl.unit_id == CASTLE for tl in u.creatable.train_locations))
full_tree = {"alias": "Full Tree", "description": "", "architecture": 2, "language": 0,
             "wonder": -1, "castle": -1,
             "bonuses": [[], [3], [], [], []],                    # one KM UU
             "tree": [[4, 74, 75, 7, 38, *castle_units], [BARRACKS, RANGE, STABLE, 109, CASTLE], []]}
with contextlib.redirect_stdout(io.StringIO()):
    full_result = apply_civ(dat, full_tree, target_slot=8)
full_warnings = [w for w in full_result.get("warnings", []) if "can't be trained" in w]
check("no 'both pages are full' warnings", not full_warnings, full_warnings[:3])
castle_moves = [m for m in full_result["button_layout"] if m["building"] == CASTLE]
check("nothing moves off Castle button 1", not castle_moves, castle_moves[:3])
check("the preview shows no Castle clash",
      not [b for b in button_layout_preview(dat, full_tree, set()) if b["building"] == CASTLE])

chariot = [l["name"] for b in button_layout_preview(dat, preview_def, PREVIEW_TECHS)
           for c in b["conflicts"] for l in c["lines"] if 1962 in l["units"]]
check("the War Chariot is called that, without '(Focus Fire)'", chariot == ["War Chariot"], chariot)

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
