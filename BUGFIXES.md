# Bug Fix Log

Tracks confirmed bugs in the civ builder (mod generation pipeline) and when they were patched.
Add a new entry here whenever a bug is fixed. Format: date patched, what broke, root cause, fix.

---

## 2026-06-29 — Elite Cavalier / Paladin unlocked too early

**Symptom:** Elite Cavalier and/or Paladin became trainable or researchable before the
correct age requirement was met.

**Root cause:** Age-requirement tech IDs were shifted by an off-by-one when the tech
chain was cloned for the custom civ slot.

**Fix:** Corrected the required-tech pointer in `civ_appender.py` so the upgrade chain
fires in the proper age.

**Commit:** `1a34d69` (2026-06-29)

---

## 2026-06-29 — UT catalog / UU name override / UT string bleed / multiplier scaling

**Symptom (several issues in one commit):**
- Castle/Imperial UT buttons sometimes showed the wrong tech name or description,
  bleeding vanilla campaign strings into the mod UI.
- UU name override (alias → display name) did not apply correctly in some codepaths.
- Multiplier scaling produced wrong deltas for certain bonus types.
- UT catalog lookup mapped KM bonus IDs to wrong vanilla tech slots.

**Root cause:** Multiple independent issues in the UT stub builder and bonus multiplier
path in `civ_appender.py`.

**Fix:** Corrected UT catalog ID mapping (`_KM_CASTLE_UT_TECHS` / `_KM_IMP_UT_TECHS`),
fixed UU name propagation, guarded string bleed by using dedicated safe pool SIDs,
and corrected the `d * N` accumulation logic for multiplied bonuses.

**Commit:** `e22bfc0` (2026-06-29)

---

## 2026-07-01 — Elite Organ Gun / Elite Caravel research buttons missing

**Symptom:** After building a Portuguese Empire custom civ, the Elite Organ Gun and
Elite Caravel upgrade buttons did not appear in the Castle / Dock.

**Root cause:** Step-0 nullification (which wipes `research_locations[0].location_id`
on existing civ-specific techs to prevent ghost buttons) ran *before*
`_allocate_tech` deep-copied the template techs 563 and 597. The clones inherited
`location_id = -1` with `research_time > 0`, making the button invisible.

**Fix:** Added `_restore_elite_upgrade_location()` in `civ_appender.py`. After each
elite-upgrade tech is cloned, it reads the base unit's own `train_locations[0].unit_id`
to recover the correct building (Castle = 82, Dock = 45) and restores the location.

**Commit:** `4943c6a` (2026-07-01)

---

## 2026-07-01 — Imperial UT hover shows "Click to play as the Burmese"

**Symptom:** The Imperial Unique Technology research button tooltip in the Castle showed
"Click to play as the Burmese" instead of the intended UT description.

**Root cause:** UT name SIDs were allocated from the 70000-range pool
(`UT_POOL_OFFSET = 126`). The Castle button hover reads from `language_dll_name + 21000`;
for the Portuguese Empire slot this produced SID 91300, which AoE2 DE's language DLL
hard-codes as the Burmese civ-picker string. Mod key-value files cannot override
language DLL strings.

**Fix:** Moved `UT_POOL_OFFSET` to 335 (first index in the 44000-range block of
`CAMPAIGN_STRING_POOL`). Hover SIDs now land at 65000–65434, which are empty vanilla
slots that mod overrides can safely fill.

**Commit:** `4943c6a` (2026-07-01)

---

## 2026-07-01 — Castle UT button shows no effect description

**Symptom:** The Castle Unique Technology research button displayed only the tech name
and cost (e.g. "Carrack (Cost: 300f, 300g)") with no effect description.

**Root cause:** `lang_desc` in the UT tech was set to `name_sid` (the tech name SID),
same as `lang_name`, so the description field carried no additional information.

**Fix:** Changed `lang_desc = name_sid + DLL_CREATION_OFFSET` (i.e. `name_sid + 1000`).
`build_all.py` now writes `"TechName (effect)"` (e.g. `"Carrack (Ships +1/+1 armor)"`)
to that SID, giving the Castle button a proper effect description line. Safe because the
44000-range name SIDs put `+1000` at 45000-range — empty in vanilla.

**Commit:** `4943c6a` (2026-07-01)

---

## 2026-07-01 — Carrack ×2 gave Elite Caravel 0 melee armor

**Symptom:** A Portuguese Empire civ with Carrack configured as a ×2 Castle UT gave
the Elite Caravel 0 melee armor instead of +2/+2.

**Root cause:** EC_ADD with `c = 8` (armor attribute) uses packed `d` values where
`d = (armor_class_id << 8) | amount`. The multiplier scaling in
`_scale_ec_for_multiplier` and `_multiply_effect` treated `d` as a plain float and
multiplied the whole value (e.g. `769 × 2 = 1538`). This corrupted the armor class
ID (class 3 → class 6), targeting an armor class that ships do not have, so the
add had no effect.

**Fix:** For `EC_ADD` with `c == 8`, both functions now unpack the class ID and amount,
scale only the amount byte, and repack: `d = (class_id << 8) | (amount × multiplier)`.
Result: `769 × 2 → 770` (class 3, +2 melee) and `1025 × 2 → 1026` (class 4, +2 pierce).

**Commit:** `4943c6a` (2026-07-01)

---

## 2026-07-03 — *(found by diagnose_civ.py — details TBD)*

<!-- 
  Template for new entries:

## YYYY-MM-DD — Short description

**Symptom:** What the user saw / what broke in-game.

**Root cause:** What the code was actually doing wrong.

**Fix:** What was changed and why it works now.

**Commit:** `<hash>` (YYYY-MM-DD)

-->
