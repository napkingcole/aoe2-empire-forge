"""
civ_appender.py — Append or overwrite a civilization in an AoE2 DE DatFile.
"""

from copy import deepcopy

from genieutils.datfile import DatFile
from genieutils.civ import Civ
from genieutils.effect import Effect, EffectCommand
from genieutils.tech import Tech, ResearchLocation, ResearchResourceCost
from genieutils.unit import TrainLocation, ResourceCost
from genieutils.unitheaders import UnitHeaders

from bonus_catalog import civ_bonus_techs, team_bonus_tech, civ_bonus_ec_list
import km_custom_uu

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
#         modding/enums/tech_ids.h.  Indices 0-38, 45, and 78-87 are real
#         vanilla DE units. The rest of 39-77 (there is no 88+ — KM's
#         uu_ids.h tops out at 77) are from-scratch KM creations with no
#         vanilla unit to point to; those are handled by km_custom_uu.py
#         instead of this dict (see apply_civ's km_uu_is_custom branch).
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
    45: (881, 882),   # Centurion — real vanilla DE unit (Romans, civ 43),
                      # not a KM-custom creation despite sitting inside the
                      # 39-77 custom-UU index range.
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
# Confirmed by scanning the actual shipped key-value-strings-utf8.txt (a real
# extract, not a guess): vanilla content is NOT confined to a low range like
# "0-26xxx" — campaign dialogue, scenario strings, and UI text are scattered
# as high as ~590000, including dense clusters throughout 40000-47000 and
# 75000-76000+ (e.g. 75001 = "Alexios Komnenos", a campaign character name).
# Our previous bases (40000, 75000) collided with real, currently-shipped
# vanilla strings — not a future risk, an active one. 600000+ is the first
# verified-clear range (checked 600000-900000 plus every offset we actually
# compute from these bases: +0, +1000, +100000, +150000). No range is
# permanently guaranteed against a future DLC ever reaching this high, but
# at ~300k IDs of headroom past anything currently shipped, that's about as
# future-proof as a shared, vendor-controlled namespace allows — and if it
# ever does need to move again, it's a one-line constant change.
# Each custom civ gets a block of STRING_BLOCK_SIZE IDs.
STRING_BASE       = 620000
STRING_BLOCK_SIZE = 100

# Offsets within each civ's string block
STR_CIV_NAME    = 0
STR_UU_NAME     = 1
STR_CASTLE_UT   = 2
STR_IMPERIAL_UT = 3

# AoE2 DLL offset conventions: name+0, creation tooltip = name+1000, help = name+100000
DLL_CREATION_OFFSET  = 1000
DLL_HELP_OFFSET      = 100000
DLL_TECH_TREE_OFFSET = 150000

# UT name strings live in their own high-range block so the engine treats them as
# brand-new strings rather than overrides of vanilla 7xxx tech names. Overriding
# vanilla IDs works for the "research complete" toast but NOT for the in-game
# Castle UT button label — confirmed in-game by comparing our mod (which reused
# vanilla 7419 for Britons' Yeomen slot and showed "Yeomen" on the button) to
# NapKingCole's Unhinged Empires mod (which uses 79xxx-range IDs and shows the
# correct UT name). Moved off the original 75000 base (see STRING_BASE comment
# above — that range is live vanilla campaign content) to a verified-clear
# range; still conflict-free with NapKingCole's 79xxx since we're nowhere near it.
STR_UT_BASE       = 650000
STR_UT_PER_CIV    = 10  # 0=Castle UT, 1=Imperial UT, 2=Imperial Scorpion (308),
                        # 3=Royal Battle Elephant (309), 4=Royal Lancer (310),
                        # 5=KM-custom UU elite TECH name (km_custom_uu.py),
                        # 6=KM-custom UU unit name, 7=KM-custom UU elite unit
                        # name — all 10 slots now spoken for; bump this
                        # constant if a future feature needs an 11th.

# llm/advanced_techniques.md (empirically tested, not a DAT-format limit —
# the unit/tech struct fields are full 32-bit ints) found that the engine's
# in-game "currently training" hover tooltip silently shows nothing if
# language_dll_creation exceeds 65535. Needs its own low, verified-clear
# range distinct from STRING_BASE/STR_UT_BASE above (those are deliberately
# high specifically to dodge vanilla content, which would be wrong here).
# Confirmed clear via the same extracted-strings scan: only 9 vanilla IDs
# exist in 50000-60000 (all in 50001-50013, scenario-editor UI text) —
# starting at 50100 stays clear with room to spare under the 65536 ceiling.
LOW_STR_BASE    = 50100
LOW_STR_PER_CIV = 4   # 0=KM-custom UU creation tooltip, 1=KM-custom Elite
                      # unit creation tooltip, 2-3 reserved.

