"""
civ_appender.py — Append or overwrite a civilization in an AoE2 DE DatFile.
"""

from copy import deepcopy

from genieutils.datfile import DatFile
from genieutils.civ import Civ
from genieutils.effect import Effect, EffectCommand
from genieutils.tech import Tech, ResearchLocation, ResearchResourceCost
from genieutils.unitheaders import UnitHeaders

from bonus_catalog import civ_bonus_techs, team_bonus_tech, civ_bonus_ec_list

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

# Display names for KM UU indices. Vanilla indices (0-38, 78-87) are creatable
# units in our pipeline. KM-custom indices (39-77, 88+) are not creatable here,
# but we still surface their names for the civ-picker description block.
# Mirrors the full `uniqueNames` table in Fritz's process_mod/modStrings.js.
_KM_UU_NAMES: dict[int, str] = {
    0:  "Longbowman",
    1:  "Throwing Axeman",
    2:  "Huskarl",
    3:  "Teutonic Knight",
    4:  "Samurai",
    5:  "Chu Ko Nu",
    6:  "Cataphract",
    7:  "Mameluke",
    8:  "War Elephant",
    9:  "Janissary",
    10: "Berserk",
    11: "Mangudai",
    12: "Woad Raider",
    13: "Conquistador",
    14: "Jaguar Warrior",
    15: "Plumed Archer",
    16: "Tarkan",
    17: "War Wagon",
    18: "Genoese Crossbowman",
    19: "Ghulam",
    20: "Kamayuk",
    21: "Magyar Huszar",
    22: "Boyar",
    23: "Organ Gun",
    24: "Shotel Warrior",
    25: "Gbeto",
    26: "Camel Archer",
    27: "Ballista Elephant",
    28: "Karambit Warrior",
    29: "Arambai",
    30: "Rattan Archer",
    31: "Konnik",
    32: "Keshik",
    33: "Kipchak",
    34: "Leitis",
    35: "Coustillier",
    36: "Serjeant",
    37: "Obuch",
    38: "Hussite Wagon",
    39: "Crusader Knight",
    40: "Xolotl Warrior",
    41: "Saboteur",
    42: "Ninja",
    43: "Flamethrower",
    44: "Photonman",
    45: "Centurion",
    46: "Apukispay",
    47: "Monkey Boy",
    48: "Amazon Warrior",
    49: "Amazon Archer",
    50: "Iroquois Warrior",
    51: "Varangian Guard",
    52: "Gendarme",
    53: "Cuahchiqueh",
    54: "Ritterbruder",
    55: "Kazak",
    56: "Szlachcic",
    57: "Cuirassier",
    58: "Rajput",
    59: "Seljuk Archer",
    60: "Numidian Javelinman",
    61: "Sosso Guard",
    62: "Swiss Pikeman",
    63: "Headhunter",
    64: "Teulu",
    65: "Maillotin",
    66: "Hashashin",
    67: "Highlander",
    68: "Stradiot",
    69: "Ahosi",
    70: "Landsknecht",
    71: "Clibinarii",
    72: "Silahtar",
    73: "Jaridah",
    74: "Wolf Warrior",
    75: "Warrior Monk",
    76: "Castellan",
    77: "Wind Warrior",
    78: "Chakram Thrower",
    79: "Urumi Swordsman",
    80: "Ratha",
    81: "Composite Bowman",
    82: "Monaspa",
    83: "White Feather Guard",
    84: "Fire Archer",
    85: "Tiger Cavalry",
    86: "Iron Pagoda",
    87: "Liao Dao",
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

# UT name strings live in their own high-range block so the engine treats them as
# brand-new strings rather than overrides of vanilla 7xxx tech names. Overriding
# vanilla IDs works for the "research complete" toast but NOT for the in-game
# Castle UT button label — confirmed in-game by comparing our mod (which reused
# vanilla 7419 for Britons' Yeomen slot and showed "Yeomen" on the button) to
# NapKingCole's Unhinged Empires mod (which uses 79xxx-range IDs and shows the
# correct UT name). Avoid 79000–79999 — that's the range NapKingCole uses, so
# this offset keeps us conflict-free if both mods ever load together.
STR_UT_BASE       = 75000
STR_UT_PER_CIV    = 10  # 0=Castle UT, 1=Imperial UT, remaining slots reserved

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
               lang_help: int = -1, lang_tech_tree: int = -1,
               hot_key_id: int = -1) -> Tech:
    """Construct a Tech with sensible defaults."""
    req = (age_req, -1, -1, -1, -1, -1) if age_req != -1 else (-1, -1, -1, -1, -1, -1)
    if location != -1:
        locations = [ResearchLocation(
            location_id=location,
            research_time=research_time,
            button_id=button,
            hot_key_id=hot_key_id,
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
        language_dll_tech_tree=lang_tech_tree,
        name=name,
        repeatable=0,
        research_locations=locations,
    )


# ── Tech tree wiring ─────────────────────────────────────────────────────────

def _apply_tree_wiring(dat: DatFile, civ_index: int, civ_def: dict,
                       base_unit_count: int) -> None:
    """
    Populate the civ's tech_tree effect (indexed by tech_tree_id, which is an
    EFFECT index) with two kinds of commands:

    1. EC type=8 'unlock tech' — for make-avail techs that the game locks by
       default and each civ must explicitly enable (e.g. Battle Elephant tech
       630, Elephant Archer tech 480).  These techs are NOT in any civ's
       type=102 disable list; instead every civ that wants them adds a type=8
       command to its TT effect.  Without this, the units never appear in
       training buildings even if the unit is "enabled" by a global tech.

    2. EC type=102 'disable tech' — for all unit-line / upgrade techs NOT in
       the civ's tree specification.

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

    # ── Step 0: Build EC type=8 'unlock' map from all civ TT effects.
    # ec8_info[tech_id] = (a, b, c, d) template for the type=8 command.
    # ec8_unit_techs[unit_id] = [tech_ids] that need type=8 to unlock and
    # whose effect enables or upgrades to unit_id.
    ec8_info: dict[int, tuple[int, int, int, float]] = {}
    for civ in dat.civs:
        tti = civ.tech_tree_id
        if 0 <= tti < len(dat.effects):
            for c in dat.effects[tti].effect_commands:
                if c.type == 8:
                    tid = int(c.a)
                    if tid not in ec8_info:
                        ec8_info[tid] = (int(c.a), int(c.b), int(c.c), c.d)
    ec8_unit_techs: dict[int, list[int]] = {}
    for tech_id, _ in ec8_info.items():
        if tech_id >= len(dat.techs):
            continue
        eid = dat.techs[tech_id].effect_id
        if eid < 0 or eid >= len(dat.effects):
            continue
        for c in dat.effects[eid].effect_commands:
            if c.type == 2 and int(c.b) == 1:   # EC_ENABLE
                ec8_unit_techs.setdefault(int(c.a), []).append(tech_id)
            elif c.type == 3:                     # EC_UPGRADE → to unit b
                ec8_unit_techs.setdefault(int(c.b), []).append(tech_id)

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

    # ── Step 3b: Collect EC type=8 unlocks needed for tree units.
    ec8_to_add: set[int] = set()
    for uid in tree_units | tree_buildings:
        for tech_id in ec8_unit_techs.get(uid, []):
            ec8_to_add.add(tech_id)

    # ── Step 3c: Mutual exclusions.
    # Armored Elephants replace the ram-line for Indian civs — disable rams when present.
    _ARMORED_ELEPHANT_MAKE_AVAIL = 837
    _RAM_TECHS = {162, 712}  # Bat Ram (make avail), Upgrade Rams
    if _ARMORED_ELEPHANT_MAKE_AVAIL in keep_enabled:
        keep_enabled -= _RAM_TECHS

    # ── Step 4: Write type=8 unlock + type=102 disable commands into TT effect.
    to_disable = all_disableable - keep_enabled
    tt_eff_id  = dat.civs[civ_index].tech_tree_id
    ec8_cmds = [
        EffectCommand(type=8, a=ec8_info[tid][0], b=ec8_info[tid][1],
                      c=ec8_info[tid][2], d=ec8_info[tid][3])
        for tid in sorted(ec8_to_add)
    ]
    dat.effects[tt_eff_id].effect_commands = ec8_cmds + [
        EffectCommand(type=102, a=-1, b=-1, c=-1, d=float(tid))
        for tid in sorted(to_disable)
    ]
    n_unlocked = len(ec8_cmds)
    print(f"       Tech tree: {len(to_disable)} techs disabled, "
          f"{len(keep_enabled & all_disableable)} unit-line techs kept"
          + (f", {n_unlocked} type=8 unlocks" if n_unlocked else ""))


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


def _apply_ec_list_entry(dat: DatFile, civ_index: int, ec_entry: dict,
                         multiplier: int = 1) -> None:
    """Create a civ-owned auto-fire tech+effect from one ec_list catalog entry.

    ec_entry format:
      {"requires": [tech_id, ...], "ecs": [{"type": T, "A": A, "B": B, "C": C, "D": D}, ...]}
    """
    requires: list[int] = ec_entry.get("requires", [])
    ecs_dicts: list[dict] = ec_entry.get("ecs", [])
    if not ecs_dicts:
        return

    cmds = [EffectCommand(type=d["type"], a=d["A"], b=d["B"], c=d["C"], d=d["D"])
            for d in ecs_dicts]
    # Multiplier: repeat all commands multiplier times total
    if multiplier > 1:
        orig = list(cmds)
        for _ in range(multiplier - 1):
            cmds.extend(deepcopy(cmd) for cmd in orig)

    eff = Effect(name="C-Bonus EC-list", effect_commands=cmds)
    dat.effects.append(eff)
    eff_id = len(dat.effects) - 1

    # Build 6-slot required_techs tuple
    n = min(len(requires), 6)
    req_tuple = tuple(requires[:n]) + (-1,) * (6 - n)

    tech = Tech(
        required_techs=req_tuple,
        resource_costs=_zero_costs(),
        required_tech_count=n,
        civ=civ_index,
        full_tech_mode=0,
        language_dll_name=-1,
        language_dll_description=-1,
        effect_id=eff_id,
        type=0,
        icon_id=-1,
        language_dll_help=-1,
        language_dll_tech_tree=-1,
        name="C-Bonus EC-list",
        repeatable=0,
        research_locations=[ResearchLocation(location_id=-1, research_time=0,
                                             button_id=0, hot_key_id=-1)],
    )
    dat.techs.append(tech)


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

# Foot archer unit IDs (unitClasses["footArcher"] from KM civbuilder.cpp line 130)
_FOOT_ARCHER_UNITS = [
    4, 8, 24, 73, 185, 492, 530, 559,      # Archer line + Longbow/ChuKoNu/Crossbow/Slinger/Arbalest variants
    763, 765, 866, 868, 1129, 1131,         # Plumed, Genoese, Rattan (base + elite)
    1800, 1802, 1968, 1970,                 # Composite Bowman, Fire Archer (base + elite)
]
_SKIRMISHER_UNITS = [6, 7, 1155]   # Skirmisher, Elite Skirmisher, Imperial Skirmisher

# Feudal Knight unit ID (reuses Ekeshik slot 1262 per KM convention)
_FEUDAL_KNIGHT  = 1262
_KNIGHT         = 38

# Farm unit IDs and their variants (for 2×2 farm resizing)
_FARM_UNITS = [50, 357, 1187, 1188, 1193, 1194, 1195]


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


def _siege_workshop_tech_ids(dat: DatFile) -> list[int]:
    """Return IDs of all techs whose primary research location is the Siege Workshop."""
    BUILDING_SIEGE_WORKSHOP = 49
    out = []
    for i, t in enumerate(dat.techs):
        locs = getattr(t, 'research_locations', [])
        if locs and locs[0].location_id == BUILDING_SIEGE_WORKSHOP:
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

    if bonus_id == 137:          # -50% food cost on Blacksmith + Siege Workshop techs
        factor = 0.5 ** mult
        tids = _blacksmith_tech_ids(dat) + _siege_workshop_tech_ids(dat)
        cmds = [
            EffectCommand(type=EC_TECH_COST, a=tid, b=0, c=0, d=rc.amount * factor)
            for tid in tids
            for rc in dat.techs[tid].resource_costs
            if rc.flag == 1 and rc.type == 0
        ]
        if cmds:
            _add_auto_fire_tech(dat, civ_index, cmds,
                                name="C-Bonus, -50% food blacksmith+siege techs")
        return True

    if bonus_id == 138:          # -50% cost on all Stable techs
        factor = 0.5 ** mult
        cmds = [
            EffectCommand(type=EC_TECH_COST, a=tid, b=rc.type, c=0, d=rc.amount * factor)
            for tid in _stable_tech_ids(dat)
            for rc in dat.techs[tid].resource_costs
            if rc.flag == 1
        ]
        if cmds:
            _add_auto_fire_tech(dat, civ_index, cmds,
                                name="C-Bonus, -50% cost stable techs")
        return True

    # ── Cavalier in Castle Age ────────────────────────────────────────────────
    if bonus_id == 103:          # Cavalier upgrade available in Castle Age
        _TECH_CAVALIER = 209
        _KNIGHT_MAKE_AVAIL = 166   # "Knight (make avail)" — fires at Castle Age
        src = dat.techs[_TECH_CAVALIER]
        new_tech = deepcopy(src)
        new_tech.civ = civ_index
        # Require Castle Age (102) + Knight make-avail (166), count=2.
        # Since 166 fires automatically when Castle Age is reached, Cavalier
        # becomes researchable the moment the civ enters Castle Age.
        new_tech.required_techs = (102, _KNIGHT_MAKE_AVAIL, -1, -1, -1, -1)
        new_tech.required_tech_count = 2
        eid = src.effect_id
        if 0 <= eid < len(dat.effects):
            new_eff = deepcopy(dat.effects[eid])
            dat.effects.append(new_eff)
            new_tech.effect_id = len(dat.effects) - 1
        dat.techs.append(new_tech)
        # Disable the global Cavalier tech (209) for this civ so it doesn't
        # reappear as a duplicate button in Imperial Age.
        tt_eff_id = dat.civs[civ_index].tech_tree_id
        dat.effects[tt_eff_id].effect_commands.append(
            EffectCommand(type=102, a=-1, b=-1, c=-1, d=float(_TECH_CAVALIER))
        )
        return True

    # ── Archer cost reductions ────────────────────────────────────────────────
    if bonus_id == 133:          # Foot archers and skirmishers cost -10/20/30%
        # Three compounding multipliers applied per age advance.
        # 0.9 × 0.889 × 0.875 ≈ 0.7  (i.e. -30% total in Imperial Age)
        all_units = _FOOT_ARCHER_UNITS + _SKIRMISHER_UNITS
        for age_req, factor in [(101, 0.9 ** mult), (102, 0.889 ** mult), (103, 0.875 ** mult)]:
            cmds = [EffectCommand(type=EC_MULTIPLY, a=uid, b=-1, c=100, d=factor)
                    for uid in all_units]
            _add_auto_fire_tech(dat, civ_index, cmds, age_req=age_req,
                                name=f"C-Bonus, foot archers+skirms cost -{10 + (age_req - 101) * 10}%")
        return True

    # ── 2×2 Farms ─────────────────────────────────────────────────────────────
    if bonus_id == 330:          # Farms are 2×2 instead of 3×3 tile footprint
        # Directly resize this civ's farm units from clearance 1.5 (3×3 tiles)
        # to 1.0 (2×2 tiles). Affects collision, clearance, and outline sizes.
        for uid in _FARM_UNITS:
            if uid >= len(dat.civs[civ_index].units):
                continue
            u = dat.civs[civ_index].units[uid]
            if u is None:
                continue
            if abs(u.collision_size_x - 1.5) < 0.01:
                u.collision_size_x = 1.0
            if abs(u.collision_size_y - 1.5) < 0.01:
                u.collision_size_y = 1.0
            cx, cy = u.clearance_size
            u.clearance_size = (
                1.0 if abs(cx - 1.5) < 0.01 else cx,
                1.0 if abs(cy - 1.5) < 0.01 else cy,
            )
            if abs(u.outline_size_x - 1.5) < 0.01:
                u.outline_size_x = 1.0
            if abs(u.outline_size_y - 1.5) < 0.01:
                u.outline_size_y = 1.0
        return True

    # ── Feudal Age Knights ────────────────────────────────────────────────────
    if bonus_id == 332:          # Knights available in Feudal Age (30HP version → upgrades to Knight)
        # Step 0: copy Knight (38) data into unit slot 1262 for this civ.
        # Slot 1262 is vanilla "Ekeshik" which has train_location.unit_id=-1 so it
        # can't be trained from anywhere. Copying Knight data gives it the Stable
        # train location (btn 2) and correct graphics, then we reduce the stats.
        knight = dat.civs[civ_index].units[_KNIGHT]
        if knight is not None and _FEUDAL_KNIGHT < len(dat.civs[civ_index].units):
            feudal_knight = deepcopy(knight)
            feudal_knight.id        = _FEUDAL_KNIGHT
            feudal_knight.enabled   = 0    # starts hidden; EC_ENABLE fires at Feudal Age
            feudal_knight.hit_points = 30
            feudal_knight.speed      = 1.25
            feudal_knight.line_of_sight = 3.0
            if feudal_knight.bird is not None:
                feudal_knight.bird.search_radius = 3.0
            if feudal_knight.creatable and feudal_knight.creatable.train_locations:
                feudal_knight.creatable.train_locations[0].train_time = 45
            dat.civs[civ_index].units[_FEUDAL_KNIGHT] = feudal_knight

        # Tech 1: make Feudal Knight available at Feudal Age
        avail_cmds = [EffectCommand(type=EC_ENABLE, a=_FEUDAL_KNIGHT, b=1, c=-1, d=0.0)]
        avail_eff = Effect(name="Feudal Knight (make avail)", effect_commands=avail_cmds)
        dat.effects.append(avail_eff)
        avail_tech = _make_tech("Feudal Knight (make avail)",
                                effect_id=len(dat.effects) - 1,
                                civ_index=civ_index,
                                age_req=101)  # fires at Feudal Age
        dat.techs.append(avail_tech)
        avail_tech_id = len(dat.techs) - 1

        # Tech 2: upgrade Feudal Knights → Knights when Castle Age is reached
        upgrade_cmds = [EffectCommand(type=EC_UPGRADE, a=_FEUDAL_KNIGHT, b=_KNIGHT, c=-1, d=0.0)]
        upgrade_eff = Effect(name="Feudal Knight → Knight (Castle Age)", effect_commands=upgrade_cmds)
        dat.effects.append(upgrade_eff)
        upgrade_tech = Tech(
            name="Feudal Knight → Knight (Castle Age)",
            required_techs=(102, avail_tech_id, -1, -1, -1, -1),
            required_tech_count=2,
            resource_costs=_zero_costs(),
            civ=civ_index,
            full_tech_mode=0,
            language_dll_name=-1,
            language_dll_description=-1,
            effect_id=len(dat.effects) - 1,
            type=0,
            icon_id=-1,
            language_dll_help=-1,
            language_dll_tech_tree=-1,
            repeatable=0,
            research_locations=[ResearchLocation(location_id=-1, research_time=0,
                                                 button_id=0, hot_key_id=-1)],
        )
        dat.techs.append(upgrade_tech)
        return True

    return False  # not handled


def _apply_bonuses(dat: DatFile, civ_index: int, civ_def: dict,
                   tb_eff_id: int) -> dict:
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
        if tech_ids:
            for tech_id in tech_ids:
                new_tid = _allocate_tech(dat, tech_id, civ_index)
                if new_tid < 0:
                    continue

                is_global = (new_tid == tech_id)
                eff_id = dat.techs[new_tid].effect_id

                if is_global:
                    # Global tech (civ=-1): never modify the shared effect.
                    # Build a stripped, multiplied copy as a new civ-specific tech.
                    if 0 <= eff_id < len(dat.effects):
                        src_cmds = [
                            ec for ec in dat.effects[eff_id].effect_commands
                            if ec.type not in (EC_ENABLE, EC_UPGRADE)
                        ]
                        # For multiplier=1 the global already fires for our civ;
                        # only add (multiplier-1) extra repetitions.
                        extra = []
                        for _ in range(max(0, multiplier - 1)):
                            extra.extend(deepcopy(ec) for ec in src_cmds)
                        if extra:
                            new_eff = Effect(name=f"C-Bonus extra {bonus_id}",
                                             effect_commands=extra)
                            dat.effects.append(new_eff)
                            extra_tech = deepcopy(dat.techs[tech_id])
                            extra_tech.civ = civ_index
                            extra_tech.effect_id = len(dat.effects) - 1
                            dat.techs.append(extra_tech)
                else:
                    # Civ-specific copy: keep all commands (EC_ENABLE and
                    # EC_UPGRADE must stay so upgrades/enables actually fire).
                    _multiply_effect(dat, eff_id, multiplier)
                applied += 1
            continue

        ec_entries = civ_bonus_ec_list(bonus_id)
        if ec_entries:
            for ec_entry in ec_entries:
                _apply_ec_list_entry(dat, civ_index, ec_entry, multiplier)
            applied += len(ec_entries)
            continue

        if _create_bonus_handler(dat, bonus_id, civ_index, multiplier):
            applied += 1
        else:
            skipped.append(bonus_id)

    print(f"       Bonuses: {applied} techs applied, "
          f"{len(skipped)} bonus IDs skipped (not in catalog): {skipped[:8]}"
          + ("…" if len(skipped) > 8 else ""))

    bonus_result = {"applied": applied, "skipped": skipped}

    # ── Team bonus (index 4) ──────────────────────────────────────────────────
    team_entries = raw[4] if len(raw) > 4 and isinstance(raw[4], list) else []
    team_applied = 0
    for entry in team_entries:
        if not isinstance(entry, (list, tuple)) or len(entry) < 1:
            continue
        tb_id      = int(entry[0])
        multiplier = int(entry[1]) if len(entry) > 1 else 1

        # catalog value is an effect index (not a tech index) — matches KM's C++:
        #   tbEffect.EffectCommands += df->Effects[teamBonuses[teamBonusIndex]]
        eff_idx = team_bonus_tech(tb_id)
        if eff_idx is None or not (0 <= eff_idx < len(dat.effects)):
            continue

        safe_cmds = list(dat.effects[eff_idx].effect_commands)
        if not safe_cmds:
            continue
        for ec in safe_cmds:
            for _ in range(multiplier):
                dat.effects[tb_eff_id].effect_commands.append(deepcopy(ec))
        team_applied += 1

    print(f"       Team bonus: {team_applied}/{len(team_entries)} entries applied")

    bonus_result["team_applied"] = team_applied
    bonus_result["team_total"]   = len(team_entries)
    return bonus_result


def _apply_km_uu(dat: DatFile, civ_index: int, km_uu_index: int) -> tuple[int, int]:
    """Allocate make-avail + elite upgrade techs for a vanilla KM UU index.

    Returns (new_make_avail_tech_id, new_elite_tech_id) — the DAT indices of
    the freshly allocated civ-specific copies. Both are -1 if the index is
    unknown. Pass these IDs to _patch_per_civ_techtree via civ_result so the
    CivTechTrees JSON Trigger Tech ID field can be updated correctly.
    """
    pair = _KM_UU_TECHS.get(km_uu_index)
    if pair is None:
        return -1, -1
    make_avail_id, elite_id = pair
    # Share _seen so the elite tech's required-tech pointer to make_avail
    # reuses the already-allocated copy instead of creating a duplicate.
    seen: dict[int, int] = {}
    new_ma = _allocate_tech(dat, make_avail_id, civ_index, seen)
    new_el = _allocate_tech(dat, elite_id,      civ_index, seen)
    print(f"       KM UU index {km_uu_index}: make-avail {make_avail_id}→{new_ma}, elite {elite_id}→{new_el}")
    return new_ma, new_el


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

def apply_civ(dat: DatFile, civ_def: dict, target_slot: int | None = None) -> dict:
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

    alias    = civ_def.get("alias", f"Custom Civ {civ_index}")
    warnings = []
    mode     = "Overwriting" if overwrite else "Appending"
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

    # Capture the original civ's UT tech IDs BEFORE nullification so the
    # CivTechTrees JSON patcher can find the vanilla Yeomen / Warwolf nodes
    # by Node ID and retarget them to our new tech IDs. The sids captured
    # here are no longer used for naming — UT name strings now live in a
    # fresh high-range (STR_UT_BASE), see _append_unique_tech_stubs.
    orig_castle_ut_sid: int | None = None
    orig_imp_ut_sid:    int | None = None
    orig_castle_ut_tech_id: int | None = None
    orig_imp_ut_tech_id:    int | None = None
    if overwrite:
        for ti, tech in enumerate(dat.techs):
            if tech.civ == civ_index:
                for loc in (tech.research_locations or []):
                    if loc.location_id == BUILDING_CASTLE:
                        if loc.button_id == 7 and orig_castle_ut_sid is None:
                            orig_castle_ut_sid = tech.language_dll_name
                            orig_castle_ut_tech_id = ti
                        elif loc.button_id == 8 and orig_imp_ut_sid is None:
                            orig_imp_ut_sid = tech.language_dll_name
                            orig_imp_ut_tech_id = ti

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
            # Also remove from all research location panels to prevent ghost buttons.
            for loc in (t.research_locations or []):
                loc.location_id = -1
            n_nullified += 1
        print(f"       Nullified {n_nullified} existing civ={civ_index} techs")

    # 1. Clone from civ 1 (first playable vanilla civ — full standard unit set).
    new_civ = deepcopy(dat.civs[1])
    # Preserve the slot's vanilla DAT name ("British", "French", ...). The engine
    # appears to key civ-description lookup off this field, so renaming it to the
    # alias makes the picker fall back to the base game's vanilla description.
    # User-visible name is handled by the string override at 10271+i.
    if overwrite:
        new_civ.name = dat.civs[civ_index].name
    else:
        new_civ.name = alias
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
    castle_ut_sid = STR_UT_BASE + civ_index * STR_UT_PER_CIV + 0
    imp_ut_sid    = STR_UT_BASE + civ_index * STR_UT_PER_CIV + 1
    castle_ut_tech_id: int | None = None
    imp_ut_tech_id:    int | None = None
    if castle_ut_entries or imperial_ut_entries:
        castle_ut_sid, imp_ut_sid, castle_ut_tech_id, imp_ut_tech_id = (
            _append_unique_tech_stubs(
                dat, civ_index, alias,
                castle_ut_entries, imperial_ut_entries)
        )

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
    km_uu_make_avail_tech_id: int = -1
    km_uu_elite_tech_id:      int = -1
    if km_uu_is_vanilla:
        km_uu_make_avail_tech_id, km_uu_elite_tech_id = _apply_km_uu(dat, civ_index, km_uu_index)
    elif km_uu_index is not None:
        msg = (f"KM UU index {km_uu_index} is a KM-custom unit "
               f"— not supported in standalone builder; vanilla UU preserved")
        print(f"       WARNING: {msg}")
        warnings.append(msg)

    # 7. Apply bonuses from catalog.
    bonus_results: dict = {"applied": 0, "skipped": [], "team_applied": 0, "team_total": 0}
    if "bonuses" in civ_def:
        bonus_results = _apply_bonuses(dat, civ_index, civ_def, tb_eff_id)

    # 8. Assign language audio: remap sound items from source civ → civ_index.
    lang_val = civ_def.get("language", 0)
    _assign_language(dat, civ_index, lang_val)

    print(f"       tech_tree_id(eff)={tt_eff_id}  team_bonus_id(eff)={tb_eff_id}")
    return {
        "civ_index":             civ_index,
        "alias":                 alias,
        "bonus_results":         bonus_results,
        "warnings":              warnings,
        "castle_ut_sid":         castle_ut_sid,
        "imp_ut_sid":            imp_ut_sid,
        "castle_ut_tech_id":     castle_ut_tech_id,
        "imp_ut_tech_id":        imp_ut_tech_id,
        "orig_castle_ut_tech_id":  orig_castle_ut_tech_id,
        "orig_imp_ut_tech_id":    orig_imp_ut_tech_id,
        "km_uu_make_avail_tech_id": km_uu_make_avail_tech_id,
        "km_uu_elite_tech_id":      km_uu_elite_tech_id,
    }


# Keep old name as alias for backwards compatibility.
def append_civ(dat: DatFile, civ_def: dict) -> int:
    return apply_civ(dat, civ_def, target_slot=None)["civ_index"]


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


# KM bonus index → vanilla DAT tech ID, for castle and imperial UTs.
# Auto-extracted from Fritz's civbuilder.cpp `castleUniqueTechIDs[]` /
# `impUniqueTechIDs[]` arrays cross-referenced against enums/tech_ids.h.
# These are the techs whose effect commands KM cloned to implement each
# preset UT. We copy their effects into our newly-created UT stub so that
# researching it actually does what the name advertises.
_KM_CASTLE_UT_TECHS: dict[int, int] = {
    0: 460, 1: 578, 2: 3, 3: 685, 4: 754, 5: 627, 6: 464, 7: 482,
    8: 462, 9: 689, 10: 574, 11: 83, 12: 16, 13: 483, 14: 516,
    15: 506, 16: 494, 17: 484, 18: 622, 19: 486, 20: 691, 21: 514,
    22: 624, 23: 576, 24: 485, 25: 487, 26: 488, 27: 572, 28: 490,
    29: 756, 30: 512, 31: 492, 32: 687, 33: 489, 34: 491, 35: 628,
    36: 463, 37: 782, 38: 784, 44: 831, 45: 833, 46: 835, 47: 455,
    48: 9, 49: 883, 50: 28, 51: 922, 52: 923, 54: 499, 55: 1070,
    56: 1080, 57: 1061, 58: 996, 59: 1006,
}

_KM_IMP_UT_TECHS: dict[int, int] = {
    0: 24, 1: 579, 2: 461, 3: 686, 4: 755, 5: 626, 6: 61, 7: 5,
    8: 52, 9: 690, 10: 575, 11: 493, 12: 457, 13: 21, 14: 517,
    15: 507, 16: 902, 17: 59, 18: 623, 19: 445, 20: 692, 21: 515,
    22: 625, 23: 577, 24: 4, 25: 6, 26: 7, 27: 573, 28: 454, 29: 757,
    30: 513, 31: 440, 32: 688, 33: 11, 34: 10, 35: 629, 36: 49,
    37: 783, 38: 785, 44: 832, 45: 834, 46: 836, 47: 884, 48: 921,
    49: 924, 54: 1069, 55: 1081, 56: 1062, 57: 997, 58: 1007,
}


def _build_ut_effect_cmds(dat: DatFile, entries: list, label: str,
                          lookup: dict[int, int]) -> list:
    """Collect effect commands for a UT's bonus entries.

    `entries` is bonuses[2] (castle) or bonuses[3] (imperial) from the KM JSON.
    `lookup` maps KM bonus_id → vanilla DAT tech ID; pass _KM_CASTLE_UT_TECHS or
    _KM_IMP_UT_TECHS depending on which slot is being built. We then deep-copy
    that tech's effect commands into our new UT stub so research actually fires
    the right behavior. Previously this called civ_bonus_techs() which uses an
    entirely different bonus-ID namespace and produced wrong effects (e.g.
    Stirrups would research Britons' "Castle 15% cheaper" tech).
    """
    cmds = []
    for entry in entries:
        if not isinstance(entry, (list, tuple)) or len(entry) < 1:
            continue
        bonus_id   = int(entry[0])
        multiplier = int(entry[1]) if len(entry) > 1 else 1
        tech_id    = lookup.get(bonus_id)
        if tech_id is None:
            print(f"       {label} bonus {bonus_id}: not in UT catalog — skipped")
            continue
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
                               imperial_ut_entries: list,
                               ) -> tuple[int, int, int | None, int | None]:
    """Create Castle UT (btn7) and Imperial UT (btn8) from bonus catalog entries.

    Returns (castle_sid, imp_sid, castle_tech_id, imp_tech_id).
    Always allocates fresh high-range string IDs (STR_UT_BASE + civ_index*10 + slot)
    so the engine's in-game UT button label honors our mod strings instead of
    falling back to the vanilla tech name baked into the base game.
    """
    # Default costs: Castle UT = 300 food + 300 gold; Imperial UT = 450 food + 225 stone
    # icon_id 33 = vanilla Castle UT icon; 107 = vanilla Imperial UT icon
    ut_configs = [
        (7,  "Castle UT",   102, castle_ut_entries,   300, 3, 300,  33, 0, _KM_CASTLE_UT_TECHS),
        (8,  "Imperial UT", 103, imperial_ut_entries, 450, 2, 225, 107, 1, _KM_IMP_UT_TECHS),
    ]
    used_sids: list[int] = []
    used_tech_ids: list[int | None] = []
    for i, (btn, label, age_req, entries, cost_food, cost_b_type, cost_b, icon, ut_slot, ut_lookup) in enumerate(ut_configs):
        name_sid = STR_UT_BASE + civ_index * STR_UT_PER_CIV + ut_slot
        used_sids.append(name_sid)
        if not entries:
            used_tech_ids.append(None)
            continue
        cmds = _build_ut_effect_cmds(dat, entries, label, ut_lookup)
        eff_id = _append_effect(dat, Effect(name=f"{alias} {label}", effect_commands=cmds))
        # Copy hotkey from first entry's vanilla tech so S/D keys work in-game.
        hotkey = -1
        if entries and isinstance(entries[0], (list, tuple)) and entries[0]:
            src_slot = int(entries[0][0])
            src_tid  = ut_lookup.get(src_slot)
            if src_tid is not None and 0 <= src_tid < len(dat.techs):
                src_locs = getattr(dat.techs[src_tid], 'research_locations', [])
                if src_locs:
                    hotkey = src_locs[0].hot_key_id
        # 4-string DAT wiring mirrors NapKingCole's Unhinged Empires pattern:
        # name (button label), description (button hover), help (full tooltip),
        # tech_tree (F1/help-context). Strings file must emit all four IDs.
        tech = _make_tech(
            name=f"{alias} {label}",
            effect_id=eff_id,
            civ_index=civ_index,
            age_req=age_req,
            location=BUILDING_CASTLE,
            button=btn,
            research_time=60,
            icon_id=icon,
            lang_name=name_sid,
            lang_desc=name_sid + DLL_CREATION_OFFSET,
            lang_help=name_sid + DLL_HELP_OFFSET,
            lang_tech_tree=name_sid + 150000,
            hot_key_id=hotkey,
        )
        # Apply costs (food + gold for castle UT; food + stone for imperial UT).
        tech.resource_costs = (
            ResearchResourceCost(type=0, amount=cost_food, flag=1),
            ResearchResourceCost(type=cost_b_type, amount=cost_b, flag=1),
            ResearchResourceCost(type=-1, amount=0, flag=0),
        )
        # KM's allocateTech() does a full struct copy of vanilla techs, which preserves
        # repeatable=1. EC_RESOURCE with b=-1 (trickle/rate type) requires repeatable=1
        # to sustain the effect (e.g. Vineyards farm gold, Paper Money market gold).
        tech.repeatable = 1
        _append_tech(dat, tech)
        used_tech_ids.append(len(dat.techs) - 1)
        print(f"       {label}: {len(cmds)} effect commands (sid={name_sid})")
    return (
        used_sids[0] if len(used_sids) > 0 else _str_id(civ_index, STR_CASTLE_UT),
        used_sids[1] if len(used_sids) > 1 else _str_id(civ_index, STR_IMPERIAL_UT),
        used_tech_ids[0] if len(used_tech_ids) > 0 else None,
        used_tech_ids[1] if len(used_tech_ids) > 1 else None,
    )
