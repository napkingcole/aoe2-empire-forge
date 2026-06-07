"""
civ_appender.py — Append or overwrite a civilization in an AoE2 DE DatFile.
"""

from copy import deepcopy

from genieutils.datfile import DatFile
from genieutils.civ import Civ
from genieutils.effect import Effect, EffectCommand
from genieutils.tech import Tech, ResearchLocation, ResearchResourceCost
from genieutils.unitheaders import UnitHeaders

from bonus_catalog import civ_bonus_techs, team_bonus_tech

# ── EffectCommand types ───────────────────────────────────────────────────────
EC_SET       = 0
EC_RESOURCE  = 1
EC_ENABLE    = 2
EC_UPGRADE   = 3
EC_ADD       = 4
EC_MULTIPLY  = 5
EC_TECH_COST = 101   # Modify tech research cost: a=tech_id, b=res(0-3), c=0(set)/1(add), d=val
EC_TECH_TIME = 103   # Modify tech research time: a=tech_id, c=0(set), d=val

# ── Building IDs ──────────────────────────────────────────────────────────────
BUILDING_CASTLE      = 82
BUILDING_BLACKSMITH  = 103

# ── KM UU index → (make_avail_tech_id, elite_upgrade_tech_id) ────────────────
# Source: fritz-net/AoE2-Civbuilder modding/civbuilder.cpp uuTechIDs[] init +
#         modding/enums/tech_ids.h.  Indices 0-38 and 78-87 are vanilla UUs;
#         39-77 and 88+ are KM-custom units (not supported here).
_KM_UU_TECHS: dict[int, tuple[int, int]] = {
    0:  (263, 360),   # Longbowman
    1:  (275, 363),   # Throwing Axeman
    2:  (446, 365),   # Huskarl
    3:  (276, 364),   # Teutonic Knight
    4:  (262, 366),   # Samurai
    5:  (268, 362),   # Chu Ko Nu
    6:  (267, 361),   # Cataphract
    7:  (269, 368),   # Mameluke
    8:  (274, 367),   # War Elephant
    9:  (271, 369),   # Janissary
    10: (399, 398),   # Berserk
    11: (273, 371),   # Mangudai
    12: (277, 370),   # Woad Raider
    13: (58,  60),    # Conquistador
    14: (431, 432),   # Jaguar Warrior
    15: (26,  27),    # Plumed Archer
    16: (1,   2),     # Tarkan
    17: (449, 450),   # War Wagon
    18: (467, 468),   # Genoese Crossbowman
    19: (839, 840),   # Ghulam
    20: (508, 509),   # Kamayuk
    21: (471, 472),   # Magyar Huszar
    22: (503, 504),   # Boyar
    23: (562, 563),   # Organ Gun
    24: (568, 569),   # Shotel Warrior
    25: (566, 567),   # Gbeto
    26: (564, 565),   # Camel Archer
    27: (614, 615),   # Ballista Elephant
    28: (616, 617),   # Karambit Warrior
    29: (618, 619),   # Arambai
    30: (620, 621),   # Rattan Archer
    31: (677, 678),   # Konnik
    32: (679, 680),   # Keshik
    33: (681, 682),   # Kipchak
    34: (683, 684),   # Leitis
    35: (750, 751),   # Coustillier
    36: (752, 753),   # Serjeant
    37: (778, 779),   # Obuch
    38: (780, 781),   # Hussite Wagon
    78: (829, 830),   # Chakram Thrower
    79: (825, 826),   # Urumi Swordsman
    80: (827, 828),   # Ratha
    81: (917, 918),   # Composite Bowman
    82: (919, 920),   # Monaspa
    83: (1063, 1064), # White Feather Guard (HKUCAV)
    84: (1073, 1074), # Fire Archer
    85: (1035, 1036), # Tiger Cavalry
    86: (990, 991),   # Iron Pagoda
    87: (1001, 1002), # Liao Dao
}

# ── String ID allocation ──────────────────────────────────────────────────────
# Vanilla strings are in the 0–26xxx range; we start well above that.
# Each custom civ gets a block of STRING_BLOCK_SIZE IDs.
STRING_BASE       = 40000
STRING_BLOCK_SIZE = 100

# Offsets within each civ's string block
STR_CIV_NAME    = 0
STR_UU_NAME     = 1
STR_CASTLE_UT   = 2
STR_IMPERIAL_UT = 3

# AoE2 DLL offset conventions: name+0, creation tooltip = name+1000, help = name+100000
DLL_CREATION_OFFSET = 1000
DLL_HELP_OFFSET     = 100000

# Vanilla AoE2 DE (all DLC) ships with 60 civs. Community testing suggests
# crashes occur around 64+; keep a small buffer.
MAX_TOTAL_CIVS = 63


# ── Helpers ───────────────────────────────────────────────────────────────────

def _str_id(civ_slot: int, offset: int) -> int:
    """Language DLL string ID for a named element of this civ."""
    return STRING_BASE + civ_slot * STRING_BLOCK_SIZE + offset


def _zero_costs() -> tuple:
    """Three empty ResearchResourceCosts (type=-1 means unused slot)."""
    empty = ResearchResourceCost(type=-1, amount=0, flag=0)
    return (deepcopy(empty), deepcopy(empty), deepcopy(empty))


