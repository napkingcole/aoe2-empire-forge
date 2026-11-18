#!/usr/bin/env python3
"""A second unique unit at the Castle (the user, 2026-11-13).

second_uu has unique_unit's shape (km_idx, name, description, overrides,
advanced_flags, elite_upgrade, appearance) and is built by the same two paths
(civ_appender._apply_second_uu): a game unit gets this civ's copies of its
techs, a preset or scenario unit is appended new.  It trains at Castle button
4 with its Elite upgrade on 9, names itself with string ids of its own, and
anything aimed at "the unique unit" (Anarchy, custom cards) reaches it too.
The hero, which also uses button 4, goes to page 2.  DAT-gated.

    venv/bin/python tests/test_second_uu.py
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


from civ_schema import from_draft, norm_second_uu, to_draft  # noqa: E402

HUSKARL, KONNIK, CRUSADER = 2, 31, 39          # km indices: two game units, one preset
CASTLE = 82

print("=== schema ===")
raw = {"km_idx": KONNIK, "name": "Druzhina", "overrides": {"hp_base": 120, "attack_elite": None},
       "advanced_flags": {"no_convert": True, "ignore_armor": True}, "junk": 1}
n = norm_second_uu(raw)
check("keeps the pick, name and overrides; drops nulls, retired flags and junk",
      n == {"km_idx": KONNIK, "name": "Druzhina", "description": "", "overrides": {"hp_base": 120},
            "advanced_flags": {"no_convert": True}}, n)
check("no pick, no second unit", norm_second_uu({"name": "x"}) is None and norm_second_uu(None) is None)
check("saves and loads", to_draft(from_draft({"second_uu": raw}))["second_uu"] == n,
      to_draft(from_draft({"second_uu": raw})).get("second_uu"))

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
units, buildings, techs = json.loads(civ_file.read_text(encoding="utf-8"))["tree"]


def build(second, hero=None, first=HUSKARL, lines=None, cards=None):
    draft = {
        "alias": "Two Units", "architecture": 2, "language": 0, "bonuses": [], "team_bonuses": [],
        "unique_unit": {"km_idx": first},
        "second_uu": second,
        "castle_ut": {"mode": "custom", "name": "Two Anarchy", "description": "x",
                      "cost": {"food": 300, "gold": 200}, "time": 40, "effects": [{"id": 12, "multiplier": 1}]},
        "imperial_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
        "tree": {"units": units, "buildings": buildings, "techs": techs},
        "custom_bonuses": cards or [{"id": "uu1", "target": {"type": "group", "id": "unique_unit"},
                                     "effects": [{"attr": "hp", "op": "add", "value": 7}]}],
    }
    if lines:
        draft["added_lines"] = lines
    if hero is not None:
        draft["hero_unit"] = {"base_unit_id": hero, "name": "", "description": ""}
    dat = load_dat(str(dat_path))
    with contextlib.redirect_stdout(io.StringIO()):
        r, _ = apply_civ_with_overrides(dat, _draft_to_civ_def(draft), SLOT, draft)
    return dat, r


def castle_buttons(dat, uid):
    u = dat.civs[SLOT].units[uid]
    return sorted((tl.unit_id, tl.button_id) for tl in u.creatable.train_locations if tl.unit_id >= 0)


print("=== a game unit as the second (Konnik), with a hero ===")
dat, r = build({"km_idx": KONNIK, "name": "Druzhina", "overrides": {"hp_base": 123},
                "elite_upgrade": {"cost": {"food": 900, "gold": 450}, "time": 33}}, hero=1703)
s = r.get("second_uu")
check("built", bool(s), r.get("warnings"))
if s:
    us = dat.civs[SLOT].units
    uu, el, et = s["unit_id"], s["elite_id"], s["elite_tech"]
    check("trains at Castle button 4, the Elite too", castle_buttons(dat, uu)[:1] == [(CASTLE, 4)]
          and castle_buttons(dat, el)[:1] == [(CASTLE, 4)], (castle_buttons(dat, uu), castle_buttons(dat, el)))
    t = dat.techs[et]
    check("its Elite upgrade is this civ's own, at Castle button 9",
          t.civ == SLOT and any(rl.location_id == CASTLE and rl.button_id == 9 for rl in t.research_locations),
          (t.civ, [(rl.location_id, rl.button_id) for rl in t.research_locations]))
    check("...at the price set for it", {rc.type: rc.amount for rc in t.resource_costs if rc.amount > 0}
          == {0: 900, 3: 450} and t.research_locations[0].research_time == 33,
          ([(rc.type, rc.amount) for rc in t.resource_costs], t.research_locations[0].research_time))
    check("named with string ids of its own",
          us[uu].language_dll_name == s["sids"][0] and us[el].language_dll_name == s["sids"][1]
          and s["names"] == ["Druzhina", "Elite Druzhina"], (s["sids"], s["names"]))
    strings = {e["sid"]: e["name"] for e in r["bonus_results"]["extra_unit_strings"]}
    check("...which the routes write (extra_unit_strings)",
          strings.get(s["sids"][0]) == "Druzhina" and strings.get(s["sids"][1]) == "Elite Druzhina")
    check("its overrides land on it", us[uu].hit_points == 123, us[uu].hit_points)
    vanilla_konnik = dat.civs[0].units[uu]
    check("...and not on the game's own Konnik", vanilla_konnik.language_dll_name != s["sids"][0])
    first = r["uu_id"]
    check("the first unique unit keeps Castle button 1", castle_buttons(dat, first)[:1] == [(CASTLE, 1)],
          castle_buttons(dat, first))
    check("the hero leaves button 4 for page 2", castle_buttons(dat, 1703)[:1] == [(CASTLE, 21)]
          or any(b > 20 for _, b in castle_buttons(dat, 1703)), castle_buttons(dat, 1703))
    # Anarchy: "the unique unit" trains at the Barracks — both of them.
    moved = {int(c.a) for e in dat.effects for c in e.effect_commands if c.type == 0 and int(c.c) == 42
             and int(c.a) in (first, uu)}
    check("Anarchy reaches both unique units", moved == {first, uu}, moved)
    hp7 = {int(c.a) for e in dat.effects for c in e.effect_commands
           if c.type == 4 and int(c.c) == 0 and c.d == 7}
    check("a card for unique units reaches both, Elites too", {first, r["elite_uu_id"], uu, el} <= hp7,
          sorted(hp7))

print("=== a preset as the second (Crusader Knight), and a line added at the Castle ===")
CASTLE_LINE = [{"id": 1, "building": CASTLE, "base": 36, "tiers": [{"age": 3}]}]   # a Bombard Cannon copy
dat, r = build({"km_idx": CRUSADER}, lines=CASTLE_LINE)
s = r.get("second_uu")
check("built", bool(s), r.get("warnings"))
if s:
    check("appended as new units, on Castle button 4",
          s["unit_id"] >= 2000 and castle_buttons(dat, s["unit_id"])[:1] == [(CASTLE, 4)],
          (s["unit_id"], castle_buttons(dat, s["unit_id"])))
    check("named after the preset", s["names"][0] == "Crusader Knight", s["names"])
check("the Castle takes one extra: the added line is left out, with a warning",
      not r.get("added_lines") and any("already has its second unique unit" in w for w in r["warnings"]),
      (r.get("added_lines"), r["warnings"]))
dat, r = build(None, lines=CASTLE_LINE + [dict(CASTLE_LINE[0], id=2)])
check("...and only one line is added there without a second unique unit",
      len(r.get("added_lines") or []) == 1, r.get("added_lines"))
check("...on the second unique unit's button, 4",
      (r.get("added_lines") or [{}])[0].get("button") == 4, (r.get("added_lines") or [{}])[0].get("button"))

print("=== a built second unique unit (a Castle line, three tiers) ===")
BUILT = [{"id": 1, "building": CASTLE, "base": 280, "name": "Super Mangonel",       # a Mangonel copy
          "tiers": [{"age": 3}, {"age": 3, "name": "Veteran Mangonel"}, {"age": 4, "name": "Elite Mangonel"}]}]
dat, r = build(None, lines=BUILT)
ln = (r.get("added_lines") or [{}])[0]
tiers = ln.get("units") or []
check("built, three tiers", len(tiers) == 3, (tiers, r["warnings"]))
if len(tiers) == 3:
    moved = {int(c.a) for e in dat.effects for c in e.effect_commands if c.type == 0 and int(c.c) == 42}
    check("Anarchy reaches every tier", set(tiers) <= moved, (tiers, sorted(moved)))
    hp7 = {int(c.a) for e in dat.effects for c in e.effect_commands
           if c.type == 4 and int(c.c) == 0 and c.d == 7}
    check("a card for unique units reaches every tier", set(tiers) <= hp7, (tiers, sorted(hp7)))
    check("...and the first unique unit still", {r["uu_id"], r["elite_uu_id"]} <= hp7)

print("=== an Elite Petard beside a second unique unit (#118) ===")
PETARD = [{"id": 1, "building": CASTLE, "base": 440, "from": 440, "tiers": [{"age": 4, "name": "Elite Petard"}]}]
from civ_schema import norm_added_lines  # noqa: E402
check("a tier after the Petard is kept when the civ is saved (preview.1 dropped every Castle line)",
      len(norm_added_lines(PETARD)) == 1)
dat, r = build({"km_idx": KONNIK}, lines=PETARD)
pl = (r.get("added_lines") or [{}])[0]
check("built beside the second unique unit (an extension isn't the Castle's extra)",
      pl.get("techs") and r.get("second_uu"), r["warnings"])
if pl.get("techs"):
    btn = [rl.button_id for rl in dat.techs[pl["techs"][0]].research_locations if rl.location_id == CASTLE]
    check("its upgrade takes neither the second unique unit's Elite button (9) nor the page button (15)",
          btn and btn[0] not in (9, 15), btn)

print("=== a Konnik as the FIRST unique unit ===")
dat, r = build(None, first=KONNIK)
check("is the Konnik the Castle trains (1225/1227), not its dismounted form listed first",
      (r["uu_id"], r["elite_uu_id"]) == (1225, 1227), (r["uu_id"], r["elite_uu_id"]))

print("=== the same unit twice ===")
dat, r = build({"km_idx": HUSKARL})
check("is left out, with a warning", r.get("second_uu") is None
      and any("same as the first" in w for w in r["warnings"]), r["warnings"])

print("=== extra projectiles on the unique units: the ranged one only (#114) ===")
LONGBOW = 0
dat, r = build({"km_idx": HUSKARL}, first=LONGBOW,
               cards=[{"id": "p2", "target": {"type": "group", "id": "unique_unit"},
                       "effects": [{"attr": "projectiles", "op": "add", "value": 2}]}])
s = r.get("second_uu") or {}
proj = {(int(c.a), int(c.c)): c.d for e in dat.effects for c in e.effect_commands
        if c.type == 4 and int(c.c) in (102, 107) and int(c.a) in (r["uu_id"], r["elite_uu_id"],
                                                                 s.get("uu_id"), s.get("elite_uu_id"))}
check("the Longbowman and its Elite: +2 to 102 and 107, as Bolt Magazine",
      all(proj.get((u, f)) == 2.0 for u in (r["uu_id"], r["elite_uu_id"]) for f in (102, 107)), proj)
check("the Huskarl (melee second) gets none", not any(a in (s.get("uu_id"), s.get("elite_uu_id"))
                                                       for a, _ in proj), (s, proj))

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
