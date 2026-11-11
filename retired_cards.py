"""retired_cards.py — unit-unlock cards retired into the tech tree (2026-11-11).

Every card here used to unlock, upgrade or dress a unit, and each now has a
home outside the card picker.  The rule (the user's, 2026-11-10): no card is
retired without one, so nothing a civ had is lost.  The homes:

  units    the game's own unit in the tree (get_civ_bonuses derives the card's
           machinery back from it, so the build is the card's build)
  hero     the hero panel (draft "hero_unit"); one hero per civ, so a second
           hero card becomes a standard unit — a copy, as the "+" makes it
  upgrade  a "+ Add Unit" extension, exactly as the "+" under the unit offers
           it (added_lines.suggested_upgrades)
  look     a unit edit's Look (the Athenians' Palintonon on the Trebuchet)

retire_cards() rewrites a civ in place.  It runs when the wizard loads a draft
(/api/builder/retire-cards) and at the top of every build
(civ_overrides.apply_civ_with_overrides), so a saved file or a KM import is
converted on its way in and no hidden card is kept.  It is idempotent: a
converted civ carries none of these cards.

Not here yet: the replacement cards (282 Winged Hussar, 307/416 Legionary,
314/417 Savar, 456 Scythian Horse Archer, 362/402 Dragon Ship) wait for the
whole-line replacement; the earlier-age cards stay cards (user, 2026-11-10).
"""
from __future__ import annotations

import copy

from civ_appender import CARD_UPGRADE_UNITS, KM_UNIT_CARDS, _UNLOCK_UNIT_BONUSES
from civ_schema import RETIRED_INTO_TREE

# Card -> the units it made trainable.  Replacements (Legionary, Savar, the
# Scythian Horse Archer) take a line's place and are left as cards for now.
UNIT_CARDS: dict[int, tuple[int, ...]] = {
    **{bid: tuple(spec["units"]) for bid, spec in _UNLOCK_UNIT_BONUSES.items()
       if not spec.get("replaces") and bid not in (416, 417)},
    361: tuple(_UNLOCK_UNIT_BONUSES[412]["units"]),   # Mounted Trebuchet, KM's copy of 412
    298: tuple(_UNLOCK_UNIT_BONUSES[415]["units"]),   # Thirisadai, KM's copy of 415
    **KM_UNIT_CARDS,                                  # Missionary, Turtle Ship, Caravel, Flaming Camel
    61: (185,),                                       # Slinger: a tree node already
}

HERO_CARDS: dict[int, int] = {338: 1966, 344: 1978, 349: 1954}   # Liu Bei, Sun Jian, Cao Cao

# A hero the tree adds as a standard unit trains where its kind does.
_HERO_BUILDING = {1966: 12, 1978: 101, 1954: 101}

# Card -> (unit edited, the edit).  457's +15% attack is dropped (the user's
# own edit, 2026-11-10): an attack edit or a bonus card does it now.
LOOK_CARDS: dict[int, tuple[int, dict]] = {457: (331, {"skin": "Athenians", "name": "Palintonon"})}

# Card -> (building, the unit extended, the unit the game upgrades it into or
# None for the card's own copy in CARD_UPGRADE_UNITS).
UPGRADE_CARDS: dict[int, tuple[int, int, int | None]] = {
    53: (101, 330, 207),     # Heavy Camel Rider -> Imperial Camel Rider (tech 521)
    286: (49, 36, 1709),     # Bombard Cannon -> Houfnice (tech 787)
    308: (49, CARD_UPGRADE_UNITS[308]["from"], None),   # Imperial Scorpion
    309: (101, CARD_UPGRADE_UNITS[309]["from"], None),  # Royal Battle Elephant
    310: (101, CARD_UPGRADE_UNITS[310]["from"], None),  # Royal Lancer
}

RETIRED = frozenset(UNIT_CARDS) | frozenset(HERO_CARDS) | frozenset(LOOK_CARDS) \
    | frozenset(UPGRADE_CARDS) | frozenset(RETIRED_INTO_TREE)


def _card_list(civ: dict) -> list | None:
    """The civ's civ-bonus list, in whichever format it is saved: the draft's
    [{id, multiplier}] or KM's [[[id, mult], ...], uu, castle, imp, team]."""
    raw = civ.get("bonuses")
    if not raw:
        return None
    if isinstance(raw[0], dict):
        return raw
    return raw[0] if isinstance(raw[0], list) else None


