# Advanced Techniques

Patterns discovered in custom mod development (~/Sites/aoe2) that go beyond the basic EC bonus system. Relevant when implementing complex civs or cloning KM units.

---

## Creating a New Unit from Scratch

Every civ must have the **same number of units** — the engine crashes on map load if any civ's unit array differs in length. When appending a new unit:

```python
new_id = len(data.civs[0].units)   # next available index

for civ in data.civs:
    src   = civ.units[SOURCE_UNIT_ID]
    clone = _clone_unit(src, data.version)  # serialization round-trip, not deepcopy
    clone.id      = new_id
    clone.enabled = 0   # disabled by default; tech enables it later
    civ.units.append(clone)

# Apply stat changes to the specific civ ONLY after the append loop:
unit = data.civs[CIV_TARGET].units[new_id]
unit.hit_points = 95
```

Use a serialization round-trip (to_bytes → from_bytes) rather than `deepcopy` to avoid shared-reference bugs in genieutils objects.

**Critical:** EC_ADD / EC_MULTIPLY targeting newly appended unit IDs does NOT work in the AoE2 engine. Stat changes for custom units must be baked directly into the DAT. Only EC commands targeting pre-existing vanilla unit IDs work reliably.

---

## Hero Units (One-at-a-Time)

```python
unit.creatable.creatable_type = 1
unit.creatable.hero_mode      = 1
```

Hero mode enforces one-at-a-time spawn enforcement and draws the gold border around the portrait.

---

## Multi-Building Training (Permanent Civ Bonus)

To make a unit trainable at multiple buildings from day one (not tech-gated), add extra `train_location` entries directly in the DAT:

```python
from copy import deepcopy
extra = deepcopy(unit.creatable.train_locations[0])
extra.unit_id   = BUILDING_STABLE     # 101
extra.button_id = 5
unit.creatable.train_locations.append(extra)
```

Apply only to the specific civ's units array (each civ has its own).

**Confirmed working:** Tarkan and Iron Pagoda (unit 1908) both use this pattern to train at Castle + Stable simultaneously.

---

## Marauders Mechanism (Tech-Gated Training at New Building)

`ATTR_TRAIN_LOC = 42` **replaces** the primary training building — it does NOT add a secondary.

```python
EC_ENABLE(a=unit_id, b=1)              # show the unit
EC_SET(a=unit_id, c=ATTR_UI_REFRESH, d=1.0)   # c=158
EC_SET(a=unit_id, c=ATTR_TRAIN_LOC, d=float(NEW_BUILDING_ID))  # c=42
EC_SET(a=unit_id, c=ATTR_UI_REFRESH, d=0.0)
```

If the unit was at Castle and you do this with Barracks, it moves to Barracks only. Use the DAT multi-building approach if you need both simultaneously.

---

## Passive Heal Aura

```python
# In tech effect:
EC_SET(a=unit_id, b=-1, c=63, d=34.0)   # Castle aura rate
EC_SET(a=unit_id, b=-1, c=63, d=32.0)   # Monk aura rate
```

`c=63 = ATTR_HEAL_RATE`. Works on any unit that can "attack" nearby allies.

---

## Slow-on-Attack Aura (blast_damage)

`unit.type_50.blast_damage` has **no corresponding EffectCommand attribute ID**. It cannot be set via a tech effect. To gate it behind a tech:

1. Clone the unit with `blast_damage = -5.0` and `blast_attack_level = 2` pre-baked, `enabled=0`
2. Use `EC_UPGRADE(base → slow_clone)` + `EC_ENABLE(slow_clone, 1)` in the tech effect

The negative `blast_damage` value slows enemies in the blast radius.

---

## Charge Attack (Comitatenses Mechanism)

Units without native charge attacks need all four attributes:

```python
EC_ADD(a=uid, b=-1, c=59, d=5.0)    # ATTR_MAX_CHARGE — pool size
EC_ADD(a=uid, b=-1, c=60, d=0.25)   # ATTR_RECHARGE_RATE — per second
EC_SET(a=uid, b=-1, c=61, d=1.0)    # ATTR_CHARGE_EVENT — trigger on attack
EC_SET(a=uid, b=-1, c=62, d=1.0)    # ATTR_CHARGE_TYPE — melee charge
```

Missing any one results in no visible charge behavior.

---

## Age-Scaling Civ Bonuses (C-Bonus Pattern)

To apply a civ-specific bonus that fires automatically when a civ advances an age:

```python
TEMPLATE_IDS = {101: 711, 102: 727, 103: 728}  # age_tech_id → template_tech_id

for age_tech, template_id in TEMPLATE_IDS.items():
    new_tech = deepcopy(data.techs[template_id])
    new_tech.civ       = CIV_TARGET
    new_tech.effect_id = my_effect_id
    new_tech.name      = f"My C-Bonus {age_tech}"
    data.techs.append(new_tech)
```