# ── Campaign-string override pool (the ONLY working string mechanism) ──────
# *** CONFIRMED: AoE2 DE's modded-strings overlay can ONLY override IDs that
# already exist in the base game's string table. *** A brand-new id (the
# old STRING_BASE/STR_UT_BASE/LOW_STR_BASE scheme, and the fixed
# 660001+/50090+ ids this section used to hardcode) is silently ignored, no
# matter how correctly it's written to the DAT or the strings file — verified
# live, including via an actual Steam Workshop publish, not just a local
# install. Overriding an EXISTING vanilla id worked immediately. See memory
# project_string_id_engine_limit.md for the full incident writeup.
#
# Pool of 1813 real, currently-defined vanilla string IDs, harvested from
# two groups of historically-themed campaigns/scenario packs (Bayinnaung 1-5
# + Le Loi 1-6 + Palermo/Prague/Porto/Plymouth/Philadelphia/Peru campaigns;
# and separately Wallace 1-7 + Joan 1-6 + Barbarossa 1-6 + Saladin 1-6 +
# Genghis Khan 1-6 + Attila 1-6 + El Cid 1-6 + Montezuma 1-6 + the single
# historical-battle scenarios Tours/Vinlandsaga/Hastings/Manzikert/
# Agincourt/Lepanto/Kyoto/Noryang Point). Deliberately restricted to IDs
# ACTUALLY DEFINED in the vanilla file (not just numerically in-range) —
# undefined-but-nearby IDs are unverified and might behave like brand-new
# ones. One known dangerous gap was found and excluded while building this:
# ids 50001-50013 sit physically between two campaign sections in the
# shipped file but are GENERIC scenario-difficulty-selector UI text used by
# every campaign, not scoped to one — confirmed by content ("Standard --
# Choose this if you have played the William Wallace campaign...") and
# excluded from the pool.
#
# Cost of using this pool: any player who has this mod's UI half active AND
# specifically plays one of the campaigns/scenarios above will see our
# override text instead of that mission's real dialogue/player names.
# Skirmish, multiplayer, and every other campaign are unaffected. Document
# this trade-off for end users (e.g. "disable the UI mod before playing
# campaigns").
CAMPAIGN_STRING_POOL: list[int] = [
    69800, 69801, 69802, 69803, 69804, 69805, 69808, 69809, 69810, 69811,
    69812, 69813, 69814, 69815, 69816, 69817, 69818, 69819, 69820, 69821,
    69822, 69823, 69824, 69825, 69826, 69827, 69828, 69829, 69830, 69831,
    69832, 69833, 69834, 69835, 69836, 69837, 69838, 69900, 69901, 69902,
    69903, 69904, 69905, 69908, 69909, 69910, 69911, 69912, 69913, 69914,
    69915, 69916, 69917, 69918, 69919, 69920, 69921, 69922, 69923, 69924,
    69925, 69926, 69927, 69928, 70000, 70001, 70002, 70003, 70004, 70005,
    70008, 70009, 70010, 70011, 70012, 70013, 70014, 70015, 70016, 70017,
    70018, 70019, 70020, 70021, 70022, 70023, 70024, 70025, 70026, 70027,
    70028, 70029, 70030, 70031, 70032, 70033, 70034, 70035, 70036, 70037,
    70038, 70100, 70101, 70102, 70103, 70104, 70105, 70106, 70108, 70109,
    70110, 70111, 70112, 70113, 70114, 70115, 70116, 70117, 70118, 70119,
    70120, 70121, 70122, 70123, 70124, 70125, 70126, 70127, 70128, 70129,
    70130, 70131, 70132, 70133, 70134, 70135, 70136, 70200, 70201, 70202,
    70203, 70204, 70205, 70206, 70208, 70209, 70210, 70211, 70212, 70213,
    70214, 70215, 70216, 70217, 70218, 70219, 70220, 70221, 70222, 70223,
    70224, 70225, 70226, 70227, 70228, 70229, 70230, 70231, 70232, 70233,
    70234, 70235, 70236, 70237, 70238, 70300, 70301, 70302, 70303, 70304,
    70305, 70306, 70307, 70308, 70309, 70310, 70311, 70312, 70313, 70314,
    70315, 70316, 70317, 70318, 70319, 70320, 70321, 70322, 70323, 70324,
    70325, 70326, 70331, 70332, 70333, 70338, 70339, 70400, 70401, 70402,
    70403, 70404, 70408, 70409, 70410, 70411, 70412, 70413, 70414, 70415,
    70416, 70417, 70418, 70419, 70420, 70421, 70422, 70423, 70424, 70425,
    70426, 70427, 70428, 70429, 70430, 70431, 70432, 70500, 70501, 70502,
    70503, 70504, 70508, 70509, 70510, 70511, 70512, 70513, 70514, 70515,
    70516, 70517, 70518, 70519, 70520, 70521, 70522, 70523, 70524, 70525,
    70526, 70527, 70528, 70529, 70530, 70531, 70532, 70533, 70534, 70535,
    70536, 70537, 70538, 70539, 70540, 70541, 70542, 70543, 70544, 70600,
    70601, 70602, 70603, 70604, 70605, 70608, 70609, 70610, 70611, 70612,
    70613, 70614, 70615, 70616, 70617, 70618, 70619, 70620, 70621, 70622,
    70623, 70624, 70700, 70701, 70702, 70703, 70704, 70705, 70708, 70709,
    70710, 70711, 70712, 70713, 70714, 70715, 70716, 70717, 70718, 70719,
    70720, 70721, 70722, 70723, 70724, 70725, 70726, 70727, 70728, 70729,
    70730, 70731, 70732, 70733, 70734,
    44000, 44001, 44008, 44009, 44010, 44011, 44012, 44013, 44014, 44015, 44016,
    44017, 44018, 44019, 44020, 44021, 44022, 44023, 44024, 44025, 44026, 44027,
    44028, 44029, 44030, 44031, 44100, 44108, 44109, 44110, 44111, 44112, 44113,
    44114, 44115, 44116, 44117, 44118, 44119, 44120, 44121, 44122, 44123, 44124,
    44125, 44126, 44200, 44208, 44209, 44210, 44211, 44212, 44213, 44214, 44215,
    44216, 44217, 44218, 44219, 44220, 44221, 44222, 44223, 44224, 44225, 44226,
    44227, 44228, 44229, 44230, 44231, 44300, 44301, 44308, 44309, 44310, 44311,
    44312, 44313, 44314, 44315, 44316, 44317, 44318, 44319, 44320, 44321, 44322,
    44323, 44324, 44325, 44326, 44327, 44328, 44329, 44330, 44331, 44400, 44401,
    44408, 44409, 44410, 44411, 44412, 44413, 44414, 44415, 44416, 44417, 44418,
    44419, 44420, 44421, 44422, 44423, 44424, 44425, 44426, 44427, 44428, 44429,
    44430, 44431, 44432, 44433, 44434, 44435, 44436, 44437, 44438, 44439, 44500,
    44501, 44502, 44508, 44509, 44510, 44511, 44512, 44513, 44514, 44515, 44516,
    44517, 44518, 44519, 44520, 44521, 44522, 44523, 44524, 44525, 44526, 44527,
    44528, 44529, 44530, 44531, 44532, 44533, 44534, 44535, 44536, 44537, 44600,
    44601, 44602, 44608, 44609, 44610, 44611, 44612, 44613, 44614, 44615, 44616,
    44617, 44618, 44619, 44620, 44621, 44622, 44623, 44624, 44625, 44626, 44627,
    44628, 44629, 44630, 44700, 44701, 44702, 44703, 44704, 44705, 44708, 44709,
    44710, 44711, 44712, 44713, 44714, 44715, 44716, 44717, 44718, 44719, 44720,
    44721, 44722, 44723, 44724, 44725, 44726, 44727, 44728, 44729, 44730, 44731,
    44732, 44733, 44734, 44735, 44736, 44737, 44738, 44800, 44801, 44802, 44803,
    44804, 44805, 44806, 44808, 44809, 44810, 44811, 44812, 44813, 44814, 44815,
    44816, 44817, 44818, 44819, 44820, 44821, 44822, 44823, 44824, 44825, 44826,
    44827, 44828, 44829, 44830, 44831, 44832, 44833, 44834, 44835, 44836, 44900,
    44901, 44902, 44903, 44908, 44909, 44910, 44911, 44912, 44913, 44914, 44915,
    44916, 44917, 44918, 44919, 44920, 44921, 44922, 44923, 44924, 44925, 44926,
    44927, 44928, 44929, 45000, 45001, 45002, 45003, 45004, 45008, 45009, 45010,
    45011, 45012, 45013, 45014, 45015, 45016, 45017, 45018, 45019, 45020, 45021,
    45022, 45023, 45024, 45025, 45026, 45027, 45028, 45029, 45100, 45101, 45102,
    45103, 45104, 45108, 45109, 45110, 45111, 45112, 45113, 45114, 45115, 45116,
    45117, 45118, 45119, 45120, 45121, 45122, 45123, 45124, 45125, 45126, 45127,
    45128, 45129, 45130, 45131, 45200, 45201, 45202, 45203, 45208, 45209, 45210,
    45211, 45212, 45213, 45214, 45215, 45216, 45217, 45218, 45219, 45220, 45221,
    45222, 45223, 45224, 45225, 45226, 45227, 45228, 45229, 45230, 45231, 45232,
    45233, 45234, 45235, 45236, 45300, 45301, 45302, 45303, 45304, 45305, 45306,
    45307, 45308, 45309, 45310, 45311, 45312, 45313, 45314, 45315, 45316, 45317,
    45400, 45401, 45402, 45403, 45404, 45408, 45409, 45410, 45411, 45412, 45413,
    45414, 45415, 45416, 45417, 45418, 45500, 45501, 45502, 45503, 45504, 45508,
    45509, 45510, 45511, 45512, 45513, 45514, 45515, 45516, 45517, 45518, 45519,
    45600, 45601, 45602, 45603, 45604, 45608, 45609, 45610, 45611, 45612, 45613,
    45614, 45615, 45616, 45700, 45701, 45702, 45703, 45704, 45705, 45708, 45709,
    45710, 45711, 45712, 45713, 45714, 45715, 45716, 45717, 45718, 45719, 45720,
    45721, 45722, 45723, 45724, 45725, 45726, 45727, 45728, 45729, 45730, 45800,
    45801, 45802, 45803, 45804, 45808, 45809, 45810, 45811, 45812, 45813, 45814,
    45815, 45816, 45817, 45818, 45819, 45820, 45821, 45822, 45823, 45824, 45825,
    45826, 45827, 45828, 45829, 45830, 45900, 45901, 45902, 45903, 45908, 45909,
    45910, 45911, 45912, 45913, 45914, 45915, 45916, 45917, 45918, 45919, 45920,
    45921, 45922, 45923, 45924, 45925, 45926, 46001, 46002, 46003, 46004, 46005,
    46008, 46009, 46010, 46011, 46012, 46013, 46014, 46015, 46016, 46017, 46018,
    46019, 46020, 46021, 46022, 46023, 46024, 46025, 46101, 46102, 46103, 46104,
    46108, 46109, 46110, 46111, 46112, 46113, 46114, 46115, 46116, 46117, 46201,
    46202, 46203, 46208, 46209, 46210, 46211, 46212, 46213, 46214, 46215, 46216,
    46217, 46218, 46219, 46220, 46221, 46222, 46223, 46224, 46225, 46226, 46301,
    46302, 46303, 46304, 46305, 46308, 46309, 46310, 46311, 46312, 46313, 46314,
    46318, 46319, 46320, 46321, 46322, 46323, 46401, 46402, 46403, 46404, 46405,
    46406, 46408, 46409, 46410, 46411, 46412, 46413, 46414, 46415, 46416, 46417,
    46418, 46419, 46420, 46500, 46501, 46502, 46503, 46504, 46505, 46506, 46507,
    46508, 46509, 46510, 46511, 46512, 46513, 46514, 46515, 46516, 46517, 46518,
    46519, 46520, 46521, 46522, 46523, 46524, 46525, 46526, 46527, 46528, 46529,
    46530, 46531, 46532, 46533, 46534, 46535, 46536, 46537, 46538, 46600, 46601,
    46602, 46603, 46608, 46609, 46610, 46611, 46612, 46613, 46614, 46615, 46616,
    46617, 46618, 46619, 46620, 46621, 46701, 46702, 46703, 46704, 46705, 46708,
    46709, 46710, 46711, 46712, 46713, 46714, 46715, 46716, 46801, 46802, 46803,
    46808, 46809, 46810, 46811, 46812, 46813, 46814, 46815, 46816, 46817, 46818,
    46819, 46820, 46821, 46822, 46823, 46824, 46825, 46826, 46827, 46900, 46901,
    46902, 46903, 46908, 46909, 46910, 46911, 46912, 46913, 46914, 46915, 46916,
    46917, 46918, 46919, 46920, 46921, 46922, 46923, 46924, 46925, 46926, 46927,
    46928, 47001, 47008, 47009, 47010, 47011, 47012, 47013, 47014, 47015, 47016,
    47017, 47018, 47019, 47020, 47021, 47022, 47023, 60000, 60001, 60002, 60003,
    60004, 60008, 60009, 60010, 60011, 60012, 60013, 60014, 60015, 60016, 60017,
    60018, 60019, 60020, 60021, 60022, 60023, 60024, 60025, 60026, 60027, 60028,
    60029, 60030, 60031, 60032, 60033, 60034, 60035, 60036, 60037, 60038, 60039,
    60040, 60041, 60042, 60043, 60044, 60045, 60046, 60047, 60048, 60049, 60050,
    60051, 60052, 60053, 60054, 60055, 60056, 60057, 60058, 60059, 60060, 60061,
    60100, 60101, 60102, 60103, 60104, 60105, 60106, 60107, 60108, 60109, 60110,
    60111, 60112, 60113, 60114, 60115, 60116, 60117, 60118, 60119, 60120, 60121,
    60122, 60123, 60124, 60125, 60126, 60127, 60128, 60129, 60130, 60131, 60132,
    60133, 60134, 60200, 60201, 60202, 60203, 60208, 60209, 60210, 60211, 60212,
    60213, 60214, 60215, 60216, 60217, 60218, 60219, 60220, 60221, 60222, 60223,
    60224, 60225, 60226, 60227, 60300, 60301, 60302, 60303, 60304, 60308, 60309,
    60310, 60311, 60312, 60313, 60314, 60315, 60316, 60317, 60318, 60319, 60320,
    60321, 60322, 60323, 60324, 60325, 60326, 60327, 60328, 60400, 60401, 60402,
    60403, 60404, 60405, 60408, 60409, 60410, 60411, 60412, 60413, 60414, 60415,
    60416, 60417, 60418, 60419, 60500, 60501, 60502, 60503, 60504, 60505, 60508,
    60509, 60510, 60511, 60512, 60513, 60514, 60515, 60516, 60517, 60518, 60519,
    60521, 60522, 60523, 60524, 60525, 60700, 60701, 60702, 60703, 60704, 60705,
    60708, 60709, 60710, 60711, 60712, 60713, 60714, 60715, 60716, 60717, 60718,
    60719, 60720, 60721, 60722, 60723, 60724, 60725, 60726, 60727, 60728, 60729,
    60730, 60731, 60732, 60733, 60734, 60735, 60736, 60737, 60738, 60739, 60740,
    60741, 60742, 60743, 60744, 60745, 60746, 60800, 60801, 60802, 60803, 60804,
    60805, 60808, 60809, 60810, 60811, 60812, 60813, 60814, 60815, 60816, 60817,
    60818, 60819, 60820, 60821, 60822, 60823, 60824, 60825, 60826, 60827, 60828,
    60900, 60901, 60902, 60903, 60908, 60909, 60910, 60911, 60912, 60913, 60914,
    60915, 60916, 60917, 60918, 60919, 60920, 60921, 60922, 60923, 60924, 60925,
    60926, 60927, 60928, 60929, 60930, 60931, 60932, 60933, 61000, 61001, 61002,
    61003, 61004, 61008, 61009, 61010, 61011, 61012, 61013, 61014, 61015, 61016,
    61017, 61018, 61019, 61020, 61021, 61022, 61023, 61024, 61025, 61026, 61027,
    61028, 61029, 61030, 61031, 61032, 61033, 61034, 61035, 61036, 61037, 61038,
    61039, 61040, 61041, 61042, 61043, 61044, 61045, 61046, 61047, 61048, 61049,
    61050, 61051, 61052, 61053, 61054, 61055, 61056, 61057, 61100, 61101, 61102,
    61103, 61104, 61108, 61109, 61110, 61111, 61112, 61113, 61114, 61115, 61116,
    61117, 61118, 61119, 61120, 61121, 61122, 61123, 61124, 61125, 61126, 61127,
    61128, 61129, 61130, 61200, 61201, 61202, 61203, 61204, 61208, 61209, 61210,
    61211, 61212, 61213, 61214, 61215, 61216, 61217, 61218, 61300, 61301, 61302,
    61303, 61308, 61309, 61310, 61311, 61312, 61313, 61314, 61315, 61316, 61400,
    61401, 61402, 61403, 61404, 61408, 61409, 61410, 61411, 61412, 61413, 61414,
    61415, 61416, 61417, 61418, 61419, 61420, 61421, 61422, 61423, 61424, 61425,
    61426, 61427, 61428, 61429, 61430, 61431, 61432, 61433, 61434, 61435, 61436,
    61437, 61438, 61439, 61500, 61501, 61502, 61503, 61508, 61509, 61510, 61511,
    61512, 61513, 61514, 61515, 61516, 61517, 61518, 61519, 61520, 61521, 61522,
    61523, 61524, 61525, 61600, 61601, 61602, 61603, 61608, 61609, 61610, 61611,
    61612, 61613, 61614, 61615, 61616, 61617, 61618, 61619, 61620, 61621, 61622,
    61623, 61624, 61625, 61626, 61627, 61628, 61629, 61700, 61701, 61702, 61708,
    61709, 61710, 61711, 61712, 61713, 61714, 61715, 61716, 61717, 61718, 61719,
    61720, 61721, 61800, 61801, 61802, 61803, 61808, 61809, 61810, 61811, 61812,
    61813, 61814, 61815, 61816, 61817, 61818, 61819, 61900, 61901, 61902, 61903,
    61908, 61909, 61910, 61911, 61912, 61913, 61914, 61915, 61916, 61917, 61918,
    61919, 61920, 61921, 61922, 61923, 61924, 61925, 61926, 61927, 62000, 62001,
    62002, 62003, 62008, 62009, 62010, 62011, 62012, 62013, 62014, 62015, 62016,
    62017, 62018, 62019, 62020, 62021, 62022, 62023, 62024, 62025, 62026, 62027,
    62028, 62029, 62100, 62101, 62102, 62103, 62104, 62108, 62109, 62110, 62111,
    62112, 62113, 62114, 62115, 62116, 62117, 62118, 62119, 62120, 62121, 62122,
    62123, 62200, 62201, 62202, 62203, 62204, 62205, 62208, 62209, 62210, 62211,
    62212, 62213, 62214, 62215, 62216, 62217, 62218, 62219, 62220, 62221, 62222,
    62223, 62224, 62225, 62226, 62227, 62228, 62229, 62230, 62231, 62232, 62300,
    62301, 62302, 62303, 62304, 62305, 62308, 62309, 62310, 62311, 62312, 62313,
    62314, 62315, 62316, 62317, 62318, 62319, 62320, 62321, 62322, 62323, 62324,
    62325, 62326, 62327, 62328, 62329, 62330, 62331, 62332, 62333, 62334, 62335,
    62336, 62337, 62338, 62339, 62340, 62341, 62342, 62343, 62400, 62401, 62402,
    62408, 62409, 62410, 62411, 62412, 62413, 62414, 62415, 62416, 62417, 62418,
    62419, 62420, 62421, 62422, 62500, 62501, 62502, 62503, 62504, 62508, 62509,
    62510, 62511, 62512, 62513, 62514, 62515, 62516, 62517, 62518, 62519, 62520,
    62521, 62522, 62523, 62524, 62600, 62601, 62602, 62603, 62604, 62608, 62609,
    62610, 62611, 62612, 62613, 62614, 62615, 62616, 62617, 62618, 62619, 62620,
    62621, 62622, 62623, 62624,
]


