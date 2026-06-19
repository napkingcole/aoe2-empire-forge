#!/usr/bin/env python3
"""
generate_ec_list.py
Generates the "ec_list" section of bonus_catalog_raw.json.

Each entry encodes one call to KM's createCivBonus():
  - requires: list of tech IDs that must be researched first (age-gate etc.)
  - ecs:      list of {type, A, B, C, D} dicts matching genieutils EffectCommand fields

Run:  python generate_ec_list.py   (prints JSON to stdout)
"""

import json
import sys

# ── amountTypetoD conversion ─────────────────────────────────────────────────
def atd(value: int, type_: int) -> float:
    """Encode (value, attack/armor class type) into an EC D float.
    Matches KM's C++ amountTypetoD():  SLOBYTE(NewD)=(int8_t)value; HIBYTE(NewD)=(uint8_t)type
    """
    v = value & 0xFF        # low byte (signed int8 wrapped to uint8)
    t = type_ & 0xFF        # high byte (uint8)
    return float(v | (t << 8))


# ── EC builder ───────────────────────────────────────────────────────────────
def ec(t, A, B, C, D):
    return {"type": t, "A": A, "B": B, "C": C, "D": D}


def entry(requires, ecs_list):
    return {"requires": requires, "ecs": ecs_list}


def free_tech_ecs(techs, time_one_index=None):
    """ECs to make each tech in `techs` cost zero and research instantly (time=0).
    time_one_index: if set, that index in techs gets research time 1 instead of 0.
    """
    ecs = []
    for j, tech in enumerate(techs):
        for k in range(4):
            ecs.append(ec(101, tech, k, 0, 0.0))
        time_val = 1.0 if (time_one_index is not None and j == time_one_index) else 0.0
        ecs.append(ec(103, tech, -1, 0, time_val))
    return ecs


# ── Unit class lists (from helpers.h / civbuilder.cpp lines 94-140) ──────────
shock       = [751, 753, 752, 1974, 1976, 1901, 1903]
steppe      = [1370, 1372]
camel       = [329, 330, 207, 1007, 1009, 1263, 282, 556, 1755, 1923]
elephant    = [239, 558, 873, 875, 1120, 1122, 1132, 1134, 1744, 1746]
gunpowder   = [5, 36, 420, 691, 46, 557, 1001, 1003, 771, 773, 1709, 1704, 1706, 1911, 831, 832, 1904, 1907]
foot_archer = [4, 8, 24, 73, 185, 492, 530, 559, 763, 765, 866, 868, 1129, 1131, 1800, 1802, 1968, 1970]
skirmisher  = [6, 7, 1155, 583, 596, 1010, 1012]
spear       = [93, 358, 359, 1786, 1787, 1788]
light_cav   = [448, 546, 441, 1707]
archery     = [4, 24, 492, 5, 7, 6, 1155, 39, 474, 185, 1010, 1012, 1911, 1952]
trebuchet   = [42, 331, 1690, 1691, 1923, 1942, 683, 729, 1948]
ram         = [35, 1258, 422, 548]
explosive   = [527, 528, 1104, 440, 1263, 706, 1911]
scorpion    = [279, 541]

# ── Building / resource lists (from helpers.h) ────────────────────────────────
military_buildings = [12, 20, 132, 498, 10, 14, 87, 86, 101, 153, 49, 150]
eco_buildings      = [68, 129, 130, 131, 562, 563, 564, 565, 584, 585, 586, 587, 1711, 1720, 1734, 1808]
town_centers       = [71, 109, 141, 142]
barracks           = [12, 20, 132, 498]
stables            = [86, 101, 153]
ranges             = [10, 14, 87]
monasteries        = [30, 31, 32, 104, 1806]
workshops          = [49, 150]
blacksmiths        = [18, 19, 103, 105]
universities       = [209, 210]
militias           = [74, 75, 77, 473, 567, 1793]
galleys            = [539, 21, 442]
productivity_rates = [47, 190, 79, 189, 216, 198, 199, 200]
gather_rates       = [214, 57, 354, 581, 216, 218, 220, 590, 259, 56, 120, 579, 122, 123, 124, 592, 13]
military_classes   = [0, 55, 22, 35, 6, 54, 13, 51, 36, 12, 44, 23, 47]
siege_classes      = [13, 51, 54, 55]
eco_upgrades       = [213, 249, 202, 203, 221, 14, 13, 12, 55, 182, 278, 279, 65, 1012, 1013, 1014]


# ── Build ec_list ─────────────────────────────────────────────────────────────
ec_list = {}

