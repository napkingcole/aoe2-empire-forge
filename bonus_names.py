"""Human-readable names for KM bonus IDs, parsed from CivBonusEnum.h."""
import json
from pathlib import Path

_NAMES: dict[int, str] | None = None
_TEAM_NAMES: dict[int, str] | None = None

# Bonus IDs that are skipped and the reason why.
SKIP_REASONS: dict[int, str] = {
    218: "Requires direct unit data modification (Castle resource trickle/refund — also ambiguous: KM source comment says 'refund 350 stone' but enum says '400 gold trickle'; stub was never implemented)",
    211: "Requires direct unit data modification (villager resource_decay_rate field — no EffectCommand path)",
    327: "Not implementable via EC commands: true 'scale each unit's existing bonus attack entries by the blacksmith delta' requires enumerating every military unit and every non-zero non-base attack class at build time — hundreds of commands per tech fire. Use bonus 401 instead ('Blacksmith upgrades add +1/+2 vs buildings'), which is a distinct but implementable building-damage bonus.",
}


def _load() -> dict[int, str]:
    global _NAMES
    if _NAMES is None:
        p = Path(__file__).parent / "bonus_names.json"
        _NAMES = {int(k): v for k, v in json.loads(p.read_text()).items()}
    return _NAMES


def _load_team() -> dict[int, str]:
    global _TEAM_NAMES
    if _TEAM_NAMES is None:
        p = Path(__file__).parent / "team_bonus_names.json"
        _TEAM_NAMES = {int(k): v for k, v in json.loads(p.read_text()).items()}
    return _TEAM_NAMES


def bonus_name(bonus_id: int) -> str:
    """Return a human-readable description for a KM bonus ID."""
    return _load().get(bonus_id, f"Bonus #{bonus_id}")


def skip_reason(bonus_id: int) -> str:
    """Return the reason a bonus ID was skipped, or a generic fallback."""
    return SKIP_REASONS.get(bonus_id, "Not in catalog")


def unsupported_bonuses() -> list[dict]:
    """Return every known KM bonus ID this builder cannot apply yet.

    Computed live from the catalog + handler dispatch table (rather than a
    hand-maintained list) so it can't drift out of sync as coverage grows.
    Each entry: {"id": int, "name": str, "reason": str}.
    """
    import bonus_catalog
    from civ_appender import HANDLED_BONUS_IDS

    catalog = bonus_catalog._load()
    covered = (
        {int(k) for k, v in catalog["civ"].items() if v}
        | {int(k) for k, v in catalog["ec_list"].items() if v}
        | HANDLED_BONUS_IDS
    )
    names = _load()
    return [
        {"id": bid, "name": name, "reason": SKIP_REASONS.get(bid, "Not yet implemented")}
        for bid, name in sorted(names.items())
        if bid not in covered
    ]


def unsupported_unique_units() -> list[dict]:
    """KM unique-unit indices we can't create. Each entry: {"id", "name"}."""
    import civ_appender as ca
    import km_custom_uu

    covered = set(ca._KM_UU_TECHS.keys()) | set(km_custom_uu.PRESETS.keys())
    return [
        {"id": i, "name": name}
        for i, name in sorted(ca._KM_UU_NAMES.items())
        if i not in covered
    ]


def unsupported_unique_techs(castle: bool) -> list[dict]:
    """KM castle/imperial UT indices we can't create. Each entry: {"id", "name"}."""
    import civ_appender as ca
    from build_all import _UNIQUE_CASTLE_STRINGS, _UNIQUE_IMP_STRINGS

    table = _UNIQUE_CASTLE_STRINGS if castle else _UNIQUE_IMP_STRINGS
    covered = set((ca._KM_CASTLE_UT_TECHS if castle else ca._KM_IMP_UT_TECHS).keys())
    return [{"id": i, "name": name} for i, name in enumerate(table) if i not in covered]


# Total team-bonus card count in KM's source (indices 0-79) — confirmed via
# the card image set (team_0..team_79).
_TEAM_BONUS_COUNT = 80

# These vanilla effect IDs belong to the Chronicles DLC civ pool, which is
# separate from the standard AoE2 DE civ pool. Chronicles civs cannot be
# selected in regular game modes, so their team bonuses are intentionally
# excluded from the catalog.
# Effects: Achaemenids=1102, Athenians=1118, Spartans=1130,
#          Macedonians=1219, Thracians=1247, Puru=1257
CHRONICLES_EFFECT_IDS: frozenset[int] = frozenset({1102, 1118, 1130, 1219, 1247, 1257})


def unsupported_team_bonuses() -> list[dict]:
    """KM team-bonus indices missing from the catalog. Each entry: {"id", "name"}."""
    import bonus_catalog

    catalog = bonus_catalog._load()
    covered = (
        {int(k) for k, v in catalog["team"].items() if v is not None}
        | {int(k) for k in catalog.get("team_ec_list", {}).keys()}
    )
    names = _load_team()
    return [
        {"id": i, "name": names.get(i, f"Team Bonus #{i}")}
        for i in range(_TEAM_BONUS_COUNT)
        if i not in covered
    ]
