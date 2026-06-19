# Tech Tree Effects

## Structure

Each civ has a `tech_tree_id` pointing to an `Effect` in `dat.effects`. That effect's `EffectCommands` list controls which units/techs the civ has access to.

The civ JSON specifies the tree as:
```json
"tree": [
  [unit_ids...],      // tree[0]: units this civ can train
  [building_ids...],  // tree[1]: buildings this civ can build
  [tech_ids...]       // tree[2]: techs this civ can research
]
```

## Two Command Pools

### Pool 1: type=102 (Disable Tech)
The "opt-out" pool. Every make-avail and upgrade tech for every unit line appears in at least one vanilla civ's TT as a type=102 disable. Our `_apply_tech_tree` function:
1. Collects all tech IDs that appear in any vanilla civ's type=102 list → `all_disableable`
2. Determines which techs this civ needs (via reverse enable/upgrade maps from tree[0]) → `keep_enabled`
3. Writes `type=102` commands for everything in `all_disableable - keep_enabled`

### Pool 2: type=8 (Unlock Tech)
The "opt-in" pool. Some techs (Battle Elephant tech 630, Elephant Archer tech 480) are NOT in any civ's type=102 list by default — they're disabled globally and each interested civ must add a `type=8` command to unlock them. Without type=8, the unit never appears even if it's in tree[0].

`_apply_tech_tree` detects these by scanning all vanilla TT effects for type=8 commands, then adds matching type=8 commands for any units in this civ's tree[0] that need them.

## Allocating Civ-Specific Techs

When a bonus requires a civ-specific tech (e.g. Cavalier in Castle Age), `_allocate_tech` deep-copies the vanilla tech and:
1. Sets `civ_id` on the copy to this civ's index
2. Recursively allocates any `required_techs` that are themselves civ-specific
3. Maps original tech IDs → allocated IDs in `_seen` to prevent duplication

Required techs that are global (civ=-1) are NOT copied — they already fire for all civs.

## Auto-Fire Techs

Techs with no ResearchLocation (location_id=-1) and zero cost fire automatically when their `required_techs` condition is met. Used for age-gated bonuses (e.g. a bonus that kicks in at Castle Age uses Feudal Age tech 101 as a prerequisite).

ResearchLocation with `location_id=-1, research_time=0` is the canonical form. A completely empty `research_locations` list causes the engine to silently ignore the tech — always provide at least one empty-location entry.

## String IDs

Custom techs need string IDs for their names. We allocate a block per civ:
- `STR_BASE_ID = 79000` (above vanilla range to avoid overwriting vanilla strings)
- `STR_BLOCK_SIZE` IDs per civ
- `STR_UT_PER_CIV = 10` slots: index 0=Castle UT name, 1=Imperial UT name

Overriding vanilla 7xxx tech IDs works for the "research complete" toast but NOT for in-game button labels. Always use 79xxx+ range for custom button labels.

## Mutual Exclusions

Armored Elephants (tech 837) and the Battering Ram line (techs 162 + 712) are mutually exclusive. If tech 837 is in `keep_enabled`, techs 162 and 712 are forcibly removed before computing `to_disable`. This is automatic in `_apply_tech_tree` Step 3c.