# ─── Free tech sets 1 (bonuses 110–119) ────────────────────────────────────
free_techs_1 = [
    [12, 13, 14, 1012, 1013, 1014],  # 110: farm + pasture upgrades
    [67, 68, 75],                     # 111: forging, iron casting, blast furnace
    [602, 875],                       # 112: arson, gambesons
    [8, 280],                         # 113: town watch, town patrol
    [322, 441],                       # 114: murder holes, herbal medicine
    [47],                             # 115: chemistry
    [254, 428, 786],                  # 116: light cavalry, hussar, winged hussar
    [213, 249],                       # 117: wheelbarrow, hand cart (both get time=1)
    [140, 63, 64],                    # 118: guard tower, keep, bombard tower
    [315],                            # 119: conscription
]
for i, techs in enumerate(free_techs_1):
    bonus_id = 110 + i
    # Bonus 117: wheelbarrow=j0, hand_cart=j1 both get time=1
    if i == 7:
        ecs = []
        for tech in techs:
            for k in range(4):
                ecs.append(ec(101, tech, k, 0, 0.0))
            ecs.append(ec(103, tech, -1, 0, 1.0))
    else:
        ecs = free_tech_ecs(techs)
    ec_list[str(bonus_id)] = [entry([], ecs)]

# ─── 120: Farmers work 15% faster ───────────────────────────────────────────
ec_list["120"] = [entry([], [
    ec(5, 214, -1, 13, 1.23),
    ec(5, 259, -1, 13, 1.23),
    ec(5, 50,  -1, 13, 1.15),
    ec(5, 1187,-1, 13, 1.15),
])]

# ─── 121: -15% age up cost ───────────────────────────────────────────────────
ec_list["121"] = [entry([], [
    ec(101, 101, 0, 1, -75.0),
    ec(101, 102, 0, 1, -120.0),
    ec(101, 102, 3, 1, -30.0),
    ec(101, 103, 0, 1, -150.0),
    ec(101, 103, 3, 1, -120.0),
])]

# ─── 122: -15% fishing ship cost ────────────────────────────────────────────
ec_list["122"] = [entry([], [ec(5, 13, -1, 104, 0.85)])]

# 123: unimplemented in KM (dock/uni techs -33%) – SKIP

# ─── 124: Advancing to Imperial -33% cost ───────────────────────────────────
ec_list["124"] = [entry([], [
    ec(101, 103, 0, 1, -333.0),
    ec(101, 103, 3, 1, -264.0),
])]

# 125: Blacksmith upgrades no gold – SKIP (requires DAT-scan)

# ─── 126: Gunpowder units fire 18% faster ───────────────────────────────────
ec_list["126"] = [entry([], [ec(5, u, -1, 10, 0.85) for u in gunpowder])]

# ─── 127: Builders work 30% faster ──────────────────────────────────────────
ec_list["127"] = [entry([], [ec(1, 195, 0, -1, 1.3)])]

# ─── 128: Military units created 11% faster ─────────────────────────────────
ec_list["128"] = [entry([], [ec(5, -1, cls, 101, 0.9) for cls in military_classes])]

# ─── 129: Villagers carry +3 ────────────────────────────────────────────────
ec_list["129"] = [entry([], [ec(4, -1, 4, 14, 3.0)])]

# ─── 130: Trebuchets +35% accuracy ──────────────────────────────────────────
ec_list["130"] = [entry([], [ec(4, u, -1, 11, 35.0) for u in trebuchet])]

# 131: No houses / -100 wood – SKIP (involves disabling house unit type)

# ─── 132: Resources last 15% longer ─────────────────────────────────────────
ec_list["132"] = [entry([], (
    [ec(6, u, -1, -1, 1.15) for u in productivity_rates] +
    [ec(5, u, -1, 13, 0.87) for u in gather_rates]
))]

# 133: Archers -10% Feudal / -20% Castle / -30% Imperial – SKIP (modifies existing effects 485/486)

# ─── 135: Stone miners work 20% faster ──────────────────────────────────────
ec_list["135"] = [entry([], [
    ec(5, 220, -1, 13, 1.2),
    ec(5, 124, -1, 13, 1.2),
])]

# ─── 136: Eco upgrades cost no wood and research 50% faster ─────────────────
ec_list["136"] = [entry([], (
    [ec(101, t, 1, 0, 0.0) for t in eco_upgrades] +
    [ec(103, t, -1, 2, 0.5) for t in eco_upgrades]
))]

# 137: -50% food cost on Blacksmith + Siege Workshop techs – handled in
#      civ_appender._create_bonus_handler (DAT-scan at build time)
# 138: -50% cost on all Stable techs – handled in
#      civ_appender._create_bonus_handler (DAT-scan at build time)

# ─── 141: Villagers +3 HP per researched eco-upgrade tech ───────────────────
ec_list["141"] = [entry([t], [ec(4, -1, 4, 0, 3.0)]) for t in eco_upgrades]