Templates 711/727/728 are global auto-fire techs (location_id=-1, research_time=0) that trigger on Feudal/Castle/Imperial age. Setting `civ=CIV_TARGET` restricts firing to that civ. Stacking three ×1.05 multipliers compounds to ×1.157 (+15.7%) at Imperial.

---

## Generate-Resources Tasks (Keshik Gold Pattern)

Task-based resource generation (`action_type=151`) is **not** an EffectCommand attribute. Rules:

- Tasks must exist in BOTH `data.unit_headers[unit_id].task_list` AND each `civ.units[unit_id].bird.tasks`
- `data.civs[0]` (template civ) must have the tasks — the engine checks civ 0 to determine whether a unit CAN run resource tasks at all
- The Keshik has 21 tasks (one per unit class_id: 0,2,4,6,12,13,18,19,20,21,22,23,35,36,43,44,47,51,54,55,59). Copying only one task 21 times = gold vs only one target class
- Gate per-civ via `EC_RESOURCE` setting the multiplier resource (213 for Keshik) from 0 to positive

`EC_MULTIPLY c=13` (ATTR_WORK_RATE) on a building does NOT affect action_type=151 tasks — only direct `task.work_value_1` mutation works.

---

## Death Refund (Tupi Mechanism)

```python
EC_RESOURCE(a=33,  b=0, d=27.0)   # resource 33=27 activates death-refund mode
EC_RESOURCE(a=295, b=0, d=0.33)   # resource 295 = refund rate (0.0–1.0)
```

---

## Instant Death / Explosion Unit

```python
clone.hit_points              = -1     # dies immediately on spawn
clone.dying_graphic           = -1     # skip dying animation
clone.dead_unit_id            = -1     # no follow-up corpse
clone.type_50.blast_attack_level = 2   # blast all units
clone.type_50.attacks[*].amount  = 25  # blast damage amount
```

Gate via `EC_SET(a=source, c=57, d=float(clone_id))` (`ATTR_DEAD_UNIT = 57`) — the explosion clone spawns when the source unit dies.

---

## EC type=7 SPAWN

Spawns units directly from a building:
```
type=7: a=unit_id, b=building_id, c=count, d=0.0
```

Rarely used; confirm behavior in-game before shipping.

---

## Attack / Armor Value Encoding

When using EC_ADD/EC_SET for attack or armor, the `d` value encodes both class and amount:

```python
def encode_armor(armor_class: int, amount: int) -> float:
    return float(armor_class * 256 + amount)

# Common classes:
# MELEE_CLASS  = 4
# PIERCE_CLASS = 3

# Example: +3 melee attack
EC_ADD(a=unit_id, b=-1, c=9, d=encode_armor(4, 3))   # c=9 = ATTR_ATTACK
```

---

## Hotkeys: hot_key_id Reference

When adding a unit to a building slot, always set `train_location.hot_key_id` explicitly — changing only `button_id` does NOT update the key binding.

| Slot | hot_key_id | Example |
|------|-----------|---------|
| Castle btn1 (Q) | 16101 | Iron Pagoda, Konnik |
| Castle btn6 (A) | 18386 | 2nd dual-UU slot |
| Krepost btn1 (Q) | 16101 | Konnik, Keshik |
| Stable btn3 (E) | 16416 | Heavy Cavalry line |
| Barracks btn2 (W) | 16078 | Pikeman/Spear |
| Barracks btn3 (E) | 16679 | Condottiero |
| Barracks btn4 (R) | 16748 | Huskarl (vanilla) |

For slots with no vanilla analogue (Castle btn10, etc.), use a building construction hotkey ID — the first character of its string becomes a fixed key. `hot_key_id=2012` → fixed G key.

---

## Language String Pitfalls

