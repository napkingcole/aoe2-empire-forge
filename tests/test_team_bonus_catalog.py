#!/usr/bin/env python3
"""Guard the two ways the team-bonus catalog has silently gone wrong.

Both bugs this pins shipped, and both were invisible to every other test,
because "the catalog has an entry for this id" was the only thing anyone ever
checked and both bugs were *well-formed* entries pointing somewhere else.

**1. The tech-id / effect-id namespace trap.**  `bonus_catalog_raw.json["team"]`
holds EFFECT indices — `_apply_bonuses` does `dat.effects[eff_idx]` — but tech
ids and effect ids are both small integers, so a tech id in that column reads
back as a perfectly valid, perfectly wrong effect.  On 2026-09-17 a fix meant to
correct team bonuses 8 and 30 wrote the two *tech* ids into it, and the game
then shipped allies a Fire Galley (effect 232) and a free Elite Leitis upgrade
(effect 721) under cards reading "Farms +10% food" and "Military buildings
provide +5 population room".  Entry 45 had pointed at 601 'Carrack' since the
catalog was extracted.

The invariant that catches it: every effect index in the `team` map must be a
real team bonus — either some civ's own `civ.team_bonus_id`, or one of the small
set of tech-delivered team bonuses listed in TECH_DELIVERED below.

**2. Key drift between the catalog and the names file.**  `team_ec_list` is
keyed by team bonus id, and on 2026-07-03 `team_bonus_names.json` was rewritten
into KM's authoritative ordering to fix a shuffle from index 11 on — but
`team_ec_list`, authored a week earlier against the *old* names, was never
re-keyed.  For ten weeks every one of its 30 entries did a different bonus's
job.  The loudest was id 54: the card said "Spearmen +3 attack vs. cavalry"
(3 commands) and the entry was "Unique Units +5% HP" (142 commands), which on a
civ with 15 team bonuses pushed the merged team-bonus effect to 246 commands and
crashed the game at startup.

There is no way to re-derive intent from an EC list alone, so this half pins the
handful of entries whose size and shape make the drift detectable: a card
promising a named handful of units must not carry a sweeping list, and the ids
whose meaning was actually confirmed stay where they were put.

Dependency-free where it can be; the `team` map check needs the DAT and skips
itself cleanly without one.

    venv/bin/python tests/test_team_bonus_catalog.py
"""

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
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


catalog = json.loads((ROOT / "bonus_catalog_raw.json").read_text())
names = json.loads((ROOT / "team_bonus_names.json").read_text())
team_map = catalog["team"]
team_ec = catalog["team_ec_list"]

# ── 1. Every `team` entry must name a real team bonus effect ─────────────────
# Two vanilla civs deliver their team bonus from a *tech* whose effect carries
# type=10 (team-scoped) commands, leaving civ.team_bonus_id an empty stub.  Those
# effects are legitimate sources even though no civ points at them, so they are
# named here rather than blanket-exempted.
TECH_DELIVERED = {
    758: "Slavic team bonus — techs[721].effect_id; civ 23's own team_bonus_id "
         "is effect 9, which DE emptied. 12 type=10 +5 pop commands.",
    240: "Chinese TB (Reapply) — techs[232].effect_id; civ 6's team_bonus_id is "
         "effect 402, which only makes tech 232 free and instant.",
    1403: "Tupi team bonus — techs[1403].effect_id; civ 59's team_bonus_id is "
          "effect 1359. 3 type=10 population commands.",
    1089: "Wu TB local — techs[1089].effect_id, and what civ 50's team_bonus_id "
          "(effect 1031) points at: 1031 holds a single type=18 indirection "
          "command naming 1089. The commands live here, so this is what team "
          "bonus 40 'Houses built 100% faster' copies.",
}

try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:
    dat_path = None

if dat_path is None:
    print("  skip team-map check — no game DAT found")
else:
    dat = load_dat(str(dat_path))
    owned = {c.team_bonus_id for c in dat.civs
             if getattr(c, "team_bonus_id", None) is not None}
    for key in sorted(team_map, key=int):
        eff_idx = team_map[key]
        label = f"team {key} ({names.get(key, '?')[:40]!r}) -> effect {eff_idx}"
        if not isinstance(eff_idx, int) or not (0 <= eff_idx < len(dat.effects)):
            check(label, False, "not a valid effect index")
            continue
        eff_name = dat.effects[eff_idx].name
        check(label, eff_idx in owned or eff_idx in TECH_DELIVERED,
              f"effect {eff_idx} {eff_name!r} is not any civ's team_bonus_id and "
              f"is not a known tech-delivered team bonus. A tech id in this "
              f"column reads back as a valid wrong effect — check "
              f"dat.techs[{eff_idx}].effect_id before trusting it.")

    # The three that were actually wrong, pinned by value so a re-extraction
    # from KM's C++ cannot quietly restore them.
    check("team 8 'Farms +10% food' -> effect 240, not tech id 232",
          team_map.get("8") == 240, f"got {team_map.get('8')}")
    check("team 30 'Military buildings +5 pop' -> effect 758, not tech id 721",
          team_map.get("30") == 758, f"got {team_map.get('30')}")
    check("team 45 has no effect entry (601 was 'Carrack'), uses its ec_list",
          "45" not in team_map and "45" in team_ec,
          f"team_map has {team_map.get('45')!r}, team_ec has 45: {'45' in team_ec}")

