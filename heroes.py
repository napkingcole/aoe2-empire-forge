"""The Heroes tab's catalog, read from the player's DAT.

A hero is any unit the game itself marks as one (`creatable.hero_mode`) that a
scenario designer can place: a combat unit (type 70), shown in the editor, with
a real display name and a train slot for civ_appender._place_hero to point at
the Castle.  That is ~200 units — the 30 the tab hand-listed until 2026-10-22,
and every campaign and scenario hero besides, including any a DLC adds.

Two kinds are left out:
  - animals (class 10): Ornlu the Wolf and the Iron Boar are heroes to the
    game, but not people a civ would train (the user's call, 2026-10-21);
  - ships (class 22): every hero trains at the Castle, so Admiral Yi or Leif
    Erikson would come out on dry land.  They need a Dock button first.

Stats come from app._unit_stats_block, as the unique-unit popups' do.  What the
DAT can't say — a hero's faction, abilities its stats don't show — lives in
static/data/hero_notes.json, written by hand and never invented.
"""
import json
from pathlib import Path

_NOTES_PATH = Path(__file__).parent / "static" / "data" / "hero_notes.json"

_ANIMAL_CLASS, _SHIP_CLASS = 10, 22
_KIND_BY_CLASS = {
    6: "infantry", 12: "cavalry",
    0: "archers", 36: "archers",              # foot archers, cavalry archers
    18: "monks",
}


def _notes() -> dict[int, dict]:
    raw = json.loads(_NOTES_PATH.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items() if not k.startswith("_")}


def is_hero(unit) -> bool:
    """A placeable hero the Castle can train (see the module docstring)."""
    cr = getattr(unit, "creatable", None)
    return bool(unit is not None and unit.type == 70 and cr is not None and cr.hero_mode
                and not unit.hide_in_editor and unit.hit_points > 0
                and cr.train_locations
                and unit.class_ not in (_ANIMAL_CLASS, _SHIP_CLASS))


def hero_catalog(dat, stats_of, name_of) -> list[dict]:
    """[{id, name, faction, category, kind, stats}], heroes by name.

    stats_of(unit) -> the stats dict the popups show; name_of(unit) -> display
    name or None.  A hero with no display name is left out — a codename like
    HGRAV tells a player nothing — unless the notes name it.
    """
    notes = _notes()
    units = dat.civs[0].units
    out, seen = [], set()
    for unit in units:
        # The notes' heroes always stay: Saladin is hidden from the editor and
        # the Warwolf Trebuchet is a type-80 unit, but both have long been offered.
        if unit is None or not (is_hero(unit) or unit.id in notes):
            continue
        note = notes.get(unit.id, {})
        name = note.get("name") or name_of(unit)
        if not name:
            continue
        # Two ids can share one name (a campaign copy); keep the first, unless
        # the notes list the other — those are the ones players already know.
        key = name.casefold()
        if key in seen and unit.id not in notes:
            continue
        seen.add(key)
        s = stats_of(unit)
        out.append({
            "id": unit.id,
            "name": name,
            "faction": note.get("faction", ""),
            "category": note.get("category", "campaign"),
            "kind": _KIND_BY_CLASS.get(unit.class_, "other"),
            "stats": {
                "hp": s["hp"], "speed": s["speed"], "attack": s["attack"],
                "ma": s["melee_armor"], "pa": s["pierce_armor"],
                "range": s["range"], "reload": s["reload_time"],
                "bonuses": s["bonuses"], "specials": note.get("specials", []),
            },
        })
    out.sort(key=lambda h: (h["category"] != "multiplayer", h["name"].casefold()))
    return out
