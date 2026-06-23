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

## "Free Team Units Per Castle" UTs (Elite Mercenaries/bonus 9) Need a Dedicated Unit Slot — Not Just an Enable

Some vanilla Castle/Imperial UTs hardcode a reference to their OWN civ's specific unique unit via undocumented effect types 7 and 12 (team-scoped variants of EC_UPGRADE/EC_ENABLE — not caught by the standard `type not in (EC_ENABLE, EC_UPGRADE)` filter, since those check types 2/3, not 7/12). Confirmed for tech 690 "Cuman Mercenaries" (KM bonus 9, imperial UT slot): type=12's `a` field is unit 1260 (Cumans' own Elite Kipchak). Blindly copying it to another civ's UT references the WRONG unit — confirmed live that this also corrupts the Castle research-button tooltip, which falls back to a vanilla Scenario Editor placeholder string ("Click to enter a filename to save your custom campaign as.", id 91202) instead of showing the UT's real text. The engine appears to choke on resolving the foreign-civ unit reference rather than failing gracefully.

**The harder part — type=12 specifically needs a SEPARATE unit, not just the right unit id.** `resource_costs`/`train_locations` live on the unit object itself, shared across every way that unit can be trained. Cumans don't reuse their normally-trained Elite Kipchak (1233, trained at the Stable for food/gold) for the "free" mechanic — they have a dedicated duplicate, **MKIPCHAK (1260)**, that exists ONLY for this: `train_locations=[TrainLocation(train_time=12, unit_id=82, button_id=4, hot_key_id=16730)]`, `resource_costs=(ResourceCost(type=214, amount=1, flag=1), ResourceCost(type=-1, amount=0, flag=0), ResourceCost(type=4, amount=1, flag=0))`. Resource 214 is a "free token" counter — tech 707 (the GLOBAL, civ=-1 tech that type=12's sibling type=18 command unlocks) sets it to 5 and adds 5 to the Castle building template's attribute 26, which is what produces the "5 free, replenishing per Castle" cap. If you instead pointed the team-enable command at the civ's REAL elite UU directly, its normal training (e.g. at the Stable) would ALSO start requiring resource 214 — breaking it for everyone who hasn't researched this UT.

**Fix pattern:** clone the civ's own elite UU into a spare/unused unit slot (confirmed-unused via a full 60-civ scan of `train_locations[0].unit_id`), keeping name/graphics/combat stats, then overwrite ONLY `train_locations`/`resource_costs`/`enabled=0` with MKIPCHAK's exact values. `civ_appender._MERCENARY_UU_SLOT = 1261` ("CUMANDISABLED" in the base dat) is reserved for this. A sibling slot, 1259 ("CUMANPLACEHOLDER"), exists with a similar but NOT identical pre-existing cost shape (references resource 215 too) — likely an abandoned dev iteration; don't trust a spare slot's pre-existing data without checking it against a confirmed-shipping reference like MKIPCHAK.

**Not every type=7/12 bonus needs this.** First Crusade (KM bonus 29, castle UT) uses type=7 the same hardcoded-unit way, but doesn't need a dedicated slot — it makes Town Centers passively SPAWN the unit, a separate production path that doesn't touch `train_locations`/`resource_costs` at all. Confirmed Sicilians' own Serjeant (1658, the unit type=7 references) is literally the SAME unit used for its own normal training — no duplicate exists for it. Check whether the effect type actually touches the training/cost system before assuming a dedicated slot is needed.

**Confirmed working live 2026-06-23** (Golden Company test civ, KM UU index 8/War Elephant line): researching the Imperial UT correctly shows the civ's own Elite War Elephant icon in the Castle's btn4 slot, trainable as the "free" unit. The exact "5 per Castle, replenishing" cap behavior relies entirely on tech 707's unmodified global mechanism — high confidence it generalizes (nothing in it is civ-specific) but only verified structurally before this, not via a full multiplayer match; the live test above is the first confirmation it also looks/behaves correctly in a real game.