def _card_id(e) -> int | None:
    try:
        return int(e["id"] if isinstance(e, dict) else e[0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _tree_units(civ: dict) -> list | None:
    tree = civ.get("tree")
    if isinstance(tree, dict):
        return tree.setdefault("units", [])
    if isinstance(tree, list) and tree and isinstance(tree[0], list):
        return tree[0]
    return None


def _upgrade_line(dat, bid: int, line_id: int) -> dict | None:
    """The "+ Add Unit" extension the "+" under the unit would make."""
    building, frm, to = UPGRADE_CARDS[bid]
    tier: dict = {"age": 4, "name": ""}
    line = {"id": line_id, "building": building, "base": frm, "role": None,
            "appearance": None, "from": frm, "tiers": [tier]}
    if to is None:
        c = CARD_UPGRADE_UNITS[bid]
        tier.update(name=c["name"], edits=dict(c["edits"]), upgrade=copy.deepcopy(c["upgrade"]))
        if c.get("appearance") is not None:
            line["appearance"] = c["appearance"]
        return line
    if dat is None:
        return None
    from added_lines import suggested_upgrades
    from civ_appender import unit_label
    row = next((r for r in suggested_upgrades(dat, frm, [{"id": to, "name": unit_label(dat, 0, to)}])
                if r["base"] == to), None)
    if row is None:
        return None
    line["base"] = to
    tier["upgrade"] = row["upgrade"]
    return line


def retire_cards(civ: dict, dat=None) -> list[str]:
    """Move every retired card on `civ` to its home, in place.  `dat` prices
    the game's own upgrades (53, 286); without it those two stay cards.
    Returns one line per card moved, for the build log and the wizard."""
    cards = _card_list(civ)
    if not cards:
        return []
    ids = [i for i in (_card_id(e) for e in cards) if i in RETIRED]
    if not ids:
        return []
    units = _tree_units(civ)
    notes: list[str] = []
    done: set[int] = set()
    for bid in dict.fromkeys(ids):
        if bid in UNIT_CARDS or bid in RETIRED_INTO_TREE:
            # No tree at all means "leave the tree alone" (the slot's own); a
            # unit list of one card's units would switch everything else off.
            if not units:
                continue
            add = RETIRED_INTO_TREE[bid]["add"] if bid in RETIRED_INTO_TREE else UNIT_CARDS[bid]
            if bid in RETIRED_INTO_TREE:
                units[:] = [u for u in units if u not in RETIRED_INTO_TREE[bid]["remove"]]
            units.extend(u for u in sorted(add) if u not in units)
            notes.append(f"Card {bid} is now in the tech tree (units {', '.join(map(str, sorted(add)))})")
        elif bid in HERO_CARDS:
            hero = HERO_CARDS[bid]
            have = (civ.get("hero_unit") or {}).get("base_unit_id")
            if have is None:
                civ["hero_unit"] = {"base_unit_id": hero, "name": "", "description": "",
                                    "overrides": {}, "flags": {}}
                notes.append(f"Card {bid} is now the civ's hero (unit {hero})")
            elif int(have) != hero:
                # One hero per civ: the one chosen stays, the card's joins the
                # tree as a standard unit, which is what the tree makes a hero.
                lines = civ.setdefault("added_lines", [])
                if not any(l.get("base") == hero and l.get("from") is None for l in lines if isinstance(l, dict)):
                    lines.append({"id": max([l.get("id", 0) for l in lines if isinstance(l, dict)] + [0]) + 1,
                                  "building": _HERO_BUILDING[hero], "base": hero, "role": None,
                                  "appearance": None, "tiers": [{"age": 4, "name": ""}]})
                notes.append(f"Card {bid}: the civ already has a hero (unit {have}), so unit {hero} "
                             f"joins the tree as a standard unit")
            else:
                notes.append(f"Card {bid}: unit {hero} is already the civ's hero")
        elif bid in LOOK_CARDS:
            uid, edit = LOOK_CARDS[bid]
            edits = civ.setdefault("unit_edits", {})
            mine = edits.setdefault(str(uid), {})
            if mine.get("skin") not in (None, edit["skin"]):
                notes.append(f"Card {bid}: unit {uid} already wears the {mine['skin']} Look; kept that one")
            else:
                for k, v in edit.items():
                    mine.setdefault(k, v)
                notes.append(f"Card {bid} is now a Look on unit {uid} ({edit['skin']})")
        elif bid in UPGRADE_CARDS:
            lines = civ.setdefault("added_lines", [])
            building, frm, to = UPGRADE_CARDS[bid]
            have = next((l for l in lines if isinstance(l, dict) and l.get("from") == frm), None)
            if have is None:
                line = _upgrade_line(dat, bid, max([l.get("id", 0) for l in lines if isinstance(l, dict)] + [0]) + 1)
                if line is None:
                    continue                    # no DAT to price it: stays a card until one is
                lines.append(line)
                notes.append(f"Card {bid} is now an upgrade after unit {frm} in the tech tree")
            else:
                notes.append(f"Card {bid}: unit {frm} already has an upgrade after it in the tree; kept that one")
        done.add(bid)
    cards[:] = [e for e in cards if _card_id(e) not in done]
    return notes
