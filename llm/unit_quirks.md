# Unit Quirks

## unit.enabled Does NOT Control Trainability

`dat.civs[civ_idx].units[uid].enabled` is NOT what determines whether a unit appears in training panels. Tested with unit 35 (Battering Ram) and unit 4 (Archer) in Britons: both have `enabled=0` yet appear in Siege Workshop / Archery Range.

**What actually controls trainability:**
1. `unit.train_location.unit_id` must point to a building that exists and is available
2. The make-avail tech for the unit must not be disabled (not in TT type=102 list), OR
3. For opt-in units (no make-avail in type=102 pool), the TT type=8 unlock must be present

`EC_ENABLE b=0` in TT effects is how Incas/Huns hide units like Mill and Spearman — it's a visibility flag on the unit panel, not a trainability gate.

## Battering Ram — Orphan Unit Pattern

Unit 35 (Battering Ram) has **no make-avail tech** in vanilla. The actual spawn chain:
- Unit **1258** (BTRAM base) trains from Siege Workshop btn 1
- Tech **162** makes unit 1258 available
- Tech **712** upgrades 1258 → 35 (Battering Ram) → 422 (Capped Ram) → 644 (Siege Ram)

To give a civ NO Battering Ram: exclude unit 1258 from `tree[0]`. This causes tech 162 to land in `to_disable`, so 1258 never appears in Siege Workshop. Removing unit 35 alone does nothing.

## EC_UPGRADE Does NOT Redirect Placements

`EC_UPGRADE(a → b)` converts existing instances of unit A to unit B when the tech fires. It does **not** redirect future placements. If a player places a new Farm after EC_UPGRADE has already converted all farms, they get a new unit-A farm, not unit-B.

For the 2×2 farm bonus (bonus 330), KM redirects placement via `duplicationUnits`. We don't have that mechanism, so instead we resize the unit data directly on unit 50 (Farm) and all its variants using `dat.civs[civ_index].units[uid]` field writes.

## KM Custom Unit Slots

KM reserves specific vanilla unit ID slots for custom purposes. These slots have `train_location.unit_id=-1` in vanilla (not trainable):

| Slot | Use |
|------|-----|
| 1262 | Feudal Knight (copies Knight data in, enables at Feudal Age, upgrades to Knight at Castle) |
| 845  | KM's 2×2 Farm copy (we don't use this; we resize unit 50 directly) |

When using slot 1262 for Feudal Knights:
1. **Copy Knight (unit 38) data first**, before any EC techs are created
2. Then overwrite hit_points, speed, LOS, search_radius, train_time
3. EC_ENABLE fires at Feudal Age to show it; EC_UPGRADE fires at Castle Age to convert it to Knight

The copy must happen before EC techs because the copy gives slot 1262 the Stable train location (button 2) from Knight — without this, EC_ENABLE fires but the unit has no building and never appears.

## Cavalier in Castle Age — Civ Gate Tech Pattern

Global Cavalier tech (209) has `required_techs=(103, 166, 768)` with `required_tech_count=2`.
- Tech 768 is a Burgundians-only gate tech that fires at Castle Age
- Copying tech 768 into a new ID doesn't satisfy tech 209's requirement for the **original** tech 768

**Fix:** Create a civ-specific copy of tech 209 with `required_techs=(102, 166)` (Castle Age + Knight make-avail). Also add a `type=102` disable for global tech 209 to the TT effect so it doesn't reappear in Imperial Age.

This is the general pattern for any bonus that depends on a civ-gate tech that belongs to a vanilla civ.

## Architecture Sets

Architecture set is set via `dat.civs[civ_index].graphics_set`. Common values mirror vanilla civs. The custom civ JSON specifies this in the `architectureSet` field (KM convention). When not specified, defaults to 0 (Western European).