# ─── 143: Military buildings built 100% faster ──────────────────────────────
ec_list["143"] = [entry([], [ec(5, b, -1, 101, 0.5) for b in military_buildings])]

# ─── 144: Resource drop-off buildings +5 population ─────────────────────────
ec_list["144"] = [entry([], [ec(0, b, -1, 21, 5.0) for b in eco_buildings])]

# ─── 145: Ballistics researched instantly ───────────────────────────────────
ec_list["145"] = [entry([], [
    ec(103, 93, -1, 0, 1.0),
    ec(101, 93, 1,  0, 0.0),
])]

# ─── Free tech sets 2 (bonuses 146–170) ─────────────────────────────────────
# freeTechs2 from civbuilder.cpp lines 3259–3284
# Index 9 (bonus 155) references royalElephantTech (dynamic) – SKIP
free_techs_2 = [
    [100, 237],           # 146: crossbow, arbalest
    [98, 655, 599],       # 147: elite skirm, imp skirm (j=1→time=1), elite genitour
    [236, 521],           # 148: heavy camel, heavy camel 1
    [74, 76, 77],         # 149: scale/chain/plate mail
    [80, 81, 82],         # 150: plate/scale/chain barding
    [199, 200, 201],      # 151: fletching, bodkin, bracer
    [316],                # 152: redemption
    [215],                # 153: squires
    [384, 434],           # 154: heavy eagle, elite eagle  (+disable 387)
    None,                 # 155: SKIP (royalElephantTech dynamic)
    [231, 252],           # 156: sanctity, fervor
    [319, 233],           # 157: atonement, illumination
    [438, 230],           # 158: theocracy, block printing
    [379, 194],           # 159: hoardings, fortified wall
    [50, 51],             # 160: masonry, architecture
    [55, 182, 278, 279],  # 161: gold mining, gold shaft, stone mining, stone shaft
    [321, 54],            # 162: sappers, treadmill crane
    [35],                 # 163: galleon
    [374, 375],           # 164: careening, dry dock
    [246],                # 165: fast fire ship only (skip dragon ship – dynamic)
    [244],                # 166: heavy demolition
    [65],                 # 167: gillnets
    [34],                 # 168: war galley
    [218],                # 169: heavy cavalry archer
    [96, 255, 838],       # 170: capped ram, siege ram, elite armored elephant
]
for i, techs in enumerate(free_techs_2):
    bonus_id = 146 + i
    if techs is None:
        continue
    ecs = []
    for j, tech in enumerate(techs):
        for k in range(4):
            ecs.append(ec(101, tech, k, 0, 0.0))
        # Bonus 147 (i=1): imp skirm (j=1, tech=655) takes 1 second
        time_val = 1.0 if (i == 1 and j == 1) else 0.0
        ecs.append(ec(103, tech, -1, 0, time_val))
    if i == 8:
        # Eagle line: disable auto-upgrade tech 387
        ecs.append(ec(102, -1, -1, -1, 387.0))
    ec_list[str(bonus_id)] = [entry([], ecs)]

# ─── 171: Trade units move and trade 20% faster ─────────────────────────────
ec_list["171"] = [entry([], [
    ec(5, -1, 2,  5,  1.2),
    ec(5, -1, 2,  13, 1.2),
    ec(5, -1, 19, 5,  1.2),
    ec(5, -1, 19, 13, 1.2),
])]

# ─── 172: Squires affects foot archers and skirmishers (req: tech 215) ──────
ec_list["172"] = [entry([215],
    [ec(5, u, -1, 5, 1.1) for u in foot_archer] +
    [ec(5, u, -1, 5, 1.1) for u in skirmisher]
)]

# ─── 173: Shock Infantry +5/10/15% speed per age ────────────────────────────
ec_list["173"] = [
    entry([101], [ec(5, u, -1, 5, 1.05)    for u in shock]),
    entry([102], [ec(5, u, -1, 5, 1.0476)  for u in shock]),
    entry([103], [ec(5, u, -1, 5, 1.0455)  for u in shock]),
]

# ─── 174: Start with +150 wood (req: loom=639, feudal=307 – dark age only) ──
ec_list["174"] = [entry([639, 307], [
    ec(1, 1,  1, -1, 150.0),
    ec(1, 92, 1, -1, 150.0),
])]

# 175 already in vanilla catalog (tech 228)

# ─── 176: Start with +50 wood +50 stone ─────────────────────────────────────
ec_list["176"] = [entry([639, 307], [
    ec(1, 1,  1, -1, 50.0),
    ec(1, 2,  1, -1, 50.0),
    ec(1, 92, 1, -1, 50.0),
    ec(1, 93, 1, -1, 50.0),
])]

