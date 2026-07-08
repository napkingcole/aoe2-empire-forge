# Effect Commands (EffectCommand)

EffectCommands are the primitive operations inside an AoE2 DE `Effect` object. They are applied when their parent tech fires. All fields: `type`, `a`, `b`, `c`, `d` (d is float, others int).

## Type Reference

### EC_SET = 0
Set a unit attribute to an absolute value.
```
a = unit_id   b = -1   c = attribute_id   d = new_value
```

### EC_RESOURCE = 1
Modify a player resource (food/wood/stone/gold or any resource slot).
```
a = resource_id   b = mode   c = -1   d = amount
```
**b modes:**
- `b=0` — set resource to d
- `b=1` — add d to resource (one-time bonus at tech fire)
- `b=-1` — trickle: add d per game second, continuously

**Critical quirk:** `b=-1` trickle requires `tech.repeatable = 1` on the parent tech. If repeatable=0 (our `_make_tech` default), the trickle fires once and stops. This burned us on Vineyards/Paper Money.

### EC_ENABLE = 2
Show or hide a unit in training panels.
```
a = unit_id   b = 1(enable) / 0(disable)   c = -1   d = 0.0
```
**Does NOT control trainability.** Units appear in training panels based on `train_location.unit_id` pointing to an available building. EC_ENABLE controls the visibility flag only. See `unit_quirks.md` for the full picture.

### EC_UPGRADE = 3
Upgrade (replace) all of one unit type with another for this civ.
```
a = from_unit_id   b = to_unit_id   c = -1   d = 0.0
```
Does NOT redirect future placements. If a player places unit A after EC_UPGRADE has fired, they still get unit A — only existing instances are converted. For placement redirection (e.g. 2×2 farms), you must copy unit data directly into the target slot.

### EC_ADD = 4
Add to a unit attribute.
```
a = unit_id   b = -1   c = attribute_id   d = delta
```

### EC_MULTIPLY = 5
Multiply a unit attribute by a factor.
```
a = unit_id   b = -1   c = attribute_id   d = multiplier
```
**Full attribute ID reference (c parameter):**

| c   | Constant           | Description |
|-----|--------------------|-------------|
| 0   | ATTR_HP            | Hit points |
| 1   | ATTR_LOS           | Line of sight |
| 5   | ATTR_SPEED         | Movement speed |
| 8   | ATTR_ARMOR         | Armor (encode: class×256 + amount) |
| 9   | ATTR_ATTACK        | Attack (encode: class×256 + amount) |
| 10  | ATTR_RELOAD_TIME   | Attack reload time (lower = faster) |
| 11  | ATTR_ACCURACY      | Accuracy percent |
| 12  | ATTR_MAX_RANGE     | Maximum attack range |
| 13  | ATTR_WORK_RATE     | Building/unit work rate multiplier |
| 22  | ATTR_BLAST         | Blast/trample radius |
| 24  | ATTR_BONUS_DMG_MOD | Incoming bonus damage multiplier |
| 42  | ATTR_TRAIN_LOC     | Training building (Marauders — REPLACES primary slot) |
| 57  | ATTR_DEAD_UNIT     | Unit spawned on death |
| 59  | ATTR_MAX_CHARGE    | Charge attack energy pool |
| 60  | ATTR_RECHARGE_RATE | Charge attack recharge rate |
| 61  | ATTR_CHARGE_EVENT  | Charge trigger (1=on attack) |
| 62  | ATTR_CHARGE_TYPE   | Charge type (1=melee) |
| 63  | ATTR_HEAL_RATE     | Passive heal aura rate |
| 101 | ATTR_TRAIN_TIME    | Unit creation time |
| 102 | ATTR_EXTRA_PROJ_1  | Extra projectile count (part 1 of 2) |
| 107 | ATTR_EXTRA_PROJ_2  | Extra projectile count (part 2 of 2) |
| 109 | ATTR_REGEN_HP      | HP regeneration per minute |
| 158 | ATTR_UI_REFRESH    | No-op toggle — pair with ATTR_TRAIN_LOC to force UI update |

**Attack/armor encoding:** `d = float(class_id * 256 + amount)`. Use the armor class IDs below.

**Full armor class list:**