def _append_effect(dat: DatFile, effect: Effect) -> int:
    dat.effects.append(effect)
    return len(dat.effects) - 1


def _append_tech(dat: DatFile, tech: Tech) -> int:
    dat.techs.append(tech)
    return len(dat.techs) - 1


def _make_tech(name: str, effect_id: int, civ_index: int,
               age_req: int = -1, location: int = -1,
               button: int = -1, research_time: int = 60,
               icon_id: int = -1,
               lang_name: int = -1, lang_desc: int = -1,
               lang_help: int = -1) -> Tech:
    """Construct a Tech with sensible defaults."""
    req = (age_req, -1, -1, -1, -1, -1) if age_req != -1 else (-1, -1, -1, -1, -1, -1)
    if location != -1:
        locations = [ResearchLocation(
            location_id=location,
            research_time=research_time,
            button_id=button,
            hot_key_id=-1,
        )]
    else:
        # Vanilla auto-fire techs always carry exactly one ResearchLocation with
        # location_id=-1, research_time=0.  An empty list causes the engine to
        # silently ignore the tech.
        locations = [ResearchLocation(location_id=-1, research_time=0,
                                      button_id=0, hot_key_id=-1)]
    return Tech(
        required_techs=req,
        resource_costs=_zero_costs(),
        required_tech_count=(1 if age_req != -1 else 0),
        civ=civ_index,
        full_tech_mode=0,
        language_dll_name=lang_name,
        language_dll_description=lang_desc,
        effect_id=effect_id,
        type=0,
        icon_id=icon_id,
        language_dll_help=lang_help,
        language_dll_tech_tree=-1,
        name=name,
        repeatable=0,
        research_locations=locations,
    )


# ── Tech tree wiring ─────────────────────────────────────────────────────────

def _apply_tree_wiring(dat: DatFile, civ_index: int, civ_def: dict,
                       base_unit_count: int) -> None:
    """
    Populate the civ's tech_tree effect (indexed by tech_tree_id, which is an
    EFFECT index) with type=102 'disable tech' commands for all unit lines and
    upgrade techs NOT present in the civ's tree specification.

    AoE2 DE mechanism:
      - tech_tree_id points to an effect in dat.effects (NOT dat.techs).
      - That effect contains type=102 commands whose d value is a tech ID to
        disable.  Disabling a "make available" tech prevents the units it
        unlocks from appearing in training buildings at runtime.
      - Upgrade techs (EC_UPGRADE) are also disabled this way.

    tree[0] = unit IDs the civ can train.
    tree[1] = building IDs the civ can build.
    tree[2] = research tech IDs the civ can research.
    """
    tree = civ_def.get("tree", [[], [], []])
    tree_units     = set(tree[0] if len(tree) > 0 and isinstance(tree[0], list) else [])
    tree_buildings = set(tree[1] if len(tree) > 1 and isinstance(tree[1], list) else [])
    tree_techs     = set(tree[2] if len(tree) > 2 and isinstance(tree[2], list) else [])

    if not tree_units and not tree_buildings and not tree_techs:
        return

    # ── Step 1: Collect all potentially-disableable tech IDs from vanilla civs.
    all_disableable: set[int] = set()
    for civ in dat.civs:
        tti = civ.tech_tree_id
        if 0 <= tti < len(dat.effects):
            for c in dat.effects[tti].effect_commands:
                if c.type == 102:
                    all_disableable.add(int(c.d))


    # ── Step 2: Build reverse maps from effect inspection of each disableable tech.
    # enable_map:  unit/building_id → [tech_ids that make it available via EC_ENABLE b=1]
    # upgrade_map: new_unit_id      → [tech_ids that upgrade to it via EC_UPGRADE]
    enable_map:  dict[int, list[int]] = {}
    upgrade_map: dict[int, list[int]] = {}
    for tech_id in all_disableable:
        if tech_id >= len(dat.techs):
            continue
        eid = dat.techs[tech_id].effect_id
        if eid < 0 or eid >= len(dat.effects):
            continue
        for c in dat.effects[eid].effect_commands:
            if c.type == 2 and c.b == 1:        # EC_ENABLE → makes unit available
                enable_map.setdefault(c.a, []).append(tech_id)
            elif c.type == 3:                    # EC_UPGRADE → produces new unit b
                upgrade_map.setdefault(c.b, []).append(tech_id)

    # ── Step 3: Compute "keep enabled" = techs the civ must NOT disable.
    keep_enabled: set[int] = set(tree_techs)  # directly specified researchable techs
    for uid in tree_units | tree_buildings:
        keep_enabled.update(enable_map.get(uid, []))   # make-avail techs
        keep_enabled.update(upgrade_map.get(uid, []))  # upgrade techs producing this unit

    # ── Step 4: Write type=102 disable commands into the civ's TT effect.
    to_disable = all_disableable - keep_enabled
    tt_eff_id  = dat.civs[civ_index].tech_tree_id
    dat.effects[tt_eff_id].effect_commands = [
        EffectCommand(type=102, a=-1, b=-1, c=-1, d=float(tid))
        for tid in sorted(to_disable)
    ]
    print(f"       Tech tree: {len(to_disable)} techs disabled, "
          f"{len(keep_enabled & all_disableable)} unit-line techs kept")


