"""
bonus_catalog.py — Maps KM bonus IDs to lists of vanilla auto-fire tech IDs.

Mechanism (matches KM's civbuilder.cpp):
  - Each civ bonus ID maps to one or more vanilla tech IDs.
  - To apply a bonus, deepcopy each tech, set tech.civ = custom_civ_index,
    deepcopy its effect (so other civs sharing that effect are unaffected),
    and append both to dat.techs / dat.effects.
  - Multiplier > 1 means repeat each EffectCommand that many times.

Source: extracted from fritz-net/AoE2-Civbuilder modding/civbuilder.cpp +
        modding/enums/tech_ids.h via parse_bonus_catalog.py.

DELIBERATE DIVERGENCE FROM KM — do not "restore" these from his source:
  - civ bonus 54 ("Fishermen work 10% faster").  KM maps it to tech 469
    (civbuilder.cpp: `civBonuses[CIV_BONUS_54_FISHERMEN_WORK_10_FASTER] = {469}`),
    but tech 469 is `[SCEN] Move Tarkan`, a scenario-editor tech that sets
    attribute 42 (train location) to -1 on units 755/757.  It has nothing to do
    with fishing and may break Tarkan training.  No vanilla tech implements this
    bonus, so it lives in ec_list instead: EC_MULTIPLY on the fishing villagers
    56 (VMFIS) and 57 (VFFIS), attribute 13, d=1.1 — the same shape vanilla uses
    for every other per-task villager work-rate bonus (see effects 956/958).

  The rest came out of the 2026-09-09 catalog sweep
  (docs/AUDIT-bonus-catalog-mismaps.md).  Four of them are KM pointing at DAT
  slots that are empty in the shipped game — `RESERVED` / unnamed techs with
  `effect_id = -1`, which he never populates either, so they have never done
  anything.  Re-extracting from his C++ would silently restore all five.

  - 357 ("Shepherds and Herders generate +10% additional food") — KM maps it to
    TECH_RESERVED_20 (tech 1003, `effect_id=-1`).  Now an ec_list `cMulResource`
    (type 6) on resource 216, livestock food, d=1.1 — the same lever bonus 94
    uses to make animals last longer.  DE dropped this Khitan bonus, so there is
    no vanilla tech left to copy.
  - 306 ("Scorpions cost -60% gold and benefit from Ballistics") — the Ballistics
    half was TECH_RESERVED_2 (tech 893, `effect_id=-1`).  DE gave Ballistics to
    every civ's Scorpions, so that half is now redundant: dropped 893, and the
    card is retitled to what tech 892 actually does, -50% gold.
  - 342 ("Careening, Dry Dock available one age earlier, cost/time -75%") —
    TECH_CAREENING_REQUIREMENT / TECH_DRY_DOCK_REQUIREMENT (1077/1078) are
    unnamed and empty.  The naval rework removed the early-availability half;
    dropped both, and the card now says what tech 1079 does — free and instant.
  - 108 ("Farm upgrades provide +125% additional food") — KM's list is
    {772, 773, 774, 815, 816, 817}, but 773/774 are the **Flemish Militia**
    make-avail and its Castle-Age stat boost, so every civ taking the farm bonus
    silently gained a unit line; 815-817 are `New Research` stubs on the empty
    effect 0.  Trimmed to {772}, which is the whole Sicilian bonus.
  - 76 ("Villagers move +5% Dark, +10% Feudal") — KM maps only {584}, the Dark
    Age step.  The Berbers' Feudal tech (600, requires 101, d=1.047619) exists
    and is simply missing from his list.  Added.

  Round 2 of the same sweep (2026-09-13):

  - 52 ("Gunpowder units cost -20%") — KM maps vanilla tech 500, which discounts
    five units and then hands Rocket Carts, Fire Lancers and Grenadiers
    **+25% hit points instead of the discount**.  That is what the shipped DAT
    does for the Portuguese, so it is vanilla-faithful and wrong for a card
    whose whole claim is a cost cut.  Now an ec_list of twelve EC_MULTIPLY on
    attribute 100, d=0.8, covering the five vanilla already had plus the ones it
    skipped (Organ Gun, Fire Lancer, Rocket Cart, Grenadier and their elites).
  - 140 ("Wonders don't cost wood…") — only the +50 population half existed.
    Added EC_SET attribute 104 = 0 on all seven WNDR ids.  The card's third
    line, "Maximum 1 Wonder", is the engine's default and needs no command, so
    it came off the card rather than being implemented.
  - 191 ("Explosive units 2x HP") — `MULT class 35` already covers Petard,
    Flaming Camel and the unbuildable Saboteur (706), but demolition **ships**
    are class 22 (Warship), shared with Galleys, so they can never be swept in
    by class.  Added 527/528/1104 and the Grenadier (1911) by id.

  Not catalog changes but the same sweep, both in civ_appender:
  - 360 ("Heavy Cavalry Archer available in Castle Age") needs
    `_ALT_PREREQ_BONUSES` wiring, because tech 218 wants 2 of [103, 192, 1004]
    and 1004 is the civ-gated trigger that _allocate_tech copies to a new id
    (CLAUDE.md quirk 9).
  - 312 ("…economic drop-off buildings cost -25%") discounted only the Mule
    Cart.  The buildings have no vanilla tech, and 312 already maps eight techs
    — and the bonus dispatch is exclusive, so an ec_list would never be read for
    it.  `_apply_dropoff_discount` runs as a supplement after the tech branch,
    the same shape bonus 105 uses after its ec_list.

TEAM BONUSES — two traps, both of which have bitten (2026-09-18):

  `team` holds EFFECT indices, not tech ids.  `_apply_bonuses` does
  `dat.effects[eff_idx]` directly.  Tech ids and effect ids are both small
  integers, so a tech id in that column does not fail — it reads back as a
  valid, wrong effect.  Three entries were wrong that way:
    - **8** ("Farms +10% food") held 232, the *tech* id, which as an effect is
      `Make Fire Galley Avail` — the bonus handed allies a Fire Galley.  The
      effect is 240, `Chinese TB (Reapply)` = `dat.techs[232].effect_id`.
    - **30** ("Military buildings provide +5 population room") held 721, the
      *tech* id, which as an effect is `Elite Leitis` — the bonus handed allies
      a free Elite Leitis upgrade.  The effect is 758 = `techs[721].effect_id`.
    - **45** ("Skirmishers, Spearmen, and Scout-lines train 20% faster") held
      601, `Carrack` (ships +1/+1 armour), since extraction.  It has no vanilla
      effect; the entry was removed so its `team_ec_list` entry is used.
  Note 8/30/83 are the modern DE shape: the civ's own `team_bonus_id` is an
  empty or trivial stub and the real commands live in a tech's effect (type=10
  for 30 and 83).  `tests/test_team_bonus_catalog.py` pins all of this by
  asserting every `team` value is some civ's `team_bonus_id` or one of three
  named tech-delivered effects.

  `team_ec_list` was keyed to the PRE-2026-07-03 team bonus names.  That day
  `team_bonus_names.json` was rewritten into KM's authoritative ordering to fix
  a shuffle from index 11 on (see BUGFIXES.md), but the 30 `team_ec_list`
  entries — authored a week earlier, on 2026-06-26 — were never re-keyed, so
  every one of them did a different bonus's job for ten weeks.  Re-keyed
  2026-09-18 by matching each entry's old name to its current id; the mapping
  was exact and unambiguous for all 30.  Ten then duplicated a real vanilla
  team-bonus effect (the effect map wins in `_apply_bonuses`, so they were dead
  code) and were dropped, leaving 20.

  The loudest case, and the one that found this: id **54** read "Spearmen +3
  attack vs. cavalry" (3 commands) and carried "Unique Units +5% HP" — 142
  EC_MULTIPLY commands.  On a civ with 15 team bonuses that pushed the merged
  team-bonus effect to 246 commands, over the engine's ~189 ceiling, and the
  game crashed before the main menu.

  Eleven ids lost their (wrong) implementation and now have none: 40, 42, 46,
  60, 61, 62, 66, 68, 72, 73, 75.  They fall out of the picker through
  `unsupported_team_bonuses()` and are listed on /limitations.

  CONTENT SWEEP of the 20 survivors (2026-09-18, same day).  Re-keying put each
  list under the right card; the sweep checked what each one actually targets.
  **Twelve of the twenty were wrong.**  Read BUGFIXES.md for the full table; the
  traps worth carrying forward:

    - **`unit.name` is an internal codename and lies.**  775 is 'MONKY' (the
      Missionary), 1137 is 'TIGER' (a wild animal), 1572 is 'MERCHANT', 594 is
      'SHEEPG'.  Read lists through `civ_appender.unit_label()`, which resolves
      `language_dll_name` against `vanilla/key-value/key-value-strings-utf8.txt`.
      Three wrong units had sat in these lists unnoticed precisely because the
      codenames looked plausible.
    - **Attribute 20 is Minimum Range, not build rate.**  Both "built 100%
      faster" cards (43, 63) were `EC_SET attr 20 = 1.0` and did nothing.  A
      building's construction time is its `creatable.train_time` — attribute
      101 — confirmed against in-game numbers (Mill 35s, Market 60s, House 25s).
    - **Armour class 19 is Unique Units and 31 is Unused.**  Bonus 48 ("vs.
      Elephant units") used 19; elephants are 5.  Bonus 47 ("vs. gunpowder")
      used 31, so it landed nowhere; gunpowder is 23.  Table:
      UGC guide `docs/general/damage_calculation.md`.
    - **The scout line straddles two object classes** — 448 is 47
      `cScoutCavalryClass`, Light Cav/Hussar/Winged Hussar are 12
      `cCavalryClass` — so it can only be targeted by explicit id.  Bonus 47 had
      used class 12 (every cavalry unit) plus class 58, which is `cLivestock`.
    - **Missing upgrade tiers everywhere** — no Pikeman in any of the three
      spear entries, no Champion, no Elite Eagle/Jaguar Warrior, one Monastery
      of four, one Market of three, one Lumber/Mining Camp of four.  Same shape
      as the civ-bonus Tier 2 findings.
    - Spear entries now carry the Donjon copies (1786/1787/1788): 14 of the 31
      vanilla effects naming the spear line do, including every civ-bonus one.

  Still not fixed, deliberately: bonus **49** ("Explosive units +20% speed")
  targets object class 35 `cPetardClass`, which cannot reach demolition ships —
  they are class 22 `cWarshipClass`, shared with Galleys.  Identical constraint
  to civ bonus 191; reaching them needs explicit ids, a behaviour change rather
  than a fix.

"createCivBonus" bonuses (those that build effects from scratch in the C++)
are not in this catalog — they require custom EffectCommand lists and are
logged as skipped at build time.
"""

