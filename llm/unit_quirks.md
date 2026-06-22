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

## Shared Train-Button Swap Requires Mirrored train_location, Not EC_ENABLE

When two units (base tier + elite tier) are meant to share one training-button slot — e.g. Longbowman → Elite Longbowman both occupying Castle btn1 — the mechanism is NOT `EC_ENABLE` on the elite unit. Checked all 39 vanilla elite-UU upgrade techs (the full `civ_appender._KM_UU_TECHS` table): zero of them use `EC_ENABLE`. Every single one is `EC_UPGRADE(base, elite)` alone.

**What actually makes the swap work:** both units' `creatable.train_locations[0]` must point at the IDENTICAL `(unit_id, button_id)` — confirmed directly: Longbowman and Elite Longbowman both have `train_location=(82, 1, ...)`. The engine appears to use this shared-slot + `EC_UPGRADE` pairing to decide which unit a button offers; it does not need an explicit enable.

**The bug this causes if missed:** when cloning a brand-new "elite" unit from an unrelated base (e.g. a campaign-hero unit, as in `km_custom_uu.py`'s custom-UU presets), the clone inherits whatever `train_location` its source unit originally had — frequently `unit_id=-1` or some unrelated building/button. If you only fix up the BASE tier's `train_location` (pointing it at Castle btn1) and forget the ELITE tier, the unit trains fine until the elite upgrade researches — at which point nothing is offered at that button anymore, since the elite clone's `train_location` never pointed there to begin with. Fix: explicitly mirror `(building, button, hot_key)` from the base tier onto the elite tier's `train_location[0]` before finishing.

## Elite-UU Upgrade Tech Icon Is Always 105 ("Gold Medal"), Never Unit-Specific

Scanned every elite-UU upgrade tech's `icon_id` across all 39 `_KM_UU_TECHS` entries (Elite Longbow, Elite Cataphract, Elite Teutonic Knight, etc.) — all 39 use `icon_id=105`. This is the universal "gold medal" elite-upgrade icon players expect; it is NOT meant to reflect the specific unit. Do not substitute the unit's own icon here — that breaks the established convention even though it might look more "related" at a glance.

## Krepost (and Similarly Building-Gated) Availability May Not Show Up in tree[1]

Don't assume "civ has building X" is fully captured by `tree[1]` containing that building's ID. Some buildings are gated behind a dedicated **bonus ID** instead — confirmed for Krepost: bonus 93 ("Can build Krepost") maps to vanilla tech 695 (`EC_ENABLE(1251, 1)`, fires at Castle Age), applied via the generic `civ_bonus_techs` catalog path, which already deepcopies and retargets it correctly for ANY civ — no civ-specific handler code needed. A real production civ_def (`ignore/barracks_enjoyers.json`) uses bonus 93 without ever listing building 1251 in `tree[1]`. If a feature needs to know "does this civ have building X," check the actual bonus IDs that grant it (cross-reference `bonus_catalog_raw.json`'s `civ` map) in addition to — not instead of — `tree[1]` membership.