# ── Bonus application ────────────────────────────────────────────────────────

def _allocate_tech(dat: DatFile, tech_id: int, civ_index: int,
                   _seen: dict | None = None) -> int:
    """
    Deepcopy tech_id and assign it exclusively to civ_index.

    Also recursively allocates any civ-specific required techs so the whole
    dependency chain fires correctly for our civ.  _seen maps original tech
    IDs to our allocated copies (prevents infinite recursion and reuse).
    """
    if _seen is None:
        _seen = {}
    if tech_id in _seen:
        return _seen[tech_id]
    if tech_id < 0 or tech_id >= len(dat.techs):
        return -1

    src_tech = dat.techs[tech_id]

    # Global techs (civ=-1) already fire for all civs — no copy needed.
    if src_tech.civ == -1:
        return tech_id

    new_tech  = deepcopy(src_tech)
    new_tech.civ = civ_index

    # Deepcopy the effect so multiplying it later cannot affect other civs.
    src_eff_id = src_tech.effect_id
    if 0 <= src_eff_id < len(dat.effects):
        new_eff = deepcopy(dat.effects[src_eff_id])
        dat.effects.append(new_eff)
        new_tech.effect_id = len(dat.effects) - 1

    # Register before recursing so circular refs don't loop.
    dat.techs.append(new_tech)
    new_tid = len(dat.techs) - 1
    _seen[tech_id] = new_tid

    # Fix required_techs: any pointer to a civ-specific tech that isn't ours
    # must be redirected to our own allocated copy of that tech.
    reqs = list(new_tech.required_techs)
    changed = False
    for i, req_id in enumerate(reqs):
        if req_id <= 0:
            continue
        if req_id >= len(dat.techs) - 1:   # guard (techs grew as we append)
            continue
        req_civ = dat.techs[req_id].civ
        if req_civ == -1 or req_civ == civ_index:
            continue  # global or already ours — leave pointer as-is
        our_req = _allocate_tech(dat, req_id, civ_index, _seen)
        if our_req >= 0:
            reqs[i] = our_req
            changed = True
    if changed:
        new_tech.required_techs = reqs

    return new_tid


def _multiply_effect(dat: DatFile, effect_id: int, multiplier: int) -> None:
    """Repeat each EffectCommand in the effect (multiplier-1) extra times."""
    if multiplier <= 1 or effect_id < 0 or effect_id >= len(dat.effects):
        return
    original = list(dat.effects[effect_id].effect_commands)
    for _ in range(multiplier - 1):
        for ec in original:
            dat.effects[effect_id].effect_commands.append(deepcopy(ec))


# ── createCivBonus implementation ────────────────────────────────────────────
# These bonus IDs cannot be expressed as vanilla tech deepcopies; they need
# custom EffectCommand lists built from scratch.

# Monastery tech IDs (vanilla AoE2 DE)
_SANCTITY       = 231
_FERVOR         = 252
_THEOCRACY      = 438
_BLOCK_PRINTING = 230
_ATONEMENT      = 319
_ILLUMINATION   = 233
_REDEMPTION     = 316

# Elephant unit IDs
_ELEPHANT_UNITS = [239, 558, 873, 875, 1120, 1122, 1132, 1134, 1744, 1746, 1180]

# Farmer unit IDs and their work-rate multipliers (from KM source)
_FARMER_WORK_RATES = [(214, 1.23), (259, 1.23), (50, 1.15), (1187, 1.15)]


def _free_tech_cmds(tech_ids: list[int]) -> list[EffectCommand]:
    """EffectCommands to zero all costs and research time for given tech IDs."""
    cmds = []
    for tid in tech_ids:
        for res in range(4):
            cmds.append(EffectCommand(type=EC_TECH_COST, a=tid, b=res, c=0, d=0.0))
        cmds.append(EffectCommand(type=EC_TECH_TIME, a=tid, b=-1, c=0, d=0.0))
    return cmds


def _add_auto_fire_tech(dat: DatFile, civ_index: int, cmds: list[EffectCommand],
                        age_req: int = -1, name: str = "C-Bonus") -> None:
    """Append a civ-owned auto-fire tech+effect with given commands."""
    eff = Effect(name=name, effect_commands=cmds)
    dat.effects.append(eff)
    eff_id = len(dat.effects) - 1
    dat.techs.append(_make_tech(name=name, effect_id=eff_id,
                                civ_index=civ_index, age_req=age_req))


def _blacksmith_tech_ids(dat: DatFile) -> list[int]:
    """Return IDs of all techs whose primary research location is the Blacksmith."""
    out = []
    for i, t in enumerate(dat.techs):
        locs = getattr(t, 'research_locations', [])
        if locs and locs[0].location_id == BUILDING_BLACKSMITH:
            out.append(i)
    return out


def _stable_tech_ids(dat: DatFile) -> list[int]:
    """Return IDs of all techs whose primary research location is the Stable."""
    BUILDING_STABLE = 101
    out = []
    for i, t in enumerate(dat.techs):
        locs = getattr(t, 'research_locations', [])
        if locs and locs[0].location_id == BUILDING_STABLE:
            out.append(i)
    return out


