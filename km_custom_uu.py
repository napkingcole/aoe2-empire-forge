"""
km_custom_uu.py — KM-custom unique units (bonuses[1] indices 39-77).

These have no vanilla-game analogue (unlike indices 0-38/78-87, which map to
real DE units via civ_appender._KM_UU_TECHS). KM's civbuilder.cpp creates them
from scratch in createNewUnits(): clone a base unit into two brand-new unit
slots (UU + Elite), then bake in stat overrides directly on the DAT.

Source: fritz-net/AoE2-Civbuilder modding/civbuilder.cpp createNewUnits(),
createUU() helper (line 801) + per-unit override blocks, lines ~1449-2536.
Index 45 (Centurion) is NOT here — it's a real vanilla DE unit (civ 43 Romans,
techs 881/882) and belongs in civ_appender._KM_UU_TECHS instead. Indices 47
(Monkey Boy) and 75 (Warrior Monk) are intentionally omitted — out of scope.

Mechanism notes:
  - Every civ's unit array must stay the same length (engine crashes
    otherwise) — see llm/unit_quirks.md. We append clones to ALL civs, then
    apply stat overrides to the target civ only.
  - EC_ADD/EC_MULTIPLY do not work on newly-appended unit IDs (see
    llm/known_limitations.md) — all stats are baked directly into unit
    fields, never via tech effects.
  - `deepcopy` (not a to_bytes/from_bytes round-trip) is used for cloning;
    verified safe against reference-sharing bugs for this project's
    genieutils-py version.

createUU()'s `techCosts`/`techTime` params are NOT the unit's own training
cost/time — they're the cost and research time of the ELITE UPGRADE TECH.
The unit's own training cost/time is whatever the cloned base unit already
had, unless a separate setUnitCosts()/setTrainTime() call (or a direct
`ResourceCosts[i].Amount = X` line, which only overwrites the amount at that
slot and leaves the inherited resource Type alone) appears in the per-unit
block. These are two genuinely independent values in KM's source — do not
conflate them.

Two combat-stat application modes, matching what KM actually did per unit:
  - "merge": the early units (39-44, 48-51) kept the base unit's full
    Attacks/Armours list and only overwrote specific *positional* entries
    (Type50.Attacks[i].Amount = X) or appended new bonus-class entries.
  - "replace": later units (46, 52+) used KM's setCombatStats() helper, which
    clears the list and rebuilds it from scratch off {class, amount} pairs,
    padding in default (0-amount) filler entries for attack classes
    11/15/21 and armor class 31 so other vanilla techs that blindly target
    those classes don't misbehave.
"""

from copy import deepcopy

from genieutils.datfile import DatFile
from genieutils.effect import Effect, EffectCommand
from genieutils.tech import Tech, ResearchLocation, ResearchResourceCost
from genieutils.unit import AttackOrArmor

BUILDING_CASTLE = 82
BUILDING_KREPOST = 1251
TRAIN_HOTKEY = 16101    # Castle btn1 (Q) — Iron Pagoda/Konnik/KM convention; also
                        # Krepost btn1 (Q) per llm/advanced_techniques.md's hotkey table.
ELITE_BUTTON = 6        # matches KM's own createUU(): setResearchLocation(eliteTech, 82, techTime, 6).
                        # civ_appender._append_elite_upgrade_tech uses btn10 for our unrelated
                        # Phase-2 custom-UU feature; deliberately NOT reused here — confirmed
                        # in-game that btn10 doesn't render correctly for this code path.
EC_ENABLE = 2
EC_UPGRADE = 3
RES_SLOTS = (0, 1, 2, 3)  # food, wood, stone, gold

# ── Vanilla unit-class membership (subset of KM's unitClasses dict) ─────────
# Needed by the bespoke aura-task units (Apukispay/Landsknecht/Rajput/etc.)
# that target "every unit of class X" with a copied Bird.TaskList entry.
#
# Deliberate scope trim: KM's unitClasses lists grow during createNewUnits()
# as earlier custom UUs push themselves on (e.g. Numidian Javelinman joins
# "spear", Photonman joins "gunpowder"). Replicating that exact build-order
# dependency would make e.g. Landsknecht's buff target list depend on which
# *other* custom UUs a civ happens to have. We target the vanilla members
# only — a minor, intentional fidelity trim, not an oversight.
SPEAR_UNITS = [93, 358, 359, 1786, 1787, 1788]
GUNPOWDER_UNITS = [5, 36, 420, 691, 46, 557, 1001, 1003, 771, 773, 1709,
                   1704, 1706, 1911, 831, 832, 1904, 1907]
CAMEL_UNITS = [329, 330, 207, 1007, 1009, 1263, 282, 556, 1755, 1923]
SHOCK_UNITS = [751, 752, 753, 1974, 1976, 1901, 1903]
CONDOTTIERO_UNIT = 882

