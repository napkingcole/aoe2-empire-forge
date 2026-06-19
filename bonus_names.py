"""Human-readable names for KM bonus IDs, parsed from CivBonusEnum.h."""
import json
from pathlib import Path

_NAMES: dict[int, str] | None = None

# Bonus IDs that are skipped and the reason why.
SKIP_REASONS: dict[int, str] = {
    131: "Not implemented in KM source",
    133: "Not implemented in KM source",
    140: "Requires direct unit data modification",
    218: "Requires direct unit data modification",
    155: "Requires dynamic tech reference (Royal Battle Elephant)",
    261: "Requires dynamic tech reference",
    362: "Requires dynamic tech reference (Dragon Ship)",
    234: "Complex tech duplication not supported",
    329: "Complex tech duplication not supported",
    279: "Requires prerequisite chain modification",
    290: "Requires prerequisite chain modification",
    308: "Requires KM custom unit (not in vanilla game)",
    309: "Requires KM custom unit (not in vanilla game)",
    310: "Requires KM custom unit (not in vanilla game)",
    330: "Requires KM custom unit (not in vanilla game)",
    331: "Requires KM custom unit (not in vanilla game)",
    332: "Requires KM custom unit (not in vanilla game)",
}


def _load() -> dict[int, str]:
    global _NAMES
    if _NAMES is None:
        p = Path(__file__).parent / "bonus_names.json"
        _NAMES = {int(k): v for k, v in json.loads(p.read_text()).items()}
    return _NAMES


def bonus_name(bonus_id: int) -> str:
    """Return a human-readable description for a KM bonus ID."""
    return _load().get(bonus_id, f"Bonus #{bonus_id}")


def skip_reason(bonus_id: int) -> str:
    """Return the reason a bonus ID was skipped, or a generic fallback."""
    return SKIP_REASONS.get(bonus_id, "Not in catalog")