# ── 2. team_ec_list keys line up with the current names file ─────────────────
# Entries whose command count was the tell when the keys had drifted.  Each is
# "this card names N things, so its list must be about N long".
EXPECTED = {
    "44": (142, 142, "Unique Units +5% HP — one MULTIPLY per unique unit; the "
                     "only entry that may be this large, and on its own it eats "
                     "three quarters of the ~189 effect-command budget."),
    "54": (6, 6, "Spearmen +3 attack vs. cavalry — Spearman/Pikeman/Halberdier "
                 "plus the three Donjon copies, which 14 of the 31 vanilla "
                 "effects naming the spear line also carry."),
    "53": (2, 2, "Steppe Lancers +3 LOS — base and elite."),
    "58": (4, 4, "Monasteries 3x HP — one id per age/architecture (30/31/32/104)."),
    "59": (3, 3, "Markets 3x HP — one id per age (84/116/137)."),
    "50": (25, 35, "All resources last 5% longer — the productivity ids plus a "
                   "compensating work-rate cut per gatherer."),
    "67": (15, 25, "Town Centers +4 LOS — every per-age/per-architecture TC id."),
}
for key, (lo, hi, why) in EXPECTED.items():
    entry = team_ec.get(key)
    n = len(entry) if entry else 0
    check(f"team_ec_list[{key}] ({names.get(key, '?')[:38]!r}) has {lo}..{hi} commands",
          entry is not None and lo <= n <= hi, f"got {n} — {why}")

# ── 2b. Content sweep results (2026-09-18) ──────────────────────────────────
# Re-keying put each ec_list under the right card; the sweep then checked what
# each one actually targets.  Twelve were wrong in ways no key check can see, so
# the specific corrections are pinned here.  Unit rosters were resolved through
# language_dll_name against the vanilla string table — `unit.name` is an internal
# codename and lies (775 'MONKY' is the Missionary, 1137 'TIGER' is an elephant
# slot, 1572 'MERCHANT' is not the Imperial Skirmisher).
ARMOUR = {"cavalry": 8, "war_elephants": 5, "standard_buildings": 21,
          "gunpowder": 23, "unique_units": 19, "unused_31": 31}


def ids_in(key):
    return [e["A"] for e in team_ec.get(key, [])]


def attrs_in(key):
    return {e["C"] for e in team_ec.get(key, [])}


def packed_armour(key):
    return {int(e["D"]) >> 8 for e in team_ec.get(key, []) if e["C"] == 9}


# Attribute 20 is Minimum Range (UGC guide), so "built 100% faster" did nothing
# at all.  A building's construction time is its creatable.train_time — attribute
# 101 — verified against the in-game numbers (Mill 35s, Market 60s, House 25s).
for key in ("43", "63"):
    check(f"team_ec_list[{key}] ({names[key][:34]!r}) uses train time, not Minimum Range",
          attrs_in(key) == {101},
          f"attributes present: {sorted(attrs_in(key))} — 20 is Minimum Range, inert here")

# Armour classes that make the card true, and the two that made it a no-op.
check("48 'vs. Elephant units' hits armour class 5, not 19 (Unique Units)",
      packed_armour("48") == {ARMOUR["war_elephants"]},
      f"got {packed_armour('48')}")
check("47 'vs. gunpowder units' hits armour class 23, not 31 (Unused)",
      packed_armour("47") == {ARMOUR["gunpowder"]},
      f"got {packed_armour('47')}")
check("54 'vs. cavalry' hits armour class 8",
      packed_armour("54") == {ARMOUR["cavalry"]}, f"got {packed_armour('54')}")
check("55 'vs. buildings' hits armour class 21",
      packed_armour("55") == {ARMOUR["standard_buildings"]}, f"got {packed_armour('55')}")

# Rosters: the wrong ids that were actually in there, and the upgrade tiers that
# were missing so the bonus evaporated when the unit upgraded.
WRONG_IDS = {
    "39": [(1026, "an Ostrich, in 'Trade units +50 HP'")],
    "45": [(1572, "the Merchant, standing in for Imperial Skirmisher 1155"),
           (594, "a Sheep, standing in for Scout Cavalry 448"),
           (74, "the Militia, which is not a spearman")],
    "54": [(74, "the Militia, which is not a spearman")],
    "55": [(829, "the Elite War Wagon"), (1137, "a wild tiger")],
}
for key, bad in WRONG_IDS.items():
    for uid, why in bad:
        check(f"team_ec_list[{key}] no longer targets {uid} ({why})",
              uid not in ids_in(key))