def _campaign_sid(slot_index: int) -> int:
    """Look up a campaign-override string id by absolute slot index.

    Raises if the pool is exhausted — fail loudly rather than silently
    reusing an id across two unrelated allocations.
    """
    if slot_index >= len(CAMPAIGN_STRING_POOL):
        raise ValueError(
            f"CAMPAIGN_STRING_POOL exhausted: need slot {slot_index}, "
            f"only have {len(CAMPAIGN_STRING_POOL)} entries."
        )
    return CAMPAIGN_STRING_POOL[slot_index]


# Vanilla's own units/techs aren't independently-numbered per field — every
# unit/tech's secondary strings sit at a FIXED arithmetic offset from its own
# "name" string id (confirmed by surveying the live dat: 593-1129 units/techs
# matching each pattern, plus matching build.py's own Budget Knight line
# `language_dll_help = BUDGET_KNIGHT_NAME_ID + 100000`). The in-game Castle
# "create unit" hover tooltip apparently relies on this offset (not on the
# unit's `language_dll_help` field having ANY value, but on it specifically
# equaling name+100000) — using an unrelated pool id for help/desc, as we did
# previously, produced a blank tooltip even though the id itself was a real,
# pre-existing one. One pool slot (the name id) is now sufficient per
# unit/tech; creation/description/help/tech-tree are all DERIVED from it.
def _creation_sid(name_sid: int) -> int:
    """Unit creation-button / tech description string: name + DLL_CREATION_OFFSET."""
    return name_sid + DLL_CREATION_OFFSET


def _help_sid(name_sid: int) -> int:
    """Unit/tech tooltip help string: name + DLL_HELP_OFFSET."""
    return name_sid + DLL_HELP_OFFSET


def _extended_tooltip_sid(name_sid: int) -> int:
    """Unit Castle-train-button EXTENDED hover tooltip: name + DLL_CREATION_OFFSET + 20000.

    Confirmed live (2026-06-22): the Castle "create unit" button's hover
    tooltip for a custom unit is NOT read from language_dll_help (name+
    100000) — that convention is correct for TECH research-button tooltips
    (Castle/Imperial UT, confirmed working) but not for a UNIT's train
    button. build.py writes real text at name+21000 for every custom unit
    WITHOUT ever assigning any unit field to that id (confirmed via grep) —
    the engine appears to derive this id automatically from
    language_dll_creation (+20000), purely a strings-file addition, no DAT
    field needed. User confirmed seeing exactly this text in-game for Elite
    Budget Knight ("Create <b>Elite Budget Knight<b> (<cost>) \\n95 HP | 12
    attack | 1/2 armor. [Budget Bois unique unit]", plus an engine-appended
    "(Hotkey: Q)" line) while the same unit's name+100000 entry never showed.
    """
    return name_sid + DLL_CREATION_OFFSET + 20000


def _tech_tree_sid(name_sid: int) -> int:
    """Tech-tree-viewer string (techs only): name + DLL_TECH_TREE_OFFSET."""
    return name_sid + DLL_TECH_TREE_OFFSET


# Vanilla AoE2 DE (all DLC) ships with 60 civs. Community testing suggests
# crashes occur around 64+; keep a small buffer.
MAX_TOTAL_CIVS = 63

# ── Pool allocation map ─────────────────────────────────────────────────────
# Three independent consumers, each given a non-overlapping block. Each unit
# or tech now needs only ONE pool slot (the "name" id) — creation/help/
# tech-tree are all derived from it via _creation_sid/_help_sid/_tech_tree_sid.
#   1. KM-custom UU strings (km_custom_uu.py): 2 slots/civ — indices
#      [civ_index*2, civ_index*2+1] (UU name, Elite name).
#   2. Castle/Imperial UT button names (_append_unique_tech_stubs): 2 more
#      slots/civ, offset to start right after block 1's full reservation.
#   3. Bonus 308/309/310 unit strings (Imperial Scorpion/Royal Battle
#      Elephant/Royal Lancer): FIXED, non-per-civ (these are SHARED/universal
#      unit slots — same physical data in every civ's array, text never
#      varies by civ) — 3 fixed slots, offset past block 2's full reservation.
# Worst case (all 3 features, all MAX_TOTAL_CIVS civs) needs
# 63*2 + 63*2 + 3 = 255 slots; the pool has 1813, comfortable headroom.
KM_UU_POOL_SLOTS_PER_CIV = 2   # 0=UU name, 1=Elite name.
UT_POOL_OFFSET = MAX_TOTAL_CIVS * KM_UU_POOL_SLOTS_PER_CIV   # 126
UT_POOL_SLOTS_PER_CIV = 2      # 0=Castle UT name, 1=Imperial UT name.
BONUS_FIXED_POOL_OFFSET = UT_POOL_OFFSET + MAX_TOTAL_CIVS * UT_POOL_SLOTS_PER_CIV  # 252

# Fixed (non-per-civ) sids for bonus 308/309/310 — computed once at import
# time since CAMPAIGN_STRING_POOL is a plain list, not dependent on any
# build-time state. Creation/help text ids are DERIVED (_creation_sid/
# _help_sid), not separate pool slots — see the offset-convention note above
# _creation_sid's definition.
IMP_SCORPION_NAME_SID      = _campaign_sid(BONUS_FIXED_POOL_OFFSET + 0)
ROYAL_ELEPHANT_NAME_SID    = _campaign_sid(BONUS_FIXED_POOL_OFFSET + 1)
ROYAL_LANCER_NAME_SID      = _campaign_sid(BONUS_FIXED_POOL_OFFSET + 2)