def _create_bonus_handler(dat: DatFile, bonus_id: int, civ_index: int,
                          multiplier: int) -> bool:
    """
    Handle a single createCivBonus-style bonus.  Returns True if handled.

    Source: fritz-net/AoE2-Civbuilder modding/civbuilder.cpp createCivBonuses().
    Only implements bonuses that have a direct effect mapping; complex structural
    bonuses (farm layouts, mill requirements) are still skipped.
    """
    mult = multiplier

    # ── Free monastery tech sets ──────────────────────────────────────────────
    if bonus_id == 156:          # {SANCTITY, FERVOR} free
        _add_auto_fire_tech(dat, civ_index,
                            _free_tech_cmds([_SANCTITY, _FERVOR]),
                            name="C-Bonus, free Sanctity+Fervor")
        return True

    if bonus_id == 157:          # {ATONEMENT, ILLUMINATION} free
        _add_auto_fire_tech(dat, civ_index,
                            _free_tech_cmds([_ATONEMENT, _ILLUMINATION]),
                            name="C-Bonus, free Atonement+Illumination")
        return True

    if bonus_id == 158:          # {THEOCRACY, BLOCK_PRINTING} free
        _add_auto_fire_tech(dat, civ_index,
                            _free_tech_cmds([_THEOCRACY, _BLOCK_PRINTING]),
                            name="C-Bonus, free Theocracy+BlockPrinting")
        return True

    if bonus_id == 152:          # {REDEMPTION} free
        _add_auto_fire_tech(dat, civ_index,
                            _free_tech_cmds([_REDEMPTION]),
                            name="C-Bonus, free Redemption")
        return True

    # ── Economic resource bonuses ─────────────────────────────────────────────
    if bonus_id == 189:          # +500 gold in Imperial Age
        amount = 500.0 * mult
        cmds = [EffectCommand(type=EC_RESOURCE, a=3, b=1, c=-1, d=amount)]
        _add_auto_fire_tech(dat, civ_index, cmds, age_req=103,
                            name=f"C-Bonus, +{int(amount)} gold Imperial")
        return True

    if bonus_id == 210:          # +50 each resource per age advance (Feudal/Castle/Imperial)
        amount = 50.0 * mult
        for age_req in [101, 102, 103]:
            cmds = [EffectCommand(type=EC_RESOURCE, a=res, b=1, c=-1, d=amount)
                    for res in range(4)]
            _add_auto_fire_tech(dat, civ_index, cmds, age_req=age_req,
                                name=f"C-Bonus, +{int(amount)} each res age{age_req}")
        return True

    # ── Unit combat bonuses ───────────────────────────────────────────────────
    if bonus_id == 208:          # Elephants +25% attack speed (reload_time × 0.8)
        d_val = 0.8 ** mult
        cmds = [EffectCommand(type=EC_MULTIPLY, a=uid, b=-1, c=10, d=d_val)
                for uid in _ELEPHANT_UNITS]
        _add_auto_fire_tech(dat, civ_index, cmds,
                            name="C-Bonus, elephants +25% attack speed")
        return True

    # ── Villager/eco bonuses ──────────────────────────────────────────────────
    if bonus_id == 120:          # Farmers work 15% faster (work_rate attr 13)
        cmds = [EffectCommand(type=EC_MULTIPLY, a=uid, b=-1, c=13, d=rate ** mult)
                for uid, rate in _FARMER_WORK_RATES]
        _add_auto_fire_tech(dat, civ_index, cmds,
                            name="C-Bonus, farmers 15% faster")
        return True

    # ── Technology cost bonuses ───────────────────────────────────────────────
    if bonus_id == 125:          # Blacksmith upgrades cost no gold
        bs_ids = _blacksmith_tech_ids(dat)
        cmds = [EffectCommand(type=EC_TECH_COST, a=tid, b=3, c=0, d=0.0)
                for tid in bs_ids]
        if cmds:
            _add_auto_fire_tech(dat, civ_index, cmds,
                                name="C-Bonus, blacksmith no gold")
        return True

    return False  # not handled


