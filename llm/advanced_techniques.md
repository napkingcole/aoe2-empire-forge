# Advanced Techniques

Patterns discovered in custom mod development (~/Sites/aoe2) that go beyond the basic EC bonus system. Relevant when implementing complex civs or cloning KM units.

---

## Tech Prerequisites — OR-Logic with required_tech_count

`tech.required_tech_count` controls how many of the `required_techs` tuple must be satisfied. Setting it to `1` while listing multiple IDs creates OR-logic — the tech unlocks when ANY ONE prerequisite is met:

```python
df.techs[COINAGE].required_techs = (techs.CASTLE_AGE, dummy_feudal_gate_id, -1, -1, -1, -1)
df.techs[COINAGE].required_tech_count = 1
# Every civ meets Castle Age → unaffected.
# Franks meet dummy_feudal_gate_id at Feudal → they unlock Coinage early.
```

To add a civ-specific early-access gate without locking out other civs:
1. Create a civ-restricted dummy tech with `civ=TARGET_CIV` that fires as a prerequisite in an earlier age.
2. Add it as an extra entry in `required_techs` WITHOUT incrementing `required_tech_count`.

This is the pattern used by Burgundians Cavalier (tech 768) and can be applied to any civ-specific age-unlock.

---

## Unit Duplication — Update base_id and copy_id

When duplicating a unit for multi-building training, update both fields after appending:

```python
civ.units.append(missionary_copy)
new_id = len(civ.units) - 1
civ.units[new_id].base_id = new_id
civ.units[new_id].copy_id = new_id
civ.units[new_id].creatable.train_location_id = NEW_BUILDING
```

Also loop every effect in the game and duplicate any EffectCommand with `a == ORIGINAL_UNIT_ID` so the copy receives the same buffs/upgrades (EXCEPT upgrade chains — those need separate handling so each tier upgrades along its own line).

---

## ResourceStorage — Building On-Build/On-Death Resource Effects

`unit.resource_storages` is a 3-tuple of `ResourceStorage(resource_id, amount, mode)` where `mode` controls when the resource change fires:

| mode | Trigger |
|------|---------|
| 1    | On creation (permanent — kept after death) |
| 2    | On death/destruction (gives back — must be negative to deduct on build) |
| 4    | On completion of construction AND on death (round-trip: deduct on build, refund on destroy) |
| 8    | On completion of construction only (permanent) |
| 64   | On completion; fire and forget (used for token resources) |

