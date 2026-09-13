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