def _apply_bonuses(dat: DatFile, civ_index: int, civ_def: dict,
                   tb_eff_id: int) -> None:
    """
    Apply civ bonuses and team bonus from civ_def to the DAT.

    bonuses[0] → civ bonuses:  [[id, multiplier], ...]
    bonuses[1] → UU reference: [id] bare int list (not processed here)
    bonuses[2] → castle UT:    [[id, multiplier], ...]
    bonuses[3] → imperial UT:  [[id, multiplier], ...]
    bonuses[4] → team bonus:   [[id, multiplier], ...]

    Each civ bonus is implemented by allocating a civ-owned copy of the
    corresponding vanilla auto-fire tech(s) and applying the multiplier.
    Team bonuses go directly into the team_bonus effect as EC_ENABLE commands
    targeting the tech's own effect commands.
    """
    raw = civ_def.get("bonuses", [])
    if not raw:
        return

    # ── Civ bonuses (index 0) ─────────────────────────────────────────────────
    civ_bonuses = raw[0] if len(raw) > 0 and isinstance(raw[0], list) else []
    skipped = []
    applied = 0
    for entry in civ_bonuses:
        if not isinstance(entry, (list, tuple)) or len(entry) < 1:
            continue
        bonus_id   = int(entry[0])
        multiplier = int(entry[1]) if len(entry) > 1 else 1

        tech_ids = civ_bonus_techs(bonus_id)
        if not tech_ids:
            if _create_bonus_handler(dat, bonus_id, civ_index, multiplier):
                applied += 1
            else:
                skipped.append(bonus_id)
            continue

        for tech_id in tech_ids:
            new_tid = _allocate_tech(dat, tech_id, civ_index)
            if new_tid < 0:
                continue
            # Strip EC_ENABLE and EC_UPGRADE: those enable specific foreign units/
            # buildings (e.g. Caravanserai via bonus 55, Flemish Militia via 108).
            eff_id = dat.techs[new_tid].effect_id
            if 0 <= eff_id < len(dat.effects):
                dat.effects[eff_id].effect_commands = [
                    ec for ec in dat.effects[eff_id].effect_commands
                    if ec.type not in (EC_ENABLE, EC_UPGRADE)
                ]
            _multiply_effect(dat, eff_id, multiplier)
            applied += 1

    print(f"       Bonuses: {applied} techs applied, "
          f"{len(skipped)} bonus IDs skipped (not in catalog): {skipped[:8]}"
          + ("…" if len(skipped) > 8 else ""))

    # ── Team bonus (index 4) ──────────────────────────────────────────────────
    team_entries = raw[4] if len(raw) > 4 and isinstance(raw[4], list) else []
    team_applied = 0
    for entry in team_entries:
        if not isinstance(entry, (list, tuple)) or len(entry) < 1:
            continue
        tb_id      = int(entry[0])
        multiplier = int(entry[1]) if len(entry) > 1 else 1

        src_tech_id = team_bonus_tech(tb_id)
        if src_tech_id is None:
            continue

        # Copy the effect commands from the vanilla tech into the team bonus effect.
        # Filter EC_ENABLE/EC_UPGRADE only when the source tech is civ-specific (civ≥0):
        # those techs bundle civ-UU enables (e.g. tech 399 civ=11 enables Berserk) that
        # must not leak to other civs.  Global techs (civ=-1) are safe to copy whole —
        # their EC_ENABLE IS the intended bonus (e.g. tech 601 civ=-1 enables Genitour).
        src_eid = dat.techs[src_tech_id].effect_id
        if src_eid < 0 or src_eid >= len(dat.effects):
            continue
        src_civ = dat.techs[src_tech_id].civ
        if src_civ >= 0:
            safe_cmds = [ec for ec in dat.effects[src_eid].effect_commands
                         if ec.type not in (EC_ENABLE, EC_UPGRADE)]
        else:
            safe_cmds = list(dat.effects[src_eid].effect_commands)
        if not safe_cmds:
            continue
        for ec in safe_cmds:
            for _ in range(multiplier):
                dat.effects[tb_eff_id].effect_commands.append(deepcopy(ec))
        team_applied += 1

    print(f"       Team bonus: {team_applied}/{len(team_entries)} entries applied")


def _apply_km_uu(dat: DatFile, civ_index: int, km_uu_index: int) -> None:
    """Allocate make-avail + elite upgrade techs for a vanilla KM UU index."""
    pair = _KM_UU_TECHS.get(km_uu_index)
    if pair is None:
        return
    make_avail_id, elite_id = pair
    _allocate_tech(dat, make_avail_id, civ_index)
    _allocate_tech(dat, elite_id, civ_index)
    print(f"       KM UU index {km_uu_index}: allocated make-avail={make_avail_id}, elite={elite_id}")


def _assign_language(dat: DatFile, civ_index: int, language_value: int) -> None:
    """Remap DAT sound items from the chosen vanilla civ to civ_index.

    language_value is the 0-based KM civ index (0 = Britons, 1 = Franks, …).
    Maps to DAT civ index = language_value + 1 (civ 0 is Gaia).
    """
    src_civ = language_value + 1
    for sound in dat.sounds:
        new_items = [deepcopy(item) for item in sound.items
                     if item.civilization == src_civ]
        for item in new_items:
            item.civilization = civ_index
        sound.items = [item for item in sound.items
                       if item.civilization != civ_index]
        sound.items.extend(new_items)


# ── Main entry point ──────────────────────────────────────────────────────────