# (sid, text) pairs callers should write UNCONDITIONALLY, once per build —
# not per-civ-looped, since these are the fixed/shared strings above.
# Harmless to write even if no civ in this build uses bonus 308/309/310.
# Deliberately NO desc/help entries here — the richer, stat-aware help text
# (built by format_unit_tooltip_help, which needs the actual unit object) is
# written per-civ by _create_bonus_handler's 308/309/310 blocks via
# bonus_results["extra_unit_strings"] instead, using _help_sid(NAME_SID) as
# the target id.
FIXED_UNIT_NAME_STRINGS: list[tuple[int, str]] = [
    (IMP_SCORPION_NAME_SID, "Imperial Scorpion"),
    (ROYAL_ELEPHANT_NAME_SID, "Royal Battle Elephant"),
    (ROYAL_LANCER_NAME_SID, "Royal Lancer"),
]


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

# ── Elite-tier "next step" units (bonuses 308/309/310) ───────────────────────
# KM repurposes unused/spare vanilla unit slots for these rather than growing
# every civ's unit array. Verified present (non-None) in the DE dat via
# inspection: 1179/1180/1181 are disguised camel-scout leftovers
# (HLELAIDISGUISED/HLELAI/HLETRIEN); 1113/1114 are an unused duplicate pair of
# the Heavy Scorpion projectile. Source: fritz-net/AoE2-Civbuilder
# civbuilder.cpp "Create Royal Lancer/Royal Battle Elephant/Imperial Scorpion".
_SCORPION                     = 279
_HEAVY_SCORPION               = 542
_IMP_SCORPION                 = 1179   # spare slot HLELAIDISGUISED
_IMP_SCORPION_PROJECTILE      = 1113   # spare slot "Projectile Heavy Scorpion"
_IMP_SCORPION_PROJECTILE_FIRE = 1114   # spare slot "Projectile Heavy Scorpion (Fire)"

_BATTLE_ELEPHANT       = 1132
_ELITE_BATTLE_ELEPHANT = 1134
_ROYAL_ELEPHANT        = 1180   # spare slot HLELAI

_STEPPE_LANCER       = 1370
_ELITE_STEPPE_LANCER = 1372
_ROYAL_LANCER        = 1181   # spare slot HLETRIEN

# Vanilla hotkey IDs for the predecessor tech at the same building/button slot.
# AoE2 DE's hotkey binding is keyed per-tech (not per button position), so the
# "next tier" research must reuse its predecessor's hot_key_id for the S/D
# shortcuts to keep working once the button is occupied by our new tech.
_HEAVY_SCORPION_HOTKEY       = 18244
_ELITE_BATTLE_ELEPHANT_HOTKEY = 18299
_ELITE_STEPPE_LANCER_HOTKEY  = 18402

_RES_NAMES = {0: "food", 1: "wood", 2: "stone", 3: "gold"}


def _format_cost_text(unit) -> str:
    """'55 gold' / '95 food, 85 gold' — for the manual flavor-text cost line.

    Distinct from the engine-substituted <cost> token (which AoE2 fills in
    automatically inside <b>...<b> (<cost>) lines) — this is the SECOND,
    human-readable line vanilla-style tooltips also carry. Pattern source:
    ~/Sites/aoe2/build.py's Elite Budget Knight tooltip — confirmed working
    in-game — "Train <b>Elite Budget Knight<b> (<cost>) \\n95 HP | 12 attack
    | 1/2 armor. Cost: 55 gold. Trainable at Castle and Krepost."
    """
    if not unit.creatable:
        return ""
    parts = [f"{rc.amount} {_RES_NAMES.get(rc.type, '?')}"
             for rc in unit.creatable.resource_costs if rc.flag == 1 and rc.amount > 0]
    return ", ".join(parts)


def format_unit_tooltip_help(unit, name: str, verb: str = "Train",
                             extra: str = "") -> str:
    """Build a unit tooltip for language_dll_help.

    Format verified byte-for-byte against the user's own CONFIRMED-WORKING
    build.py output (Elite Budget Knight, actually shipped and playtested
    "dozens of times" — id 105821 in the real built mod):
        'Train <b>Elite Budget Knight<b> (<cost>) \\n95 HP | 12 attack | 1/2
        armor. Cost: 55 gold. Trainable at Castle and Krepost.'

    An earlier revision of this function instead matched a real VANILLA
    unit's tooltip (Mameluke, id 26103) — verb "Create", no space before
    "\\n", plus a trailing "<hp> <attack> <armor> <piercearmor> <range>"
    token line. That change did NOT fix the blank Gendarme tooltip it was
    meant to address, and turned out to directly contradict the actual
    confirmed-working reference for CUSTOM (non-vanilla) units — vanilla's
    own tooltip format is evidently not the right thing to copy here.
    Reverted to match build.py exactly: verb "Train", space kept before
    "\\n", no trailing token line.

    `extra` appends free-form text (e.g. "Trainable at Castle and Krepost.").
    <cost> is an engine token, auto-substituted by AoE2 itself.
    """
    melee = getattr(unit.type_50, "displayed_melee_armour", None) if unit.type_50 else None
    pierce = getattr(unit.creatable, "displayed_pierce_armour", None) if unit.creatable else None
    attack = getattr(unit.type_50, "displayed_attack", None) if unit.type_50 else None
    armor_text = f"{melee if melee is not None else 0}/{pierce if pierce is not None else 0}"
    cost_text = _format_cost_text(unit)
    line2 = f"{unit.hit_points} HP | {attack if attack is not None else 0} attack | {armor_text} armor."
    if cost_text:
        line2 += f" Cost: {cost_text}."
    if extra:
        line2 += f" {extra}"
    return f"{verb} <b>{name}<b> (<cost>) \\n{line2}"


def format_unit_extended_tooltip(unit, name: str, tag: str = "") -> str:
    """Build the Castle train-button EXTENDED hover tooltip (name+21000).

    This is a SEPARATE string slot from format_unit_tooltip_help's name+
    100000 entry — see _extended_tooltip_sid's docstring for how this was
    discovered (the user's confirmed-working Elite Budget Knight showed
    EXACTLY this text in-game, not the name+100000 one). Matches build.py's
    own format precisely: verb "Create" (not "Train" — different from
    format_unit_tooltip_help), no "Cost:" breakdown line, ends with a
    bracketed tag instead (e.g. "[Budget Bois unique unit]").
    """
    melee = getattr(unit.type_50, "displayed_melee_armour", None) if unit.type_50 else None
    pierce = getattr(unit.creatable, "displayed_pierce_armour", None) if unit.creatable else None
    attack = getattr(unit.type_50, "displayed_attack", None) if unit.type_50 else None
    armor_text = f"{melee if melee is not None else 0}/{pierce if pierce is not None else 0}"
    line2 = f"{unit.hit_points} HP | {attack if attack is not None else 0} attack | {armor_text} armor."
    if tag:
        line2 += f" [{tag}]"
    return f"Create <b>{name}<b> (<cost>) \\n{line2}"


def _setup_imperial_scorpion_unit(dat: DatFile) -> None:
    """Write Imperial Scorpion unit data into slot 1179 for every civ.

    Matches civ.Units[UNIT_IMP_SCORPION] = civ.Units[542] in KM's civbuilder.cpp,
    plus the buffed projectile pair (1113/1114). Identical for every civ — only
    the upgrade tech (civ-specific, added by the caller) decides who can
    actually research their way into fielding one.
    """
    for civ in dat.civs:
        src = civ.units[_HEAVY_SCORPION]
        if src is None:
            continue
        u = deepcopy(src)
        u.id = _IMP_SCORPION
        # See km_custom_uu.py's identical fix — base_id/copy_id aren't reset
        # by deepcopy and would otherwise keep pointing at the predecessor
        # unit (Heavy Scorpion, 542). Not known to be hero/campaign-linked
        # like Gendarme's base, but reset for consistency/correctness.
        u.base_id = _IMP_SCORPION
        u.copy_id = _IMP_SCORPION
        u.name = "IMPBAL"
        # Without these, the unit keeps showing "Heavy Scorpion" (the
        # predecessor's inherited dll fields) everywhere in the UI even
        # after a successful upgrade — same bug class as km_custom_uu's
        # units, fixed there first.
        # creation/help MUST sit at name+1000/name+100000 — this is the
        # vanilla engine convention the Castle hover-tooltip actually keys
        # off (see _creation_sid/_help_sid docstring). language_dll_hotkey_text
        # deliberately left untouched — same reasoning as km_custom_uu.py.
        u.language_dll_name     = IMP_SCORPION_NAME_SID
        u.language_dll_help     = _help_sid(IMP_SCORPION_NAME_SID)
        u.language_dll_creation = _creation_sid(IMP_SCORPION_NAME_SID)
        u.hit_points = 60
        if u.type_50:
            u.type_50.displayed_attack = 18
            for atk in u.type_50.attacks:
                if atk.class_ == 3:   # ranged/pierce damage class
                    atk.amount = 18
            u.type_50.projectile_unit_id = _IMP_SCORPION_PROJECTILE
        if u.creatable:
            u.creatable.secondary_projectile_unit = _IMP_SCORPION_PROJECTILE
        u.enabled = 0
        civ.units[_IMP_SCORPION] = u

        for proj_id, label in ((_IMP_SCORPION_PROJECTILE, "Projectile Imperial Scorpion"),
                                (_IMP_SCORPION_PROJECTILE_FIRE, "Projectile Imperial Scorpion (Fire)")):
            p = civ.units[proj_id]
            if p is None or p.type_50 is None:
                continue
            p.name = label
            p.type_50.displayed_attack = 14
            for atk in p.type_50.attacks:
                if atk.class_ == 3:
                    atk.amount = 14


