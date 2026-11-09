"""Units the player adds to a building on the tech tree page ("+ Add Unit").

A line is 1-4 tiers.  Every tier is a fresh copy of the same base unit,
appended to every civ (as km_custom_uu does for a custom UU) and enabled only
for the civ that added it:

  * tier 1 is made available by a hidden, civ-owned tech at its age;
  * each later tier has its own upgrade button at the building (EC_UPGRADE from
    the tier before), and only that: the vanilla upgrades leave it alone.  An
    earlier version also hung each tier on its AI role's vanilla upgrade
    (Pikeman upgraded the Guard line), since the game's AI researches upgrades
    only by name; in game that confused the player, who expects Pikeman to be
    about Spearmen (2026-11-09).  So an AI playing the civ trains tier 1 and
    never upgrades it.
  * all tiers share one (building, button) slot — EC_UPGRADE redirects the
    train button only then (quirk 3) — the building's first free column (1-4;
    the fifth column is the building's own commands, the rally point), with the
    upgrade one row below when that is free, else in any free tech slot.

Stats: a tier's edit carries to every later tier that doesn't set that field
itself, so an upgrade never makes a unit worse.  Names come from the mod-wide
editor string block (civ_appender._editor_sid).

Built inside apply_civ BEFORE the bonus cards, so class-targeted and "Trained
at" cards reach the new units.  The AI half (joining the role's unit line in
unitlines.json) is patch_unitline_roles, run by build_all.dat_json_files; the
F2 tree nodes are build_civ._added_line_nodes.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

from genieutils.effect import Effect, EffectCommand
from genieutils.tech import ResearchResourceCost
from genieutils.unit import TrainLocation

EC_ENABLE, EC_UPGRADE = 2, 3
AGE_TECHS = {2: 101, 3: 102, 4: 103}            # Feudal, Castle, Imperial Age
_AGE_OF_TECH = {v: k for k, v in AGE_TECHS.items()}
ELITE_UPGRADE_ICON = 105                         # the gold medal every elite UU tech uses
# An upgrade's default cost and time when the role has no vanilla upgrade at
# that age: the Militia line's (Man-at-Arms, Long Swordsman, Two-Handed
# Swordsman), the most ordinary upgrades in the game.
_DEFAULT_UPGRADE = {2: ({0: 100, 3: 40}, 40), 3: ({0: 150, 3: 65}, 40), 4: ({0: 200, 3: 100}, 45)}
_RES = {"food": 0, "wood": 1, "stone": 2, "gold": 3}
# Train buttons a line may take, page 1 then page 2; its upgrade goes +5.  No
# vanilla unit or tech uses the fifth column at the Barracks, Archery Range or
# Stable (DAT survey 2026-11-09): it is the building's commands — a Knight put
# on button 5 answered the rally point's hotkey in game.
_TRAIN_BUTTONS = (1, 2, 3, 4, 21, 22, 23, 24)
_RESERVED = {5, 10, 25, 30}
_ANY_BUTTONS = tuple(b for b in (*range(1, 16), *range(21, 36)) if b not in _RESERVED)


# ── The AI's unit lines (unitlines.json) ─────────────────────────────────────

_LINES_CACHE: dict = {}


def game_unit_lines(dat_path=None) -> list[dict]:
    """unitlines.json's UnitLines, from beside `dat_path` (default: the DAT
    being built) — [] if there is none."""
    import dat_reader
    from build_civ import _find_adjacent_json
    if dat_path is None:
        dat_path = dat_reader.last_loaded
    key = str(dat_path)
    if key not in _LINES_CACHE:
        lines: list = []
        if dat_path is not None:
            path = _find_adjacent_json(Path(dat_path), "unitlines.json")
            try:
                if path is not None and path.exists():
                    lines = json.loads(path.read_text(encoding="utf-8")).get("UnitLines", [])
            except (OSError, ValueError):
                lines = []
        _LINES_CACHE.clear()
        _LINES_CACHE[key] = lines
    return _LINES_CACHE[key]


# ── The unit picker's catalog ────────────────────────────────────────────────

NAVAL_CLASSES = (2, 20, 21, 22)      # trade cog, transport, fishing ship, warship
_CIVILIAN, _ANIMAL = 4, 10
CATALOG_GROUPS = ("standard", "regional", "unique", "chronicles", "scenario", "hero")


def _tree_availability(dat_path) -> tuple[dict[int, set[str]], dict[str, str], set[int], dict[int, str]]:
    """From the player's own files: unit id -> the civs whose tree has it
    (CivTechTrees/*.json), civ -> era ("base", "antiquity") and the unique
    units civilizations.json names, with the civ each belongs to."""
    from build_civ import _find_adjacent_json
    avail: dict[int, set[str]] = {}
    era: dict[str, str] = {}
    uus: dict[int, str] = {}
    civs_json = _find_adjacent_json(Path(dat_path), "civilizations.json")
    try:
        for c in json.loads(civs_json.read_text(encoding="utf-8"))["civilization_list"]:
            name = c.get("tech_tree_name") or c.get("internal_name")
            if not name or c.get("internal_name") == "Gaia":
                continue
            era[name.upper()] = c.get("era") or "base"
            for k in ("unique_unit_id", "elite_unique_unit_id"):
                if isinstance(c.get(k), int) and c[k] >= 0:
                    uus[c[k]] = name.upper()
    except (AttributeError, OSError, ValueError, KeyError):
        pass
    folder = civs_json.parent / "CivTechTrees" if civs_json is not None else None
    for f in sorted(folder.glob("*.json")) if folder is not None and folder.is_dir() else ():
        civ = f.stem.upper()
        try:
            nodes = json.loads(f.read_text(encoding="utf-8")).get("civ_techs_units") or []
        except (OSError, ValueError):
            continue
        for n in nodes:
            if n.get("Use Type") == "Unit" and n.get("Node Status") != "NotAvailable":
                avail.setdefault(int(n["Node ID"]), set()).add(civ)
    return avail, era, set(uus), uus


_CHRONICLES_STRINGS: dict = {}


def chronicles_strings() -> dict[int, str]:
    """The Chronicles units' names (405xxx), which live in the game's paphos
    key-value file rather than the main one _string_table reads."""
    from civ_appender import _STRING_LINE_RE, _strings_source
    src = _strings_source()
    key = str(src)
    if key not in _CHRONICLES_STRINGS:
        table: dict[int, str] = {}
        path = src.parent / "key-value-paphos-strings-utf8.txt" if src else None
        try:
            if path is not None and path.exists():
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        m = _STRING_LINE_RE.match(line)
                        if m:
                            table[int(m.group(1))] = m.group(2)
        except OSError:
            pass
        _CHRONICLES_STRINGS.clear()
        _CHRONICLES_STRINGS[key] = table
    return _CHRONICLES_STRINGS[key]


def is_military(unit) -> bool:
    """A unit that fights (or converts and heals): what "+ Add Unit" offers."""
    from heroes import can_fight
    return bool(unit is not None and unit.type == 70 and unit.creatable is not None
                and unit.hit_points > 0 and unit.class_ not in (_CIVILIAN, _ANIMAL)
                and can_fight(unit))


def unit_catalog(dat, dat_path, name_of) -> list[dict]:
    """Every military unit a line can copy, one per name, grouped for the
    picker: standard (most civs have it), regional (a few), unique (one civ, or
    a civ's unique unit), chronicles (only the Chronicles civs), scenario (no
    civ trains it) and hero.  [{id, name, group, cls, at, naval}]"""
    from heroes import is_hero
    avail, era, uus, uu_civ = _tree_availability(dat_path)
    base_civs = {c for c, e in era.items() if e == "base"} or set().union(*avail.values()) if avail else set()
    half = max(2, len(base_civs) // 2)
    units = dat.civs[0].units
    rows = []
    for uid, u in enumerate(units):
        if not is_military(u):
            continue
        name = name_of(u)
        if not name:
            continue
        at = sorted({tl.unit_id for tl in u.creatable.train_locations if tl.unit_id >= 0})
        civs = avail.get(uid, set())
        if is_hero(u):
            group = "hero"
        elif uid in uus:
            group = "chronicles" if era.get(uu_civ[uid]) == "antiquity" else "unique"
        elif civs:
            mine = civs & base_civs
            group = ("chronicles" if not mine else "standard" if len(mine) >= half
                     else "unique" if len(mine) == 1 else "regional")
        elif at or u.hide_in_editor:
            continue            # trained somewhere no tree shows: campaign copies
        else:
            group = "scenario"
        rows.append({"id": uid, "name": name, "group": group, "cls": u.class_, "at": at,
                     "naval": u.class_ in NAVAL_CLASSES, "in_tree": bool(civs),
                     "icon": u.icon_id})
    # One per name: a tree's unit before a copy of it, then the lowest id.
    rows.sort(key=lambda r: (r["name"].casefold(), not r["in_tree"], r["id"]))
    out, seen = [], set()
    for r in rows:
        if r["name"].casefold() in seen:
            continue
        seen.add(r["name"].casefold())
        out.append(r)
    return out


def default_role(unit_lines: list[dict], base: int) -> int | None:
    """The LineID of the AI line holding the base unit, or None."""
    return next((int(l["LineID"]) for l in unit_lines
                 if base in (l.get("IDChain") or []) and "LineID" in l), None)


def role_chain(unit_lines: list[dict], role: int | None) -> list[int]:
    return next((list(l.get("IDChain") or []) for l in unit_lines
                 if role is not None and l.get("LineID") == role), [])


def role_upgrades(dat, chain: list[int]) -> dict[int, int]:
    """{age: tech} — the global, researchable techs upgrading one unit of the
    role's line to another, by the age they need (Pikeman -> 3, Halberdier -> 4)."""
    members = set(chain)
    out: dict[int, int] = {}
    for tid, t in enumerate(dat.techs):
        if t.civ != -1 or not any(rl.location_id >= 0 for rl in t.research_locations):
            continue
        if not 0 <= t.effect_id < len(dat.effects):
            continue
        if not any(c.type == EC_UPGRADE and int(c.a) in members and int(c.b) in members
                   for c in dat.effects[t.effect_id].effect_commands):
            continue
        age = next((_AGE_OF_TECH[r] for r in t.required_techs if r in _AGE_OF_TECH), None)
        if age is not None:
            out.setdefault(age, tid)
    return out


# ── Names ────────────────────────────────────────────────────────────────────

def default_names(base_name: str, n: int) -> list[str]:
    """Tier 1 is the base's name; the last tier of two or more is "Elite …";
    tiers between are "Veteran …" (and "Heavy …" for a fourth)."""
    if n == 1:
        return [base_name]
    middle = ["Veteran", "Heavy"][: n - 2]
    return [base_name] + [f"{m} {base_name}" for m in middle] + [f"Elite {base_name}"]


def _tooltip(dat, base: int, name: str, desc: str = "") -> str | None:
    """The base unit's own Castle tooltip, renamed, without its grey
    "Upgrades: ..." line (that names the base's line, not this one), and with
    the line's own description in place of the base's when it has one."""
    from build_civ import rich_unit_tooltip
    rich = rich_unit_tooltip(dat, base, name, desc)
    if rich is None:
        return None
    return "\\n".join(l for l in rich.split("\\n") if not l.startswith("<GREY>"))


# ── Building the lines ───────────────────────────────────────────────────────

def _upgrades_into_absent(dat, tech, present: set[int]) -> bool:
    """A unit upgrade (Heavy Camel, Elite Battle Elephant) whose units the civ
    has none of.  The tree page draws these as unit nodes, not tech nodes, so
    the tech list never says they are off."""
    if not 0 <= tech.effect_id < len(dat.effects):
        return False
    ups = [c for c in dat.effects[tech.effect_id].effect_commands if c.type == EC_UPGRADE]
    return bool(ups) and not any(int(c.b) in present or int(c.a) in present for c in ups)


def _occupied(dat, civ_index: int, civ_def: dict, building: int) -> set[int]:
    """Buttons the civ already uses at `building`: its units' and the techs it
    can research there.  A tech the tree page draws counts only when the tree
    has it: opt-in techs (Heavy Camel, Elite Battle Elephant) are never switched
    off explicitly, and counting them kept the Stable's camel and elephant
    columns from a civ with neither."""
    from civ_appender import _civ_present_units, _editor_nodes, _tree_tech_ids
    units = dat.civs[civ_index].units
    used: set[int] = set()
    for uid in _civ_present_units(civ_def, dat, civ_index):
        u = units[uid] if 0 <= uid < len(units) else None
        if u is not None and u.creatable is not None:
            used |= {tl.button_id for tl in u.creatable.train_locations if tl.unit_id == building}
    tt = dat.effects[dat.civs[civ_index].tech_tree_id]
    disabled = {int(c.d) for c in tt.effect_commands if c.type == 102}
    drawn, tree = _editor_nodes()["techs"], _tree_tech_ids(civ_def)
    present = _civ_present_units(civ_def, dat, civ_index)
    for tid, t in enumerate(dat.techs):
        if t.civ not in (-1, civ_index) or tid in disabled:
            continue
        if tid in drawn and tree and tid not in tree and t.civ == -1:
            continue
        if _upgrades_into_absent(dat, t, present):
            continue
        used |= {rl.button_id for rl in t.research_locations if rl.location_id == building}
    return used


def _pick_buttons(used: set[int], tiers: int) -> tuple[int | None, int | None]:
    """(train button, upgrade button): the first free column, its upgrade one
    row below when that is free, else in any free slot."""
    train = next((b for b in (*_TRAIN_BUTTONS, *_ANY_BUTTONS) if b not in used), None)
    if train is None or tiers == 1:
        return train, None
    below = train + 5
    if below not in used and below not in _RESERVED:
        return train, below
    # The top row of each page is for units; an upgrade never goes there.
    return train, next((b for b in _ANY_BUTTONS
                        if b not in used and b != train and (b - 1) % 20 >= 5), None)


def _hotkey(grid: tuple, building: int, button: int, fallback: int) -> int:
    """The hotkey of whatever sits at that grid position (_grid_hotkeys)."""
    by_bldg, by_pos = grid
    pos = button - 20 if button > 20 else button
    return by_bldg.get((building, pos), by_pos.get(pos, fallback))


def _flowed_edits(tiers: list[dict]) -> list[dict]:
    """Each tier's edits with every earlier tier's carried forward."""
    out, carried = [], {}
    for t in tiers:
        carried = {**carried, **(t.get("edits") or {})}
        out.append(dict(carried))
    return out


_ICON_CACHE: dict = {}


def _upgrade_icon(dat, unit_icon: int, role_tech: int | None) -> int:
    """An upgrade's icon (techs have their own icon set): the icon of a vanilla
    upgrade INTO a unit that looks like this tier (a Savar-looking tier gets the
    Savar's), else the role's vanilla upgrade at that age (Pikeman's), else the
    gold medal every elite unique-unit upgrade wears."""
    key = id(dat)
    if key not in _ICON_CACHE:
        units, by_look = dat.civs[0].units, {}
        for t in dat.techs:
            if not any(rl.location_id >= 0 for rl in t.research_locations):
                continue
            if not 0 <= t.effect_id < len(dat.effects):
                continue
            for c in dat.effects[t.effect_id].effect_commands:
                b = int(c.b)
                if c.type == EC_UPGRADE and 0 <= b < len(units) and units[b] is not None:
                    by_look.setdefault(units[b].icon_id, t.icon_id)
        _ICON_CACHE.clear()
        _ICON_CACHE[key] = by_look
    by_look = _ICON_CACHE[key]
    if unit_icon in by_look:
        return by_look[unit_icon]
    return dat.techs[role_tech].icon_id if role_tech is not None else ELITE_UPGRADE_ICON


def _write_edits(u, e: dict) -> None:
    from civ_overrides import write_bonus_attacks, write_unit_cost, write_unit_stats
    stats = {k: v for k, v in e.items() if k not in ("cost", "bonus", "name")}
    if stats:
        write_unit_stats(u, stats)
    if "cost" in e:
        write_unit_cost(u, e["cost"], f"added unit {u.id}")
    if e.get("bonus"):
        write_bonus_attacks(u, e["bonus"])


def _costs(cost: dict) -> tuple:
    pairs = [(r, a) for r, a in sorted(cost.items()) if a > 0][:3]
    return tuple(ResearchResourceCost(type=r, amount=a, flag=1) for r, a in pairs) + tuple(
        ResearchResourceCost(type=-1, amount=0, flag=0) for _ in range(3 - len(pairs)))


def apply_added_lines(dat, civ_index: int, civ_def: dict, warnings: list) -> list[dict]:
    """Build civ_def["added_lines"] for this civ.  Returns one record per line
    built: {id, building, role, units, techs, names, sids, tech_sids, ages,
    button, strings: (extra_unit_strings, extra_tech_strings)}."""
    from civ_appender import (_OWN_STRING_NAMES, _append_effect, _append_tech, _display_name,
                              _editor_sid, _every_civ, _make_tech, appearance_ok, copy_unit_look,
                              look_elite, unit_label)
    from civ_schema import norm_added_lines
    lines = norm_added_lines(civ_def.get("added_lines"))
    if not lines:
        return []
    unit_lines = game_unit_lines()
    target = dat.civs[civ_index].units
    template = dat.civs[0].units                      # Gaia: never a build target
    built: list[dict] = []
    used_by_building: dict[int, set[int]] = {}
    from civ_appender import _grid_hotkeys
    grid = _grid_hotkeys(dat)
    if not hasattr(dat, "_ef_added_units"):
        dat._ef_added_units = {}
    added_units = dat._ef_added_units.setdefault(civ_index, set())
    from civ_appender import _tree_building_ids
    have = _tree_building_ids(civ_def)
    for line in lines:
        base, building, tiers = line["base"], line["building"], line["tiers"]
        # The tree page hides a line whose building is off; the build agrees.
        # (The Town Center is always on; a tree with no buildings listed is a
        # KM file that never chose, so it keeps them.)
        if have and building != 109 and building not in have:
            print(f"       Added line {line['id']}: {unit_label(dat, 0, building)} isn't in the tree — skipped")
            continue
        src = target[base] if 0 <= base < len(target) else None
        if src is None or src.creatable is None:
            msg = f"Added line {line['id']}: unit {base} can't be trained, so it can't be copied — skipped"
            print(f"       WARNING: {msg}")
            warnings.append(msg)
            continue
        used = used_by_building.setdefault(building, _occupied(dat, civ_index, civ_def, building))
        train_btn, up_btn = _pick_buttons(used, len(tiers))
        if train_btn is None or (len(tiers) > 1 and up_btn is None):
            msg = (f"Added line {line['id']}: {unit_label(dat, 0, building)} has no free "
                   f"button left — skipped")
            print(f"       WARNING: {msg}")
            warnings.append(msg)
            continue
        used |= {train_btn} | ({up_btn} if up_btn else set())

        # One copy of the base per tier, in every civ (ids must line up).
        first = len(template)
        ids = [first + i for i in range(len(tiers))]
        for civ in _every_civ(dat):
            own = civ.units[base] if base < len(civ.units) else None
            for uid in ids:
                u = deepcopy(own if own is not None else src)
                u.id, u.base_id, u.copy_id, u.enabled = uid, uid, uid, 0
                civ.units.append(u)
        if base < len(dat.unit_headers):
            for _ in ids:
                dat.unit_headers.append(deepcopy(dat.unit_headers[base]))
        added_units.update(ids)
        if not hasattr(dat, "_ef_added_lines"):
            dat._ef_added_lines = {}
        dat._ef_added_lines[(civ_index, line["id"])] = list(ids)   # custom cards' "line" target

        # Unnamed tiers follow tier 1's name: "Guard" -> "Elite Guard".
        from civ_appender import _string_table
        sid = src.language_dll_name
        stem = (tiers[0]["name"] or _string_table().get(sid) or chronicles_strings().get(sid)
                or _display_name(sid, src.name) or unit_label(dat, 0, base))
        names = [t["name"] or d for t, d in zip(tiers, default_names(stem, len(tiers)))]
        look = line.get("appearance")
        look_last = look_elite(dat, look) if look is not None else None
        desc = (line.get("description") or "").replace("\\", " ").replace('"', '\\"')
        hk_train = _hotkey(grid, building, train_btn, -1)
        unit_strings, sids = [], []
        for n, (uid, tier, edits) in enumerate(zip(ids, tiers, _flowed_edits(tiers))):
            u = target[uid]
            tl0 = src.creatable.train_locations[0] if src.creatable.train_locations else None
            u.creatable.train_locations = [TrainLocation(
                train_time=tl0.train_time if tl0 else 30, unit_id=building,
                button_id=train_btn, hot_key_id=hk_train)]
            # A hero's copy is a unit like any other: no gold border, no
            # regeneration, convertible (hero status is creatable.hero_mode).
            u.creatable.hero_mode = 0
            _write_edits(u, edits)
            wear = look_last if (n == len(ids) - 1 and look_last is not None) else look
            if wear is not None:
                if appearance_ok(template[wear], u):
                    copy_unit_look(template[wear], u)
                else:
                    warnings.append(f"{names[n]}: {unit_label(dat, 0, wear)}'s look doesn't fit "
                                    "(not the same kind and size) — kept its own")
            sid = _editor_sid(dat)
            _OWN_STRING_NAMES[sid] = names[n]
            sids.append(sid)
            for unit in (u, template[uid]):              # Gaia's copy names it in the UI too
                unit.language_dll_name, unit.language_dll_creation = sid, sid + 1000
                unit.language_dll_help = sid + 100000
            kv = names[n].replace('"', '\\"')
            hover = _tooltip(dat, base, kv, desc)
            unit_strings.append({"sid": sid, "name": kv, "desc_sid": sid + 100000,
                                 "help_text": hover or f"Create <b>{kv}<b> (<cost>)",
                                 "ext_sid": sid + 21000,
                                 "ext_text": hover or f"Create <b>{kv}<b> (<cost>)"})

        # Tier 1: available at its age; later tiers researched.  The role's
        # vanilla upgrade at an age only supplies the defaults: cost, time and,
        # failing a better match, the icon.
        role = line.get("role")
        if role is None:
            role = default_role(unit_lines, base)
        vanilla = role_upgrades(dat, role_chain(unit_lines, role)) if role is not None else {}
        avail = _append_effect(dat, Effect(name=f"{names[0]} (available)", effect_commands=[
            EffectCommand(type=EC_ENABLE, a=ids[0], b=1, c=-1, d=0.0)]))
        avail_tech = _make_tech(f"{names[0]} (available)", avail, civ_index,
                                age_req=AGE_TECHS.get(tiers[0]["age"], -1))
        techs = [_append_tech(dat, avail_tech)]
        tech_strings, tech_sids = [], []
        hk_up = _hotkey(grid, building, up_btn, -1) if up_btn else -1
        for n in range(1, len(ids)):
            age = tiers[n]["age"]
            ride = vanilla.get(age)          # the role's own upgrade at this age
            up = tiers[n].get("upgrade") or {}
            if ride is not None:
                rt = dat.techs[ride]
                d_cost = {rc.type: rc.amount for rc in rt.resource_costs if rc.type in (0, 1, 2, 3) and rc.amount > 0}
                d_time = next((rl.research_time for rl in rt.research_locations if rl.location_id >= 0), 40)
            else:
                d_cost, d_time = _DEFAULT_UPGRADE[age]
            cost = ({_RES[r]: a for r, a in up["cost"].items()} if "cost" in up else d_cost)
            time = up.get("time", d_time)
            eff = _append_effect(dat, Effect(name=f"Upgrade to {names[n]}", effect_commands=[
                EffectCommand(type=EC_UPGRADE, a=ids[n - 1], b=ids[n], c=-1, d=0.0)]))
            sid = _editor_sid(dat)
            _OWN_STRING_NAMES[sid] = names[n]
            tech = _make_tech(f"Upgrade to {names[n]}", eff, civ_index, age_req=AGE_TECHS[age],
                              location=building, button=up_btn, research_time=time,
                              icon_id=_upgrade_icon(dat, target[ids[n]].icon_id, ride),
                              lang_name=sid, lang_desc=sid + 1000, lang_help=sid + 21000,
                              lang_tech_tree=sid + 150000, hot_key_id=hk_up)
            tech.required_techs = (AGE_TECHS[age], techs[-1], -1, -1, -1, -1)
            tech.required_tech_count = 2
            tech.resource_costs = _costs(cost)
            tid = _append_tech(dat, tech)
            techs.append(tid)
            tech_sids.append(sid)
            kv, prev = names[n].replace('"', '\\"'), names[n - 1].replace('"', '\\"')
            tech_strings.append({"sid": sid, "name": kv, "label": f"Upgrade to {kv}",
                                 "hover": f"Upgrade to <b>{kv}<b> (<cost>)\\nUpgrades your {prev} to {kv}."})
        print(f"       Added line: {' -> '.join(names)} at {unit_label(dat, 0, building)} "
              f"button {train_btn} (units {ids}"
              + (f", AI line {role}" if role else "") + ")")
        built.append({"id": line["id"], "building": building, "base": base, "role": role,
                      "units": ids, "techs": techs, "names": names, "sids": sids,
                      "tech_sids": tech_sids, "ages": [t["age"] for t in tiers],
                      "button": train_btn, "upgrade_button": up_btn,
                      "strings": (unit_strings, tech_strings)})
    return built


# ── The AI: join the role's line ─────────────────────────────────────────────

def patch_unitline_roles(unit_lines: list[dict], civs_overrides: dict) -> int:
    """Append each added line's units to its role's IDChain, so the AI's
    "train spearman-line" can pick them.  The chain is global, but no other civ
    can train these units, so only the civ that added them is affected.
    Returns the number of units added."""
    n = 0
    for ov in civs_overrides.values():
        for line in ov.get("added_lines") or []:
            entry = next((l for l in unit_lines if l.get("LineID") == line.get("role")), None)
            if entry is None:
                continue
            chain = entry.setdefault("IDChain", [])
            for uid in line["units"]:
                if uid not in chain:
                    chain.append(uid)
                    n += 1
    return n


# ── Line membership: what names the role's units reaches the line ────────────

# Unit attributes a membership copy may carry: stats, costs and timings — never
# names (50), graphics (71, 73, ...), button placement (42, 43, 158), the dead
# unit (57) or hero flags (126, 127).
MEMBER_ATTRIBUTES = frozenset({
    0, 1, 5, 8, 9, 10, 11, 12, 13, 14, 19, 20, 22, 23, 24,   # combat, LOS, work, carry
    46, 48, 49,                                              # the shown attack/armour
    59, 60, 61, 62, 63,                                      # charge attack, heal aura
    100, 101, 102, 103, 104, 105, 106, 107, 109,             # costs, train time, projectiles, regen
})


def extend_line_membership(dat, civ_index: int, lines: list[dict], unit_lines: list[dict] | None = None) -> int:
    """An added line joins its AI role's line for effects too (the user's
    rule, 2026-11-09: "if a unit was added to a line, add it to the bonus
    targets").  Every stat command that names a unit of the role's line by id —
    in the civ's tech tree and team bonus effects and in every tech it can
    research or gets (cards, UTs, Blacksmith, Supplies) — is copied for each of
    the line's units.  One copy per distinct command, not per vanilla unit it
    named: a "Spearmen +25% HP" card multiplies 93, 358 and 359 alike, and three
    copies would compound to +95%.  Returns the number of commands added."""
    if unit_lines is None:
        unit_lines = game_unit_lines()
    civ = dat.civs[civ_index]
    ours = {t for line in lines for t in line["techs"]}
    effects = {civ.tech_tree_id, civ.team_bonus_id}
    effects |= {t.effect_id for tid, t in enumerate(dat.techs)
                if t.civ in (-1, civ_index) and tid not in ours}
    added = 0
    for line in lines:
        members = set(role_chain(unit_lines, line.get("role"))) - set(line["units"])
        if not members:
            continue
        for eid in sorted(e for e in effects if 0 <= e < len(dat.effects)):
            cmds = dat.effects[eid].effect_commands
            have = {(c.type, int(c.a), c.b, c.c, c.d) for c in cmds}
            wanted = {(c.type, c.b, c.c, c.d) for c in cmds
                      if c.type in (0, 4, 5) and int(c.a) in members and c.c in MEMBER_ATTRIBUTES}
            for typ, b, attr, d in sorted(wanted):
                for uid in line["units"]:
                    if (typ, uid, b, attr, d) not in have:
                        cmds.append(EffectCommand(type=typ, a=uid, b=b, c=attr, d=d))
                        added += 1
    return added