import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).parent / "bonus_catalog_raw.json"
_catalog_data: dict | None = None


def _load() -> dict:
    global _catalog_data
    if _catalog_data is None:
        with open(_CATALOG_PATH) as f:
            _catalog_data = json.load(f)
    return _catalog_data


def civ_bonus_techs(bonus_id: int) -> list[int]:
    """Return the list of vanilla tech IDs that implement civ bonus `bonus_id`.
    Returns [] if the bonus is unknown or uses createCivBonus (not in catalog).
    """
    return _load()["civ"].get(str(bonus_id), [])


def team_bonus_tech(team_bonus_id: int) -> int | None:
    """Return the vanilla tech ID for team bonus `team_bonus_id`, or None."""
    val = _load()["team"].get(str(team_bonus_id))
    return val if isinstance(val, int) else None


def civ_bonus_ec_list(bonus_id: int) -> list[dict]:
    """Return ec_list entries for civ bonus `bonus_id`, or [] if none.

    Each entry is a dict:
      {
        "requires": [tech_id, ...],  # prerequisite tech IDs (empty = always fires)
        "ecs":      [{type, A, B, C, D}, ...]
      }
    """
    return _load()["ec_list"].get(str(bonus_id), [])


def team_bonus_ec_list(team_bonus_id: int) -> list[dict]:
    """Return EC dicts for a KM team bonus with no vanilla effect, or [].

    Each dict: {"type": T, "A": A, "B": B, "C": C, "D": D}
    """
    return _load().get("team_ec_list", {}).get(str(team_bonus_id), [])
