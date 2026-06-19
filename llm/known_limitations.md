# Known Engine Limitations & Workarounds

Documented constraints in the AoE2 DE dat engine that affect what's achievable via EffectCommand modding. Each entry includes the symptom, root cause, and our workaround.

---

## Farm Placement Cannot Be Redirected via EC_UPGRADE

**Symptom:** 2×2 farm bonus looks correct in unit data, but newly placed farms are still 3×3 visually.

**Root cause:** `EC_UPGRADE(50 → 845)` converts existing farms but does not redirect the placement pointer. New farms placed after the tech fires spawn as unit 50.

**Workaround:** Directly modify `dat.civs[civ_index].units[uid]` field values for unit 50 and all farm variants: `collision_size_x/y`, `clearance_size`, `outline_size_x/y` from 1.5 → 1.0.

**Remaining limitation:** Farm graphics (crop sprite) are baked at 3×3 tile size. The placement footprint becomes 2×2 but the visual may look oversized.

---

## EC_RESOURCE Trickle Requires repeatable=1

**Symptom:** Unique tech fires, "research complete" toast appears, but no gold trickle happens in-game. (Aegis cheat masked this because it sets villager work rates to 0.)

**Root cause:** `EC_RESOURCE` with `b=-1` (trickle mode) is a continuous effect that requires the engine to re-fire the tech repeatedly. With `repeatable=0`, the engine fires it once and the trickle never sustains.

**Workaround:** Set `tech.repeatable = 1` before `_append_tech(dat, tech)` in `_append_unique_tech_stubs`. This is now the correct baseline for all UT techs with trickle effects.

---

## Civ-Gate Techs Cannot Be Cloned for Prerequisite Satisfaction

**Symptom:** Copying tech 768 (Burgundians Castle Age gate) into a new slot for a custom civ doesn't make tech 209 (Cavalier) satisfy its prerequisites.

**Root cause:** Tech 209's `required_techs` tuple contains the literal ID 768. It checks whether tech 768 has fired, not whether "any civ-gate tech with the same purpose" has fired. Our allocated copy has a different ID and is never checked.

**Workaround:** Create a civ-specific copy of tech 209 itself with simplified `required_techs=(102, 166)` (Castle Age + Knight make-avail), then disable global tech 209 via type=102 so it doesn't duplicate in Imperial Age.

---

## Opt-In Techs Invisible Without type=8 Unlock

**Symptom:** Battle Elephants or Elephant Archers in tree[0] but never appear in training buildings.

**Root cause:** These techs are not in any vanilla civ's type=102 pool — they're globally opt-in. Omitting type=102 for them doesn't enable them; they need an explicit `type=8` command in the TT effect.

**Workaround:** `_apply_tech_tree` Step 0 builds `ec8_unit_techs` by scanning all vanilla TT effects for type=8 commands, then Step 3b adds the appropriate type=8 commands for any tree[0] units that need them.

---

## Empty research_locations Causes Tech to Be Silently Ignored

**Symptom:** Auto-fire tech with no research location never fires.

**Root cause:** A completely empty `research_locations` list causes the engine to skip the tech silently (treated as malformed).

**Workaround:** Always provide at least one `ResearchLocation(location_id=-1, research_time=0)`. This is the canonical form for auto-fire techs.

---

## EC_ADD/EC_MULTIPLY Do Not Work on Newly Appended Unit IDs

**Symptom:** Tech fires but newly cloned unit's stats are unchanged.

**Root cause:** The AoE2 engine does not process EC_ADD or EC_MULTIPLY targeting unit IDs that were appended to the DAT by a mod. Only commands targeting pre-existing vanilla unit IDs work reliably.

**Workaround:** Bake all stat changes directly into `dat.civs[civ_index].units[new_id]` field assignments during the build step. Do not use tech effects to apply deltas on custom unit IDs.

---

## blast_damage / blast_attack_level Are Not Settable via EffectCommand

**Symptom:** Attempting to apply a slow-on-attack or AOE damage aura via a tech has no effect.

**Root cause:** `unit.type_50.blast_damage` and `unit.type_50.blast_attack_level` have no corresponding EffectCommand attribute ID.

**Workaround:** Pre-set these fields on the unit in the DAT. To gate behind a tech, create a cloned "buffed" unit with the fields pre-set (enabled=0), then use `EC_UPGRADE(base → clone)` + `EC_ENABLE(clone, 1)` in the tech effect.

---

## ATTR_WORK_RATE Does Not Affect Generate-Resources Tasks

**Symptom:** `EC_MULTIPLY c=13` on a building speeds up unit production but has no effect on resource generation tasks.

**Root cause:** `action_type=151` generate-resources tasks are not governed by the work rate attribute. They only respond to direct mutation of `task.work_value_1` in the DAT, or a per-civ multiplier resource (e.g. resource 213 for Keshik gold).

**Workaround:** Set the multiplier resource to a positive value via `EC_RESOURCE` in the tech effect; set it to 0 to disable. Gate the task itself via resource rather than work rate.

---

## Generate-Resources Tasks Require Presence in civ[0] AND unit_headers

**Symptom:** Resource generation tasks added to a specific civ's unit never fire.

**Root cause:** The engine checks `data.civs[0]` (the template/Gaia civ) to determine whether a unit CAN run tasks at all. Tasks must also exist in `data.unit_headers[unit_id].task_list`. Adding tasks only to the target civ is insufficient.

**Workaround:** Always add generate-resources tasks to BOTH `unit_headers[uid].task_list` AND every civ's `units[uid].bird.tasks`, including civ 0.

---

## All Civs Must Have the Same Unit Array Length

**Symptom:** Engine crash on map load, or invisible units.

**Root cause:** The engine reads unit counts from the DAT header and assumes all civs have the same number of units. A mismatch causes undefined behavior or a hard crash.

**Workaround:** When appending a new unit, always append a clone to ALL civs in a loop before applying any civ-specific stat changes.

---

## String Override Scope: 7xxx IDs vs 79xxx IDs

**Symptom:** Custom UT name shows correctly in the "research complete" toast but shows the wrong name on the button in the building panel.

**Root cause:** Overriding a vanilla string ID (e.g. 7419 for Britons' Yeomen) replaces the string globally. The toast picks up the override but the in-game button label may cache or re-derive from vanilla sources.

**Workaround:** Use 79xxx+ range IDs for all custom button labels (new strings, not overrides of vanilla IDs). NapKingCole's Unhinged Empires mod convention.