def apply_civ(dat: DatFile, civ_def: dict, target_slot: int | None = None) -> int:
    """
    Apply a custom civ to dat.  Returns the civ's index.

    target_slot — if given, overwrite that civ slot (keeps total count stable).
                  If None, append a new slot (may fail if already at engine limit).

    civ_def follows the KM JSON schema:
        alias, architecture, wonder, castle, language,
        tree (units/buildings/techs arrays),
        bonuses, unique_unit (Phase 2 additions).
    """
    overwrite = target_slot is not None
    civ_index = target_slot if overwrite else len(dat.civs)

    if not overwrite and civ_index >= MAX_TOTAL_CIVS:
        raise ValueError(
            f"Cannot exceed {MAX_TOTAL_CIVS} total civs — "
            f"already at {civ_index}. Use --replace to overwrite a vanilla civ slot."
        )

    alias = civ_def.get("alias", f"Custom Civ {civ_index}")
    mode  = "Overwriting" if overwrite else "Appending"
    print(f"  [{civ_index}] {mode} civ: {alias!r}")

    # 0. When overwriting, neutralize existing civ-specific techs for this slot
    #    so they don't bleed into the new civ (ghost Castle buttons, old bonuses).
    has_custom_uu = civ_def.get("unique_unit", {}).get("base_unit_id") is not None

    # Detect KM vanilla UU from bonuses[1][0].  Vanilla indices (0-38, 78-87) are
    # fully supported; KM-custom indices (39-77, 88+) fall back to vanilla UU preserve.
    _bonuses_raw_pre = civ_def.get("bonuses", [])
    _uu_ref = (_bonuses_raw_pre[1]
               if len(_bonuses_raw_pre) > 1 and isinstance(_bonuses_raw_pre[1], list)
               else [])
    km_uu_index = _uu_ref[0] if _uu_ref and isinstance(_uu_ref[0], int) else None
    km_uu_is_vanilla = km_uu_index is not None and km_uu_index in _KM_UU_TECHS

    # For nullification: treat a recognised vanilla KM UU the same as a custom UU —
    # don't preserve the original civ's UU techs (the desired UU will be allocated later).
    suppress_preserve = has_custom_uu or km_uu_is_vanilla

    if overwrite:
        # When no UU is being set, preserve the vanilla UU make-avail techs,
        # their elite upgrade techs, AND any civ-specific prerequisite techs in
        # that chain (e.g. an effect-less gate tech that the elite upgrade requires).
        preserve_indices: set[int] = set()
        if not suppress_preserve:
            vanilla_uu_ids: set[int] = set()
            for i, t in enumerate(dat.techs):
                if t.civ != civ_index:
                    continue
                eid = t.effect_id
                if 0 <= eid < len(dat.effects):
                    for ec in dat.effects[eid].effect_commands:
                        if ec.type == EC_ENABLE and ec.b == 1:
                            vanilla_uu_ids.add(ec.a)
                            preserve_indices.add(i)

            for i, t in enumerate(dat.techs):
                if t.civ != civ_index:
                    continue
                eid = t.effect_id
                if 0 <= eid < len(dat.effects):
                    cmds = dat.effects[eid].effect_commands
                    if any(ec.type == EC_UPGRADE and ec.a in vanilla_uu_ids
                           for ec in cmds):
                        preserve_indices.add(i)

            # Follow prerequisite chains: if a preserved tech requires another
            # civ-specific tech, preserve that one too (even if it has no effect).
            changed = True
            while changed:
                changed = False
                for i in list(preserve_indices):
                    for req_id in dat.techs[i].required_techs:
                        if req_id < 0 or req_id >= len(dat.techs):
                            continue
                        if dat.techs[req_id].civ == civ_index and req_id not in preserve_indices:
                            preserve_indices.add(req_id)
                            changed = True

        n_nullified = 0
        for i, t in enumerate(dat.techs):
            if t.civ != civ_index:
                continue
            if i in preserve_indices:
                continue
            t.civ = 99  # civ 99 never exists → tech silently never fires
            n_nullified += 1
        print(f"       Nullified {n_nullified} existing civ={civ_index} techs")

    # 1. Clone from civ 1 (first playable vanilla civ — full standard unit set).
    new_civ = deepcopy(dat.civs[1])
    new_civ.name     = alias
    new_civ.icon_set = civ_def.get("architecture", 1)

    # Castle graphic: copy units[82] from the chosen source civ (0-indexed KM value → DAT civ N+1).
    castle_src = civ_def.get("castle", 0) + 1
    if castle_src != 1 and castle_src < len(dat.civs):
        src_units = dat.civs[castle_src].units
        if len(src_units) > 82 and src_units[82] is not None:
            new_civ.units[82] = deepcopy(src_units[82])

    # Wonder graphic: copy units[276] from the chosen source civ.
    wonder_src = civ_def.get("wonder", 0) + 1
    if wonder_src != 1 and wonder_src < len(dat.civs):
        src_units = dat.civs[wonder_src].units
        if len(src_units) > 276 and src_units[276] is not None:
            new_civ.units[276] = deepcopy(src_units[276])

    if overwrite:
        dat.civs[civ_index] = new_civ
    else:
        dat.civs.append(new_civ)

    # Snapshot the unit count before we append UU slots so _apply_tree_wiring
    # can skip our custom units (they're managed by the elite upgrade tech, not tree[]).
    base_unit_count = len(dat.civs[0].units)

    # 2. Append UU and Elite UU to every civ (unit arrays must stay same length).
    #    Skip entirely when unique_unit has no base_unit_id (avoids Militia clone).
    uu_id, elite_uu_id = -1, -1
    if civ_def.get("unique_unit", {}).get("base_unit_id") is not None:
        uu_id, elite_uu_id = _append_unique_units(dat, civ_index, civ_def)
        print(f"       UU: {uu_id}  Elite UU: {elite_uu_id}")
    else:
        print("       UU: skipped (no base_unit_id)")

    # 3. Elite upgrade tech (Castle, btn10).
    if uu_id >= 0 and elite_uu_id >= 0:
        _append_elite_upgrade_tech(dat, civ_index, alias, uu_id, elite_uu_id)

    # 4. Castle UT and Imperial UT — from bonuses[2] and bonuses[3].
    _bonuses_raw       = civ_def.get("bonuses", [])
    castle_ut_entries  = (_bonuses_raw[2]
                          if len(_bonuses_raw) > 2 and isinstance(_bonuses_raw[2], list)
                          else [])
    imperial_ut_entries = (_bonuses_raw[3]
                           if len(_bonuses_raw) > 3 and isinstance(_bonuses_raw[3], list)
                           else [])
    if castle_ut_entries or imperial_ut_entries:
        _append_unique_tech_stubs(dat, civ_index, alias,
                                  castle_ut_entries, imperial_ut_entries)

    # 5. Team bonus and tech tree effects.
    # tech_tree_id and team_bonus_id are EFFECT indices (not tech indices).
    # Vanilla civs point these directly at entries in dat.effects.
    tb_eff_id = _append_effect(dat, Effect(name=f"{alias} Team Bonus", effect_commands=[]))
    tt_eff_id = _append_effect(dat, Effect(name=f"{alias} Tech Tree",  effect_commands=[]))

    new_civ.team_bonus_id = tb_eff_id
    new_civ.tech_tree_id  = tt_eff_id

    # 6. Apply tech tree wiring: set unit.enabled based on tree[0]/tree[1].
    if "tree" in civ_def:
        _apply_tree_wiring(dat, civ_index, civ_def, base_unit_count)

    # 6b. KM vanilla UU: allocate make-avail + elite techs AFTER tree wiring so
    #     the freshly-appended techs aren't in all_disableable and won't be disabled.
    if km_uu_is_vanilla:
        _apply_km_uu(dat, civ_index, km_uu_index)
    elif km_uu_index is not None:
        print(f"       WARNING: KM UU index {km_uu_index} is a KM-custom unit "
              f"— not supported in standalone builder; vanilla UU preserved")

    # 7. Apply bonuses from catalog.
    if "bonuses" in civ_def:
        _apply_bonuses(dat, civ_index, civ_def, tb_eff_id)

    # 8. Assign language audio: remap sound items from source civ → civ_index.
    lang_val = civ_def.get("language", 0)
    _assign_language(dat, civ_index, lang_val)

    print(f"       tech_tree_id(eff)={tt_eff_id}  team_bonus_id(eff)={tb_eff_id}")
    return civ_index


