"""
civ_schema.py — empireforge_v2 JSON schema normalizer.

Two public functions:
  from_draft(draft)  → empireforge_v2 dict  (wizard → saveable file)
  to_draft(schema)   → wizard draft dict    (saveable file → build pipeline)

empireforge_v2 (SCHEMA_VER 2) is the only format written.  civbuilder_v1 is
accepted on read and never emitted; is_empireforge() covers both.

The wizard draft format is a superset of the schema: it adds UI-only keys
(dat_path) that don't belong in a shareable civ file.  _draftVer IS included
in the schema to prevent stale builder.js migrations when a saved file is
loaded back into localStorage as the live draft.  Everything else maps 1-to-1,
so the two formats stay tightly coupled by design.

build_all.py detects a "format" key via is_civbuilder_v1() and calls to_draft()
before passing the file through the wizard_build pipeline.
"""

from __future__ import annotations

import custom_bonus

FORMAT_KEY   = "empireforge_v2"
SCHEMA_VER   = 2
_DRAFT_VER   = 4   # current wizard draft version

# Legacy format key accepted on read (but never written)
_FORMAT_KEY_V1 = "civbuilder_v1"

# Unique-unit advanced flags that were offered once and have been withdrawn.
# Dropped silently on both doors so an older saved civ keeps loading, rather
# than carrying a flag nothing implements.
#   ignore_armor — removed 2026-09-18.  AoE2 has no data-level way to grant it;
#     the implementation aimed the attack at armour class 50, which no unit has,
#     so the unit dealt the engine minimum of 1 damage to everything.
RETIRED_UU_FLAGS = frozenset({"ignore_armor"})

# Civ bonus cards withdrawn because they cannot do what they say.  Filtered in
# civ_appender.get_civ_bonuses, the accessor every build path, the in-game
# description and the View Civ page read through, so an old civ or a KM import
# that carries one still loads but no longer claims it.
#   333 "Siege Towers can fire arrows" — withdrawn 2026-10-09 (issue #69).  KM's
#     card only ADDS attack; the Siege Tower has no range, projectile, reload or
#     attack at all, so nothing ever fired (reported in-game).  Making it shoot
#     means building a ranged attack from scratch — not done, so not offered.
#   51 "Train Longboats at Docks" — retired 2026-10-16 into the tech tree (see
#     RETIRED_INTO_TREE): it still does what it says, but it has a better home.
RETIRED_CIV_BONUSES = frozenset({333, 51})

# KM's custom unique units (km_custom_uu.PRESETS 39-77) were all retired from
# the picker 2026-10-22 and brought back 2026-10-24 (the user's call, after
# players asked for them — the Headhunter, the Jaridah and the rest are what
# their civs were built on).  Retired now are only the seven whose game unit
# the picker already offers under the same name, as a scenario unit with the
# game's own stats (118-124): there the game's version wins.  Hidden, not
# deleted: a saved civ or KM import that carries one still builds it.
#   40 Xolotl Warrior, 42 Ninja, 43 Flamethrower, 44 Photonman,
#   48 Amazon Warrior, 49 Amazon Archer, 50 Iroquois Warrior
RETIRED_UUS = frozenset({40, 42, 43, 44, 48, 49, 50})