# ─── 177: Start with +70 food +30 gold ──────────────────────────────────────
ec_list["177"] = [entry([639, 307], [
    ec(1, 0,  1, -1, 70.0),
    ec(1, 3,  1, -1, 30.0),
    ec(1, 91, 1, -1, 70.0),
    ec(1, 94, 1, -1, 30.0),
])]

# ─── 178: Monks train 66% faster ────────────────────────────────────────────
ec_list["178"] = [entry([], [
    ec(5, -1,  18, 101, 0.6),
    ec(5, 1811, -1, 101, 0.6),
])]

# ─── 179: Trebuchets train 50% faster ───────────────────────────────────────
ec_list["179"] = [entry([], [ec(5, u, -1, 101, 0.66) for u in trebuchet])]

# ─── 180: Cavalry archers train 33% faster (class 36 = cav archer) ──────────
ec_list["180"] = [entry([], [ec(5, -1, 36, 101, 0.8)])]

# ─── 181: Petards train 200% faster (class 35 = land explosive) ─────────────
ec_list["181"] = [entry([], [ec(5, -1, 35, 101, 0.33)])]

# ─── 182: Petards +8 pierce armor ───────────────────────────────────────────
ec_list["182"] = [entry([], [ec(4, -1, 35, 8, atd(8, 3))])]

# ─── 183: Bloodlines free in Castle Age ─────────────────────────────────────
ec_list["183"] = [entry([102], [
    ec(101, 435, 0, 0, 0.0),
    ec(101, 435, 3, 0, 0.0),
    ec(103, 435, -1, 0, 0.0),
])]

# ─── 184: Galleys +1 range (attributes 12=max range, 1=min range, 23=accuracy) ─
ec_list["184"] = [entry([], (
    [ec(4, g, -1, 12, 1.0) for g in galleys] +
    [ec(4, g, -1, 1,  1.0) for g in galleys] +
    [ec(4, g, -1, 23, 1.0) for g in galleys]
))]

# ─── 185: +100 wood +100 stone each age up ──────────────────────────────────
ec_list["185"] = [
    entry([101], [ec(1, 1, 1, -1, 100.0), ec(1, 2, 1, -1, 100.0)]),
    entry([102], [ec(1, 1, 1, -1, 100.0), ec(1, 2, 1, -1, 100.0)]),
    entry([103], [ec(1, 1, 1, -1, 100.0), ec(1, 2, 1, -1, 100.0)]),
]

# ─── 186: +400 food upon Castle Age ─────────────────────────────────────────
ec_list["186"] = [entry([102], [ec(1, 0, 1, -1, 400.0)])]

# ─── 187: +350 stone upon Castle Age ────────────────────────────────────────
ec_list["187"] = [entry([102], [ec(1, 2, 1, -1, 350.0)])]

# ─── 188: +250 wood upon Feudal Age ─────────────────────────────────────────
ec_list["188"] = [entry([101], [ec(1, 1, 1, -1, 250.0)])]

# ─── 189: +500 gold upon Imperial Age ───────────────────────────────────────
ec_list["189"] = [entry([103], [ec(1, 3, 1, -1, 500.0)])]

# ─── 190: Monks with relics +100 HP and +100 pierce armor ───────────────────
ec_list["190"] = [entry([], [
    ec(4, -1, 43, 0, 100.0),
    ec(4, -1, 43, 8, atd(100, 3)),
])]

# ─── 191: Land explosive units 2x HP ────────────────────────────────────────
ec_list["191"] = [entry([], [ec(5, -1, 35, 0, 2.0)])]

# 192, 193: already in vanilla catalog

# ─── 194: Castles and Kreposts +2000 HP ─────────────────────────────────────
ec_list["194"] = [entry([], [
    ec(4, 82,   -1, 0, 2000.0),
    ec(4, 1251, -1, 0, 2000.0),
])]

# 195: Blacksmith upgrades free an age later – SKIP (dynamic per-tech scan)

# ─── 196: Barracks -75 wood ─────────────────────────────────────────────────
ec_list["196"] = [entry([], [ec(4, b, -1, 104, -75.0) for b in barracks])]

# ─── 197: Stables -75 wood ──────────────────────────────────────────────────
ec_list["197"] = [entry([], [ec(4, s, -1, 104, -75.0) for s in stables])]

# ─── 198: Archery Ranges -75 wood ───────────────────────────────────────────
ec_list["198"] = [entry([], [ec(4, r, -1, 104, -75.0) for r in ranges])]

# ─── 199: Monasteries -100 wood ─────────────────────────────────────────────
ec_list["199"] = [entry([], [ec(4, m, -1, 104, -100.0) for m in monasteries])]

