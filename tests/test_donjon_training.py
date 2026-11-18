#!/usr/bin/env python3
"""What the Donjon, Krepost and Settlement train, after a unit is customised (#132).

A player swapped the Halberdier for a "Heavy Spearman" and it stopped showing
at the Donjon.  An added tier trained only at its own building, though the
unit it replaces or extends trains at others too (the Spearman line at the
Donjon, the Petard at the Krepost), and the Settlement card's slot is inserted
by commands naming the vanilla Spearmen.  The Krepost and the Donjon train
every unique unit, the second and a built one too — at the Donjon from the
Castle Age only (the user, 2026-11-17), which the units' own make-available
techs already ensure; the Serjeant stays Feudal there, as in the game.
A player has the Donjon from card 109 and the Krepost from card 93 (the tree
drops a Donjon node, and a Krepost node alone builds nothing), so these civs
take the cards — the first QA mod ticked the nodes and could build neither.
DAT-gated.

    venv/bin/python tests/test_donjon_training.py
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


try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
civ_file = ROOT / "my_civs" / "19_Cannoneers.json"
if dat_path is None or not civ_file.exists():
    print("  skip  no game DAT (or my_civs/19_Cannoneers.json) found")
    sys.exit(0)

from civ_overrides import apply_civ_with_overrides  # noqa: E402
from retired_cards import TREE_VERSION  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402

SLOT = 1
CASTLE, DONJON, KREPOST, SETTLEMENT, BARRACKS = 82, 1665, 1251, 2556, 12
PIKEMAN, HALBERDIER, PETARD, MAN_AT_ARMS = 358, 359, 440, 77
MAILLOTINS, KONNIK, SERJEANT = 65, 31, 36                    # km indices
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]


DONJON_CARD, KREPOST_CARD = 109, 93


def build(bonuses=(DONJON_CARD,), second=None, lines=(), first=MAILLOTINS):
    draft = {"tree_version": TREE_VERSION, "alias": "Donjon", "architecture": 2, "language": 0,
             "bonuses": [{"id": b, "multiplier": 1} for b in bonuses], "team_bonuses": [],
             "unique_unit": {"km_idx": first}, "second_uu": second,
             "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
             "imperial_ut": {"mode": "vanilla", "effects": [{"id": 4, "multiplier": 1}]},
             "tree": {"units": units, "buildings": buildings, "techs": techs},
             "added_lines": list(lines)}
    dat = load_dat(str(dat_path))
    with contextlib.redirect_stdout(io.StringIO()):
        r, _ = apply_civ_with_overrides(dat, _draft_to_civ_def(draft), SLOT, draft)
    return dat, r


def slots(dat, uid):
    u = dat.civs[SLOT].units[uid]
    return sorted((tl.unit_id, tl.button_id) for tl in u.creatable.train_locations if tl.unit_id >= 0)


def inserted(dat, uid):
    """Buildings a tech this civ gets inserts a train slot for `uid` at."""
    from added_lines import _slot_blocks
    civ = dat.civs[SLOT]
    effects = {civ.tech_tree_id} | {t.effect_id for t in dat.techs if t.civ == SLOT}
    return {b for e in effects if 0 <= e < len(dat.effects)
            for u, b, _ in _slot_blocks(dat.effects[e].effect_commands) if u == uid}


HEAVY = {"id": 1, "building": BARRACKS, "base": MAN_AT_ARMS, "replaces": HALBERDIER,
         "tiers": [{"age": 4, "name": "Heavy Spearman"}]}
AFTER = {"id": 2, "building": BARRACKS, "base": HALBERDIER, "from": HALBERDIER,
         "tiers": [{"age": 4, "name": "Heavy Halberdier"}]}
ELITE_PETARD = {"id": 3, "building": CASTLE, "base": PETARD, "from": PETARD,
                "tiers": [{"age": 4, "name": "Elite Petard"}]}

print("=== the reporter's civ: Maillotins, the Halberdier replaced, a Donjon ===")
dat, r = build(lines=[HEAVY])
check("the game's own Halberdier trains at the Donjon, button 2",
      (DONJON, 2) in slots(dat, HALBERDIER) and (DONJON, 2) in slots(dat, PIKEMAN))
heavy = (r.get("added_lines") or [{}])[0].get("units") or []
check("the Heavy Spearman is built", len(heavy) == 1, r["warnings"])
if heavy:
    check("...and trains at the Barracks AND the Donjon, both on the Halberdier's button 2",
          slots(dat, heavy[0]) == [(BARRACKS, 2), (DONJON, 2)], slots(dat, heavy[0]))
uu, elite = r["uu_id"], r["elite_uu_id"]
check("the Maillotins and their Elite train at the Castle and the Donjon, button 1",
      slots(dat, uu) == [(CASTLE, 1), (DONJON, 1)] and slots(dat, elite) == [(CASTLE, 1), (DONJON, 1)],
      (slots(dat, uu), slots(dat, elite)))
check("...on the Serjeant's Donjon hotkey",
      {tl.hot_key_id for tl in dat.civs[SLOT].units[uu].creatable.train_locations if tl.unit_id == DONJON}
      == {16408})
avail = [t for t in dat.techs if t.civ == SLOT and t.effect_id >= 0 and any(
    c.type == 2 and int(c.a) == uu and int(c.b) == 1 for c in dat.effects[t.effect_id].effect_commands)]
check("...only from the Castle Age: the tech that makes them available waits for it",
      avail and all(102 in t.required_techs for t in avail), [list(t.required_techs) for t in avail])

print("=== a tier after the Halberdier ===")
dat, r = build(lines=[AFTER])
after = (r.get("added_lines") or [{}])[0].get("units") or []
check("trains at the Donjon too", after and (DONJON, 2) in slots(dat, after[0]),
      slots(dat, after[0]) if after else r["warnings"])

print("=== no Donjon, no Donjon slot ===")
dat, r = build(bonuses=(), lines=[HEAVY])
check("the Maillotins train at the Castle only", slots(dat, r["uu_id"]) == [(CASTLE, 1)], slots(dat, r["uu_id"]))

print("=== the Serjeant, who builds Donjons ===")
dat, r = build(first=SERJEANT)
check("trains at the Donjon as the game's does", (DONJON, 1) in slots(dat, r["uu_id"]), slots(dat, r["uu_id"]))
dat, r = build(second={"km_idx": SERJEANT}, first=KONNIK)
s = r.get("second_uu")
check("as the second unique unit, he moves to Donjon button 4, beside the first on 1",
      s and slots(dat, s["unit_id"]) == [(CASTLE, 4), (DONJON, 4)] and (DONJON, 1) in slots(dat, r["uu_id"]),
      (slots(dat, s["unit_id"]), slots(dat, r["uu_id"])) if s else r["warnings"])
if s:
    check("...and his Elite upgrade, researched there too, to button 9",
          {rl.button_id for rl in dat.techs[s["elite_tech"]].research_locations if rl.location_id == DONJON} == {9},
          [(rl.location_id, rl.button_id) for rl in dat.techs[s["elite_tech"]].research_locations])

print("=== a second unique unit, and the Krepost ===")
dat, r = build(bonuses=(DONJON_CARD, KREPOST_CARD), second={"km_idx": KONNIK}, lines=[ELITE_PETARD])
s = r.get("second_uu")
check("the second unique unit trains at the Castle, Krepost and Donjon, all on button 4",
      s and slots(dat, s["unit_id"]) == [(CASTLE, 4), (KREPOST, 4), (DONJON, 4)],
      slots(dat, s["unit_id"]) if s else r["warnings"])
check("the first at all three on button 1",
      slots(dat, r["uu_id"]) == [(CASTLE, 1), (KREPOST, 1), (DONJON, 1)],
      slots(dat, r["uu_id"]))
ep = next((ln for ln in r.get("added_lines") or [] if ln.get("from") == PETARD), {}).get("units") or []
check("an Elite Petard trains at the Krepost, as the Petard does",
      ep and {b for b, _ in slots(dat, ep[0])} == {CASTLE, KREPOST}, slots(dat, ep[0]) if ep else r["warnings"])

print("=== built at the Castle (a second unique unit made from a unit) ===")
BUILT = {"id": 4, "building": CASTLE, "base": 280, "name": "Super Mangonel", "tiers": [{"age": 3}, {"age": 4}]}
dat, r = build(bonuses=(DONJON_CARD, KREPOST_CARD), lines=[BUILT])
tiers = (r.get("added_lines") or [{}])[0].get("units") or []
check("every tier trains at the Krepost and the Donjon too",
      len(tiers) == 2 and all({b for b, _ in slots(dat, t)} == {CASTLE, KREPOST, DONJON} for t in tiers),
      [slots(dat, t) for t in tiers] or r["warnings"])

print("=== tiers past a replacement, and their pictures ===")
TWO = {"id": 5, "building": BARRACKS, "base": PIKEMAN, "replaces": HALBERDIER,
       "tiers": [{"age": 3, "name": "Heavy Spearman"}, {"age": 4, "name": "Halberdier"}]}
MANGOS = {"id": 6, "building": CASTLE, "base": 280, "name": "Super Mangonel",
          "tiers": [{"age": 3}, {"age": 3}, {"age": 4}]}
dat, r = build(lines=[TWO, MANGOS])
two = next((ln for ln in r.get("added_lines") or [] if ln["id"] == 5), None)
halb_btn = {rl.button_id for rl in dat.techs[429].research_locations if rl.location_id == BARRACKS}
check("the next tier's upgrade shares the Halberdier upgrade's button, as the game's chains do (7)",
      two and two["upgrade_button"] in halb_btn and halb_btn == {7},
      (two or {}).get("upgrade_button"))
units0 = dat.civs[0].units
tower_icons = {t.icon_id for t in dat.techs if 0 <= t.effect_id < len(dat.effects) and any(
    c.type == 3 and 0 <= int(c.b) < len(units0) and units0[int(c.b)] is not None and units0[int(c.b)].type == 80
    for c in dat.effects[t.effect_id].effect_commands)}
mangos = next((ln for ln in r.get("added_lines") or [] if ln["id"] == 6), None)
icons = [dat.techs[t].icon_id for t in (mangos or {}).get("techs", []) if dat.techs[t].research_locations
         and any(rl.location_id >= 0 for rl in dat.techs[t].research_locations)]
check("a Mangonel line's upgrades wear no building's picture (the Guard Tower's shares its number)",
      mangos and icons and not set(icons) & tower_icons, icons)

print("=== the Mapuche Settlement card (371) ===")
dat, r = build(bonuses=(DONJON_CARD, 371), lines=[HEAVY])
check("the game's Spearmen get a Settlement slot from it", SETTLEMENT in inserted(dat, HALBERDIER),
      inserted(dat, HALBERDIER))
heavy = (r.get("added_lines") or [{}])[0].get("units") or []
check("...and so does the Heavy Spearman, once", heavy and SETTLEMENT in inserted(dat, heavy[0]),
      inserted(dat, heavy[0]) if heavy else r["warnings"])
if heavy:
    from added_lines import _slot_blocks
    n = sum(1 for e in dat.effects for u, b, _ in _slot_blocks(e.effect_commands)
            if u == heavy[0] and b == SETTLEMENT)
    check("...in one effect only (two inserts would be two buttons)", n == 1, n)

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