# ── Preset table ─────────────────────────────────────────────────────────────
# Schema per entry:
#   name            display name
#   base_unit_id    vanilla unit cloned for both tiers
#   elite_tech      {"cost": (food,wood,stone,gold), "time": int} — research
#                   cost/time of the Elite-upgrade tech (NOT the unit's own
#                   training cost/time — see module docstring)
#   unit_cost       None, or {"mode": "full", "uu": (f,w,s,g), "elite": (f,w,s,g)}
#                   (setUnitCosts — full type+amount+flag rewrite), or
#                   {"mode": "amount", "uu": [(slot,amount),...], "elite": [...]}
#                   (direct `ResourceCosts[i].Amount = X` — keeps the slot's
#                   inherited resource Type, only the amount changes)
#   post_cost       [(tier, slot, type, amount, flag), ...] — applied AFTER
#                   unit_cost, for KM's one-off follow-up ResourceCosts[]
#                   rewrites (Headhunter food-only hack, Numidian Javelinman
#                   elite wood nerf). tier = "uu" | "elite".
#   unit_train_time (uu, elite) — None entry = inherit from base unit
#   hp              (uu, elite) — None = inherit
#   speed           (uu, elite) — None = inherit
#   mode            "merge" | "replace" (see module docstring)
#   attacks         (uu_list, elite_list)
#     - "merge": list of (index, amount) positional overwrites on the cloned
#       base unit's existing Attacks list, or ("new", class, amount) to
#       append a brand-new bonus-class entry. None = leave list untouched.
#     - "replace": list of (class, amount) — full rebuild, KM semantics.
#   armors          same shape as attacks
#   displayed_attack, displayed_melee_armor, displayed_pierce_armor
#     (uu, elite) explicit overrides — KM sets these by hand in "merge" mode
#     since the touched index isn't reliably the displayed one; in "replace"
#     mode these are auto-derived from the attacks/armors class list instead
#     and this field should be (None, None).
#   extra           dict of one-off fields, recognized keys:
#     "max_range": (uu, elite)
#     "reload_time": (uu, elite)              (Type50.DisplayedReloadTime)
#     "bonus_damage_resistance": (uu, elite)
#     "hero_mode": (uu, elite)
#     "charge": {"max_charge", "recharge_rate", "charge_event", "charge_type",
#                "tiers": ("uu",) | ("elite",) | ("uu","elite")}
#     "break_off_combat": (uu, elite)
#     "armors_pop_back": bool   — KM pops the last default armor entry before
#                                 customizing (Varangian Guard only)
#     "name_internal": (uu_name, elite_name)  — cosmetic .name field only
#
# KM-custom UU indices intentionally NOT present here: 45 (Centurion — real
# vanilla unit, see civ_appender._KM_UU_TECHS), 47 (Monkey Boy — skipped),
# 75 (Warrior Monk — skipped), and the 6 bespoke aura-task units (41 Saboteur,
# 46 Apukispay, 56 Szlachcic, 58 Rajput, 70 Landsknecht, 76 Castellan) — see
# BESPOKE_TASKS below, not yet implemented.
PRESETS: dict[int, dict] = {
    # 39 — Crusader Knight
    39: {
        "name": "Crusader Knight", "base_unit_id": 1723,
        "elite_tech": {"cost": (600, 0, 0, 1200), "time": 45},
        "unit_cost": None, "post_cost": [],
        "unit_train_time": (None, None), "hp": (90, None), "speed": (None, None),
        "mode": "merge",
        "attacks": ([(0, 16)], None), "armors": ([(0, 3), (2, 3)], None),
        "displayed_attack": (16, None),
        "displayed_melee_armor": (2, None), "displayed_pierce_armor": (2, None),
        "extra": {"hero_mode": (2, 2), "name_internal": (None, "ECRUSADERKNIGHT")},
    },
    # 40 — Xolotl Warrior
    40: {
        "name": "Xolotl Warrior", "base_unit_id": 1570,
        "elite_tech": {"cost": (800, 0, 0, 800), "time": 60},
        "unit_cost": {"mode": "amount", "uu": [(0, 30), (1, 60)], "elite": [(0, 30), (1, 60)]},
        "post_cost": [],
        "unit_train_time": (None, None), "hp": (95, 115), "speed": (None, None),
        "mode": "merge",
        "attacks": ([(0, 5)], [(0, 6)]), "armors": ([(2, 0)], [(0, 3)]),
        "displayed_attack": (5, 6),
        "displayed_melee_armor": (None, 3), "displayed_pierce_armor": (0, None),
        "extra": {"reload_time": (0.9, 0.8)},
    },
    # 42 — Ninja
    42: {
        "name": "Ninja", "base_unit_id": 1145,
        "elite_tech": {"cost": (0, 500, 0, 600), "time": 100},
        "unit_cost": None, "post_cost": [],
        "unit_train_time": (None, None), "hp": (None, 60), "speed": (1.15, 1.3),
        "mode": "merge",
        "attacks": ([("new", 19, 5), (2, 11)], [("new", 19, 7), (2, 14)]),
        "armors": (None, [(2, 2)]),
        "displayed_attack": (11, 14),
        "displayed_melee_armor": (None, None), "displayed_pierce_armor": (None, 2),
        "extra": {"break_off_combat": (1, 1)},
    },
    # 43 — Flamethrower
    43: {
        "name": "Flamethrower", "base_unit_id": 188,
        "elite_tech": {"cost": (0, 1000, 0, 1000), "time": 75},
        "unit_cost": {"mode": "full", "uu": (0, 125, 0, 50), "elite": (0, 125, 0, 50)},
        "post_cost": [],
        "unit_train_time": (None, None), "hp": (None, None), "speed": (None, None),
        "mode": "merge",
        "attacks": ([("new", 17, 8), (1, 7), (0, 8), (2, 0)],
                    [("new", 17, 12), (1, 9), (0, 12), (2, 0)]),
        "armors": (None, [(0, 4)]),
        "displayed_attack": (7, 9),
        "displayed_melee_armor": (None, 4), "displayed_pierce_armor": (None, None),
        "extra": {"max_range": (None, 5)},
    },
    # 44 — Photonman
    44: {
        "name": "Photonman", "base_unit_id": 1577,
        "elite_tech": {"cost": (1000, 0, 0, 1000), "time": 120},
        "unit_cost": {"mode": "amount", "uu": [(1, 140)], "elite": [(1, 140)]},
        "post_cost": [],
        "unit_train_time": (50, 50), "hp": (30, 30), "speed": (0.9, 0.9),
        "mode": "merge",
        "attacks": ([("new", 17, 10)], [("new", 17, 10)]),
        "armors": ([(0, -3), (2, -3)], [(0, -3), (2, -3)]),
        "displayed_attack": (None, None),
        "displayed_melee_armor": (-3, -3), "displayed_pierce_armor": (-3, -3),
        "extra": {"max_range": (8, None), "reload_time": (5.5, 5.5),
                  "name_internal": (None, "EPHOTON")},
    },
    # 48 — Amazon Warrior
    48: {
        "name": "Amazon Warrior", "base_unit_id": 825,
        "elite_tech": {"cost": (600, 0, 0, 1000), "time": 70},
        "unit_cost": {"mode": "amount", "uu": [(0, 50), (1, 15)], "elite": [(0, 50), (1, 15)]},
        "post_cost": [],
        "unit_train_time": (None, None), "hp": (None, 60), "speed": (None, 1.2),
        "mode": "merge",
        "attacks": ([(2, 13), ("new", 10, 10), ("new", 14, 30)],
                    [(2, 15), ("new", 10, 20), ("new", 14, 30)]),
        "armors": (None, None),
        "displayed_attack": (13, 15),
        "displayed_melee_armor": (None, None), "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": (None, "Elite Amazon Warrior")},
    },
    # 49 — Amazon Archer
    49: {
        "name": "Amazon Archer", "base_unit_id": 850,
        "elite_tech": {"cost": (600, 0, 0, 400), "time": 60},
        "unit_cost": {"mode": "amount", "uu": [(0, 25), (1, 35)], "elite": [(0, 25), (1, 35)]},
        "post_cost": [],
        "unit_train_time": (None, None), "hp": (35, 35), "speed": (1.1, 1.2),
        "mode": "merge",
        # idx2 reclassed from pierce(1) to villager-bonus class 10; idx5 (a
        # 6th attack slot in KM's source DAT) no longer exists in the
        # current DE dat, so it falls back to an append — see
        # _apply_merge_attacks. idx3 is the existing pierce-attack class,
        # amount-only (also the displayed attack).
        "attacks": ([("reclass", 2, 10, 5), (3, 4), ("reclass", 5, 14, 5)],
                    [("reclass", 2, 10, 10), (3, 5), ("reclass", 5, 14, 5)]),
        "armors": ([(2, 0)], [(2, 0)]),
        "displayed_attack": (4, 5),
        "displayed_melee_armor": (None, None), "displayed_pierce_armor": (0, None),
        "extra": {"name_internal": (None, "Elite Amazon Archer")},
    },
    # 50 — Iroquois Warrior
    50: {
        "name": "Iroquois Warrior", "base_unit_id": 1374,
        "elite_tech": {"cost": (800, 0, 0, 700), "time": 70},
        "unit_cost": None, "post_cost": [],
        "unit_train_time": (None, None), "hp": (None, 80), "speed": (None, None),
        "mode": "merge",
        "attacks": ([(1, 5), ("new", 26, 10), ("new", 22, 6), ("new", 13, 12), (2, 7)],
                    [(1, 10), ("new", 26, 10), ("new", 22, 12), ("new", 13, 12), (2, 11)]),
        "armors": (None, None),
        "displayed_attack": (7, 11),
        "displayed_melee_armor": (None, None), "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": (None, "EIRWAR")},
    },
    # 51 — Varangian Guard
    51: {
        "name": "Varangian Guard", "base_unit_id": 1681,
        "elite_tech": {"cost": (900, 0, 0, 900), "time": 90},
        "unit_cost": {"mode": "full", "uu": (70, 0, 0, 45), "elite": (70, 0, 0, 45)},
        "post_cost": [],
        "unit_train_time": (None, None), "hp": (80, 100), "speed": (1.4, 1.4),
        "mode": "merge",
        "attacks": ([(0, 9), ("new", 15, 6)], [(0, 11), ("new", 15, 10)]),
        "armors": ([(0, 0), (2, 5)], [(0, 0), (2, 7)]),
        "displayed_attack": (9, 11),
        "displayed_melee_armor": (0, 0), "displayed_pierce_armor": (5, 7),
        "extra": {
            "hero_mode": (0, 0), "armors_pop_back": True,
            "name_internal": ("VARANG", "EVARANG"),
        },
    },
    # 52 — Gendarme
    52: {
        "name": "Gendarme", "base_unit_id": 1281,
        "elite_tech": {"cost": (1000, 0, 0, 850), "time": 110},
        "unit_cost": {"mode": "full", "uu": (95, 0, 0, 85), "elite": (95, 0, 0, 85)},
        "post_cost": [],
        "unit_train_time": (20, 20), "hp": (75, 100), "speed": (1.3, 1.3),
        "mode": "replace",
        "attacks": ([(4, 10)], [(4, 13)]),
        "armors": ([(3, 5), (4, 5), (8, 0), (19, 0)], [(3, 7), (4, 7), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("GENDARME", "EGENDARME")},
    },
    # 53 — Cuahchiqueh
    53: {
        "name": "Cuahchiqueh", "base_unit_id": 1067,
        "elite_tech": {"cost": (600, 0, 0, 900), "time": 60},
        "unit_cost": {"mode": "full", "uu": (40, 0, 0, 30), "elite": (40, 0, 0, 30)},
        "post_cost": [],
        "unit_train_time": (11, 11), "hp": (80, 105), "speed": (1.1, 1.1),
        "mode": "replace",
        "attacks": ([(29, 5), (21, 1), (1, 5), (4, 6), (8, 0), (32, 5)],
                    [(29, 7), (21, 1), (1, 5), (4, 8), (8, 0), (32, 5)]),
        "armors": ([(4, 1), (3, -1), (19, 0)], [(4, 1), (3, -1), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"reload_time": (0.9, 0.8), "name_internal": ("CCQ", "ECCQ")},
    },
    # 54 — Ritterbruder
    54: {
        "name": "Ritterbruder", "base_unit_id": 1727,
        "elite_tech": {"cost": (850, 0, 0, 850), "time": 60},
        "unit_cost": {"mode": "full", "uu": (80, 0, 0, 75), "elite": (80, 0, 0, 75)},
        "post_cost": [],
        "unit_train_time": (22, 22), "hp": (125, 150), "speed": (1.3, 1.3),
        "mode": "replace",
        "attacks": ([(4, 11)], [(4, 13)]),
        "armors": ([(3, 1), (4, 6), (8, 0), (19, 0)], [(3, 2), (4, 11), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("SUPERTEUTONIC", "ESUPERTEUTONIC")},
    },
    # 55 — Kazak
    55: {
        "name": "Kazak", "base_unit_id": 1269,
        "elite_tech": {"cost": (0, 1100, 0, 500), "time": 70},
        "unit_cost": {"mode": "full", "uu": (0, 65, 0, 55), "elite": (0, 65, 0, 55)},
        "post_cost": [],
        "unit_train_time": (25, 25), "hp": (80, 100), "speed": (1.35, 1.35),
        "mode": "replace",
        "attacks": ([(27, 2), (3, 5), (21, 3)], [(27, 2), (3, 7), (21, 5)]),
        "armors": ([(28, 0), (4, 1), (3, 0), (15, 0), (8, 0), (19, 0)],
                   [(28, 0), (4, 2), (3, 0), (15, 0), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"max_range": (5, 6), "name_internal": ("KAZAK", "EKAZAK")},
    },
    # 57 — Cuirassier
    57: {
        "name": "Cuirassier", "base_unit_id": 1186,
        "elite_tech": {"cost": (650, 0, 0, 800), "time": 60},
        "unit_cost": {"mode": "full", "uu": (70, 0, 0, 35), "elite": (70, 0, 0, 35)},
        "post_cost": [],
        "unit_train_time": (11, 9), "hp": (50, 65), "speed": (1.55, 1.55),
        "mode": "replace",
        "attacks": ([(4, 16), (10, 10), (23, 6), (32, 6), (25, 5)],
                    [(4, 19), (10, 10), (23, 9), (32, 9), (25, 7)]),
        "armors": ([(4, -2), (3, 2), (8, 0), (19, 0)], [(4, -2), (3, 4), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("CHEVAL", "ECHEVAL")},
    },
    # 59 — Seljuk Archer
    59: {
        "name": "Seljuk Archer", "base_unit_id": 943,
        "elite_tech": {"cost": (0, 800, 0, 700), "time": 65},
        "unit_cost": {"mode": "full", "uu": (0, 50, 0, 70), "elite": (0, 50, 0, 70)},
        "post_cost": [],
        "unit_train_time": (16, 13), "hp": (50, 65), "speed": (1.4, 1.4),
        "mode": "replace",
        "attacks": ([(3, 7)], [(3, 9)]),
        "armors": ([(28, 0), (4, -2), (3, 0), (15, 0), (8, 0), (19, 0)],
                   [(28, 0), (4, -2), (3, 1), (15, 0), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"max_range": (4, 4), "name_internal": ("SELJUK", "ESELJUK")},
    },
    # 60 — Numidian Javelinman
    60: {
        "name": "Numidian Javelinman", "base_unit_id": 1036,
        "elite_tech": {"cost": (0, 600, 0, 400), "time": 45},
        "unit_cost": {"mode": "full", "uu": (0, 80, 0, 30), "elite": (0, 80, 0, 30)},
        "post_cost": [("elite", 1, 3, 15, 1)],   # KM nerfs elite gold cost 30->15 post-hoc
        "unit_train_time": (17, 17), "hp": (65, 80), "speed": (None, None),
        "mode": "replace",
        "attacks": ([(3, 5), (28, 2), (15, 3), (27, 1)], [(3, 6), (28, 3), (15, 5), (27, 1)]),
        "armors": ([(4, 0), (15, 1), (8, -1), (3, 3), (19, 0)],
                   [(4, 0), (15, 1), (8, -1), (3, 4), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("NUMIDIAN", "ENUMIDIAN")},
    },
    # 61 — Sosso Guard
    61: {
        "name": "Sosso Guard", "base_unit_id": 1574,
        "elite_tech": {"cost": (1000, 0, 0, 700), "time": 65},
        "unit_cost": {"mode": "full", "uu": (55, 0, 0, 5), "elite": (55, 0, 0, 5)},
        "post_cost": [],
        "unit_train_time": (12, 14), "hp": (60, 75), "speed": (1.1, 1.1),
        "mode": "replace",
        "attacks": ([(4, 6), (8, 22), (5, 25), (30, 16)], [(4, 7), (8, 44), (5, 50), (30, 32)]),
        "armors": ([(1, 0), (4, 0), (3, 1), (27, 0), (19, 0)], [(1, 0), (4, 0), (3, 2), (27, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("SOSSOG", "ESOSSOG")},
    },
    # 62 — Swiss Pikeman
    62: {
        "name": "Swiss Pikeman", "base_unit_id": 892,
        "elite_tech": {"cost": (600, 0, 0, 1200), "time": 45},
        "unit_cost": {"mode": "full", "uu": (40, 0, 0, 50), "elite": (40, 0, 0, 50)},
        "post_cost": [],
        "unit_train_time": (19, 19), "hp": (80, 95), "speed": (0.9, 0.9),
        "mode": "replace",
        "attacks": ([(4, 5), (8, 5), (5, 15), (30, 3)], [(4, 6), (8, 10), (5, 20), (30, 6)]),
        "armors": ([(1, 0), (3, 1), (4, 1), (27, 0), (19, 0)], [(1, 0), (3, 1), (4, 1), (27, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"max_range": (2, 2), "name_internal": ("SWISSPIKE", "ESWISSPIKE")},
    },
    # 63 — Headhunter
    63: {
        "name": "Headhunter", "base_unit_id": 1673,
        "elite_tech": {"cost": (400, 0, 0, 300), "time": 50},
        "unit_cost": {"mode": "full", "uu": (0, 0, 0, 75), "elite": (0, 0, 0, 75)},
        # KM zeroes the gold slot to food=0 post-hoc so the unit has only a
        # food cost — needed for Corvinian-Army-style "add for free" compat.
        "post_cost": [("uu", 1, 0, 0, 1), ("elite", 1, 0, 0, 1)],
        "unit_train_time": (15, 15), "hp": (60, 65), "speed": (1.33, 1.33),
        "mode": "replace",
        "attacks": ([(4, 7)], [(4, 8)]),
        "armors": ([(4, 1), (3, 0), (8, 0), (19, 0)], [(4, 1), (3, 0), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("BOUNTY", "EBOUNTY")},
    },
    # 64 — Teulu
    64: {
        "name": "Teulu", "base_unit_id": 1683,
        "elite_tech": {"cost": (600, 0, 0, 550), "time": 45},
        "unit_cost": {"mode": "full", "uu": (65, 0, 0, 40), "elite": (65, 0, 0, 40)},
        "post_cost": [],
        "unit_train_time": (10, 10), "hp": (70, 85), "speed": (0.95, 0.95),
        "mode": "replace",
        "attacks": ([(4, 10)], [(4, 12)]),
        "armors": ([(1, 0), (4, 0), (3, 1), (19, 0)], [(1, 0), (4, 0), (3, 1), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {
            "charge": {"max_charge": 10, "recharge_rate": 0.1, "charge_event": 0,
                      "charge_type": 2, "tiers": ("uu",)},
            "name_internal": ("TEULU", "ETEULU"),
        },
    },
    # 65 — Maillotins
    65: {
        "name": "Maillotins", "base_unit_id": 1685,
        "elite_tech": {"cost": (950, 0, 0, 250), "time": 35},
        "unit_cost": {"mode": "full", "uu": (90, 0, 0, 10), "elite": (90, 0, 0, 10)},
        "post_cost": [],
        "unit_train_time": (8, 8), "hp": (40, 40), "speed": (0.9, 0.9),
        "mode": "replace",
        "attacks": ([(4, 20)], [(4, 27)]),
        "armors": ([(1, 0), (4, 0), (3, 3), (19, 0)], [(1, 0), (4, 0), (3, 5), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"reload_time": (4, 4), "name_internal": ("GHALMARAZ", "EGHALMARAZ")},
    },
    # 66 — Hashashin
    66: {
        "name": "Hashashin", "base_unit_id": 1035,
        "elite_tech": {"cost": (500, 0, 0, 1250), "time": 60},
        "unit_cost": {"mode": "full", "uu": (25, 0, 0, 85), "elite": (25, 0, 0, 85)},
        "post_cost": [],
        "unit_train_time": (14, 14), "hp": (85, 105), "speed": (1.45, 1.45),
        "mode": "replace",
        "attacks": ([(4, 12), (19, 8), (36, 25)], [(4, 14), (19, 12), (36, 50)]),
        "armors": ([(4, 1), (3, 1), (8, 0), (19, 0)], [(4, 1), (3, 1), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("STONERS", "ESTONERS")},
    },
    # 67 — Highlander
    67: {
        "name": "Highlander", "base_unit_id": 453,
        "elite_tech": {"cost": (850, 0, 0, 700), "time": 65},
        "unit_cost": {"mode": "full", "uu": (75, 0, 0, 35), "elite": (75, 0, 0, 35)},
        "post_cost": [],
        "unit_train_time": (13, 13), "hp": (60, 75), "speed": (0.95, 0.95),
        "mode": "replace",
        "attacks": ([(4, 9), (1, 5), (8, 5), (32, 5)], [(4, 13), (1, 6), (8, 6), (32, 6)]),
        "armors": ([(4, 1), (3, 1), (1, 0), (19, 0)], [(4, 1), (3, 1), (1, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("CHAD", "ECHAD")},
    },
    # 68 — Stradiot
    68: {
        "name": "Stradiot", "base_unit_id": 1677,
        "elite_tech": {"cost": (800, 0, 0, 850), "time": 65},
        "unit_cost": {"mode": "full", "uu": (75, 0, 0, 55), "elite": (75, 0, 0, 55)},
        "post_cost": [],
        "unit_train_time": (20, 20), "hp": (80, 100), "speed": (1.4, 1.4),
        "mode": "replace",
        "attacks": ([(4, 9), (8, 4)], [(4, 12), (8, 6)]),
        "armors": ([(8, 0), (4, 0), (3, 0), (19, 0)], [(8, 0), (4, 1), (3, 1), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"max_range": (1, 1), "name_internal": ("STRADIOT", "ESTRADIOT")},
    },
    # 69 — Ahosi
    69: {
        "name": "Ahosi", "base_unit_id": 1066,
        "elite_tech": {"cost": (450, 0, 0, 350), "time": 40},
        "unit_cost": {"mode": "full", "uu": (45, 0, 0, 15), "elite": (45, 0, 0, 15)},
        "post_cost": [],
        # KM calls setTrainTime twice (9,9 then 7,7) — final value wins.
        "unit_train_time": (7, 7), "hp": (45, 55), "speed": (1.25, 1.25),
        "mode": "replace",
        "attacks": ([(3, 15)], [(3, 19)]),
        "armors": ([(1, 0), (4, 0), (3, 0), (19, 0)], [(1, 0), (4, 0), (3, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"max_range": (0, 0), "name_internal": ("AHOSI", "EAHOSI")},
    },
    # 71 — Clibinarii
    71: {
        "name": "Clibinarii", "base_unit_id": 932,
        "elite_tech": {"cost": (950, 0, 0, 850), "time": 65},
        "unit_cost": {"mode": "full", "uu": (95, 0, 0, 75), "elite": (95, 0, 0, 75)},
        "post_cost": [],
        "unit_train_time": (30, 28), "hp": (140, 180), "speed": (1.25, 1.25),
        "mode": "replace",
        "attacks": ([(4, 15)], [(4, 19)]),
        "armors": ([(8, 0), (3, 2), (4, 2), (19, 0)], [(8, 0), (3, 3), (4, 3), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("CLIBS", "ECLIBS")},
    },
    # 72 — Silahtar
    72: {
        "name": "Silahtar", "base_unit_id": 1267,
        "elite_tech": {"cost": (0, 1100, 0, 650), "time": 75},
        "unit_cost": {"mode": "full", "uu": (0, 40, 0, 70), "elite": (0, 40, 0, 70)},
        "post_cost": [],
        "unit_train_time": (34, 29), "hp": (60, 80), "speed": (1.25, 1.25),
        "mode": "replace",
        "attacks": ([(3, 6), (1, 3), (32, 3)], [(3, 8), (1, 6), (32, 6)]),
        "armors": ([(28, 0), (15, 0), (8, 0), (19, 2), (4, 1), (3, 0)],
                   [(28, 0), (15, 0), (8, 0), (19, 2), (4, 2), (3, 1)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"bonus_damage_resistance": (0.5, 0.5), "name_internal": ("NTWFTW", "ENTWFTW")},
    },
    # 73 — Jaridah
    73: {
        "name": "Jaridah", "base_unit_id": 777,
        "elite_tech": {"cost": (900, 0, 0, 450), "time": 60},
        "unit_cost": {"mode": "full", "uu": (50, 0, 0, 35), "elite": (50, 0, 0, 35)},
        "post_cost": [],
        "unit_train_time": (14, 14), "hp": (60, 90), "speed": (1.48, 1.48),
        "mode": "replace",
        "attacks": ([(4, 11), (30, 8), (5, 25)], [(4, 13), (30, 14), (5, 45)]),
        "armors": ([(4, 1), (3, 0), (8, 12), (19, 0)], [(4, 1), (3, 0), (8, 16), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("JARIDAH", "EJARIDAH")},
    },
    # 74 — Wolf Warrior
    74: {
        "name": "Wolf Warrior", "base_unit_id": 702,
        "elite_tech": {"cost": (800, 0, 0, 700), "time": 65},
        "unit_cost": {"mode": "full", "uu": (85, 0, 0, 50), "elite": (85, 0, 0, 50)},
        "post_cost": [],
        "unit_train_time": (21, 21), "hp": (125, 150), "speed": (1.3, 1.3),
        "mode": "replace",
        "attacks": ([(4, 13)], [(4, 15)]),
        "armors": ([(4, 3), (3, 0), (8, 0), (19, 0)], [(4, 5), (3, 0), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("WHERE", "EWHERE")},
    },
    # 77 — Wind Warrior
    77: {
        "name": "Wind Warrior", "base_unit_id": 749,
        "elite_tech": {"cost": (600, 0, 0, 900), "time": 65},
        "unit_cost": {"mode": "full", "uu": (55, 0, 0, 35), "elite": (55, 0, 0, 35)},
        "post_cost": [],
        "unit_train_time": (12, 12), "hp": (55, 65), "speed": (1.15, 1.15),
        "mode": "replace",
        "attacks": ([(4, 8), (20, 8), (11, 1)], [(4, 10), (20, 12), (11, 2)]),
        "armors": ([(1, 0), (4, 0), (3, 1), (19, 0)], [(1, 0), (4, 0), (3, 2), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"name_internal": ("LIGHTNINGMCQUEEN", "ELIGHTNINGMCQUEEN")},
    },

    # ── Bespoke aura-task units ──────────────────────────────────────────────
    # These 6 need everything the entries above need PLUS a Bird.TaskList
    # copy (see BESPOKE_TASKS below) that grants a passive buff/heal/regen
    # aura. The standard fields here only cover stats/cost/combat — the aura
    # itself is wired separately in append_km_custom_uu.

    # 41 — Saboteur
    41: {
        "name": "Saboteur", "base_unit_id": 706,
        "elite_tech": {"cost": (0, 600, 600, 0), "time": 40},
        "unit_cost": {"mode": "full", "uu": (0, 0, 50, 50), "elite": (0, 0, 50, 50)},
        "post_cost": [],
        "unit_train_time": (15, 15), "hp": (None, 70), "speed": (None, None),
        "mode": "merge",
        "attacks": ([(1, 40), ("new", 20, 60), ("new", 26, 600)],
                    [(1, 55), ("new", 20, 120), ("new", 26, 1200)]),
        "armors": (None, [(2, 5)]),
        "displayed_attack": (40, 55),
        "displayed_melee_armor": (None, None), "displayed_pierce_armor": (None, 5),
        "extra": {
            "blast": {"attack_level": (1, 1), "width": (1, 2.5)},
            "name_internal": (None, "EHDSQD"),
        },
    },
    # 46 — Apukispay
    46: {
        "name": "Apukispay", "base_unit_id": 1074,
        "elite_tech": {"cost": (800, 0, 0, 900), "time": 70},
        "unit_cost": {"mode": "full", "uu": (50, 0, 0, 85), "elite": (50, 0, 0, 85)},
        "post_cost": [],
        "unit_train_time": (20, 20), "hp": (70, 90), "speed": (1.15, 1.3),
        "mode": "replace",
        "attacks": ([(4, 9)], [(4, 12)]),
        "armors": ([(4, 1), (3, 0), (19, 0)], [(4, 2), (3, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"break_off_combat": (32, 32), "name_internal": ("APU", "EAPU")},
    },
    # 56 — Szlachcic
    56: {
        "name": "Szlachcic", "base_unit_id": 1721,
        "elite_tech": {"cost": (750, 0, 0, 650), "time": 60},
        "unit_cost": {"mode": "full", "uu": (75, 0, 0, 60), "elite": (75, 0, 0, 60)},
        "post_cost": [],
        "unit_train_time": (18, 18), "hp": (115, 145), "speed": (None, None),
        "mode": "replace",
        "attacks": ([(4, 10)], [(4, 12)]),
        "armors": ([(4, 4), (3, 1), (8, 0), (19, 0)], [(4, 5), (3, 2), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"break_off_combat": (96, 96), "name_internal": ("SZLACH", "ESZLACH")},
    },
    # 58 — Rajput
    58: {
        "name": "Rajput", "base_unit_id": 1184,
        "elite_tech": {"cost": (750, 0, 0, 750), "time": 55},
        "unit_cost": {"mode": "full", "uu": (70, 0, 0, 70), "elite": (70, 0, 0, 70)},
        "post_cost": [],
        "unit_train_time": (16, 16), "hp": (95, 125), "speed": (1.52, 1.52),
        "mode": "replace",
        "attacks": ([(4, 9)], [(4, 11)]),
        "armors": ([(4, 0), (3, 1), (8, 0), (19, 0)], [(4, 0), (3, 2), (8, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {"break_off_combat": (32, 32), "name_internal": ("RAJPUT", "ERAJPUT")},
    },
    # 70 — Landsknecht (no setUnitCosts call in source — keeps base unit's cost)
    70: {
        "name": "Landsknecht", "base_unit_id": 439,
        "elite_tech": {"cost": (850, 0, 0, 650), "time": 60},
        "unit_cost": None, "post_cost": [],
        "unit_train_time": (11, 11), "hp": (45, 55), "speed": (1.02, 1.02),
        "mode": "replace",
        "attacks": ([(4, 12), (21, 2)], [(4, 14), (21, 2)]),
        "armors": ([(1, 3), (4, 1), (3, 0), (19, 0)], [(1, 3), (4, 1), (3, 0), (19, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {
            "break_off_combat": (32, 32),
            # KM sets eID's full name/creation/help but only creation/help for
            # uuID (no Name string on the base tier) — replicated via
            # name_internal for the cosmetic field; the lang_dll asymmetry
            # itself isn't replicated (see module-level naming-string note).
            "name_internal": ("GOALS", "EGOALS"),
        },
    },
    # 76 — Castellan
    76: {
        "name": "Castellan", "base_unit_id": 1718,
        "elite_tech": {"cost": (700, 0, 0, 900), "time": 75},
        "unit_cost": {"mode": "full", "uu": (65, 0, 0, 90), "elite": (65, 0, 0, 90)},
        "post_cost": [],
        "unit_train_time": (35, 35), "hp": (55, 65), "speed": (None, None),
        "mode": "replace",
        "attacks": ([(4, 13)], [(4, 16)]),
        "armors": ([(4, 0), (3, 0), (8, 0), (19, 0), (36, 0)],
                   [(4, 0), (3, 0), (8, 0), (19, 0), (36, 0)]),
        "displayed_attack": (None, None), "displayed_melee_armor": (None, None),
        "displayed_pierce_armor": (None, None),
        "extra": {
            "break_off_combat": (96, 96), "line_of_sight": (9, 15),
            "name_internal": ("YATHQUEEN", "EYATHQUEEN"),
        },
    },
}

# ── Bespoke aura-task wiring ─────────────────────────────────────────────────
# Each entry copies a Task from a SOURCE unit's Bird.TaskList[index] (cloning
# field-for-field, then overriding the listed fields) onto BOTH the UU and
# Elite tier's own Bird.TaskList. When "for_each" is set, one such task is
# generated per unit ID in that class list, with unit_id pinned to that
# specific target (matching KM's per-class loop in createNewUnits()).
BESPOKE_TASKS: dict[int, list[dict]] = {
    41: [  # Saboteur — copied verbatim (no field overrides); likely wires up
           # the unit's self-destruct/explosion AI behavior rather than a
           # numeric buff. Source: Elephant Archer (1120) task[5].
        {"source_unit": 1120, "source_task_index": 5, "overrides": {}},
    ],
    46: [  # Apukispay — +100% work value / fast-recheck aura for every
           # "shock" class unit (Eagle line, Jian Swordsman, Fire Lancer).
        {"source_unit": 1790, "source_task_index": 5,
         "overrides": {"class_id": -1, "work_value_1": 100.0, "work_value_2": 5.0,
                       "search_wait_time": 109.0, "work_range": 2.0},
         "for_each": SHOCK_UNITS},
    ],
    56: [  # Szlachcic — three monk-aura-derived tasks (class 18, class 43,
           # and a hardcoded target unit 1811) sharing the same work params.
        {"source_unit": 1803, "source_task_index": 5,
         "overrides": {"class_id": 18, "unit_id": -1, "work_value_1": 5.0,
                       "work_value_2": 5.0, "search_wait_time": 9.0, "work_range": 10.0}},
        {"source_unit": 1803, "source_task_index": 5,
         "overrides": {"class_id": 43, "unit_id": -1, "work_value_1": 5.0,
                       "work_value_2": 5.0, "search_wait_time": 9.0, "work_range": 10.0}},
        {"source_unit": 1803, "source_task_index": 5,
         "overrides": {"class_id": -1, "unit_id": 1811, "work_value_1": 5.0,
                       "work_value_2": 5.0, "search_wait_time": 9.0, "work_range": 10.0}},
    ],
    58: [  # Rajput — small speed/work aura for every "camel" class unit.
        {"source_unit": 1790, "source_task_index": 5,
         "overrides": {"class_id": -1, "work_value_1": 1.05, "work_value_2": 1.0,
                       "search_wait_time": 5.0, "work_range": 3.0},
         "for_each": CAMEL_UNITS},
    ],
    70: [  # Landsknecht — aura for every "spear" unit, every "gunpowder"
           # unit, and the Condottiero (882) specifically.
        {"source_unit": 1790, "source_task_index": 5,
         "overrides": {"class_id": -1, "work_value_1": 0.4, "work_value_2": 6.0,
                       "search_wait_time": 10.0, "work_range": 5.0, "target_diplomacy": 4},
         "for_each": SPEAR_UNITS},
        {"source_unit": 1790, "source_task_index": 5,
         "overrides": {"class_id": -1, "work_value_1": 0.4, "work_value_2": 6.0,
                       "search_wait_time": 10.0, "work_range": 5.0, "target_diplomacy": 4},
         "for_each": GUNPOWDER_UNITS},
        {"source_unit": 1790, "source_task_index": 5,
         "overrides": {"class_id": -1, "unit_id": CONDOTTIERO_UNIT, "work_value_1": 0.4,
                       "work_value_2": 6.0, "search_wait_time": 10.0, "work_range": 5.0,
                       "target_diplomacy": 4}},
    ],
    76: [  # Castellan — single large-radius heal/regen-style aura (class 4
           # targets, i.e. melee-class allies).
        {"source_unit": 1803, "source_task_index": 5,
         "overrides": {"class_id": 4, "unit_id": -1, "work_value_1": 1.25,
                       "work_value_2": 40.0, "search_wait_time": 10.0, "work_range": 12.0}},
    ],
}


def _apply_bespoke_tasks(dat: DatFile, uu_unit, elite_unit, km_uu_index: int) -> None:
    for spec in BESPOKE_TASKS.get(km_uu_index, []):
        source = dat.civs[0].units[spec["source_unit"]]
        base_task = source.bird.tasks[spec["source_task_index"]]
        targets = spec.get("for_each")
        unit_ids = targets if targets is not None else [None]
        for target_unit_id in unit_ids:
            task = deepcopy(base_task)
            for field, value in spec["overrides"].items():
                setattr(task, field, value)
            if target_unit_id is not None:
                task.unit_id = target_unit_id
            uu_unit.bird.tasks.append(deepcopy(task))
            elite_unit.bird.tasks.append(deepcopy(task))


def _apply_merge_attacks(target_list: list, overrides: list | None) -> None:
    """'merge' mode: positional amount overwrite, positional class+amount
    reclass, or append a brand-new bonus-class entry.

    Reclass falls back to append when the index doesn't exist in the current
    DAT's attack/armor list — KM's source was written against an earlier DE
    snapshot, and at least one base unit (Amazon Archer, 850) has since
    gained/lost entries, making some of KM's literal indices stale. Treating
    a now-missing index as "this class doesn't exist yet, add it" preserves
    intent without crashing.
    """
    if overrides is None:
        return
    for entry in overrides:
        verb = entry[0]
        if verb == "new":
            _, cls, amount = entry
            target_list.append(AttackOrArmor(class_=cls, amount=amount))
        elif verb == "reclass":
            _, idx, new_cls, amount = entry
            if idx < len(target_list):
                target_list[idx].class_ = new_cls
                target_list[idx].amount = amount
            else:
                target_list.append(AttackOrArmor(class_=new_cls, amount=amount))
        else:
            idx, amount = entry
            if idx < len(target_list):
                target_list[idx].amount = amount


def _apply_replace_combat(unit, attacks: list, armors: list) -> None:
    """'replace' mode: full rebuild, mirrors KM's setCombatStats() exactly,
    including the default 0-amount filler entries for classes other vanilla
    techs assume exist (attack 11/15/21, armor 31)."""
    new_attacks = [AttackOrArmor(class_=c, amount=a) for c, a in attacks]
    present = {c for c, _ in attacks}
    for filler in (15, 11, 21):
        if filler not in present:
            new_attacks.append(AttackOrArmor(class_=filler, amount=0))
    unit.type_50.attacks = new_attacks
    disp_attack = next((a for c, a in attacks if c in (3, 4, 31)), None)
    if disp_attack is not None:
        unit.type_50.displayed_attack = disp_attack

    new_armors = [AttackOrArmor(class_=c, amount=a) for c, a in armors]
    if not any(c == 31 for c, _ in armors):
        new_armors.append(AttackOrArmor(class_=31, amount=0))
    unit.type_50.armours = new_armors
    for c, a in armors:
        if c == 3:
            unit.creatable.displayed_pierce_armour = a
        elif c == 4:
            unit.type_50.displayed_melee_armour = a


def _apply_unit_cost(unit, cost_spec: dict | None, tier: str) -> None:
    if cost_spec is None:
        return
    rc = unit.creatable.resource_costs
    if cost_spec["mode"] == "full":
        food, wood, stone, gold = cost_spec[tier]
        slot = 0
        for res_type, amount in zip(RES_SLOTS, (food, wood, stone, gold)):
            if amount > 0:
                rc[slot].type = res_type
                rc[slot].amount = amount
                rc[slot].flag = 1
                slot += 1
        for i in range(slot, 3):
            rc[i].type = -1
            rc[i].amount = 0
            rc[i].flag = 0
    elif cost_spec["mode"] == "amount":
        for slot_idx, amount in cost_spec[tier]:
            rc[slot_idx].amount = amount


def _apply_post_cost(uu_unit, elite_unit, post_cost: list) -> None:
    for tier, slot, type_, amount, flag in post_cost:
        unit = uu_unit if tier == "uu" else elite_unit
        rc = unit.creatable.resource_costs[slot]
        rc.type, rc.amount, rc.flag = type_, amount, flag


def _apply_preset_stats(uu_unit, elite_unit, preset: dict) -> None:
    hp = preset["hp"]
    if hp[0] is not None:
        uu_unit.hit_points = hp[0]
    if hp[1] is not None:
        elite_unit.hit_points = hp[1]

    speed = preset["speed"]
    if speed[0] is not None:
        uu_unit.speed = speed[0]
    if speed[1] is not None:
        elite_unit.speed = speed[1]

    tt = preset["unit_train_time"]
    if tt[0] is not None and uu_unit.creatable.train_locations:
        uu_unit.creatable.train_locations[0].train_time = tt[0]
    if tt[1] is not None and elite_unit.creatable.train_locations:
        elite_unit.creatable.train_locations[0].train_time = tt[1]

    mode = preset["mode"]
    uu_attacks, elite_attacks = preset["attacks"]
    uu_armors, elite_armors = preset["armors"]
    if mode == "merge":
        _apply_merge_attacks(uu_unit.type_50.attacks, uu_attacks)
        _apply_merge_attacks(elite_unit.type_50.attacks, elite_attacks)
        _apply_merge_attacks(uu_unit.type_50.armours, uu_armors)
        _apply_merge_attacks(elite_unit.type_50.armours, elite_armors)
        if preset["extra"].get("armors_pop_back"):
            uu_unit.type_50.armours.pop()
            elite_unit.type_50.armours.pop()
        da_uu, da_elite = preset["displayed_attack"]
        if da_uu is not None:
            uu_unit.type_50.displayed_attack = da_uu
        if da_elite is not None:
            elite_unit.type_50.displayed_attack = da_elite
        dma_uu, dma_elite = preset["displayed_melee_armor"]
        if dma_uu is not None:
            uu_unit.type_50.displayed_melee_armour = dma_uu
        if dma_elite is not None:
            elite_unit.type_50.displayed_melee_armour = dma_elite
        dpa_uu, dpa_elite = preset["displayed_pierce_armor"]
        if dpa_uu is not None:
            uu_unit.creatable.displayed_pierce_armour = dpa_uu
        if dpa_elite is not None:
            elite_unit.creatable.displayed_pierce_armour = dpa_elite
    else:
        _apply_replace_combat(uu_unit, uu_attacks, uu_armors)
        _apply_replace_combat(elite_unit, elite_attacks, elite_armors)

    extra = preset["extra"]
    if "max_range" in extra:
        u_r, e_r = extra["max_range"]
        if u_r is not None:
            uu_unit.type_50.max_range = u_r
        if e_r is not None:
            elite_unit.type_50.max_range = e_r
    if "reload_time" in extra:
        u_t, e_t = extra["reload_time"]
        if u_t is not None:
            uu_unit.type_50.displayed_reload_time = u_t
        if e_t is not None:
            elite_unit.type_50.displayed_reload_time = e_t
    if "bonus_damage_resistance" in extra:
        u_b, e_b = extra["bonus_damage_resistance"]
        if u_b is not None:
            uu_unit.type_50.bonus_damage_resistance = u_b
        if e_b is not None:
            elite_unit.type_50.bonus_damage_resistance = e_b
    # Default hero_mode to 0 (not hero-limited) for both tiers — many base
    # units cloned here (e.g. Gendarme's HVYTAU, a campaign hero) inherit
    # hero_mode=1, which silently caps the player to training exactly one.
    # Presets that genuinely want hero mode (Crusader Knight=2, and
    # Varangian Guard which explicitly resets to 0 already) override below.
    u_h, e_h = extra.get("hero_mode", (0, 0))
    if u_h is not None:
        uu_unit.creatable.hero_mode = u_h
    if e_h is not None:
        elite_unit.creatable.hero_mode = e_h
    if "break_off_combat" in extra:
        u_bo, e_bo = extra["break_off_combat"]
        if u_bo is not None:
            uu_unit.type_50.break_off_combat = u_bo
        if e_bo is not None:
            elite_unit.type_50.break_off_combat = e_bo
    if "charge" in extra:
        c = extra["charge"]
        for tier in c["tiers"]:
            unit = uu_unit if tier == "uu" else elite_unit
            unit.creatable.max_charge = c["max_charge"]
            unit.creatable.recharge_rate = c["recharge_rate"]
            unit.creatable.charge_event = c["charge_event"]
            unit.creatable.charge_type = c["charge_type"]
    if "blast" in extra:
        b = extra["blast"]
        u_lvl, e_lvl = b["attack_level"]
        if u_lvl is not None:
            uu_unit.type_50.blast_attack_level = u_lvl
        if e_lvl is not None:
            elite_unit.type_50.blast_attack_level = e_lvl
        u_w, e_w = b["width"]
        if u_w is not None:
            uu_unit.type_50.blast_width = u_w
        if e_w is not None:
            elite_unit.type_50.blast_width = e_w
    if "line_of_sight" in extra:
        u_los, e_los = extra["line_of_sight"]
        if u_los is not None:
            uu_unit.line_of_sight = u_los
        if e_los is not None:
            elite_unit.line_of_sight = e_los

    name_internal = extra.get("name_internal", (None, None))
    if name_internal[0]:
        uu_unit.name = name_internal[0]
    if name_internal[1]:
        elite_unit.name = name_internal[1]

    _apply_unit_cost(uu_unit, preset["unit_cost"], "uu")
    _apply_unit_cost(elite_unit, preset["unit_cost"], "elite")
    _apply_post_cost(uu_unit, elite_unit, preset["post_cost"])


def _make_avail_tech(dat: DatFile, civ_index: int, name: str, uu_id: int) -> int:
    """Free, hidden auto-fire tech: enables the UU once the civ reaches Castle Age."""
    eff = Effect(name=f"{name} (make avail)",
                effect_commands=[EffectCommand(type=EC_ENABLE, a=uu_id, b=1, c=-1, d=0.0)])
    dat.effects.append(eff)
    eff_id = len(dat.effects) - 1
    empty = ResearchResourceCost(type=-1, amount=0, flag=0)
    tech = Tech(
        name=f"{name} (make avail)",
        required_techs=(102, -1, -1, -1, -1, -1), required_tech_count=1,
        resource_costs=(deepcopy(empty), deepcopy(empty), deepcopy(empty)),
        civ=civ_index, full_tech_mode=1, repeatable=1,
        language_dll_name=-1, language_dll_description=-1,
        effect_id=eff_id, type=0, icon_id=-1,
        language_dll_help=-1, language_dll_tech_tree=-1,
        research_locations=[ResearchLocation(location_id=-1, research_time=0,
                                             button_id=0, hot_key_id=-1)],
    )
    dat.techs.append(tech)
    return len(dat.techs) - 1


ELITE_UPGRADE_ICON = 105   # Universal "gold medal" elite-upgrade icon — EVERY vanilla
                          # elite UU tech uses this same icon_id (confirmed by scanning
                          # all 39 entries in civ_appender._KM_UU_TECHS: all icon_id=105).
                          # Previously passed the unit's own icon here, which broke the
                          # convention players expect — reverted.


CASTLE_BTN6_HOTKEY = 18386   # Castle button 6 / "A" key — confirmed against the
                            # actual dat (e.g. tech 365 "Elite Huskarl" uses this
                            # exact value at location=82, button=6).

def _elite_tech(dat: DatFile, civ_index: int, name: str, uu_id: int, elite_id: int,
                make_avail_id: int, preset: dict, name_sid: int, desc_sid: int) -> int:
    # Vanilla elite-upgrade techs (confirmed across all 39 _KM_UU_TECHS entries,
    # e.g. tech 361 "Elite Cataphract") use ONLY EC_UPGRADE — never EC_ENABLE.
    # The engine swaps which unit a shared Castle button offers purely from the
    # EC_UPGRADE pairing, as long as both units' train_locations point at the
    # identical (building, button) — see the train_location mirroring below in
    # append_km_custom_uu. Adding EC_ENABLE here was harmless but unnecessary;
    # dropped to match vanilla exactly.
    eff = Effect(
        name=f"Elite {name}",
        effect_commands=[
            EffectCommand(type=EC_UPGRADE, a=uu_id, b=elite_id, c=-1, d=0.0),
        ],
    )
    dat.effects.append(eff)
    eff_id = len(dat.effects) - 1

    food, wood, stone, gold = preset["elite_tech"]["cost"]
    cost_pairs = [(t, a) for t, a in zip(RES_SLOTS, (food, wood, stone, gold)) if a > 0]
    n = min(len(cost_pairs), 3)
    resource_costs = tuple(
        ResearchResourceCost(type=t, amount=a, flag=1) for t, a in cost_pairs[:n]
    ) + tuple(ResearchResourceCost(type=-1, amount=0, flag=0) for _ in range(3 - n))

    tech = Tech(
        name=f"Elite {name}",
        required_techs=(103, make_avail_id, -1, -1, -1, -1), required_tech_count=2,
        resource_costs=resource_costs,
        civ=civ_index, full_tech_mode=1, repeatable=1,
        # name_sid is an EXISTING vanilla string id (see
        # civ_appender.CAMPAIGN_STRING_POOL); description/help follow the
        # vanilla engine's own fixed offset convention (name+1000/name+
        # 100000) rather than reusing name_sid directly — see
        # civ_appender._creation_sid/_help_sid's docstring for how this was
        # confirmed to be load-bearing for the Castle hover tooltip.
        language_dll_name=name_sid, language_dll_description=name_sid + 1000,
        effect_id=eff_id, type=0, icon_id=ELITE_UPGRADE_ICON,
        language_dll_help=desc_sid, language_dll_tech_tree=-1,
        research_locations=[ResearchLocation(location_id=BUILDING_CASTLE,
                                             research_time=preset["elite_tech"]["time"],
                                             button_id=ELITE_BUTTON,
                                             hot_key_id=CASTLE_BTN6_HOTKEY)],
    )
    dat.techs.append(tech)
    return len(dat.techs) - 1


def append_km_custom_uu(dat: DatFile, civ_index: int, km_uu_index: int,
                        uu_name_sid: int, uu_desc_sid: int,
                        elite_name_sid: int, elite_desc_sid: int,
                        has_krepost: bool = False) -> tuple[int, int, int, int] | None:
    """Materialize a KM-custom UU (bonuses[1] index 39-77) for civ_index.

    Appends two new units (UU + Elite) to every civ's array, bakes preset
    stats into the target civ's copies only, and creates a make-avail
    (Castle Age) tech + an elite-upgrade (Imperial Age) tech.

    Four string IDs, caller-allocated from civ_appender.CAMPAIGN_STRING_POOL
    (an EXISTING-id pool) for the two "name" ids; desc ids are expected to
    already be the DERIVED value civ_appender._help_sid(name_sid) computes
    (name_sid+100000) — see that helper's docstring for why this exact
    arithmetic relationship (not just "any pre-existing id") turned out to
    be load-bearing for the Castle hover tooltip:
      - uu_name_sid: the UU's own language_dll_name (language_dll_creation
        is derived here as uu_name_sid+1000).
      - uu_desc_sid: the UU's language_dll_help (the rich "Train <b>Name<b>
        (<cost>) \\nstats" tooltip) — caller passes _help_sid(uu_name_sid).
      - elite_name_sid / elite_desc_sid: same shape for the Elite tier, ALSO
        reused as the elite TECH's own language_dll_name/language_dll_help
        (its Castle button label / research tooltip) — consistent, since the
        tech's button conceptually represents "upgrade to Elite {name}".

    has_krepost: if True, both units get a SECOND train_location at the
    Krepost (matching the user's custom Budget Knight mod convention of
    multi-building UU training — see llm/advanced_techniques.md's
    "Multi-Building Training" pattern). This function only adds the train
    slot; it does NOT grant Krepost buildability itself — that depends on
    whatever mechanism already makes Krepost available to civ_index (today,
    only the Bulgarian civ slot has a working Krepost-enable tech in
    vanilla, and even that is civ-locked rather than tree[1]-driven).

    Returns (uu_id, elite_id, make_avail_tech_id, elite_tech_id), or None if
    km_uu_index isn't implemented.
    """
    preset = PRESETS.get(km_uu_index)
    if preset is None:
        return None

    base_id = preset["base_unit_id"]
    new_id = len(dat.civs[0].units)
    uu_id, elite_id = new_id, new_id + 1

    for civ in dat.civs:
        base = civ.units[base_id]
        uu = deepcopy(base)
        uu.id = uu_id
        # base_id/copy_id are NOT reset by deepcopy — they keep pointing at
        # the SOURCE unit (e.g. 1281 for Gendarme's campaign-hero base,
        # "HVYTAU"). Confirmed in-game: leaving this unchanged causes the
        # Castle hover tooltip to show that source's hardcoded/campaign-
        # linked bio text (e.g. "Lan Xang"/"Hill Tribes", player-slot names
        # from the Bayinnaung campaign) instead of anything we set via
        # language_dll_name/help/creation — those fields are correctly
        # written, but apparently NOT what the engine reads once it
        # resolves "this is fundamentally a copy of unit 1281" via base_id/
        # copy_id. Repointing both at the clone's own new id severs that
        # link entirely.
        uu.base_id = uu_id
        uu.copy_id = uu_id
        uu.enabled = 0
        civ.units.append(uu)

        elite = deepcopy(base)
        elite.id = elite_id
        elite.base_id = elite_id
        elite.copy_id = elite_id
        elite.enabled = 0
        civ.units.append(elite)

    if base_id < len(dat.unit_headers):
        dat.unit_headers.append(deepcopy(dat.unit_headers[base_id]))
        dat.unit_headers.append(deepcopy(dat.unit_headers[base_id]))

    uu_unit = dat.civs[civ_index].units[uu_id]
    elite_unit = dat.civs[civ_index].units[elite_id]
    _apply_preset_stats(uu_unit, elite_unit, preset)
    _apply_bespoke_tasks(dat, uu_unit, elite_unit, km_uu_index)

    # Fresh name/help/creation strings for the units themselves — without
    # this, both tiers keep showing their cloned base unit's original name
    # (e.g. Gendarme's base, a campaign hero, kept showing that hero's name).
    # name_sid is an EXISTING vanilla id (see
    # civ_appender.CAMPAIGN_STRING_POOL's docstring); desc_sid (passed in by
    # the caller as _help_sid(name_sid) = name_sid+100000) and the
    # language_dll_creation we derive here as name_sid+1000 are NOT
    # independent pool ids — they're the vanilla engine's own fixed offset
    # convention. This turned out to be the actual cause of the blank Castle
    # hover tooltip: the engine doesn't just need "any pre-existing id" in
    # language_dll_help, it specifically expects help = name+100000 (and,
    # apparently, creation = name+1000) — confirmed by surveying the live
    # dat (593-1129 units/techs matching this pattern) and by the user's own
    # working build.py (`language_dll_help = NAME_ID + 100000`).
    #
    # language_dll_hotkey_text deliberately left untouched — it's
    # "display only" for the key hint, not the main tooltip, and inherits
    # whatever the cloned base unit had.
    for unit, name_sid, desc_sid in (
        (uu_unit, uu_name_sid, uu_desc_sid),
        (elite_unit, elite_name_sid, elite_desc_sid),
    ):
        unit.language_dll_name = name_sid
        unit.language_dll_help = desc_sid
        unit.language_dll_creation = name_sid + 1000
    # Also patch civ 0 (template) — per llm/advanced_techniques.md, the
    # engine can fall back to civ0's value for some UI lookups otherwise.
    for unit_id, name_sid, desc_sid in (
        (uu_id, uu_name_sid, uu_desc_sid),
        (elite_id, elite_name_sid, elite_desc_sid),
    ):
        civ0_unit = dat.civs[0].units[unit_id]
        civ0_unit.language_dll_name = name_sid
        civ0_unit.language_dll_help = desc_sid
        civ0_unit.language_dll_creation = name_sid + 1000

    if uu_unit.creatable and uu_unit.creatable.train_locations:
        tl = uu_unit.creatable.train_locations[0]
        tl.unit_id = BUILDING_CASTLE
        tl.button_id = 1
        tl.hot_key_id = TRAIN_HOTKEY

        # Mirror the Elite tier onto the IDENTICAL (building, button) slot.
        # Confirmed against vanilla (e.g. Longbowman/Elite Longbowman both
        # train_location=(82,1,...)) — the engine swaps which unit a shared
        # Castle button offers purely from this shared slot + the
        # EC_UPGRADE pairing in the elite tech, no EC_ENABLE needed. Without
        # this mirror, the elite tier kept whatever irrelevant train_location
        # its cloned base unit originally had (e.g. Gendarme's campaign-hero
        # base pointed at building=-1), so once upgraded, nothing trains
        # from Castle btn1 at all.
        if elite_unit.creatable and elite_unit.creatable.train_locations:
            elite_tl = elite_unit.creatable.train_locations[0]
            elite_tl.unit_id = BUILDING_CASTLE
            elite_tl.button_id = 1
            elite_tl.hot_key_id = TRAIN_HOTKEY

        if has_krepost:
            # Multi-building training pattern (llm/advanced_techniques.md):
            # deepcopy the Castle slot, retarget to Krepost, same button so
            # the Q hotkey and tooltip stay consistent. Krepost btn1 (Q)
            # shares hot_key_id=16101 with Castle btn1 in vanilla (Konnik,
            # Keshik), so TRAIN_HOTKEY is reused as-is, not a new constant.
            krepost_tl = deepcopy(tl)
            krepost_tl.unit_id = BUILDING_KREPOST
            uu_unit.creatable.train_locations.append(krepost_tl)
            if elite_unit.creatable and elite_unit.creatable.train_locations:
                elite_krepost_tl = deepcopy(elite_unit.creatable.train_locations[0])
                elite_krepost_tl.unit_id = BUILDING_KREPOST
                elite_unit.creatable.train_locations.append(elite_krepost_tl)

    make_avail_id = _make_avail_tech(dat, civ_index, preset["name"], uu_id)
    elite_tech_id = _elite_tech(dat, civ_index, preset["name"], uu_id, elite_id,
                                make_avail_id, preset, elite_name_sid, elite_desc_sid)
    return uu_id, elite_id, make_avail_id, elite_tech_id