# ─── 200: Siege Workshops -100 wood ─────────────────────────────────────────
ec_list["200"] = [entry([], [ec(4, w, -1, 104, -100.0) for w in workshops])]

# ─── 201: Military buildings -50 wood ───────────────────────────────────────
ec_list["201"] = [entry([], [ec(4, b, -1, 104, -50.0) for b in military_buildings])]

# ─── 202: Blacksmith + University -100 wood ─────────────────────────────────
ec_list["202"] = [entry([], (
    [ec(4, b, -1, 104, -100.0) for b in blacksmiths] +
    [ec(4, u, -1, 104, -100.0) for u in universities]
))]

# ─── 203: Infantry +1 attack vs villagers per age (4 techs: Dark + 3 ages) ──
ec_list["203"] = [
    entry([],    [ec(4, -1, 6, 9, atd(1, 10))]),
    entry([101], [ec(4, -1, 6, 9, atd(1, 10))]),
    entry([102], [ec(4, -1, 6, 9, atd(1, 10))]),
    entry([103], [ec(4, -1, 6, 9, atd(1, 10))]),
]

# 204 already in vanilla catalog

# ─── 205: Galleys +1 attack (pierce) ────────────────────────────────────────
ec_list["205"] = [entry([], [ec(4, g, -1, 9, atd(1, 3)) for g in galleys])]

# ─── 206: Steppe Lancers +10 vs villagers ───────────────────────────────────
ec_list["206"] = [entry([], [ec(4, u, -1, 9, atd(10, 10)) for u in steppe])]

# ─── 207: Steppe Lancers attack 33% faster ──────────────────────────────────
ec_list["207"] = [entry([], [ec(5, u, -1, 10, 0.75) for u in steppe])]

# ─── 208: Elephant units attack 25% faster ──────────────────────────────────
ec_list["208"] = [entry([], [ec(5, u, -1, 10, 0.8) for u in elephant])]

# 209: Stone walls in dark age – SKIP (modifies tech prerequisite pointers)

# ─── 210: +50 each resource per age ─────────────────────────────────────────
ec_list["210"] = [
    entry([101], [ec(1, i, 1, -1, 50.0) for i in range(4)]),
    entry([102], [ec(1, i, 1, -1, 50.0) for i in range(4)]),
    entry([103], [ec(1, i, 1, -1, 50.0) for i in range(4)]),
]

# 211 already in catalog (empty)

# ─── 212: Camel units attack 20% faster ─────────────────────────────────────
ec_list["212"] = [entry([], [ec(5, u, -1, 10, 0.83333) for u in camel])]

# ─── 213: Mangonels can cut trees (attack type 18 = tree) ───────────────────
ec_list["213"] = [entry([], [ec(4, 280, -1, 9, atd(100, 18))])]

# ─── 214: Free Siege Tower in Feudal Age (cost -50%; enable filtered by appender)
ec_list["214"] = [entry([101], [ec(5, 1105, -1, 100, 0.5)])]

# ─── 215: Rams and Siege Towers x2 garrison capacity ────────────────────────
ec_list["215"] = [entry([], (
    [ec(5, u, -1, 2, 2.0) for u in ram] +
    [ec(5, 1105, -1, 2, 2.0)]
))]

# ─── 216: Towers provide +15 population (class 52 = tower) ─────────────────
ec_list["216"] = [entry([], [ec(0, -1, 52, 21, 15.0)])]

# ─── 217: Gunpowder units move 20% faster ───────────────────────────────────
ec_list["217"] = [entry([], [ec(5, u, -1, 5, 1.2) for u in gunpowder])]

# 218 already in catalog (empty)

# ─── 219: Monk units move 20% faster (class 18=monk, 43=monk-with-relic) ────
ec_list["219"] = [entry([], [
    ec(5, -1,  18, 5, 1.2),
    ec(5, -1,  43, 5, 1.2),
    ec(5, 1811,-1,  5, 1.2),
])]

# 220 already in catalog

# 221: Spearman-line and Barracks techs available earlier – SKIP (modifies prereqs)
# 222: Cows from mills – SKIP (KM custom units)
# 223: Start with a horse – SKIP (EC type 7 spawn unit; complex)

# ─── 224: Siege Towers 2x HP ─────────────────────────────────────────────────
ec_list["224"] = [entry([], [ec(5, 1105, -1, 0, 2.0)])]

# ─── 225: Siege Towers train 100% faster ────────────────────────────────────
ec_list["225"] = [entry([], [ec(5, 1105, -1, 101, 0.5)])]

# 226 already in catalog

# ─── 227: Cannon Galleons with ballistics (unit 374 = cannon galleon) ────────
ec_list["227"] = [entry([], [
    ec(0, 374, -1, 19, 1.0),
    ec(0, 374, -1, 5,  7.0),
])]

