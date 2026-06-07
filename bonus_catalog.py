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
