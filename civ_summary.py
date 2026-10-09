"""civ_summary.py — one civ, summarised for showing off (issue #57).

Players share their civs as Discord screenshots, PDFs and Google Docs.  The
share page renders this summary as an in-game-style card; the same summary
renders to Markdown and plain text for the copy buttons, so the three can
never say different things.

Bonus, unique-tech and team-bonus wording is the in-game wording: the same
bonus_names / team_bonus_names text and unique-tech form ("Name (description)")
the build writes into the civ selection screen.

    summarize(schema, uu_catalog, techtree)   -> dict
    to_markdown(summary) / to_text(summary)   -> str

`schema` is an Empire Forge civ file (civ_schema shape).  The caller converts a
Builder draft (civ_schema.from_draft) or a KM file (app._km_to_draft) first.
"""
from __future__ import annotations

import json
from pathlib import Path

import custom_bonus
from build_all import _ut_bonus_id, _ut_name, ut_name_and_desc, ut_selection_text
from build_civ import _tree_sets
from civ_appender import get_civ_bonuses, get_team_bonuses
from civ_schema import norm_elite_upgrade, to_draft
from wizard_build import _draft_to_civ_def

_ROOT = Path(__file__).parent


def _names(file: str) -> dict[str, str]:
    try:
        return json.loads((_ROOT / file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# The stats a unit block shows, in order: (stats key, label, override prefix).
_STAT_ROWS = (("hp", "HP", "hp"), ("attack", "Attack", "attack"),
              ("melee_armor", "Melee armor", "melee"), ("pierce_armor", "Pierce armor", "pierce"),
              ("range", "Range", "range"), ("reload_time", "Reload", "reload"),
              ("speed", "Speed", "speed"), ("train_time", "Train time", "train"))
_FLAG_TEXT = {
    "no_convert": "cannot be converted",
    "trample": "trample damage",
    "regen_hp": "regenerates HP",
    "bonus_dmg_resist": "resists {v}% bonus damage",
    "charge_pool": "charge attack (+{v} damage)",
}


def _fmt(v) -> str:
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return str(v)


def _attack_bonuses(stats: dict) -> list[str]:
    """'+4 vs buildings' from the UU catalog's stats (not a civ_def)."""
    return [f"+{n} vs {what}" for what, n in ((stats.get("base") or {}).get("bonuses") or [])]


def _unit_block(entry: dict | None, uu: dict) -> dict | None:
    """The UU: name, icon, description, base/elite stats with the player's
    overrides applied (and marked), cost, traits, elite upgrade."""
    if entry is None and not uu.get("name"):
        return None
    stats = (entry or {}).get("stats") or {}
    ov = uu.get("overrides") or {}
    rows = []
    for key, label, pfx in _STAT_ROWS:
        cells, changed = [], False
        for tier in ("base", "elite"):
            v = (stats.get(tier) or {}).get(key)
            if ov.get(f"{pfx}_{tier}") is not None:
                v, changed = ov[f"{pfx}_{tier}"], True
            cells.append(v)
        if any(c is not None for c in cells):
            rows.append({"label": label, "base": cells[0], "elite": cells[1], "changed": changed})
    cost = (entry or {}).get("training_cost") or ""
    if any(ov.get(f"cost_{r}") for r in ("food", "wood", "stone", "gold")):
        cost = " ".join(f"{ov[f'cost_{r}']}{r[0].upper()}" for r in ("food", "wood", "stone", "gold")
                        if ov.get(f"cost_{r}"))
    flags = uu.get("advanced_flags") or {}
    traits = [t.format(v=_fmt(flags[k])) for k, t in _FLAG_TEXT.items() if flags.get(k)]
    up = norm_elite_upgrade(uu.get("elite_upgrade")) or (entry or {}).get("elite_upgrade")
    up_text = ""
    if up:
        parts = [f"{n} {r}" for r, n in (up.get("cost") or {}).items() if n]
        if up.get("time"):
            parts.append(f"{up['time']}s")
        up_text = ", ".join(parts)
    name = (uu.get("name") or "").strip() or (entry or {}).get("name") or "Unique Unit"
    return {"name": name, "base_name": (entry or {}).get("name") or "",
            "icon": (entry or {}).get("icon"), "description": (uu.get("description") or "").strip(),
            "ranged": bool(stats.get("ranged")), "stats": rows, "cost": cost,
            "attack_bonuses": _attack_bonuses(stats),
            "traits": traits, "elite_upgrade": up_text}


def _uts(schema: dict, civ_def: dict) -> list[dict]:
    out = []
    for key, group, castle, label in (("castle_ut", 2, True, "Castle Age"),
                                      ("imperial_ut", 3, False, "Imperial Age")):
        ut = schema.get(key) if isinstance(schema.get(key), dict) else {}
        name = (ut.get("name") or "").strip() or _ut_name(_ut_bonus_id(civ_def, group), castle=castle) or ""
        name, desc = ut_name_and_desc(name, ut.get("description") or "")
        if name:
            out.append({"age": label, "name": name, "description": desc,
                        "text": ut_selection_text(name, desc)})
    return out


# A node is "standard" when at least a third of the game's civs have it in the
# shipped CivTechTrees (Militia 55/59, Hand Cannoneer 24, Champion 40); below
# that it is regional or unique (Battle Elephant 6, Fire Lancer 5, Slinger 4).
# "Missing" lists only standard nodes the civ lacks — nobody misses an Eagle
# Warrior — and "extras" the regional ones it has, as players write them up.
_STANDARD_SHARE = 1 / 3
_standard_cache: set | None = None


def _standard_nodes() -> set[tuple[str, int]]:
    global _standard_cache
    if _standard_cache is None:
        counts: dict[tuple[str, int], int] = {}
        files = sorted((_ROOT / "CivTechTrees").glob("*.json"))
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for sec in ("civ_techs_units", "civ_techs_buildings"):
                for n in data.get(sec, []):
                    if n.get("Node Status") != "NotAvailable":
                        k = (n.get("Use Type"), n.get("Node ID"))
                        counts[k] = counts.get(k, 0) + 1
        need = max(1, round(len(files) * _STANDARD_SHARE))
        _standard_cache = {k for k, c in counts.items() if c >= need}
    return _standard_cache


def _tech_tree(tree: tuple, techtree: dict) -> dict:
    """Per building, from the editor's own layout (FULL.json): standard nodes
    the civ is missing and regional/unique ones it has; plus standard
    buildings it lacks (camps a Settlement / Folwark / Mule Cart replaces
    don't count)."""
    from build_civ import _REGIONAL_CAMP_SWAPS
    units, buildings, techs = tree                      # build_civ._tree_sets
    std = _standard_nodes()
    replaced = {r for b, spec in _REGIONAL_CAMP_SWAPS.items() if b in buildings for r in spec["replaces"]}
    by_bldg: dict[int, list] = {}
    for n in techtree.get("units_techs", []):
        by_bldg.setdefault(n.get("building_id"), []).append(n)
    rows, missing_buildings, seen_b = [], [], set()
    for b in techtree.get("buildings", []):
        bid, bname = b.get("node_id"), b.get("name") or str(b.get("node_id"))
        if bid not in buildings:
            if ("Building", bid) in std and bid not in replaced and bname not in seen_b:
                missing_buildings.append(bname)
                seen_b.add(bname)
            continue
        missing, extras, seen = [], [], set()
        for n in by_bldg.get(bid, []):
            name, kind = n.get("name") or "", "Unit" if n.get("use_type") == "Unit" else "Tech"
            if not name or name in seen:
                continue
            seen.add(name)
            owned = n.get("node_id") in (units if kind == "Unit" else techs)
            standard = (kind, n.get("node_id")) in std
            if standard and not owned:
                missing.append(name)
            elif owned and not standard:
                extras.append(name)
        if missing or extras:
            rows.append({"building": bname, "missing": missing, "extras": extras})
    return {"buildings": rows, "missing_buildings": missing_buildings}


def summarize(schema: dict, uu_catalog: list[dict], techtree: dict) -> dict:
    """Everything the share page, the Markdown and the plain text show."""
    draft = to_draft(schema)
    civ_def = _draft_to_civ_def(draft)
    bonus_names, team_names = _names("bonus_names.json"), _names("team_bonus_names.json")

    civ_bonuses = []
    for bid, mult in ((e[0], e[1] if len(e) > 1 else 1) for e in get_civ_bonuses(schema)
                      if isinstance(e, (list, tuple)) and e):
        if str(bid) in bonus_names:
            civ_bonuses.append(bonus_names[str(bid)] + (f" [x{mult}]" if int(mult) > 1 else ""))
    for card in custom_bonus.normalize(schema.get("custom_bonuses")):
        civ_bonuses.append(custom_bonus.card_text(card))
    team = [team_names[str(e[0])] for e in get_team_bonuses(schema)
            if isinstance(e, (list, tuple)) and e and str(e[0]) in team_names]

    uu = schema.get("unique_unit") or {}
    entry = next((e for e in uu_catalog if e.get("km_idx") == uu.get("km_idx")), None)
    hero = schema.get("hero_unit") if isinstance(schema.get("hero_unit"), dict) else None
    hero_block = None
    if hero and hero.get("base_unit_id") is not None:
        hero_block = {"name": (hero.get("name") or "").strip() or "Hero",
                      "description": (hero.get("description") or "").strip()}

    tagline = (schema.get("tagline") or "").strip()
    return {
        "name": (schema.get("alias") or "").strip() or "Unnamed civilization",
        "tagline": f"{tagline} civilization" if tagline else "",
        # The Builder's "Share description" (View Civ only, never the game);
        # a KM import's description otherwise.
        "description": ((schema.get("share_description") or schema.get("description") or "").strip()),
        "emblem": schema.get("emblem") if str(schema.get("emblem") or "").startswith("data:image") else "",
        "civ_bonuses": civ_bonuses,
        "unique_unit": _unit_block(entry, uu),
        "unique_techs": _uts(schema, civ_def),
        "team_bonuses": team,
        "hero": hero_block,
        "tech_tree": _tech_tree(_tree_sets(schema), techtree),
    }


# ── Copy formats ──────────────────────────────────────────────────────────────

def _unit_lines(u: dict, md: bool) -> list[str]:
    b = (lambda s: f"**{s}**") if md else (lambda s: s)
    lines = [b(u["name"]) + (f" ({u['base_name']})" if u["base_name"] and u["base_name"] != u["name"] else "")]
    if u["description"]:
        lines.append(u["description"])
    if u["stats"]:
        has_elite = any(r["elite"] is not None and r["elite"] != r["base"] for r in u["stats"])
        cells = [f"{r['label']} {_fmt(r['base'])}"
                 + (f"/{_fmt(r['elite'])}" if has_elite and r["elite"] is not None else "")
                 + ("*" if r["changed"] else "") for r in u["stats"]]
        lines.append(("Stats (base/elite): " if has_elite else "Stats: ") + ", ".join(cells))
    for label, val in (("Cost", u["cost"]), ("Attack bonuses", ", ".join(u["attack_bonuses"])),
                       ("Traits", ", ".join(u["traits"])), ("Elite upgrade", u["elite_upgrade"])):
        if val:
            lines.append(f"{label}: {val}")
    if any(r["changed"] for r in u["stats"]):
        lines.append("* changed from the original unit")
    return lines


def _render(s: dict, md: bool) -> str:
    h = (lambda t: f"## {t}") if md else (lambda t: t.upper())
    bullet = "- " if md else "• "
    # The page's options and edits ride along on the summary: show_* flags,
    # and lists the player retyped on the card (see /api/civ/render).
    out = [f"# {s['name']}" if md else s["name"].upper()]
    if s.get("tagline"):
        out.append(f"_{s['tagline']}_" if md else s["tagline"])
    if s.get("description") and s.get("show_description", True):
        out.append(s["description"])
    if s["civ_bonuses"]:
        out += ["", h("Civilization bonuses")] + [bullet + x for x in s["civ_bonuses"]]
    if s["unique_unit"]:
        out += ["", h("Unique unit")] + _unit_lines(s["unique_unit"], md)
    if s["unique_techs"]:
        out += ["", h("Unique technologies")] + [
            f"{bullet}{t['age']}: {t['text']}" if t.get("age") else f"{bullet}{t['text']}"
            for t in s["unique_techs"]]
    if s["team_bonuses"]:
        out += ["", h("Team bonus")] + [bullet + x for x in s["team_bonuses"]]
    if s["hero"]:
        out += ["", h("Hero"), s["hero"]["name"]] + ([s["hero"]["description"]] if s["hero"]["description"] else [])
    tt = s["tech_tree"] if s.get("show_tech_tree", True) else None
    if tt is not None:
        out += ["", h("Tech tree")]
    if tt is not None and not tt["buildings"] and not tt["missing_buildings"]:
        out.append("The standard tech tree.")
    if tt is not None and tt["missing_buildings"]:
        out.append(f"{bullet}No {', '.join(tt['missing_buildings'])}")
    for b in (tt or {}).get("buildings", []):
        name = f"**{b['building']}**" if md else b["building"]
        parts = ([f"also {', '.join(b['extras'])}"] if b["extras"] else []) \
            + ([f"missing {', '.join(b['missing'])}"] if b["missing"] else [])
        out.append(f"{bullet}{name}: " + "; ".join(parts))
    out += ["", "Made with Empire Forge — https://empireforge.app"]
    return "\n".join(out).strip() + "\n"


def to_markdown(summary: dict) -> str:
    return _render(summary, md=True)


def to_text(summary: dict) -> str:
    return _render(summary, md=False)