# ─── 228: Warships +10 vs villagers (class 22 = warship) ────────────────────
ec_list["228"] = [entry([], [ec(4, -1, 22, 9, atd(10, 10))])]

# 229 already in catalog (empty)

# ─── 230: Town Centers +50% work rate in Imperial Age ───────────────────────
ec_list["230"] = [entry([103], [ec(5, 142, -1, 13, 1.5)])]

# ─── 231: Feudal Age cost -25% ───────────────────────────────────────────────
ec_list["231"] = [entry([], [ec(101, 101, 0, 1, -125.0)])]

# ─── 232: Spearmen and Skirmishers train 50% faster ─────────────────────────
ec_list["232"] = [entry([], (
    [ec(5, u, -1, 101, 0.66) for u in spear] +
    [ec(5, u, -1, 101, 0.66) for u in skirmisher]
))]

# ─── 233: Spearman-line +25% HP ─────────────────────────────────────────────
ec_list["233"] = [entry([], [ec(5, u, -1, 0, 1.25) for u in spear])]

# 234: Market techs no gold – SKIP (dynamic DAT scan)

# ─── 235: Trees last 100% longer ────────────────────────────────────────────
ec_list["235"] = [entry([], [
    ec(6, 189, -1, -1, 2.0),
    ec(5, 123, -1, 13, 0.5),
    ec(5, 218, -1, 13, 0.5),
])]

# ─── 236: Stone resources last 30% longer ───────────────────────────────────
ec_list["236"] = [entry([], [
    ec(6, 79,  -1, -1, 1.3),
    ec(5, 124, -1, 13, 0.769231),
    ec(5, 220, -1, 13, 0.769231),
])]

# ─── 237: Gold resources last 30% longer ────────────────────────────────────
ec_list["237"] = [entry([], [
    ec(6, 47,  -1, -1, 1.3),
    ec(5, 579, -1, 13, 0.769231),
    ec(5, 581, -1, 13, 0.769231),
])]

# ─── 238: Berries contain +35% food ─────────────────────────────────────────
ec_list["238"] = [entry([], [
    ec(6, 198, -1, -1, 1.35),
    ec(5, 120, -1, 13, 0.741),
    ec(5, 354, -1, 13, 0.741),
])]

# 239: City Walls upgrade chain – SKIP (complex unit upgrade chain modification)

# ─── 240: Fish contain +35% food ────────────────────────────────────────────
ec_list["240"] = [entry([], [
    ec(6, 200, -1, -1, 1.35),
    ec(5, 13,  -1, 13, 0.741),
    ec(5, 56,  -1, 13, 0.741),
    ec(5, 57,  -1, 13, 0.741),
])]

# ─── 241: Units garrisoned in buildings heal 2x faster (attr 108) ────────────
ec_list["241"] = [entry([], [
    ec(5, -1, 52, 108, 2.0),
    ec(5, -1, 3,  108, 2.0),
])]

# ─── 242: Repairers work 100% faster (units 156, 222 = builder/repairer) ─────
ec_list["242"] = [entry([], [
    ec(5, 156, -1, 13, 2.0),
    ec(5, 222, -1, 13, 2.0),
])]

# ─── 243: Skirmishers +1 vs infantry (class 1 = infantry) ───────────────────
ec_list["243"] = [entry([], [ec(4, u, -1, 9, atd(1, 1)) for u in skirmisher])]

# ─── 244: Archery range units +1 pierce attack ──────────────────────────────
ec_list["244"] = [entry([], [ec(4, u, -1, 9, atd(1, 3)) for u in archery])]

# ─── 245: Archery units +1 melee armor per age ──────────────────────────────
ec_list["245"] = [
    entry([101], [ec(4, u, -1, 8, atd(1, 4)) for u in archery]),
    entry([102], [ec(4, u, -1, 8, atd(1, 4)) for u in archery]),
    entry([103], [ec(4, u, -1, 8, atd(1, 4)) for u in archery]),
]

# ─── 246: Siege units +1 pierce armor in Castle and Imperial ─────────────────
ec_list["246"] = [
    entry([102], [ec(4, -1, cls, 8, atd(1, 3)) for cls in siege_classes]),
    entry([103], [ec(4, -1, cls, 8, atd(1, 3)) for cls in siege_classes]),
]

# 247: Parthian Tactics in Castle Age – SKIP (modifies tech prerequisites)

# ─── 248: Castle Age -25% cost ───────────────────────────────────────────────
ec_list["248"] = [entry([], [
    ec(101, 102, 0, 1, -200.0),
    ec(101, 102, 3, 1, -50.0),
])]