MUST_CONTAIN = {
    "45": [(1155, "Imperial Skirmisher"), (448, "Scout Cavalry"), (358, "Pikeman")],
    "48": [(567, "Champion"), (358, "Pikeman")],
    "54": [(358, "Pikeman")],
    "55": [(1132, "Battle Elephant"), (873, "Elephant Archer"), (1744, "Armored Elephant")],
    "56": [(752, "Elite Eagle Warrior"), (726, "Elite Jaguar Warrior")],
    "58": [(30, "Monastery age 1"), (31, "Monastery age 2"), (32, "Monastery age 3")],
    "59": [(116, "Market age 2"), (137, "Market age 3")],
    "43": [(565, "Lumber Camp age 4"), (587, "Mining Camp age 4")],
    "50": [(216, "the female Hunter — vanilla pairs the genders in all 16 "
                 "effects that name either")],
}
for key, wanted in MUST_CONTAIN.items():
    for uid, why in wanted:
        check(f"team_ec_list[{key}] includes {uid} ({why})", uid in ids_in(key))

# 40 is the Wu team bonus, found by scanning vanilla for attribute-101 writes to
# buildings.  It had been written off with the other ten orphans as "KM-invented,
# no vanilla effect to copy"; that was an assumption, and for this one it was
# wrong.  The other ten were then re-checked by the same method and really do
# have nothing to copy.
check("40 'Houses built 100% faster' maps to the Wu effect",
      team_map.get("40") == 1089, f"got {team_map.get('40')}")

# No id may be implemented twice: the effect map wins in _apply_bonuses, so an
# ec_list sharing its key is dead code that reads like a live implementation.
overlap = sorted(set(team_ec) & set(team_map), key=int)
check("no id has both a team effect and an ec_list", not overlap,
      f"ids in both: {overlap}")

# Every key on both sides must be a team bonus that actually exists.
import bonus_names  # noqa: E402

bad_keys = [k for k in list(team_ec) + list(team_map)
            if not (0 <= int(k) < bonus_names._TEAM_BONUS_COUNT)]
check("every catalog key is inside _TEAM_BONUS_COUNT", not bad_keys,
      f"out of range: {sorted(set(bad_keys), key=int)}")

# ── 3. The merged effect must be able to hold a full pick ────────────────────
# _apply_bonuses concatenates every picked team bonus into one effect, and the
# engine crashes at startup past ~189 commands.  Nothing stops a user picking
# fifteen, so the check that matters is "is any single one big enough to be a
# hazard on its own", which is how id 44 has to be treated.
sizes = {}
for key, entry in team_ec.items():
    sizes[key] = len(entry)
if dat_path is not None:
    for key, eff_idx in team_map.items():
        if isinstance(eff_idx, int) and 0 <= eff_idx < len(dat.effects):
            sizes[key] = len(dat.effects[eff_idx].effect_commands)
    heavy = {k: n for k, n in sizes.items() if n > 100}
    check("only the documented giant exceeds 100 commands", set(heavy) <= {"44"},
          f"heavy entries: { {k: (sizes[k], names.get(k)) for k in sorted(heavy, key=int)} }")

    # ── 4. apply_civ's guard actually fires ──────────────────────────────────
    # The catalog checks above stop the *known* way to overrun the ceiling.
    # They cannot stop a user picking id 44 plus a dozen twenty-command bonuses,
    # so the guard is the real safety net — and an untested safety net is the
    # one that turns out not to work.
    import contextlib
    import io

    from civ_appender import apply_civ  # noqa: E402

    def build_team(team_ids, slot):
        cd = {"alias": "TB Probe", "description": "", "architecture": 2,
              "language": 0, "wonder": -1, "castle": -1,
              # bonuses = [civ, [uu_idx], castle_ut, imperial_ut, team]
              "bonuses": [[], [], [], [], [[i, 1] for i in team_ids]],
              "tree": [[], [], []]}
        with contextlib.redirect_stdout(io.StringIO()):
            return apply_civ(dat, cd, target_slot=slot)

    # 44 alone is 142; adding the three 20-command vanilla bonuses clears 185.
    over = build_team([44, 82, 71, 34], slot=5)
    warned = [w for w in over.get("warnings", []) if "Team bonus effect has" in w]
    check("apply_civ warns when the merged team-bonus effect overruns",
          bool(warned), f"warnings were: {over.get('warnings')}")
    check("the overrun warning names the biggest contributor (#44)",
          bool(warned) and "#44" in warned[0], f"got: {warned}")

    # The reporter's own 15-bonus pick, which used to land at 246 commands.
    ok = build_team([54, 82, 75, 71, 15, 25, 53, 37, 32, 1, 14, 35, 27, 6, 4],
                    slot=6)
    check("the 15-team-bonus civ that crashed now builds under the ceiling",
          not [w for w in ok.get("warnings", []) if "Team bonus effect has" in w],
          f"warnings were: {ok.get('warnings')}")
    check("a team bonus with no implementation is reported, not silently dropped",
          any("#75" in w and "no implementation" in w
              for w in ok.get("warnings", [])),
          f"warnings were: {ok.get('warnings')}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