# Cards whose choice moved into the tech tree.  A civ that picked one reads as
# if its tree held `add` and not `remove`, derived on every read (as the Unlock
# cards are) so an old civ or a KM import keeps building what it built before.
#   51 Longboats — since Viking Sagas the Longship is a regional Dock line
#     (Vikings, Danes, Saxons, Varangians), sharing button 8 with the
#     Demolition line it replaced on the card.
RETIRED_INTO_TREE: dict[int, dict[str, frozenset]] = {
    51: {"add": frozenset({250, 533}), "remove": frozenset({1104, 527, 528})},
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ut_effect(e: dict, own_tier: str) -> dict:
    """One UT effect, always with its preset pool.  Either slot may draw from
    either pool and the ids clash between them (castle 1 is not imperial 1), so
    the pool is written out every time; a file from before the pools merged has
    none, which means the slot's own — see civ_appender.UT_SLOT_TIER."""
    tier = e.get("tier")
    return {"id": int(e["id"]), "multiplier": int(e.get("multiplier", 1)),
            "tier": tier if tier in ("castle", "imperial") else own_tier}


def _clean(d: dict) -> dict:
    """Remove _doc / _doc_example / _section_* annotation keys."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _cost_dict(d: dict | None) -> dict:
    d = d or {}
    return {
        "food":  int(d.get("food",  0) or 0),
        "wood":  int(d.get("wood",  0) or 0),
        "stone": int(d.get("stone", 0) or 0),
        "gold":  int(d.get("gold",  0) or 0),
    }


# ── civbuilder_v1 → wizard draft ──────────────────────────────────────────────

def to_draft(schema: dict) -> dict:
    """
    Convert a civbuilder_v1 JSON dict into the wizard draft format expected by
    _draft_to_civ_def, _apply_uu_overrides, and _override_ut_costs.

    Unknown / Phase-Two keys (unit_overrides, button_moves, free_techs, second_uu)
    are passed through unchanged so future handlers can
    act on them without schema changes.

    When second_uu is implemented, build it on km_custom_uu.append_km_custom_uu
    — it already appends new units to every civ's array and wires the make-avail
    and elite-upgrade techs with the string-id arithmetic CLAUDE.md quirk 8
    depends on.
    """
    s = _clean(schema)

    # ── UU ───────────────────────────────────────────────────────────────────
    raw_uu   = _clean(s.get("unique_unit") or {})
    overrides = _clean(raw_uu.get("overrides") or {})
    adv_flags = _clean(raw_uu.get("advanced_flags") or {})

    # Strip null values so the build functions treat absence == "no override"
    overrides = {k: v for k, v in overrides.items() if v is not None}
    adv_flags = {k: v for k, v in adv_flags.items()
                 if v is not None and v is not False and k not in RETIRED_UU_FLAGS}

    uu = {
        "km_idx":      raw_uu.get("km_idx"),
        "vanilla_id":  raw_uu.get("vanilla_id"),
        "name":        raw_uu.get("name",        ""),
        "description": raw_uu.get("description", ""),
    }
    if overrides:
        uu["overrides"] = overrides
    if adv_flags:
        uu["advanced_flags"] = adv_flags
    elite_up = norm_elite_upgrade(raw_uu.get("elite_upgrade"))
    if elite_up:
        uu["elite_upgrade"] = elite_up
    if isinstance(raw_uu.get("appearance"), int):         # another unit's look (civ_appender)
        uu["appearance"] = raw_uu["appearance"]

    # ── UTs ──────────────────────────────────────────────────────────────────
    def _ut(raw: dict | None, own_tier: str) -> dict:
        raw = _clean(raw or {})
        ut: dict = {
            "mode":            raw.get("mode", "vanilla"),
            "vanilla_km_idx":  raw.get("vanilla_km_idx"),
            "name":            raw.get("name",        ""),
            "description":     raw.get("description", ""),
            "cost":            _cost_dict(raw.get("cost")),
            "time":            int(raw.get("time") or 0),
            "effects": [_ut_effect(e, own_tier) for e in (raw.get("effects") or [])
                        if isinstance(e, dict) and "id" in e],
            # Library cards in a Build Custom UT (#75).
            "custom_bonuses": custom_bonus.normalize(raw.get("custom_bonuses")),
        }
        return ut

    # ── Bonuses ──────────────────────────────────────────────────────────────
    def _bonus_list(raw: list | None) -> list:
        out = []
        for b in (raw or []):
            if isinstance(b, dict) and "id" in b:
                out.append({"id": int(b["id"]), "multiplier": int(b.get("multiplier", 1))})
        return out

    # ── Tree ─────────────────────────────────────────────────────────────────
    raw_tree = _clean(s.get("tree") or {})
    tree = {
        "units":     [int(x) for x in (raw_tree.get("units")     or [])],
        "buildings": [int(x) for x in (raw_tree.get("buildings") or [])],
        "techs":     [int(x) for x in (raw_tree.get("techs")     or [])],
    }

    # ── Hero unit ────────────────────────────────────────────────────────────
    raw_hero = _clean(s.get("hero_unit") or {})
    if raw_hero and raw_hero.get("base_unit_id") is not None:
        hero: dict | None = {
            "base_unit_id": raw_hero["base_unit_id"],
            "name":         raw_hero.get("name", ""),
            "description":  raw_hero.get("description", ""),
            "overrides": {k: v for k, v in _clean(raw_hero.get("overrides") or {}).items() if v is not None},
            "flags":     {k: v for k, v in _clean(raw_hero.get("flags")     or {}).items() if v not in (None, False)},
        }
    else:
        hero = None

    draft: dict = {
        "_draftVer":   _DRAFT_VER,

        # Identity
        "alias":       s.get("alias",       "Custom Civ"),
        "tagline":     s.get("tagline",      ""),
        "description": s.get("description", ""),
        # View Civ only (#57); no build route reads it.
        "share_description": s.get("share_description", ""),

        # Appearance
        "architecture": s.get("architecture", 2),
        "language":     s.get("language",     0),
        "wonder": s["wonder"] if "wonder" in s else s.get("wonder_model", -1),
        "castle": s["castle"] if "castle" in s else s.get("castle_model", -1),
        "emblem":       s.get("emblem",       ""),

        # Core content
        "hero_unit":    hero,
        "unique_unit":  uu,
        "bonuses":      _bonus_list(s.get("bonuses")),
        "custom_bonuses": custom_bonus.normalize(s.get("custom_bonuses")),
        "team_bonuses": _bonus_list(s.get("team_bonuses")),
        "custom_team_bonuses": custom_bonus.normalize(s.get("custom_team_bonuses")),
        "castle_ut":    _ut(s.get("castle_ut"), "castle"),
        "imperial_ut":  _ut(s.get("imperial_ut"), "imperial"),
        "tree":         tree,
        "long_range_ship":       s.get("long_range_ship"),
        "long_range_ship_elite": s.get("long_range_ship_elite", True),
        "starting_scout":        s.get("starting_scout"),
        "monk_skin":             s.get("monk_skin"),
        # DAT civ index whose Monastery is copied (civ_appender.MONASTERY_SKIN_OPTIONS).
        "monastery_skin_building": s.get("monastery_skin_building"),

        # Phase Two pass-throughs (not yet consumed by build pipeline)
        "second_uu":              s.get("second_uu"),
        "unit_edits":             norm_unit_edits(s.get("unit_edits")),
        "tech_edits":             norm_tech_edits(s.get("tech_edits")),
        "added_lines":            norm_added_lines(s.get("added_lines")),
        "unit_overrides":         s.get("unit_overrides",         []),
        "button_moves":           s.get("button_moves",           []),
        "free_techs":             s.get("free_techs",             []),
    }
    return draft


# ── wizard draft → civbuilder_v1 ──────────────────────────────────────────────

def from_draft(draft: dict) -> dict:
    """
    Convert a wizard draft dict into a clean civbuilder_v1 JSON dict suitable
    for saving to disk and sharing.  UI-only keys (_draftVer, dat_path) are
    stripped; null-override fields are collapsed.
    """
    uu_raw   = draft.get("unique_unit") or {}
    overrides = uu_raw.get("overrides") or {}
    adv_flags = {k: v for k, v in (uu_raw.get("advanced_flags") or {}).items()
                 if k not in RETIRED_UU_FLAGS}

    def _ut_out(ut_raw: dict | None, own_tier: str) -> dict:
        ut_raw = ut_raw or {}
        return {
            "mode":           ut_raw.get("mode",        "vanilla"),
            "vanilla_km_idx": ut_raw.get("vanilla_km_idx"),
            "name":           ut_raw.get("name",        ""),
            "description":    ut_raw.get("description", ""),
            "cost":           _cost_dict(ut_raw.get("cost")),
            "time":           int(ut_raw.get("time") or 0),
            "effects": [_ut_effect(e, own_tier) for e in (ut_raw.get("effects") or [])
                        if isinstance(e, dict) and "id" in e],
            "custom_bonuses": custom_bonus.normalize(ut_raw.get("custom_bonuses")),
        }

    def _bonus_out(lst: list | None) -> list:
        out = []
        for b in (lst or []):
            if isinstance(b, dict) and "id" in b:
                out.append({"id": int(b["id"]), "multiplier": int(b.get("multiplier", 1))})
        return out

    raw_tree = draft.get("tree") or {}
    tree_out = {
        "units":     [int(x) for x in (raw_tree.get("units")     or [])],
        "buildings": [int(x) for x in (raw_tree.get("buildings") or [])],
        "techs":     [int(x) for x in (raw_tree.get("techs")     or [])],
    }

    raw_hero_d = draft.get("hero_unit") or {}
    if raw_hero_d and raw_hero_d.get("base_unit_id") is not None:
        hero_out: dict | None = {
            "base_unit_id": raw_hero_d["base_unit_id"],
            "name":         raw_hero_d.get("name", ""),
            "description":  raw_hero_d.get("description", ""),
            "overrides":    raw_hero_d.get("overrides", {}),
            "flags":        raw_hero_d.get("flags", {}),
        }
    else:
        hero_out = None

    uu_out: dict = {
        "km_idx":      uu_raw.get("km_idx"),
        "vanilla_id":  uu_raw.get("vanilla_id"),
        "name":        uu_raw.get("name",        ""),
        "description": uu_raw.get("description", ""),
        "overrides":   {k: v for k, v in overrides.items()  if v is not None},
        "advanced_flags": {k: v for k, v in adv_flags.items() if v is not None},
    }
    elite_up = norm_elite_upgrade(uu_raw.get("elite_upgrade"))
    if elite_up:
        uu_out["elite_upgrade"] = elite_up
    if isinstance(uu_raw.get("appearance"), int):
        uu_out["appearance"] = uu_raw["appearance"]

    schema: dict = {
        "format":         FORMAT_KEY,
        "schema_version": SCHEMA_VER,
        "_draftVer":      _DRAFT_VER,   # prevents stale builder.js migrations on reload

        "alias":       draft.get("alias",       ""),
        "tagline":     draft.get("tagline",      ""),
        "description": draft.get("description", ""),
        "share_description": (draft.get("share_description") or "").strip(),

        "architecture": draft.get("architecture", 2),
        "language":     draft.get("language",     0),
        # wonder_model / castle_model: canonical schema names (for build pipeline via to_draft).
        # wonder / castle:             wizard draft names (for direct localStorage load in browser).
        "wonder_model": draft.get("wonder",  -1),
        "castle_model": draft.get("castle",  -1),
        "wonder":       draft.get("wonder",  -1),
        "castle":       draft.get("castle",  -1),
        "emblem":       draft.get("emblem",  ""),

        "hero_unit":    hero_out,
        "unique_unit":  uu_out,
        "second_uu":    draft.get("second_uu"),

        "bonuses":      _bonus_out(draft.get("bonuses")),
        "custom_bonuses": custom_bonus.normalize(draft.get("custom_bonuses")),
        "team_bonuses": _bonus_out(draft.get("team_bonuses")),
        "custom_team_bonuses": custom_bonus.normalize(draft.get("custom_team_bonuses")),

        "castle_ut":    _ut_out(draft.get("castle_ut"), "castle"),
        "imperial_ut":  _ut_out(draft.get("imperial_ut"), "imperial"),

        "tree": tree_out,
        "long_range_ship":         draft.get("long_range_ship"),
        "long_range_ship_elite":   draft.get("long_range_ship_elite", True),
        "starting_scout":          draft.get("starting_scout"),
        "monk_skin":               draft.get("monk_skin"),
        "monastery_skin_building": draft.get("monastery_skin_building"),

        "unit_edits":              norm_unit_edits(draft.get("unit_edits")),
        "tech_edits":              norm_tech_edits(draft.get("tech_edits")),
        "added_lines":             norm_added_lines(draft.get("added_lines")),
        "unit_overrides":          draft.get("unit_overrides",          []),
        "button_moves":            draft.get("button_moves",            []),
        "free_techs":              draft.get("free_techs",              []),
    }
    return schema


# ── Format detection ──────────────────────────────────────────────────────────

def norm_elite_upgrade(raw) -> dict | None:
    """The Elite UU upgrade's custom cost and research time, or None if unset.

    {"cost": {"food", "wood", "stone", "gold"}, "time": seconds}.  Zero means
    "keep the game's", exactly as for the UT cost (civ_overrides.
    _set_tech_cost_time), so an all-zero entry is dropped rather than saved.
    Issue #68.
    """
    if not isinstance(raw, dict):
        return None

    def num(v):
        try:
            return max(0, int(float(v or 0)))
        except (TypeError, ValueError):
            return 0
    cost = raw.get("cost") if isinstance(raw.get("cost"), dict) else {}
    out = {"cost": {r: num(cost.get(r)) for r in ("food", "wood", "stone", "gold")},
           "time": num(raw.get("time"))}
    return out if out["time"] or any(out["cost"].values()) else None


# ── Tech-tree edits (the tree page's side panel) ─────────────────────────────
#
# unit_edits — {unit id: fields}, written straight onto the civ's own copy of
#   the unit (civ_overrides._apply_unit_edits), so they cost no effect commands.
#   A cost is the COMPLETE spendable cost: unlisted or 0 resources are not
#   charged.  Cost and train time flow down the unit's upgrade line.
# tech_edits — {tech id: {"cost": {...}, "time": s}}, applied as multiply
#   "ghost" commands, since a tech is shared by every civ.
#
# Each field is clamped to what its DAT field holds; anything unreadable is
# dropped rather than guessed at.

_SHORT = 32767
_UNIT_EDIT_FIELDS: dict[str, tuple[type, float, float]] = {
    "hp":     (int,   1,   _SHORT),
    "attack": (int,   0,   _SHORT),
    # Armour can be negative: the Dark Age House has -2 melee.
    "melee":  (int,   -_SHORT, _SHORT),
    "pierce": (int,   -_SHORT, _SHORT),
    "range":  (float, 0,   100),
    "reload": (float, 0.1, 100),
    "speed":  (float, 0,   10),
    "los":    (float, 0,   100),
    "train":  (int,   1,   _SHORT),
}
_RESOURCES = ("food", "wood", "stone", "gold")


def _num(v, kind, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    x = min(max(x, lo), hi)
    return int(round(x)) if kind is int else round(x, 3)


def _norm_cost(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    out = {r: _num(raw.get(r) or 0, int, 0, _SHORT) for r in _RESOURCES}
    return {r: (v or 0) for r, v in out.items()}


def _id_key(k) -> str | None:
    try:
        i = int(k)
    except (TypeError, ValueError):
        return None
    return str(i) if i >= 0 else None


UNIT_NAME_MAX = 40


def norm_unit_name(raw) -> str:
    """A unit's new name: one line, no control characters, at most 40 long."""
    if not isinstance(raw, str):
        return ""
    text = " ".join("".join(c if c.isprintable() else " " for c in raw).split())
    return text[:UNIT_NAME_MAX].strip()


def norm_unit_edits(raw) -> dict:
    """{"<unit id>": {name, hp, attack, melee, pierce, range, reload, speed, los,
    train, cost: {food, wood, stone, gold}, bonus: {"<class>": amount}}}."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for k, e in raw.items():
        key = _id_key(k)
        if key is None or not isinstance(e, dict):
            continue
        clean: dict = {}
        name = norm_unit_name(e.get("name"))
        if name:
            clean["name"] = name
        for f, (kind, lo, hi) in _UNIT_EDIT_FIELDS.items():
            if e.get(f) is not None and (v := _num(e[f], kind, lo, hi)) is not None:
                clean[f] = v
        cost = _norm_cost(e.get("cost"))
        if cost is not None:
            clean["cost"] = cost
        # "Available from": the age it becomes available in (civ_overrides._apply_age_moves).
        if e.get("age") is not None and (a := _num(e["age"], int, 1, 4)) is not None:
            clean["age"] = a
        if isinstance(e.get("bonus"), dict):
            bonus = {}
            for c, a in e["bonus"].items():
                ck = _id_key(c)
                # 3 and 4 are the unit's own pierce/melee attack ("attack").
                if ck is None or int(ck) in (3, 4):
                    continue
                if (v := _num(a, int, 0, _SHORT)) is not None:
                    bonus[ck] = v
            if bonus:
                clean["bonus"] = bonus
        if clean:
            out[key] = clean
    return out


def norm_tech_edits(raw) -> dict:
    """{"<tech id>": {"cost": {food, wood, stone, gold}, "time": seconds, "age": 1-4}}."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for k, e in raw.items():
        key = _id_key(k)
        if key is None or not isinstance(e, dict):
            continue
        clean: dict = {}
        cost = _norm_cost(e.get("cost"))
        if cost is not None:
            clean["cost"] = cost
        if e.get("time") is not None and (t := _num(e["time"], int, 0, _SHORT)) is not None:
            clean["time"] = t
        if e.get("age") is not None and (a := _num(e["age"], int, 1, 4)) is not None:
            clean["age"] = a
        if clean:
            out[key] = clean
    return out


# ── Added lines (the tree page's "+ Add Unit") ──────────────────────────────
#
# added_lines — [{id, building, base, role, appearance, description, tiers: [{age, name,
#   edits, upgrade}]}].  A line is 1-4 tiers, each a copy of the same base unit,
#   each in a later age than the one before; tier 1 is made available at its age,
#   every later tier has its own upgrade tech (cost/time in `upgrade`).  `edits`
#   is one unit_edits entry, and a tier's edit carries to the later tiers unless
#   they set that field themselves (stats never fall back with an upgrade).
#   `role` is the AI's unit line it joins (a unitlines.json LineID, None = the
#   one holding the base unit).  Built by added_lines.apply_added_lines.

ADDED_LINE_BUILDINGS = (12, 87, 101, 49, 45, 104, 109)  # Barracks .. Town Center
ADDED_LINE_MAX_TIERS = 4
ADDED_LINE_DESC_MAX = 300


def norm_added_lines(raw) -> list:
    out: list = []
    if not isinstance(raw, list):
        return out
    seen: set[int] = set()
    for line in raw:
        if not isinstance(line, dict):
            continue
        lid = _num(line.get("id"), int, 1, 1_000_000)
        building = _num(line.get("building"), int, -1, _SHORT)
        base = _id_key(line.get("base"))
        if lid is None or lid in seen or building not in ADDED_LINE_BUILDINGS or base is None:
            continue
        # An extension: its tiers upgrade on from this unit (Halberdier ->
        # Elite Halberdier), rather than starting a line of their own.
        frm = _id_key(line.get("from")) if line.get("from") is not None else None
        # A replacement: the unit a vanilla upgrade gives (Paladin) becomes this
        # line's one tier (Savar).  One tier, its upgrade the vanilla one.
        rep = _id_key(line.get("replaces")) if line.get("replaces") is not None else None
        if rep is not None:
            frm = None
        tiers: list = []
        for t in line.get("tiers") or []:
            if not isinstance(t, dict) or len(tiers) == (1 if rep is not None else ADDED_LINE_MAX_TIERS):
                continue
            age = _num(t.get("age"), int, 1, 4)
            if age is None or (tiers and age <= tiers[-1]["age"]):
                continue                                 # each tier a later age
            tier: dict = {"age": age, "name": norm_unit_name(t.get("name"))}
            edits = norm_unit_edits({"0": dict(t.get("edits") or {}, name=None, age=None)}).get("0")
            if edits:
                tier["edits"] = edits
            if tiers or frm is not None:                 # a new line's tier 1 has no upgrade
                up = norm_tech_edits({"0": t.get("upgrade") or {}}).get("0")
                if up:
                    tier["upgrade"] = up
            tiers.append(tier)
        if not tiers:
            continue
        # unitlines.json's LineIDs are -400..-199; anything else is no role, not
        # the nearest real line (clamping 7 to -199 would join an unrelated one).
        role = _num(line.get("role"), int, -_SHORT, _SHORT) if line.get("role") is not None else None
        role = role if role is not None and -400 <= role <= -199 else None
        look = _id_key(line.get("appearance")) if line.get("appearance") is not None else None
        seen.add(lid)
        desc = line.get("description")
        desc = " ".join("".join(c if c.isprintable() else " " for c in desc).split())[:ADDED_LINE_DESC_MAX] \
            if isinstance(desc, str) else ""
        out.append({"id": lid, "building": building, "base": int(base), "role": role,
                    "appearance": int(look) if look is not None else None,
                    "description": desc, "tiers": tiers})
        if frm is not None:
            out[-1]["from"] = int(frm)
        if rep is not None:
            out[-1]["replaces"] = int(rep)
    return out


def is_empireforge(data: dict) -> bool:
    """Return True for any Empire Forge format (current v2 or legacy v1)."""
    fmt = data.get("format", "")
    return fmt in (FORMAT_KEY, _FORMAT_KEY_V1)

def is_civbuilder_v1(data: dict) -> bool:
    """Backward-compat alias for build_all.py."""
    return is_empireforge(data)

def is_km_format(data: dict) -> bool:
    """Return True if data looks like a KrakenMeister civ JSON (no 'format' key)."""
    return not is_empireforge(data) and "bonuses" in data and isinstance(data.get("bonuses"), list)


# Tech-tree nodes KM's builder never offered, keyed tech → the node whose
# presence implies it.  A KM tree can't tick them, so their absence carries no
# intent — but the tree sweep reads absence as "unticked" (CLAUDE.md quirk 15)
# and disabled them for every imported civ.  Diffing KM's aoe2techtree data
# against _editor_nodes() gives 8 such techs.  Two are implied here:
#   35  Galleon — has no effect of its own since the naval rework, so the sweep
#       cannot tie it to the Galleon unit (442); KM civs with Galleons lost them.
#   906 Fishing Lines — added after KM; Gillnets (65) now requires it.
# Carvel Hull / Clinker Construction (907-910) are a per-civ naval choice, and
# Cranequins (1452) only touches the Mounted Crossbowman, which KM cannot pick.
#
# The build no longer needs this: civ_appender._apply_tree_wiring keeps the
# unticked prerequisites of every ticked node, for any format (2026-10-08).
# It remains for app.py's KM import, so the editor shows the imported tree
# as the build will make it.
KM_IMPLIED_TECHS: dict[int, tuple[str, int]] = {
    35:  ("units", 442),
    906: ("techs", 65),
}


def km_implied_techs(units, techs) -> set[int]:
    """Techs a KM tree implies but could not express.  See KM_IMPLIED_TECHS."""
    have = {"units": set(units), "techs": set(techs)}
    return {tid for tid, (kind, node) in KM_IMPLIED_TECHS.items()
            if node in have[kind]}