def _setup_royal_battle_elephant_unit(dat: DatFile) -> None:
    """Write Royal Battle Elephant unit data into slot 1180 for every civ.

    Matches civ.Units[UNIT_ROYAL_ELEPHANT] = civ.Units[1134] in KM's source.
    KM left the cosmetic graphic overrides commented out ("seem wrong"), so we
    keep Elite Battle Elephant's graphics as-is, same as upstream.
    """
    for civ in dat.civs:
        src = civ.units[_ELITE_BATTLE_ELEPHANT]
        if src is None:
            continue
        u = deepcopy(src)
        u.id = _ROYAL_ELEPHANT
        u.base_id = _ROYAL_ELEPHANT
        u.copy_id = _ROYAL_ELEPHANT
        u.name = "RBATELE"
        u.language_dll_name     = ROYAL_ELEPHANT_NAME_SID
        u.language_dll_help     = _help_sid(ROYAL_ELEPHANT_NAME_SID)
        u.language_dll_creation = _creation_sid(ROYAL_ELEPHANT_NAME_SID)
        u.hit_points = 330
        if u.type_50:
            u.type_50.displayed_attack = 15
            for atk in u.type_50.attacks:
                if atk.class_ == 4:   # melee damage class
                    atk.amount = 15
            for arm in u.type_50.armours:
                if arm.class_ == 3:   # pierce armour class
                    arm.amount = 4
        if u.creatable:
            u.creatable.displayed_pierce_armour = 4
        u.enabled = 0
        civ.units[_ROYAL_ELEPHANT] = u


def _setup_royal_lancer_unit(dat: DatFile) -> None:
    """Write Royal Lancer unit data into slot 1181 for every civ.

    Matches civ.Units[UNIT_ROYAL_LANCER] = civ.Units[1372] in KM's source,
    including the Cuman Chief graphic reskin (graphic IDs 10508-10513 are
    vanilla DE assets, verified present in the dat).
    """
    for civ in dat.civs:
        src = civ.units[_ELITE_STEPPE_LANCER]
        if src is None:
            continue
        u = deepcopy(src)
        u.id = _ROYAL_LANCER
        u.base_id = _ROYAL_LANCER
        u.copy_id = _ROYAL_LANCER
        u.name = "RSLANCER"
        u.language_dll_name     = ROYAL_LANCER_NAME_SID
        u.language_dll_help     = _help_sid(ROYAL_LANCER_NAME_SID)
        u.language_dll_creation = _creation_sid(ROYAL_LANCER_NAME_SID)
        u.hit_points = 100
        u.standing_graphic = (10510, 10511)
        u.dying_graphic = 10509
        if u.type_50:
            u.type_50.displayed_attack = 13
            u.type_50.attack_graphic = 10508
            for atk in u.type_50.attacks:
                if atk.class_ == 4:   # melee damage class
                    atk.amount = 13
        if u.dead_fish:
            u.dead_fish.walking_graphic = 10513
        u.enabled = 0
        civ.units[_ROYAL_LANCER] = u


def _add_upgrade_tier_tech(dat: DatFile, civ_index: int, *, name: str,
                           from_units: list[int], to_unit: int,
                           prereq_tech: int, location: int, button: int,
                           research_time: int, icon_id: int,
                           costs: list[tuple[int, int]],
                           hot_key_id: int, name_sid: int) -> int:
    """Create a civ-owned "next tier" unit-upgrade tech (KM Royal/Imperial pattern).

    Upgrades both from_units (e.g. base + elite tier) into to_unit, gated on
    prereq_tech (the elite/make-avail tech), reusing the predecessor's
    building/button slot — exactly one of the unit-line techs sharing that
    button is ever active for a given civ, so this never collides in-game.
    Returns the new tech ID.

    name_sid is an EXISTING vanilla id from CAMPAIGN_STRING_POOL; description/
    help/tech-tree ids are all DERIVED from it via the fixed vanilla offset
    convention (_creation_sid/_help_sid/_tech_tree_sid) — NOT independent pool
    slots. The Castle hover tooltip turned out to key off this exact
    arithmetic relationship, not just "any pre-existing id" (see those
    helpers' docstring for how this was confirmed).
    """
    eff = Effect(
        name=name,
        effect_commands=[
            EffectCommand(type=EC_UPGRADE, a=fu, b=to_unit, c=-1, d=0.0)
            for fu in from_units
        ],
    )
    eff_id = _append_effect(dat, eff)
    tech = _make_tech(
        name=name, effect_id=eff_id, civ_index=civ_index,
        age_req=prereq_tech, location=location, button=button,
        research_time=research_time, icon_id=icon_id,
        lang_name=name_sid, lang_desc=_creation_sid(name_sid),
        lang_help=_help_sid(name_sid), lang_tech_tree=_tech_tree_sid(name_sid),
        hot_key_id=hot_key_id,
    )
    n = min(len(costs), 3)
    tech.resource_costs = tuple(
        ResearchResourceCost(type=t, amount=a, flag=1) for t, a in costs[:n]
    ) + tuple(ResearchResourceCost(type=-1, amount=0, flag=0) for _ in range(3 - n))
    # _make_tech defaults repeatable=0, but every comparable vanilla "next
    # tier" upgrade tech (Paladin, Elite Battle Elephant, Elite Steppe
    # Lancer) has repeatable=1. Without it the engine appears to evaluate
    # this tech's eligibility once and never reconsider it — exactly the
    # bug behind Royal Battle Elephant never showing a button even after
    # its prerequisite (Elite Battle Elephant) completes via a free-tech
    # bonus fired well after this tech was created. Same class of fix as
    # _append_unique_tech_stubs' repeatable=1 override below.
    tech.repeatable = 1
    _append_tech(dat, tech)
    return len(dat.techs) - 1


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
    tech = _make_tech(name=name, effect_id=eff_id,
                      civ_index=civ_index, age_req=age_req)
    # _make_tech defaults repeatable=0, but vanilla's own free-tech auto-fire
    # wrappers (e.g. Bulgarians' tech 693, Lithuanians'/Poles' 790/791) are
    # all repeatable=1 — matches the same fix applied to the "next tier"
    # upgrade techs themselves in _add_upgrade_tier_tech.
    tech.repeatable = 1
    dat.techs.append(tech)


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


def _market_tech_ids(dat: DatFile) -> list[int]:
    """Return IDs of all techs whose primary research location is the Market."""
    BUILDING_MARKET = 84
    out = []
    for i, t in enumerate(dat.techs):
        locs = getattr(t, 'research_locations', [])
        if locs and locs[0].location_id == BUILDING_MARKET:
            out.append(i)
    return out


def _barracks_tech_ids(dat: DatFile) -> list[int]:
    """Return IDs of all techs whose primary research location is the Barracks."""
    BUILDING_BARRACKS = 12
    out = []
    for i, t in enumerate(dat.techs):
        locs = getattr(t, 'research_locations', [])
        if locs and locs[0].location_id == BUILDING_BARRACKS:
            out.append(i)
    return out


def _find_upgrade_tech(dat: DatFile, from_unit: int, to_unit: int,
                       civ_filter: int | None = None) -> int | None:
    """Return the tech ID whose effect upgrades from_unit → to_unit, or None.

    civ_filter restricts the search to a specific civ's tech. Required for
    upgrade techs that are civ-specific (e.g. the Royal Battle Elephant tech
    created per-civ by bonus 309) rather than global — without it, a
    multi-civ build could match a DIFFERENT civ's copy of the tech.
    """
    for i, tech in enumerate(dat.techs):
        if civ_filter is not None and tech.civ != civ_filter:
            continue
        eid = tech.effect_id
        if eid < 0 or eid >= len(dat.effects):
            continue
        for ec in dat.effects[eid].effect_commands:
            if ec.type == EC_UPGRADE and int(ec.a) == from_unit and int(ec.b) == to_unit:
                return i
    return None