| ID | Name | Notes |
|----|------|-------|
| 0  | WONDER | |
| 1  | INFANTRY | |
| 2  | TURTLE_SHIP | |
| 3  | PIERCE | base pierce armor/attack |
| 4  | MELEE | base melee armor/attack |
| 5  | ELEPHANT | |
| 8  | CAVALRY | |
| 11 | BUILDING | |
| 13 | STONE_WALL_GATE | |
| 14 | PREDATOR_ANIMAL | |
| 15 | ARCHER | |
| 16 | SHIP | |
| 17 | RAM_TREBUCHET | |
| 19 | UNIQUE_UNIT | |
| 20 | SIEGE_WEAPON | |
| 21 | STANDARD_BUILDING | |
| 22 | WALL_GATE | |
| 23 | GUNPOWDER | |
| 24 | HUNTED_PREDATOR_ANIMAL | |
| 25 | MONK | |
| 26 | CASTLE | |
| 27 | SPEARMAN | |
| 28 | CAVALRY_ARCHER | |
| 29 | EAGLE_WARRIOR | |
| 30 | CAMEL | |
| 32 | CONDOTTIERO | |
| 34 | FISHING_SHIP | |
| 35 | MAMELUKE | |
| 36 | HERO | |
| 37 | BALLISTA_ELEPHANT_WAGON | |
| 38 | SKIRMISHER | |
| 39 | CAMEL_SHOTEL | |

**"All units" targeting:** `a=-1, b=class_id` applies to all units of that class (same pattern as Chemistry).

**EC_ADD "needs baseline zero" caveat:** If a unit has NO existing attack entry for a given armor class, `EC_ADD` against that class does nothing — the engine finds no matching entry to add to. You must first set a baseline `AttackOrArmor(class, 0)` on the unit data directly before the tech fires.

### type = 6 — Resource Modifier Multiplicative
Multiply a resource value by a factor.
```
a = resource_id   b = 0(set)/1(add)   c = -1   d = multiplier
```

### Scoped Variants (TEAM / ENEMY / NEUTRAL / GAIA)
All of types 0–7 have four additional scoped forms that apply the same effect to a different player group. Add the corresponding offset to the base type number:

| Base type | +10 = TEAM | +20 = ENEMY | +30 = NEUTRAL | +40 = GAIA |
|-----------|-----------|------------|--------------|-----------|
| 0 (SET)   | 10 | 20 | 30 | 40 |
| 1 (RESOURCE ADD) | 11 | 21 | 31 | 41 |
| 2 (ENABLE) | 12 | 22 | 32 | 42 |
| 3 (UPGRADE) | 13 | 23 | 33 | 43 |
| 4 (ADD) | 14 | 24 | 34 | 44 |
| 5 (MULTIPLY) | 15 | 25 | 35 | 45 |
| 6 (RES_MULTIPLY) | 16 | 26 | 36 | 46 |
| 7 (SPAWN) | 17 | 27 | 37 | 47 |
| 8 (MODIFY_TECH) | 18 | 28 | 38 | 48 |

Example: type=14 = TEAM_ATTRIBUTE_MODIFIER_ADDITIVE; gives the bonus to all allied players. This is how team bonuses work (e.g. "Team gets +5 LOS on scouts").

### EC_TECH_COST = 101
Modify the resource cost of a tech.
```
a = tech_id   b = resource(0-3)   c = 0(set)/1(add)   d = value
```
To zero a tech's cost across all resources: loop b=0..3 with c=0, d=0.0.

### EC_TECH_TIME = 103
Modify the research time of a tech.
```
a = tech_id   b = -1   c = 0(set)   d = seconds
```

## Non-standard Types

### type = 8 — Unlock Tech
Makes a tech researchable for this civ. Used for opt-in techs (Battle Elephants, Elephant Archers) that are NOT in the global type=102 disable pool — every civ that wants them must explicitly add a type=8 command to its tech tree effect.
```
a, b, c, d copied verbatim from any vanilla civ that already has it
```

### type = 102 — Disable Tech
Disables a tech for this civ. Used in the tech tree effect to block unit lines not in the civ's tree.
```
a = -1   b = -1   c = -1   d = float(tech_id)
```
Note: only techs that appear in at least one vanilla civ's type=102 list can be disabled this way (they must be in `all_disableable`). Opt-in techs (type=8 pool) cannot be disabled via type=102.