# Keep old name as alias for backwards compatibility.
def append_civ(dat: DatFile, civ_def: dict) -> int:
    return apply_civ(dat, civ_def, target_slot=None)


# ── Unique unit helpers ───────────────────────────────────────────────────────

def _append_unique_units(dat: DatFile, civ_index: int, civ_def: dict) -> tuple[int, int]:
    """Append base UU and elite UU to all civs. Returns (uu_id, elite_uu_id)."""
    uu_id       = _append_one_unit(dat, civ_index, civ_def, elite=False)
    elite_uu_id = _append_one_unit(dat, civ_index, civ_def, elite=True)
    return uu_id, elite_uu_id


def _append_one_unit(dat: DatFile, civ_index: int, civ_def: dict, elite: bool) -> int:
    """
    Deep-copy a base unit, apply stat overrides for the custom civ, and
    append the clone to every civ's unit list + unit_headers.
    Returns the new unit ID.
    """
    uu_def  = civ_def.get("unique_unit", {})
    base_id = uu_def.get("base_unit_id", 74)  # 74 = Militia fallback
    stats   = uu_def.get("stats", {})
    alias   = civ_def.get("alias", "Custom")
    label   = ("Elite " if elite else "") + uu_def.get("name", f"{alias} Warrior")

    base_template = dat.civs[0].units[base_id]
    if base_template is None:
        raise ValueError(f"base_unit_id {base_id} is None in civ 0 — choose a different base.")

    new_id = len(dat.civs[0].units)

    for civ_idx, civ in enumerate(dat.civs):
        source = civ.units[base_id] or base_template
        u = deepcopy(source)
        u.id      = new_id
        # Base UU enabled only for the custom civ; elite starts disabled everywhere
        # (enabled by the elite upgrade tech at runtime).
        u.enabled = 1 if (civ_idx == civ_index and not elite) else 0

        if civ_idx == civ_index:
            _apply_uu_stats(u, stats, elite, civ_def)

        civ.units.append(u)

    # Unit header is required for task scheduling — clone from base unit's header.
    src_hdr = dat.unit_headers[base_id] if base_id < len(dat.unit_headers) else None
    dat.unit_headers.append(deepcopy(src_hdr) if src_hdr else UnitHeaders(exists=0))

    return new_id


