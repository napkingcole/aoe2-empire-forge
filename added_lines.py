"""Units the player adds to a building on the tech tree page ("+ Add Unit").

A line is 1-4 tiers.  Every tier is a fresh copy of the same base unit,
appended to every civ (as km_custom_uu does for a custom UU) and enabled only
for the civ that added it:

  * tier 1 is made available by a hidden, civ-owned tech at its age;
  * each later tier has its own upgrade button at the building (EC_UPGRADE from
    the tier before), and ALSO rides the vanilla upgrade of the AI role at that
    age (Pikeman, Halberdier, ...): the game's AI researches upgrades only by
    name, so the vanilla tech upgrading the line too is the one way its AI gets
    the later tiers (the user's call, 2026-11-09).  Researching either does it;
    the vanilla one switches our button off.
  * all tiers share one (building, button) slot — EC_UPGRADE redirects the
    train button only then (quirk 3) — chosen as the building's first free
    column, with the upgrade one row below (+5), as vanilla lays out lines.

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
# Train buttons a line may take, page 1 then page 2; its upgrade goes +5.
_TRAIN_BUTTONS = (1, 2, 3, 4, 5, 21, 22, 23, 24, 25)
_ANY_BUTTONS = tuple(range(1, 16)) + tuple(range(21, 36))


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


def _tooltip(dat, base: int, name: str) -> str | None:
    """The base unit's own Castle tooltip, renamed, without its grey
    "Upgrades: ..." line (that names the base's line, not this one)."""
    from build_civ import rich_unit_tooltip
    rich = rich_unit_tooltip(dat, base, name)
    if rich is None:
        return None
    return "\\n".join(l for l in rich.split("\\n") if not l.startswith("<GREY>"))


# ── Building the lines ───────────────────────────────────────────────────────

def _occupied(dat, civ_index: int, civ_def: dict, building: int) -> set[int]:
    """Buttons the civ already uses at `building`: its units' and the techs it
    can research there."""
    from civ_appender import _civ_present_units
    units = dat.civs[civ_index].units
    used: set[int] = set()
    for uid in _civ_present_units(civ_def, dat, civ_index):
        u = units[uid] if 0 <= uid < len(units) else None
        if u is not None and u.creatable is not None:
            used |= {tl.button_id for tl in u.creatable.train_locations if tl.unit_id == building}
    tt = dat.effects[dat.civs[civ_index].tech_tree_id]
    disabled = {int(c.d) for c in tt.effect_commands if c.type == 102}
    for tid, t in enumerate(dat.techs):
        if t.civ in (-1, civ_index) and tid not in disabled:
            used |= {rl.button_id for rl in t.research_locations if rl.location_id == building}
    return used


def _pick_buttons(used: set[int], tiers: int) -> tuple[int | None, int | None]:
    """(train button, upgrade button): the first free column whose slot below
    is free too, else the first free column and any free slot."""
    for b in _TRAIN_BUTTONS:
        if b not in used and (tiers == 1 or b + 5 not in used):
            return b, (b + 5 if tiers > 1 else None)
    train = next((b for b in _ANY_BUTTONS if b not in used), None)
    if train is None or tiers == 1:
        return train, None
    return train, next((b for b in _ANY_BUTTONS if b not in used and b != train), None)


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
        stem = tiers[0]["name"] or _display_name(src.language_dll_name, src.name) or unit_label(dat, 0, base)
        names = [t["name"] or d for t, d in zip(tiers, default_names(stem, len(tiers)))]
        look = line.get("appearance")
        look_last = look_elite(dat, look) if look is not None else None
        hk_train = _hotkey(grid, building, train_btn, -1)
        unit_strings, sids = [], []
        for n, (uid, tier, edits) in enumerate(zip(ids, tiers, _flowed_edits(tiers))):
            u = target[uid]
            tl0 = src.creatable.train_locations[0] if src.creatable.train_locations else None
            u.creatable.train_locations = [TrainLocation(
                train_time=tl0.train_time if tl0 else 30, unit_id=building,
                button_id=train_btn, hot_key_id=hk_train)]
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
            hover = _tooltip(dat, base, kv)
            unit_strings.append({"sid": sid, "name": kv, "desc_sid": sid + 100000,
                                 "help_text": hover or f"Create <b>{kv}<b> (<cost>)",
                                 "ext_sid": sid + 21000,
                                 "ext_text": hover or f"Create <b>{kv}<b> (<cost>)"})

        # Tier 1: available at its age.  Later tiers: researched, or ridden.
        role = line.get("role")
        if role is None:
            role = default_role(unit_lines, base)
        rides = role_upgrades(dat, role_chain(unit_lines, role)) if role is not None else {}
        avail = _append_effect(dat, Effect(name=f"{names[0]} (available)", effect_commands=[
            EffectCommand(type=EC_ENABLE, a=ids[0], b=1, c=-1, d=0.0)]))
        avail_tech = _make_tech(f"{names[0]} (available)", avail, civ_index,
                                age_req=AGE_TECHS.get(tiers[0]["age"], -1))
        techs = [_append_tech(dat, avail_tech)]
        tech_strings, tech_sids, ridden = [], [], []
        hk_up = _hotkey(grid, building, up_btn, -1) if up_btn else -1
        for n in range(1, len(ids)):
            age = tiers[n]["age"]
            ride = rides.get(age)
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
                              icon_id=(dat.techs[ride].icon_id if ride is not None else ELITE_UPGRADE_ICON),
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
            if ride is not None:
                # The AI's way up: the vanilla upgrade it researches by name
                # upgrades this line as well, and retires our button.
                cmds = dat.effects[dat.techs[ride].effect_id].effect_commands
                cmds.append(EffectCommand(type=EC_UPGRADE, a=ids[n - 1], b=ids[n], c=-1, d=0.0))
                cmds.append(EffectCommand(type=102, a=-1, b=-1, c=-1, d=float(tid)))
                ridden.append(ride)
        print(f"       Added line: {' -> '.join(names)} at {unit_label(dat, 0, building)} "
              f"button {train_btn} (units {ids}"
              + (f", rides {ridden}" if ridden else "") + (f", AI line {role}" if role else "") + ")")
        built.append({"id": line["id"], "building": building, "base": base, "role": role,
                      "units": ids, "techs": techs, "names": names, "sids": sids,
                      "tech_sids": tech_sids, "ages": [t["age"] for t in tiers],
                      "button": train_btn, "rides": ridden,
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
