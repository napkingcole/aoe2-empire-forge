"""
civ_schema.py — civbuilder_v1 JSON schema normalizer.

Two public functions:
  from_draft(draft)  → civbuilder_v1 dict  (wizard → saveable file)
  to_draft(schema)   → wizard draft dict   (saveable file → build pipeline)

The wizard draft format is a superset of civbuilder_v1: it adds UI-only keys
(_draftVer, dat_path) that don't belong in a shareable civ file. Everything
else maps 1-to-1, so the two formats stay tightly coupled by design.

build_all.py detects "format": "civbuilder_v1" in a JSON file and calls
to_draft() before passing it through the wizard_build pipeline.
"""

from __future__ import annotations

FORMAT_KEY   = "civbuilder_v1"
SCHEMA_VER   = 1
_DRAFT_VER   = 4   # current wizard draft version


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
    monk_skin_unit, monastery_skin_building) are passed through unchanged so
    future handlers can act on them without schema changes.
    """
    s = _clean(schema)

    # ── UU ───────────────────────────────────────────────────────────────────
    raw_uu   = _clean(s.get("unique_unit") or {})
    overrides = _clean(raw_uu.get("overrides") or {})
    adv_flags = _clean(raw_uu.get("advanced_flags") or {})

    # Strip null values so the build functions treat absence == "no override"
    overrides = {k: v for k, v in overrides.items() if v is not None}
    adv_flags = {k: v for k, v in adv_flags.items() if v is not None and v is not False}

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

    # ── UTs ──────────────────────────────────────────────────────────────────
    def _ut(raw: dict | None) -> dict:
        raw = _clean(raw or {})
        ut: dict = {
            "mode":       raw.get("mode", "vanilla"),
            "vanilla_id": raw.get("vanilla_id"),
            "name":       raw.get("name",        ""),
            "description":raw.get("description", ""),
            "cost":       _cost_dict(raw.get("cost")),
            "time":       int(raw.get("time") or 0),
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

        # Appearance
        "architecture": s.get("architecture", 2),
        "language":     s.get("language",     0),
        "wonder":       s.get("wonder_model", -1),
        "castle":       s.get("castle_model", -1),
        "emblem":       s.get("emblem",       ""),

        # Core content
        "hero_unit":    hero,
        "unique_unit":  uu,
        "bonuses":      _bonus_list(s.get("bonuses")),
        "team_bonuses": _bonus_list(s.get("team_bonuses")),
        "castle_ut":    _ut(s.get("castle_ut")),
        "imperial_ut":  _ut(s.get("imperial_ut")),
        "tree":         tree,

        # Phase Two pass-throughs (not yet consumed by build pipeline)
        "second_uu":              s.get("second_uu"),
        "unit_overrides":         s.get("unit_overrides",         []),
        "button_moves":           s.get("button_moves",           []),
        "free_techs":             s.get("free_techs",             []),
        "monk_skin_unit":         s.get("monk_skin_unit"),
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
    adv_flags = uu_raw.get("advanced_flags") or {}

    def _ut_out(ut_raw: dict | None) -> dict:
        ut_raw = ut_raw or {}
        return {
            "mode":        ut_raw.get("mode",        "vanilla"),
            "vanilla_id":  ut_raw.get("vanilla_id"),
            "name":        ut_raw.get("name",        ""),
            "description": ut_raw.get("description", ""),
            "cost":        _cost_dict(ut_raw.get("cost")),
            "time":        int(ut_raw.get("time") or 0),
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

    schema: dict = {
        "format":         FORMAT_KEY,
        "schema_version": SCHEMA_VER,

        "alias":       draft.get("alias",       ""),
        "tagline":     draft.get("tagline",      ""),
        "description": draft.get("description", ""),

        "architecture": draft.get("architecture", 2),
        "language":     draft.get("language",     0),
        "wonder_model": draft.get("wonder",  -1),
        "castle_model": draft.get("castle",  -1),
        "emblem":       draft.get("emblem",  ""),

        "hero_unit":    hero_out,
        "unique_unit":  uu_out,
        "second_uu":    draft.get("second_uu"),

        "bonuses":      _bonus_out(draft.get("bonuses")),
        "team_bonuses": _bonus_out(draft.get("team_bonuses")),

        "castle_ut":    _ut_out(draft.get("castle_ut")),
        "imperial_ut":  _ut_out(draft.get("imperial_ut")),

        "tree": tree_out,

        "unit_overrides":          draft.get("unit_overrides",          []),
        "button_moves":            draft.get("button_moves",            []),
        "free_techs":              draft.get("free_techs",              []),
        "monk_skin_unit":          draft.get("monk_skin_unit"),
        "monastery_skin_building": draft.get("monastery_skin_building"),
    }
    return schema


# ── Format detection ──────────────────────────────────────────────────────────

def is_civbuilder_v1(data: dict) -> bool:
    return data.get("format") == FORMAT_KEY
