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
RETIRED_CIV_BONUSES = frozenset({333})


# ── Helpers ───────────────────────────────────────────────────────────────────

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

    Unknown / Phase-Two keys (unit_overrides, button_moves, free_techs, second_uu,
    monastery_skin_building) are passed through unchanged so future handlers can
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

    # ── UTs ──────────────────────────────────────────────────────────────────
    def _ut(raw: dict | None) -> dict:
        raw = _clean(raw or {})
        ut: dict = {
            "mode":            raw.get("mode", "vanilla"),
            "vanilla_km_idx":  raw.get("vanilla_km_idx"),
            "name":            raw.get("name",        ""),
            "description":     raw.get("description", ""),
            "cost":            _cost_dict(raw.get("cost")),
            "time":            int(raw.get("time") or 0),
            "effects": [
                {"id": int(e["id"]), "multiplier": int(e.get("multiplier", 1))}
                for e in (raw.get("effects") or [])
                if isinstance(e, dict) and "id" in e
            ],
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
        "castle_ut":    _ut(s.get("castle_ut")),
        "imperial_ut":  _ut(s.get("imperial_ut")),
        "tree":         tree,
        "long_range_ship":       s.get("long_range_ship"),
        "long_range_ship_elite": s.get("long_range_ship_elite", True),
        "starting_scout":        s.get("starting_scout"),
        "monk_skin":             s.get("monk_skin"),

        # Phase Two pass-throughs (not yet consumed by build pipeline)
        "second_uu":              s.get("second_uu"),
        "unit_overrides":         s.get("unit_overrides",         []),
        "button_moves":           s.get("button_moves",           []),
        "free_techs":             s.get("free_techs",             []),
        "monastery_skin_building":s.get("monastery_skin_building"),
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

    def _ut_out(ut_raw: dict | None) -> dict:
        ut_raw = ut_raw or {}
        return {
            "mode":           ut_raw.get("mode",        "vanilla"),
            "vanilla_km_idx": ut_raw.get("vanilla_km_idx"),
            "name":           ut_raw.get("name",        ""),
            "description":    ut_raw.get("description", ""),
            "cost":           _cost_dict(ut_raw.get("cost")),
            "time":           int(ut_raw.get("time") or 0),
            "effects": [
                {"id": int(e["id"]), "multiplier": int(e.get("multiplier", 1))}
                for e in (ut_raw.get("effects") or [])
                if isinstance(e, dict) and "id" in e
            ],
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

        "castle_ut":    _ut_out(draft.get("castle_ut")),
        "imperial_ut":  _ut_out(draft.get("imperial_ut")),

        "tree": tree_out,
        "long_range_ship":         draft.get("long_range_ship"),
        "long_range_ship_elite":   draft.get("long_range_ship_elite", True),
        "starting_scout":          draft.get("starting_scout"),
        "monk_skin":               draft.get("monk_skin"),

        "unit_overrides":          draft.get("unit_overrides",          []),
        "button_moves":            draft.get("button_moves",            []),
        "free_techs":              draft.get("free_techs",              []),
        "monastery_skin_building": draft.get("monastery_skin_building"),
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