# ─── 249: Cavalry +1 attack (melee, classes 12=cavalry, 47=camel as cavalry) ─
ec_list["249"] = [entry([], [
    ec(4, -1, 12, 9, atd(1, 4)),
    ec(4, -1, 47, 9, atd(1, 4)),
])]

# ─── 250: Infantry/cavalry +1 vs buildings per age; +2 in Imperial ───────────
ec_list["250"] = [
    entry([101], [ec(4, -1, 6,  9, atd(1, 21)), ec(4, -1, 12, 9, atd(1, 21)), ec(4, -1, 47, 9, atd(1, 21))]),
    entry([102], [ec(4, -1, 6,  9, atd(1, 21)), ec(4, -1, 12, 9, atd(1, 21)), ec(4, -1, 47, 9, atd(1, 21))]),
    entry([103], [ec(4, -1, 6,  9, atd(2, 21)), ec(4, -1, 12, 9, atd(2, 21)), ec(4, -1, 47, 9, atd(2, 21))]),
]

# ─── 251: Buildings +3 pierce armor (classes 3=building, 52=tower) ───────────
ec_list["251"] = [entry([], [
    ec(4, -1, 3,  8, atd(3, 3)),
    ec(4, -1, 52, 8, atd(3, 3)),
])]

# ─── 252: Foot archers +5/10/15% speed per age ──────────────────────────────
ec_list["252"] = [
    entry([101], [ec(5, u, -1, 5, 1.05)   for u in foot_archer]),
    entry([102], [ec(5, u, -1, 5, 1.0476) for u in foot_archer]),
    entry([103], [ec(5, u, -1, 5, 1.0455) for u in foot_archer]),
]

# ─── 253: Foot archers and skirmishers +1 vs villagers ──────────────────────
ec_list["253"] = [entry([], (
    [ec(4, u, -1, 9, atd(1, 10)) for u in foot_archer] +
    [ec(4, u, -1, 9, atd(1, 10)) for u in skirmisher]
))]

# ─── 254: Gunpowder +10 bonus vs camels (class 30 = camel) ──────────────────
ec_list["254"] = [entry([], [ec(4, u, -1, 9, atd(10, 30)) for u in gunpowder])]

# ─── 255: Shock Infantry +6 vs stone defenses (classes 13, 22, 26) ───────────
ec_list["255"] = [entry([], (
    [ec(4, u, -1, 9, atd(6, 13)) for u in shock] +
    [ec(4, u, -1, 9, atd(3, 22)) for u in shock] +
    [ec(4, u, -1, 9, atd(6, 26)) for u in shock]
))]

# ─── 256: Scouts, Light Cavalry, Hussar +4 vs stone defenses ─────────────────
ec_list["256"] = [entry([], (
    [ec(4, u, -1, 9, atd(4, 13)) for u in light_cav] +
    [ec(4, u, -1, 9, atd(2, 22)) for u in light_cav] +
    [ec(4, u, -1, 9, atd(4, 26)) for u in light_cav]
))]

# 257 already in vanilla catalog
# 258: Villagers +1 carry per TC tech – SKIP (dynamic DAT scan)

# ─── 259: Farms 10x HP ───────────────────────────────────────────────────────
ec_list["259"] = [entry([], [
    ec(5, 50,   -1, 0, 10.0),
    ec(5, 1187, -1, 0, 10.0),
])]

# ─── 260: Militia-line +2 vs cavalry and +1 vs camel ────────────────────────
ec_list["260"] = [entry([], (
    [ec(4, m, -1, 9, atd(2, 8))  for m in militias] +
    [ec(4, m, -1, 9, atd(1, 30)) for m in militias]
))]

# 261: Elite Steppe Lancer free – SKIP (refs dynamic royalLancerTech)

# ─── 262: Steppe Lancers +2 pierce armor ────────────────────────────────────
ec_list["262"] = [entry([], [ec(4, u, -1, 8, atd(2, 3)) for u in steppe])]

# ─── 263: Castles and Kreposts +100/+50 vs buildings ────────────────────────
ec_list["263"] = [entry([], [
    ec(4, 82,   -1, 9, atd(100, 11)),
    ec(4, 1251, -1, 9, atd(50,  11)),
])]

# ─── 264: Villagers work 10% faster in Imperial Age ─────────────────────────
ec_list["264"] = [entry([103], [ec(5, -1, 4, 13, 1.1)])]

# ─── 265: Outposts +5 garrison space and +15 LOS ────────────────────────────
ec_list["265"] = [entry([], [
    ec(4, 598, -1, 2,  5.0),
    ec(0, 598, -1, 30, 15.0),
])]