def _create_bonus_handler(dat: DatFile, bonus_id: int, civ_index: int,
                          multiplier: int, extra_strings: list[dict],
                          extra_unit_strings: list[dict] | None = None) -> bool:
    """
    Handle a single createCivBonus-style bonus.  Returns True if handled.

    Source: fritz-net/AoE2-Civbuilder modding/civbuilder.cpp createCivBonuses().
    Only implements bonuses that have a direct effect mapping; complex structural
    bonuses (farm layouts, mill requirements) are still skipped.

    extra_strings collects {"sid", "name"} entries for any new player-visible
    research button this call creates, so the caller can write matching
    key-value string text (button label / hover / help / tech-tree) — mirrors
    how _append_unique_tech_stubs' castle/imperial UT strings are surfaced.

    extra_unit_strings (optional) collects {"sid", "name", "help_text"}
    entries for any new player-visible UNIT this call creates (distinct from
    extra_strings, which is research-button text) — used by bonuses
    308/309/310 to attach a proper "Train <b>Name<b> (<cost>) \\nstats"
    tooltip instead of the bare-name fallback in FIXED_UNIT_NAME_STRINGS.
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

    if bonus_id == 155:          # {ELITE_BATTLE_ELEPHANT, Royal Battle Elephant} free
        # Royal Battle Elephant is a civ-specific tech created by bonus 309 —
        # only meaningful (and only present in the DAT) if 309 is also on
        # this civ's bonus list and was applied first. civ_def bonus order
        # matters here: 309 must come before 155 in bonuses[0].
        #
        # Staged on purpose (two auto-fire techs, not one): vanilla's
        # telescoping free-tech chains (e.g. Bulgarians' free Man-at-Arms ->
        # Long Swordsman -> Two-Handed Swordsman, tech 693) work because each
        # tier has its OWN age gate strictly higher than the previous tier's,
        # so each tier's "now eligible" moment always lands on a fresh age
        # transition — the engine's natural recheck point. Royal Battle
        # Elephant has no age gate of its own (only "Elite Battle Elephant
        # done"), so zeroing both techs' cost unconditionally from turn 0
        # gives the engine no later event to notice Royal became eligible
        # once Elite finishes mid-Imperial-Age. Gating the second wrapper on
        # tech 631 itself makes ITS firing (and therefore its EC_TECH_COST/
        # TIME application to Royal) a discrete event correlated with
        # Elite's actual completion, instead of speculative turn-0 state.
        _ELITE_BATTLE_ELEPHANT_TECH = 631
        _add_auto_fire_tech(dat, civ_index,
                            _free_tech_cmds([_ELITE_BATTLE_ELEPHANT_TECH]),
                            name="C-Bonus, free Elite Battle Elephant")
        royal_tid = _find_upgrade_tech(dat, _BATTLE_ELEPHANT, _ROYAL_ELEPHANT,
                                       civ_filter=civ_index)
        if royal_tid is not None:
            _add_auto_fire_tech(dat, civ_index,
                                _free_tech_cmds([royal_tid]),
                                age_req=_ELITE_BATTLE_ELEPHANT_TECH,
                                name="C-Bonus, free Royal Battle Elephant")
        else:
            print("       WARNING: bonus 155 fired without a Royal Battle Elephant "
                  "tech for this civ (bonus 309 missing or applied after 155) — "
                  "only Elite Battle Elephant made free")
        return True

    if bonus_id == 261:          # Elite Steppe Lancer (+ Royal Lancer) upgrade free
        # KM's original source frees BOTH Elite Steppe Lancer and Royal
        # Lancer from one combined effect (mirrors bonus 155's
        # ELITE_BATTLE_ELEPHANT+royalElephantTech pairing). Royal Lancer
        # didn't exist in this codebase when 261 was first implemented here,
        # so it only freed the elite tier — same gap 155 had, same staged
        # fix: the second wrapper is gated on tid itself, not unconditional,
        # so its cost-zeroing lands as a fresh event correlated with the
        # elite tier's completion (see _add_upgrade_tier_tech's repeatable
        # comment for the other half of this fix).
        tid = _find_upgrade_tech(dat, _STEPPE_LANCER, _ELITE_STEPPE_LANCER)
        if tid is not None:
            _add_auto_fire_tech(dat, civ_index,
                                _free_tech_cmds([tid]),
                                name="C-Bonus, Elite Steppe Lancer free")
            royal_tid = _find_upgrade_tech(dat, _STEPPE_LANCER, _ROYAL_LANCER,
                                           civ_filter=civ_index)
            if royal_tid is not None:
                _add_auto_fire_tech(dat, civ_index,
                                    _free_tech_cmds([royal_tid]),
                                    age_req=tid,
                                    name="C-Bonus, Royal Lancer free")
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

    if bonus_id == 234:          # Market techs cost no gold
        mkt_ids = _market_tech_ids(dat)
        cmds = [EffectCommand(type=EC_TECH_COST, a=tid, b=3, c=0, d=0.0)
                for tid in mkt_ids]
        if cmds:
            _add_auto_fire_tech(dat, civ_index, cmds,
                                name="C-Bonus, market no gold")
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

    if bonus_id == 290:          # Barracks technologies cost -50%
        factor = 0.5 ** mult
        cmds = [
            EffectCommand(type=EC_TECH_COST, a=tid, b=rc.type, c=0, d=rc.amount * factor)
            for tid in _barracks_tech_ids(dat)
            for rc in dat.techs[tid].resource_costs
            if rc.flag == 1
        ]
        if cmds:
            _add_auto_fire_tech(dat, civ_index, cmds,
                                name="C-Bonus, -50% barracks tech cost")
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

    if bonus_id == 247:          # Parthian Tactics available in Castle Age
        # Find all Imperial Age techs at the Archery Range (= Parthian Tactics).
        # We scan rather than hardcode because tech IDs can drift across versions.
        _ARCHERY_RANGE = 87
        tt_eff_id = dat.civs[civ_index].tech_tree_id
        for orig_tid, t in enumerate(dat.techs):
            locs = getattr(t, 'research_locations', [])
            if not locs or locs[0].location_id != _ARCHERY_RANGE:
                continue
            if 103 not in t.required_techs:   # must be gated on Imperial Age
                continue
            new_tech = deepcopy(t)
            new_tech.civ = civ_index
            reqs = list(new_tech.required_techs)
            reqs[reqs.index(103)] = 102        # shift: Imperial → Castle Age
            new_tech.required_techs = tuple(reqs)
            eid = t.effect_id
            if 0 <= eid < len(dat.effects):
                new_eff = deepcopy(dat.effects[eid])
                dat.effects.append(new_eff)
                new_tech.effect_id = len(dat.effects) - 1
            dat.techs.append(new_tech)
            dat.effects[tt_eff_id].effect_commands.append(
                EffectCommand(type=102, a=-1, b=-1, c=-1, d=float(orig_tid))
            )
        return True

    if bonus_id == 221:          # Spearman/Militia upgrades one age earlier (except Man-at-Arms)
        # Shift Castle Age (102) Barracks techs to Feudal Age (101), and
        # Imperial Age (103) Barracks techs to Castle Age (102).
        # Man-at-Arms (gated on Feudal Age 101) is intentionally excluded.
        _SHIFT = {103: 102, 102: 101}
        tt_eff_id = dat.civs[civ_index].tech_tree_id
        for orig_tid in _barracks_tech_ids(dat):
            t = dat.techs[orig_tid]
            reqs = list(t.required_techs)
            shift_idx = next((j for j, r in enumerate(reqs) if r in _SHIFT), None)
            if shift_idx is None:
                continue   # no age gate to shift (or Feudal Age gate = Man-at-Arms)
            new_tech = deepcopy(t)
            new_tech.civ = civ_index
            new_reqs = list(new_tech.required_techs)
            new_reqs[shift_idx] = _SHIFT[reqs[shift_idx]]
            new_tech.required_techs = tuple(new_reqs)
            eid = t.effect_id
            if 0 <= eid < len(dat.effects):
                new_eff = deepcopy(dat.effects[eid])
                dat.effects.append(new_eff)
                new_tech.effect_id = len(dat.effects) - 1
            dat.techs.append(new_tech)
            dat.effects[tt_eff_id].effect_commands.append(
                EffectCommand(type=102, a=-1, b=-1, c=-1, d=float(orig_tid))
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
            # See _add_upgrade_tier_tech's comment — vanilla's comparable
            # tech-gated-on-another-tech upgrades (Paladin, Elite Battle
            # Elephant) all use repeatable=1, not the repeatable=0 default.
            # Applied here defensively for the same dependency shape (gated
            # on avail_tech_id completing, not just an age).
            repeatable=1,
            research_locations=[ResearchLocation(location_id=-1, research_time=0,
                                                 button_id=0, hot_key_id=-1)],
        )
        dat.techs.append(upgrade_tech)
        return True

    # ── Elite-tier "next step" upgrades ───────────────────────────────────────
    if bonus_id == 308:          # Heavy Scorpion → Imperial Scorpion
        _setup_imperial_scorpion_unit(dat)
        # name_sid/desc_sid reused from the unit's own fixed pool sids — the
        # tech conceptually represents "Imperial Scorpion" too, same pattern
        # as km_custom_uu.py's elite tech reusing the elite unit's strings.
        # No separate extra_strings entry needed: the extra_unit_strings
        # entry below already writes both ids.
        _add_upgrade_tier_tech(
            dat, civ_index, name="Imperial Scorpion",
            from_units=[_SCORPION, _HEAVY_SCORPION], to_unit=_IMP_SCORPION,
            prereq_tech=239, location=49, button=8, research_time=150,
            icon_id=38, costs=[(0, 1200), (1, 1000)],
            hot_key_id=_HEAVY_SCORPION_HOTKEY,
            name_sid=IMP_SCORPION_NAME_SID,
        )
        if extra_unit_strings is not None:
            unit_obj = dat.civs[civ_index].units[_IMP_SCORPION]
            extra_unit_strings.append({
                "sid": IMP_SCORPION_NAME_SID, "name": "Imperial Scorpion",
                "desc_sid": _help_sid(IMP_SCORPION_NAME_SID),
                "help_text": format_unit_tooltip_help(
                    unit_obj, "Imperial Scorpion", extra="Trainable at Siege Workshop."),
                "ext_sid": _extended_tooltip_sid(IMP_SCORPION_NAME_SID),
                "ext_text": format_unit_extended_tooltip(
                    unit_obj, "Imperial Scorpion", tag="unique unit"),
            })
        # Cosmetic fire-arrow reskin once the civ researches Chemistry (47).
        # KM appends this to the global Chemistry effect; we scope it to a
        # civ-owned auto-fire tech instead so a civ=-1 effect shared by every
        # other civ in the DAT is never mutated.
        _add_auto_fire_tech(
            dat, civ_index,
            [EffectCommand(type=EC_UPGRADE, a=_IMP_SCORPION_PROJECTILE,
                           b=_IMP_SCORPION_PROJECTILE_FIRE, c=-1, d=0.0)],
            age_req=47, name="Imperial Scorpion fire arrow (Chemistry)",
        )
        return True

    if bonus_id == 309:          # Elite Battle Elephant → Royal Battle Elephant
        _setup_royal_battle_elephant_unit(dat)
        _add_upgrade_tier_tech(
            dat, civ_index, name="Royal Battle Elephant",
            from_units=[_BATTLE_ELEPHANT, _ELITE_BATTLE_ELEPHANT], to_unit=_ROYAL_ELEPHANT,
            prereq_tech=631, location=101, button=9, research_time=200,
            icon_id=121, costs=[(0, 1200), (3, 1000)],
            hot_key_id=_ELITE_BATTLE_ELEPHANT_HOTKEY,
            name_sid=ROYAL_ELEPHANT_NAME_SID,
        )
        if extra_unit_strings is not None:
            unit_obj = dat.civs[civ_index].units[_ROYAL_ELEPHANT]
            extra_unit_strings.append({
                "sid": ROYAL_ELEPHANT_NAME_SID, "name": "Royal Battle Elephant",
                "desc_sid": _help_sid(ROYAL_ELEPHANT_NAME_SID),
                "help_text": format_unit_tooltip_help(
                    unit_obj, "Royal Battle Elephant", extra="Trainable at Stable."),
                "ext_sid": _extended_tooltip_sid(ROYAL_ELEPHANT_NAME_SID),
                "ext_text": format_unit_extended_tooltip(
                    unit_obj, "Royal Battle Elephant", tag="unique unit"),
            })
        return True

    if bonus_id == 310:          # Elite Steppe Lancer → Royal Lancer
        _setup_royal_lancer_unit(dat)
        _add_upgrade_tier_tech(
            dat, civ_index, name="Royal Lancer",
            from_units=[_STEPPE_LANCER, _ELITE_STEPPE_LANCER], to_unit=_ROYAL_LANCER,
            prereq_tech=715, location=101, button=9, research_time=100,
            icon_id=123, costs=[(0, 1200), (3, 900)],
            hot_key_id=_ELITE_STEPPE_LANCER_HOTKEY,
            name_sid=ROYAL_LANCER_NAME_SID,
        )
        if extra_unit_strings is not None:
            unit_obj = dat.civs[civ_index].units[_ROYAL_LANCER]
            extra_unit_strings.append({
                "sid": ROYAL_LANCER_NAME_SID, "name": "Royal Lancer",
                "desc_sid": _help_sid(ROYAL_LANCER_NAME_SID),
                "help_text": format_unit_tooltip_help(
                    unit_obj, "Royal Lancer", extra="Trainable at Stable."),
                "ext_sid": _extended_tooltip_sid(ROYAL_LANCER_NAME_SID),
                "ext_text": format_unit_extended_tooltip(
                    unit_obj, "Royal Lancer", tag="unique unit"),
            })
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
    extra_strings: list[dict] = []
    extra_unit_strings: list[dict] = []
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

        if _create_bonus_handler(dat, bonus_id, civ_index, multiplier, extra_strings, extra_unit_strings):
            applied += 1
        else:
            skipped.append(bonus_id)

    print(f"       Bonuses: {applied} techs applied, "
          f"{len(skipped)} bonus IDs skipped (not in catalog): {skipped[:8]}"
          + ("…" if len(skipped) > 8 else ""))

    bonus_result = {"applied": applied, "skipped": skipped, "extra_tech_strings": extra_strings,
                    "extra_unit_strings": extra_unit_strings}

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
    km_uu_is_custom = km_uu_index is not None and km_uu_index in km_custom_uu.PRESETS

    # For nullification: treat a recognised vanilla/custom KM UU the same as a
    # custom UU — don't preserve the original civ's UU techs (the desired UU
    # will be allocated later).
    suppress_preserve = has_custom_uu or km_uu_is_vanilla or km_uu_is_custom

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
    elif not (km_uu_is_vanilla or km_uu_is_custom):
        # Only truly "skipped" when no UU is being set at all. A vanilla KM
        # UU reuse (km_uu_is_vanilla, e.g. bonuses[1]=[0] → Longbowman) or a
        # from-scratch KM-custom UU (km_uu_is_custom) is handled later by
        # _apply_km_uu / km_custom_uu.append_km_custom_uu, which print their
        # own accurate line — printing "skipped" here as well was misleading
        # since the UU does in fact get applied via that other path.
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
    _ut_pool_base = UT_POOL_OFFSET + civ_index * UT_POOL_SLOTS_PER_CIV
    castle_ut_sid = _campaign_sid(_ut_pool_base + 0)
    imp_ut_sid    = _campaign_sid(_ut_pool_base + 1)
    castle_ut_desc_sid = _help_sid(castle_ut_sid)
    imp_ut_desc_sid    = _help_sid(imp_ut_sid)
    castle_ut_tech_id: int | None = None
    imp_ut_tech_id:    int | None = None
    castle_ut_pending_uu_subs: list = []
    imp_ut_pending_uu_subs:    list = []
    if castle_ut_entries or imperial_ut_entries:
        (castle_ut_sid, imp_ut_sid, castle_ut_tech_id, imp_ut_tech_id,
         castle_ut_desc_sid, imp_ut_desc_sid,
         castle_ut_pending_uu_subs, imp_ut_pending_uu_subs) = (
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
    km_uu_custom_unit_strings: list[dict] = []
    if km_uu_is_vanilla:
        km_uu_make_avail_tech_id, km_uu_elite_tech_id = _apply_km_uu(dat, civ_index, km_uu_index)
        # Extract the actual elite UNIT id (not just the tech id) from the
        # elite-upgrade tech's own EC_UPGRADE command (a=base, b=elite) — the
        # standard vanilla elite-upgrade convention — so deferred UU
        # substitutions (see UU_SUBSTITUTION_TYPES) can use this civ's real
        # elite UU rather than the catalog source civ's hardcoded one.
        if 0 <= km_uu_elite_tech_id < len(dat.techs):
            elite_eff_id = dat.techs[km_uu_elite_tech_id].effect_id
            if 0 <= elite_eff_id < len(dat.effects):
                for ec in dat.effects[elite_eff_id].effect_commands:
                    if ec.type == EC_UPGRADE:
                        elite_uu_id = ec.b
                        break
    elif km_uu_is_custom:
        # Pool-based allocation (see CAMPAIGN_STRING_POOL docstring) for the
        # two "name" ids; desc/help ids are DERIVED via _help_sid (name+
        # 100000) — the vanilla engine convention the Castle hover tooltip
        # actually keys off, not an independent pool slot (confirmed live —
        # see _help_sid's docstring for how this was tracked down).
        pool_base = civ_index * KM_UU_POOL_SLOTS_PER_CIV
        uu_name_sid    = _campaign_sid(pool_base + 0)
        elite_name_sid = _campaign_sid(pool_base + 1)
        uu_desc_sid    = _help_sid(uu_name_sid)
        elite_desc_sid = _help_sid(elite_name_sid)
        # Krepost-trainability is conditional on the civ already having
        # Krepost available — we only ADD the train slot here, we don't
        # grant Krepost itself (see km_custom_uu.append_km_custom_uu's
        # has_krepost docstring for what's and isn't covered).
        # Krepost-presence signal: bonus 93 ("Can build Krepost") is the
        # actual mechanism (maps to vanilla tech 695, generically deepcopied
        # per-civ by _apply_bonuses' civ_bonus_techs path below) — confirmed
        # against a real civ_def (ignore/barracks_enjoyers.json) that grants
        # Krepost via bonus 93 WITHOUT listing building 1251 in tree[1] at
        # all. tree[1] membership is checked too as a defensive secondary
        # signal, but bonus 93 is the one that's actually load-bearing.
        _bonuses_pre = civ_def.get("bonuses", [[]])
        _civ_bonuses_pre = _bonuses_pre[0] if _bonuses_pre and isinstance(_bonuses_pre[0], list) else []
        has_krepost_bonus = any(isinstance(e, (list, tuple)) and e and e[0] == 93
                                for e in _civ_bonuses_pre)
        _tree_pre = civ_def.get("tree", [[], [], []])
        has_krepost_tree = (len(_tree_pre) > 1 and isinstance(_tree_pre[1], list)
                            and 1251 in _tree_pre[1])
        has_krepost = has_krepost_bonus or has_krepost_tree
        result = km_custom_uu.append_km_custom_uu(
            dat, civ_index, km_uu_index, uu_name_sid, uu_desc_sid,
            elite_name_sid, elite_desc_sid, has_krepost=has_krepost)
        uu_unit_id, elite_unit_id, km_uu_make_avail_tech_id, km_uu_elite_tech_id = result
        elite_uu_id = elite_unit_id
        preset_name = km_custom_uu.PRESETS[km_uu_index]["name"]
        # No separate extra_tech_strings entry for the elite tech — it
        # reuses elite_name_sid/elite_desc_sid directly (same ids as the
        # elite unit's own strings below), so writing the unit strings
        # already covers the tech's button text too.
        _trainable_extra = "Trainable at Castle and Krepost." if has_krepost else "Trainable at Castle."
        uu_obj    = dat.civs[civ_index].units[uu_unit_id]
        elite_obj = dat.civs[civ_index].units[elite_unit_id]
        km_uu_custom_unit_strings = [
            {"sid": uu_name_sid, "name": preset_name, "desc_sid": uu_desc_sid,
             "help_text": format_unit_tooltip_help(uu_obj, preset_name, extra=_trainable_extra),
             "ext_sid": _extended_tooltip_sid(uu_name_sid),
             "ext_text": format_unit_extended_tooltip(uu_obj, preset_name, tag=f"{alias} unique unit")},
            {"sid": elite_name_sid, "name": f"Elite {preset_name}", "desc_sid": elite_desc_sid,
             "help_text": format_unit_tooltip_help(elite_obj, f"Elite {preset_name}", extra=_trainable_extra),
             "ext_sid": _extended_tooltip_sid(elite_name_sid),
             "ext_text": format_unit_extended_tooltip(elite_obj, f"Elite {preset_name}", tag=f"{alias} unique unit")},
        ]
        print(f"       KM-custom UU index {km_uu_index} ({preset_name}): "
              f"make-avail tech {km_uu_make_avail_tech_id}, elite tech {km_uu_elite_tech_id}"
              + (", Krepost-trainable" if has_krepost else ""))
    elif km_uu_index is not None:
        msg = (f"KM UU index {km_uu_index} is a KM-custom unit "
               f"— not supported in standalone builder; vanilla UU preserved")
        print(f"       WARNING: {msg}")
        warnings.append(msg)

    # 6c. Patch deferred UU-substitution effect commands (see
    #     UU_SUBSTITUTION_TYPES / _build_ut_effect_cmds) now that this civ's
    #     own elite UU id is fully resolved across all 3 possible paths above.
    mercenary_slot_ready = False
    for pending in (castle_ut_pending_uu_subs, imp_ut_pending_uu_subs):
        for eff_id, ec in pending:
            if elite_uu_id < 0:
                continue
            if ec.type == 12:
                # Castle-btn4 "free train" mechanic needs the dedicated
                # _MERCENARY_UU_SLOT clone, not the civ's real elite UU
                # directly (see _setup_mercenary_uu_unit's docstring).
                if not mercenary_slot_ready:
                    _setup_mercenary_uu_unit(dat, civ_index, elite_uu_id)
                    mercenary_slot_ready = True
                ec.a = _MERCENARY_UU_SLOT
            else:
                ec.a = elite_uu_id
            dat.effects[eff_id].effect_commands.append(ec)
    if (castle_ut_pending_uu_subs or imp_ut_pending_uu_subs) and elite_uu_id < 0:
        msg = ("Castle/Imperial UT references this civ's own elite unique "
               "unit, but this civ has no UU defined — effect left as a no-op.")
        print(f"       WARNING: {msg}")
        warnings.append(msg)

    # 7. Apply bonuses from catalog.
    bonus_results: dict = {"applied": 0, "skipped": [], "team_applied": 0, "team_total": 0,
                           "extra_tech_strings": [], "extra_unit_strings": []}
    if "bonuses" in civ_def:
        bonus_results = _apply_bonuses(dat, civ_index, civ_def, tb_eff_id)
        bonus_results.setdefault("extra_unit_strings", [])
    bonus_results["extra_unit_strings"].extend(km_uu_custom_unit_strings)

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
        "castle_ut_desc_sid":    castle_ut_desc_sid,
        "imp_ut_desc_sid":       imp_ut_desc_sid,
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


# Effect types that hardcode a reference to the SOURCE civ's own unique unit
# rather than a generic/universal unit or attribute — team-scoped variants of
# EC_ENABLE (type 7, used by First Crusade/bonus 29 castle UT) and (type 12,
# used by Cuman Mercenaries/bonus 9 imperial UT). Confirmed by inspecting the
# vanilla DAT: tech 690 (Cuman Mercenaries) type=12 command's `a` is unit 1260
# = Cumans' own Elite Kipchak; tech 756 (First Crusade) type=7 command's `a`
# is unit 1658 = Sicilians' own Serjeant. Blindly copying these to another
# civ references the WRONG unit and was confirmed live to also corrupt the
# Castle research-button tooltip (falls back to a vanilla Scenario Editor
# placeholder string, "Click to enter a filename..."). In both cases only the
# `a` field is civ-specific — `b`/`c`/`d` reference universal infrastructure
# (e.g. b=109 = Town Center, the same unit id for every civ) and are safe to
# keep as-is once `a` is substituted with the CURRENT civ's own elite UU id.
UU_SUBSTITUTION_TYPES = (7, 12)

# type=12 (Cuman Mercenaries-style "team gets free trains at the Castle")
# specifically needs a DEDICATED unit slot, not just a substituted unit id —
# Cumans' own MKIPCHAK (1260) is a SEPARATE unit from the normally-trained
# Elite Kipchak (1233), because resource_costs/train_locations live on the
# unit object itself: reusing the civ's real elite UU directly would make its
# NORMAL training (e.g. at the Stable) also require resource 214, breaking it
# for everyone who hasn't researched this UT. _MERCENARY_UU_SLOT (1261,
# "CUMANDISABLED" in the base dat) is an unused-everywhere spare slot already
# shaped for exactly this purpose — confirmed via a full 60-civ scan that no
# civ currently wires its train_locations to a real building. We overwrite
# its resource_costs/train_locations with MKIPCHAK's own EXACT, confirmed-
# shipping values (not this slot's pre-existing ones, which differ slightly —
# e.g. reference resource 215 — and were likely an abandoned dev iteration,
# given the slot's own name). type=7 (First Crusade) does NOT need this: it
# makes Town Centers passively spawn the unit (a separate production path
# from training/resource_costs entirely), so direct substitution is correct
# and sufficient — confirmed Sicilians' own Serjeant (1658) is literally the
# SAME unit used for normal training, no dedicated duplicate exists for it.
_MERCENARY_UU_SLOT = 1261


def _setup_mercenary_uu_unit(dat: DatFile, civ_index: int, elite_uu_id: int) -> None:
    """Clone this civ's own elite UU into _MERCENARY_UU_SLOT for the Castle
    btn4 "free unit" mechanic (Cuman Mercenaries/bonus 9), preserving its
    name/graphics/combat stats but giving it MKIPCHAK's own train_location
    (Castle, btn4) and resource_costs (1 unit of resource 214 — the "free
    token" tech 707 sets to 5 per Castle, copied verbatim/unmodified).
    """
    elite = dat.civs[civ_index].units[elite_uu_id]
    clone = deepcopy(elite)
    clone.id = _MERCENARY_UU_SLOT
    # Stay hidden until the type=12 "team enable" command fires at research
    # time — matches MKIPCHAK's own baseline (enabled=0 in the vanilla dat).
    clone.enabled = 0
    clone.creatable.train_locations = [
        TrainLocation(train_time=12, unit_id=BUILDING_CASTLE, button_id=4, hot_key_id=16730),
    ]
    clone.creatable.resource_costs = (
        ResourceCost(type=214, amount=1, flag=1),
        ResourceCost(type=-1, amount=0, flag=0),
        ResourceCost(type=4, amount=1, flag=0),
    )
    dat.civs[civ_index].units[_MERCENARY_UU_SLOT] = clone


def _build_ut_effect_cmds(dat: DatFile, entries: list, label: str,
                          lookup: dict[int, int]) -> tuple[list, list]:
    """Collect effect commands for a UT's bonus entries.

    `entries` is bonuses[2] (castle) or bonuses[3] (imperial) from the KM JSON.
    `lookup` maps KM bonus_id → vanilla DAT tech ID; pass _KM_CASTLE_UT_TECHS or
    _KM_IMP_UT_TECHS depending on which slot is being built. We then deep-copy
    that tech's effect commands into our new UT stub so research actually fires
    the right behavior. Previously this called civ_bonus_techs() which uses an
    entirely different bonus-ID namespace and produced wrong effects (e.g.
    Stirrups would research Britons' "Castle 15% cheaper" tech).

    Returns (cmds, pending_uu_subs). `pending_uu_subs` holds EffectCommand
    templates (see UU_SUBSTITUTION_TYPES) whose `.a` still needs to be set to
    THIS civ's own elite UU unit id once it's known — the UU is sometimes
    resolved later than the UT stub (e.g. KM-custom UU presets), so the caller
    must patch `.a` in and append these to the tech's effect afterward. Until
    patched, the UT silently has no functional effect for that specific entry
    (better than referencing another civ's unit).
    """
    cmds: list = []
    pending_uu_subs: list = []
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
        all_cmds = dat.effects[eid].effect_commands
        for ec in all_cmds:
            if ec.type in (EC_ENABLE, EC_UPGRADE):
                continue
            if ec.type in UU_SUBSTITUTION_TYPES:
                print(f"       {label} bonus {bonus_id}: deferring unit "
                      f"substitution for type={ec.type} command (needs this "
                      f"civ's own elite UU)")
                for _ in range(multiplier):
                    pending_uu_subs.append(deepcopy(ec))
                continue
            for _ in range(multiplier):
                cmds.append(deepcopy(ec))
    return cmds, pending_uu_subs


def _append_unique_tech_stubs(dat: DatFile, civ_index: int, alias: str,
                               castle_ut_entries: list,
                               imperial_ut_entries: list,
                               ) -> tuple[int, int, int | None, int | None, int, int,
                                          list, list]:
    """Create Castle UT (btn7) and Imperial UT (btn8) from bonus catalog entries.

    Returns (castle_name_sid, imp_name_sid, castle_tech_id, imp_tech_id,
    castle_desc_sid, imp_desc_sid, castle_pending_uu_subs, imp_pending_uu_subs).
    name_sid comes from CAMPAIGN_STRING_POOL (UT_POOL_OFFSET block) — an
    EXISTING vanilla id; desc_sid is DERIVED via _help_sid(name_sid) (name+
    100000), matching the vanilla engine convention the Castle hover tooltip
    actually keys off (see _help_sid's docstring). The pending_uu_subs lists
    (see _build_ut_effect_cmds/UU_SUBSTITUTION_TYPES) must be patched in by
    the caller once this civ's own elite UU id is resolved — apply_civ may
    not know it yet at this point (e.g. KM-custom UU presets resolve later).
    """
    # Default costs: Castle UT = 300 food + 300 gold; Imperial UT = 450 food + 225 stone
    # icon_id 33 = vanilla Castle UT icon; 107 = vanilla Imperial UT icon
    pool_base = UT_POOL_OFFSET + civ_index * UT_POOL_SLOTS_PER_CIV
    ut_configs = [
        (7,  "Castle UT",   102, castle_ut_entries,   300, 3, 300,  33,
         _campaign_sid(pool_base + 0), _KM_CASTLE_UT_TECHS),
        (8,  "Imperial UT", 103, imperial_ut_entries, 450, 2, 225, 107,
         _campaign_sid(pool_base + 1), _KM_IMP_UT_TECHS),
    ]
    used_name_sids: list[int] = []
    used_desc_sids: list[int] = []
    used_tech_ids: list[int | None] = []
    pending_subs_per_slot: list[list] = []
    for (btn, label, age_req, entries, cost_food, cost_b_type, cost_b, icon,
         name_sid, ut_lookup) in ut_configs:
        desc_sid = _help_sid(name_sid)
        used_name_sids.append(name_sid)
        used_desc_sids.append(desc_sid)
        if not entries:
            used_tech_ids.append(None)
            pending_subs_per_slot.append([])
            continue
        cmds, pending_uu_subs = _build_ut_effect_cmds(dat, entries, label, ut_lookup)
        eff_id = _append_effect(dat, Effect(name=f"{alias} {label}", effect_commands=cmds))
        pending_subs_per_slot.append([(eff_id, ec) for ec in pending_uu_subs])
        # Copy hotkey from first entry's vanilla tech so S/D keys work in-game.
        hotkey = -1
        if entries and isinstance(entries[0], (list, tuple)) and entries[0]:
            src_slot = int(entries[0][0])
            src_tid  = ut_lookup.get(src_slot)
            if src_tid is not None and 0 <= src_tid < len(dat.techs):
                src_locs = getattr(dat.techs[src_tid], 'research_locations', [])
                if src_locs:
                    hotkey = src_locs[0].hot_key_id
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
            lang_desc=_creation_sid(name_sid),
            lang_help=desc_sid,
            lang_tech_tree=_tech_tree_sid(name_sid),
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
        used_name_sids[0], used_name_sids[1],
        used_tech_ids[0] if len(used_tech_ids) > 0 else None,
        used_tech_ids[1] if len(used_tech_ids) > 1 else None,
        used_desc_sids[0], used_desc_sids[1],
        pending_subs_per_slot[0] if len(pending_subs_per_slot) > 0 else [],
        pending_subs_per_slot[1] if len(pending_subs_per_slot) > 1 else [],
    )