The "only one castle at a time" pattern:
1. Give all civs `civ.resources[CASTLE_RESOURCE] = 1` as a starting balance.
2. Add `ResourceCost(CASTLE_RESOURCE, 1, flag=0)` to the Castle's costs — checks you have 1 but doesn't deduct (flag=0 = don't pay).
3. Add `ResourceStorage(CASTLE_RESOURCE, -1, mode=2)` to Castle's storages — deducts 1 on completion, refunds on destruction.

---

## Hero Mode Flags

`unit.creatable.hero_mode` is a bitmask — combine by addition:

| Value | Effect |
|-------|--------|
| 1     | One-at-a-time (gold border portrait, can't train another while alive) |
| 2     | Cannot be converted |
| 4     | HP regeneration |
| 6     | Cannot be converted AND regenerates (2+4) |

Full list on the [AoE2DE UGC Guide](https://ugc.aoe2.rocks/).

---

## Charge Type 4 — Projectile Dodge

In addition to melee charges (`charge_type=1`), `charge_type=4` implements a projectile dodge (Shrivamsha Rider pattern):

```python
unit.creatable.max_charge = 1
unit.creatable.recharge_rate = 1
unit.creatable.charge_event = 0   # not triggered by attacking
unit.creatable.charge_type = 4    # dodge mode
```

Can be applied to any unit or building — the Shrivamsha Rider is the canonical reference.

---

## civ.resources[] — Starting Resource Values

Each `Civ` object has a `resources` list indexed by resource ID. You can set any slot directly without using EC_RESOURCE:

```python
CUSTOM_RESOURCE = 120
for civ in df.civs:
    civ.resources[CUSTOM_RESOURCE] = 1  # every civ starts with 1 of this resource
```

This is how starting scout ID, MERCENARY_KIPCHAK_COUNT cap, and similar per-civ startup values work in vanilla. Useful for building-limit or token mechanics.

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

## Unit Voice Assignment — DAT + .wem Files Both Required

Unit voices in AoE2:DE do **not** respond to DAT SoundItem changes alone. Two things must happen:

### 1. DAT SoundItem remapping (KM 3-phase algorithm)

`assign_all_languages(dat, assignments)` in `civ_appender.py` runs after all civs are processed:

- **Phase 1:** For each `(civ_index, lang_val)`, copy every SoundItem where `item.civilization == lang_val + 1` into a temporary slot at `civ_index + 100`
- **Phase 2:** Delete all items where `0 < civilization < 100` (removes all vanilla per-civ sound bindings)
- **Phase 3:** Subtract 100 from all remaining `>= 100` items, landing them at their final civ slots

This is exactly KM's `assignLanguages()` algorithm (`civOffset=100`, `civbuilder.cpp` line 564).

### 2. Physical .wem files in the UI mod

The engine resolves the SoundItem `filename` (e.g. `jvmb.wav`) and looks for a matching `.wem` file at `resources/_common/drs/sounds/jvmb.wem` inside the UI mod zip. Without the file, it falls back to Wwise audio bank routing, which plays the slot's vanilla civ's voices (typically Aztec for a new slot).

**Source:** `voice_files/<lang_val>/` in the project root — 43 folders (0–42, one per KM language index), ~58 .wem files each. Pre-extracted from the game by KM's build server. `_build_combined_ui_zip` in `build_all.py` takes `lang_values: set[int]` and writes the matching .wems into the UI zip.

**KM language index → civ voice prefix mapping (confirmed):**

| lang_val | prefix | Civ |
|----------|--------|-----|
| 0 | b | Britons |
| 1 | ff | Franks |
| 2 | g | Goths |
| 3 | te | Teutons |
| 4 | j | Japanese |
| 5 | c | Chinese |

Read `Japanese.json` (or any KM civ JSON) — the `language` field is the 0-based KM civ index = the subfolder number.

---

## Architecture Copy — Castle and Wonder Are Both class_=3

`_copy_architecture(dat, src_idx, dst_idx)` copies building graphics for all units whose `class_` is in `_ARCH_BUILDING_CLASSES = {3, 52, 27, 39}`. Both Castle (unit 82) and Wonder (unit 276) have `class_=3`, so both would be overwritten by an architecture copy.

**Critical:** `_copy_architecture` is called AFTER the castle and wonder are assigned in `apply_civ`. Without an explicit exclusion, the architecture pass silently overwrites the user's castle/wonder choice with the architecture set's graphics.

**Fix (already in code):** The guard in `_copy_architecture` excludes both:
```python
if cls in _ARCH_BUILDING_CLASSES and i != BUILDING_CASTLE and i != BUILDING_WONDER:
```

`BUILDING_CASTLE = 82`, `BUILDING_WONDER = 276` are defined at the top of `civ_appender.py`. If you ever add additional per-civ building choices that have `class_` in `_ARCH_BUILDING_CLASSES`, add them to this exclusion list.

---

## Building/Unit IDs Quick Reference

| Constant | ID |
|----------|----|
| BUILDING_CASTLE | 82 |
| BUILDING_WONDER | 276 |
| BUILDING_KREPOST | 1251 |
| BUILDING_BARRACKS | 12 |
| BUILDING_STABLE | 101 |
| BUILDING_ARCHERY_RANGE | 87 |
| UNIT_SABOTEUR | 706 — safe base for cloning explosion units |
| MELEE_ARMOR_CLASS | 4 |
| PIERCE_ARMOR_CLASS | 3 |

## Building Architecture-Set Variant Lists

Each building type has multiple unit IDs — one per architecture set. When applying a stat change to "all versions of Barracks" you must iterate all variants:

```python
ARCHERY_RANGE_ALL = [87, 10, 14]
BARRACKS_ALL      = [12, 498, 132, 20]
BLACKSMITH_ALL    = [103, 18, 19]
MONASTERY_ALL     = [104, 31, 32]
DOCK_ALL          = [45, 133, 47, 51]
SIEGE_WORKSHOP_ALL= [49, 150]
HOUSE_ALL         = [70, 463, 464, 465, 191, 192]
TOWN_CENTER_ALL   = [109, 71, 141, 142, 618, 619, 620, 621, 614, 615, 616, 617, 481, 482, 483, 484, 611, 612, 613, 597]
MARKET_ALL        = [84, 116, 137, 1646]
STABLE_ALL        = [101, 86, 153]
MILL_ALL          = [68, 129, 130, 131]
UNIVERSITY_ALL    = [209, 210]
LUMBER_CAMP_ALL   = [562, 563, 564, 565]
MINING_CAMP_ALL   = [584, 585, 586, 587]
FOLWARK_ALL       = [1734, 1711, 1720]
```

For per-civ graphic changes (not stat changes), iterate `df.civs` instead — each civ's unit list holds the civ-specific version. Stat changes should go through all architecture variants above.