# ─── 266: Builders and repairers +10 pierce armor ───────────────────────────
ec_list["266"] = [entry([], [
    ec(4, 118, -1, 8, atd(10, 3)),
    ec(4, 212, -1, 8, atd(10, 3)),
    ec(4, 156, -1, 8, atd(10, 3)),
    ec(4, 222, -1, 8, atd(10, 3)),
])]

# ─── 267: Castles and Kreposts +30 population ───────────────────────────────
ec_list["267"] = [entry([], [
    ec(4, 82,   -1, 21, 30.0),
    ec(4, 1251, -1, 21, 30.0),
])]

# ─── 268: Bombard Towers +30 vs rams (class 17 = ram) ───────────────────────
ec_list["268"] = [entry([], [ec(4, 236, -1, 9, atd(30, 17))])]

# ─── 269: Towers +6 bonus vs cavalry (class 8 = cavalry; class 52 = tower) ──
ec_list["269"] = [entry([], [ec(4, -1, 52, 9, atd(6, 8))])]

# 270: Feudal monks – SKIP (KM custom unit)

# ─── 271: Scorpions and Ballistas produced 50% faster ───────────────────────
ec_list["271"] = [entry([], (
    [ec(5, u,    -1, 101, 0.66) for u in scorpion] +
    [ec(5, 1120, -1, 101, 0.66),
     ec(5, 1122, -1, 101, 0.66),
     ec(5, 827,  -1, 101, 0.66),
     ec(5, 829,  -1, 101, 0.66)]
))]

# ─── 272: Town Centers fire 25% faster ──────────────────────────────────────
ec_list["272"] = [entry([], [ec(5, t, -1, 10, 0.8) for t in town_centers])]

# ─── 273: Trebuchets -50% gold cost ─────────────────────────────────────────
ec_list["273"] = [entry([], [ec(5, u, -1, 105, 0.5) for u in trebuchet])]

# ─── 274: Explosive units +blast radius (attr 22 = blast width) ─────────────
ec_list["274"] = [entry([], [ec(5, u, -1, 22, 2.0) for u in explosive])]

# ─── 275: Gunpowder +8 bonus vs buildings (class 11 = building) ─────────────
ec_list["275"] = [entry([], [ec(4, u, -1, 9, atd(8, 11)) for u in gunpowder])]

# ─── 276: Shock Infantry +1 pierce armor ────────────────────────────────────
ec_list["276"] = [entry([], [ec(4, u, -1, 8, atd(1, 3)) for u in shock])]

# 277-279: per-tech dynamic – SKIP

# 302 already in catalog, but let's verify with explicit ECs:
# Galleys and Dromons +1M+1P (galley=21), +2M+2P (war galley=442, dromon=1795)
ec_list["302"] = [entry([], [
    ec(4, 21,   -1, 8, atd(1, 3)),
    ec(4, 21,   -1, 8, atd(1, 4)),
    ec(4, 442,  -1, 8, atd(2, 3)),
    ec(4, 442,  -1, 8, atd(2, 4)),
    ec(4, 1795, -1, 8, atd(2, 3)),
    ec(4, 1795, -1, 8, atd(2, 4)),
])]

# 323: Buildings rebate stone – SKIP (per-building-area dynamic scan)

# ─── 324: Villagers cooperate (aura effect attr 63) ─────────────────────────
ec_list["324"] = [entry([], [ec(0, -1, 4, 63, 96.0)])]

# 325: Husbandry affects attack speed – SKIP (clones effect 39 at runtime)

# ─── 326: Trade yields stone ─────────────────────────────────────────────────
ec_list["326"] = [entry([], [ec(1, 253, -1, -1, 10.0)])]

# 327: Blacksmith upgrades affect bonus damage – SKIP (complex per-tech chain)

# ─── 328: Cavalry archers have a dodge chance ────────────────────────────────
ec_list["328"] = [entry([], [
    ec(0, -1, 36, 59, 1.0),
    ec(0, -1, 36, 60, 0.05),
    ec(0, -1, 36, 61, 0.0),
    ec(0, -1, 36, 62, 4.0),
])]

# 329: Farmers don't require Mills – SKIP (modifies tech prerequisite chain)
# 330: 2x2 farms – SKIP (KM custom units)
# 331: Archery range techs -50% – SKIP (empty effect stub)
# 332: Knights in Feudal Age – SKIP (KM custom unit)

# ─── 333: Siege Towers fire arrows (+6 melee and building attack) ────────────
ec_list["333"] = [entry([], [
    ec(4, 1105, -1, 9, atd(6, 3)),
    ec(4, 1105, -1, 9, atd(6, 11)),
    ec(4, 885,  -1, 9, atd(6, 3)),
    ec(4, 885,  -1, 9, atd(6, 11)),
])]

# Output
print(json.dumps(ec_list, indent=2))
