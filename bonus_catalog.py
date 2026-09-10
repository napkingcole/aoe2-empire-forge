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