def _apply_uu_stats(u, stats: dict, elite: bool, civ_def: dict) -> None:
    """Apply stat overrides from civ_def to the unit object in place."""
    alias = civ_def.get("alias", "Custom")
    uu_def = civ_def.get("unique_unit", {})

    # Stat scaling for elite: +20% HP, +2 attack over base as a simple default.
    hp_bonus     = 20 if elite else 0
    attack_bonus =  2 if elite else 0

    if "hp" in stats:
        u.hit_points = stats["hp"] + hp_bonus
    if "speed" in stats:
        u.speed = stats["speed"]

    if u.type_50:
        if "attack" in stats:
            for atk in u.type_50.attacks:
                if atk.class_ == 4:  # melee damage class
                    atk.amount = stats["attack"] + attack_bonus
            u.type_50.displayed_attack = stats["attack"] + attack_bonus
        if "melee_armor" in stats:
            for arm in u.type_50.armours:
                if arm.class_ == 4:
                    arm.amount = stats["melee_armor"]
            u.type_50.displayed_melee_armour = stats["melee_armor"]
        if "pierce_armor" in stats:
            for arm in u.type_50.armours:
                if arm.class_ == 3:
                    arm.amount = stats["pierce_armor"]
        if "range" in stats:
            u.type_50.max_range = stats["range"]

    if u.creatable:
        if "cost" in stats:
            _apply_unit_costs(u.creatable.resource_costs, stats["cost"])
        if "train_time" in stats and u.creatable.train_locations:
            u.creatable.train_locations[0].train_time = stats["train_time"]
        # Wire to Castle btn1 (Q hotkey)
        if u.creatable.train_locations:
            tl = u.creatable.train_locations[0]
            tl.unit_id   = BUILDING_CASTLE
            tl.button_id = 1
            tl.hot_key_id = 16101


def _apply_unit_costs(resource_costs, cost_dict: dict) -> None:
    """Overwrite resource_costs with values from cost_dict (food/wood/stone/gold)."""
    RES = {"food": 0, "wood": 1, "stone": 2, "gold": 3}
    for rc in resource_costs:
        rc.type = -1; rc.amount = 0; rc.flag = 0
    slot = 0
    for key, res_type in RES.items():
        amount = cost_dict.get(key, 0)
        if amount > 0 and slot < len(resource_costs):
            resource_costs[slot].type   = res_type
            resource_costs[slot].amount = amount
            resource_costs[slot].flag   = 1
            slot += 1


# ── Tech helpers ──────────────────────────────────────────────────────────────

def _append_elite_upgrade_tech(dat: DatFile, civ_index: int, alias: str,
                                uu_id: int, elite_uu_id: int) -> None:
    """Elite upgrade at Castle btn10, requires Castle Age (102)."""
    eff = Effect(
        name=f"{alias} Elite Upgrade Effect",
        effect_commands=[
            EffectCommand(type=EC_ENABLE,  a=elite_uu_id, b=1,          c=-1, d=0.0),
            EffectCommand(type=EC_UPGRADE, a=uu_id,       b=elite_uu_id, c=-1, d=0.0),
        ],
    )
    eff_id = _append_effect(dat, eff)
    _append_tech(dat, _make_tech(
        name=f"Elite {alias} Upgrade",
        effect_id=eff_id,
        civ_index=civ_index,
        age_req=102,
        location=BUILDING_CASTLE,
        button=10,
        research_time=40,
        icon_id=105,
    ))


def _build_ut_effect_cmds(dat: DatFile, entries: list, label: str) -> list:
    """Collect effect commands from catalog for a UT's bonus entries."""
    cmds = []
    for entry in entries:
        if not isinstance(entry, (list, tuple)) or len(entry) < 1:
            continue
        bonus_id   = int(entry[0])
        multiplier = int(entry[1]) if len(entry) > 1 else 1
        tech_ids = civ_bonus_techs(bonus_id)
        if not tech_ids:
            print(f"       {label} bonus {bonus_id}: not in catalog — skipped")
            continue
        for tech_id in tech_ids:
            if tech_id < 0 or tech_id >= len(dat.techs):
                continue
            eid = dat.techs[tech_id].effect_id
            if eid < 0 or eid >= len(dat.effects):
                continue
            src = [ec for ec in dat.effects[eid].effect_commands
                   if ec.type not in (EC_ENABLE, EC_UPGRADE)]
            for ec in src:
                for _ in range(multiplier):
                    cmds.append(deepcopy(ec))
    return cmds


def _append_unique_tech_stubs(dat: DatFile, civ_index: int, alias: str,
                               castle_ut_entries: list,
                               imperial_ut_entries: list) -> None:
    """Create Castle UT (btn9) and Imperial UT (btn15) from bonus catalog entries."""
    # Default costs: Castle UT = 300 food + 300 gold; Imperial UT = 450 food + 225 stone
    ut_configs = [
        (7,  "Castle UT",   102, castle_ut_entries,   300, 3, 300),
        (8,  "Imperial UT", 103, imperial_ut_entries, 450, 2, 225),
    ]
    for btn, label, age_req, entries, cost_food, cost_b_type, cost_b in ut_configs:
        if not entries:
            continue
        cmds = _build_ut_effect_cmds(dat, entries, label)
        eff_id = _append_effect(dat, Effect(name=f"{alias} {label}", effect_commands=cmds))
        tech = _make_tech(
            name=f"{alias} {label}",
            effect_id=eff_id,
            civ_index=civ_index,
            age_req=age_req,
            location=BUILDING_CASTLE,
            button=btn,
            research_time=60,
        )
        # Apply costs (food + gold for castle UT; food + stone for imperial UT).
        tech.resource_costs = (
            ResearchResourceCost(type=0, amount=cost_food, flag=1),
            ResearchResourceCost(type=cost_b_type, amount=cost_b, flag=1),
            ResearchResourceCost(type=-1, amount=0, flag=0),
        )
        _append_tech(dat, tech)
        print(f"       {label}: {len(cmds)} effect commands")