- **MAJOR — the modded-strings overlay can ONLY override IDs that already exist in the base game's string table.** A brand-new ID outside that range is silently ignored by the engine, no matter which `language_dll_*` field points at it, no matter how correctly it's written to the DAT and the strings file, and regardless of whether the mod is installed locally or published to Steam Workshop. Confirmed via a controlled live test: rich tooltip text at a brand-new high-range id (e.g. 750016) never appeared in-game despite being independently verified correct at every layer; the SAME text at an *existing* vanilla id (70104) worked immediately. This is NOT a DAT-struct width issue — the relevant struct fields are full 32-bit ints (verified against genieutils' actual format), so the field can numerically hold any id; the limitation is in how the engine resolves the overlay file. See [[project_string_id_engine_limit]] in memory for the full incident writeup. **Practical implication: any high "verified-clear" range is a false sense of safety — collision-free is not the same as working.** Use `civ_appender.CAMPAIGN_STRING_POOL` (real, currently-defined campaign IDs) instead of inventing a new range.
- **KM units with 405xxx/505xxx dll values** must be patched in BOTH the target civ AND `dat.civs[0]` (civ0 template). If only the target civ is patched, the game may fall back to civ0's broken value for UI display.
- **Override vanilla IDs for repurposed units**: pointing `language_dll_name` to a custom string ID that doesn't exist in the game's base string table causes blank training buttons — consistent with the finding above; this was the same symptom, just first noticed for the simpler "name" field years before the full scope was understood.

### String-ID Sourcing — Use Existing IDs, Not "Clear" Ranges

Don't allocate a brand-new numeric range and verify it's merely *collision-free* — that doesn't mean it works (see above). Instead, harvest a pool of IDs that are **actually defined** in the shipped `key-value-strings-utf8.txt` (request the full file from the user if you only have a partial extract — campaign content lives in separate per-campaign sections, e.g. `// Bayinnaung 4`). Locate campaign-mission boundaries via `grep -n "^// [A-Za-z].* [0-9]$"`, then extract real IDs per mission via `grep -E "^[0-9]+\s"`. Prefer adjacent missions of the SAME campaign so the "disable the UI mod before playing campaign X" caveat stays scoped to as few campaigns as possible. `civ_appender.CAMPAIGN_STRING_POOL` is the reference implementation (1813 ids) — fully migrated across `km_custom_uu.py`, bonus 308/309/310, and the Castle/Imperial UT button-name block.

**You only need ONE pool id per unit/tech** (the "name" id) — every other field is a fixed arithmetic offset from it, matching vanilla's own internal convention (confirmed by surveying the live dat and by the user's own confirmed-working `~/Sites/aoe2/build.py`, whose `_sids(base)` helper returns exactly these offsets):
- `name` → `language_dll_name`
- `name+1000` (`DLL_CREATION_OFFSET`) → `language_dll_creation` (units) / `language_dll_description` (techs)
- `name+100000` (`DLL_HELP_OFFSET`) → `language_dll_help` — works for TECH research-button tooltips, NOT a unit's train-button tooltip (see below)
- `name+150000` (`DLL_TECH_TREE_OFFSET`) → `language_dll_tech_tree` (techs only)
- `name+21000` — units only, no DAT field, see below

Setting a field to a derived offset id is not enough on its own — you must ALSO write override text at that exact id in the strings file, or the engine falls back to whatever real (possibly very visible, colored) vanilla content already happens to live at that numeric slot instead of leaving it blank. This caused a real regression once: a Castle UT button started showing an unrelated campaign dialogue line because the `+1000` write was missing.

**The accepted cost:** overriding an existing id changes that text everywhere the game reads it, including inside the campaign mission that originally owned it. This only affects players who have the mod's UI half active AND specifically play that exact mission — skirmish, multiplayer, and every other campaign are unaffected.

### Unit Tooltip Text — TWO separate slots, only one has a DAT field

A custom unit's Castle "create unit" train-button hover tooltip is **not** read from `language_dll_help` (`name+100000`) — that's the wrong slot for units (it IS correct for tech research buttons). It's read from **`name+21000`, a string id with no corresponding DAT field at all** — confirmed live by diffing the user's own shipped, playtested `build.py` mod (Elite Budget Knight) against its actual in-game text. The engine appears to derive this id internally from `language_dll_creation+20000`; you just need to write the text, no field to set.

```python
# name+21000 — the one that actually shows in the Castle train-button tooltip.
# Verb "Create", no "Cost:" breakdown, ends with a bracketed tag.
civ_appender.format_unit_extended_tooltip(unit, name, tag="Civname unique unit")
# -> "Create <b>{name}<b> (<cost>) \n{HP} HP | {attack} attack | {melee}/{pierce} armor. [{tag}]"

# name+100000 — also write this; it's read by OTHER UI surfaces (research-style
# tooltips elsewhere) even though it's not what the Castle train button shows.
# Verb "Train", keeps a space before \n, ends with a Cost:/Trainable-at line.
civ_appender.format_unit_tooltip_help(unit, name, extra="Trainable at Castle.")
# -> "Train <b>{name}<b> (<cost>) \n{HP} HP | {attack} attack | {melee}/{pierce} armor. Cost: {cost}. {extra}"
```

- `<cost>` in both is an **engine token** — AoE2 substitutes the real formatted cost automatically. Do not pre-format it yourself.
- For an upgrade-TECH's own research button (not a unit), use only the `+100000`/`Research` convention — techs don't need the `+21000` slot, since the research-button widget correctly reads `language_dll_help`.
- Reference implementations: `civ_appender.format_unit_tooltip_help()` (the `+100000` text) and `civ_appender.format_unit_extended_tooltip()` (the `+21000` text, `_extended_tooltip_sid()` computes the id).

---

## Building/Unit IDs Quick Reference

| Constant | ID |
|----------|----|
| BUILDING_CASTLE | 82 |
| BUILDING_KREPOST | 1251 |
| BUILDING_BARRACKS | 12 |
| BUILDING_STABLE | 101 |
| BUILDING_ARCHERY_RANGE | 87 |
| UNIT_SABOTEUR | 706 — safe base for cloning explosion units |
| MELEE_ARMOR_CLASS | 4 |
| PIERCE_ARMOR_CLASS | 3 |
