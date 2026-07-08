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

## 2026-07-03 — Team bonus label shows wrong text in diagnostic and in-game description

**Symptom:** A civ with team bonus 33 (conversion resistance) showed "Scout Cavalry,
Light Cavalry, Hussar +1 pierce armor" in both the `diagnose_civ.py` output and the
in-game civilization picker description. The actual mod effect (conversion resistance)
was applied correctly; only the display text was wrong.

**Root cause:** Two separate issues:
1. `team_bonus_names.json` had entries shuffled from index 11 onward vs. KM's
   authoritative `card_descriptions[4]` ordering in `common.js`. Index 33 was
   "Trade units yield 10% food" instead of "Units resist conversion."
2. `diagnose_civ.py`, `build_all.py`, and `app.py` all looked up team bonus labels
   from `bonus_names.json` (the *civ* bonus catalog) instead of `team_bonus_names.json`.
   `bonus_names.json["33"]` = the Scout Cavalry pierce armor string.

**Fix:** Rewrote `team_bonus_names.json` with the correct KM ordering for indices 0–79.
Added `_TEAM_BONUS_NAMES` dict and `_team_bonus_label()` in `diagnose_civ.py`.
Added `_TEAM_BONUS_NAMES` dict in `build_all.py` (exported) and imported + used it in
`app.py` for team bonus description generation.

**Commit:** (2026-07-03)

---

## 2026-07-07 — Custom flag icon missing from in-game civ picker and in-game interface

**Symptom:** A civ with a custom flag showed the default AoE2 flag icon in both the
civilization picker menu and the in-game interface, even though the widgetui folder
was present.

**Root cause:** `_build_ui_zip` in `build_civ.py` wrote the flag PNG to
`widgetui/textures/ingame/icons/civ_techtree_buttons/` (tech-tree button) but not to
`widgetui/textures/menu/civs/` (the civ picker / in-game flag slot).

**Fix:** Added the missing `widgetui/textures/menu/civs/{fn}.png` write after the
per-variant icon loop in `_build_ui_zip`. Also added warning logs to `_decode_flag`
for silent Pillow/JPEG failures.

**Commit:** (2026-07-07)

---

## 2026-07-07 — Bonus #283 broke Bombard Cannons, Bombard Towers, and Cannon Galleons

**Symptom:** A civ with bonus #283 (Chemistry and Hand Cannoneer available in Castle
Age) could not train Bombard Cannons even in Imperial Age. Houfnice upgrade was also
missing because it depends on Bombard Cannon being researchable first.

**Root cause:** The original bonus #283 handler cloned Chemistry (tech 47) as a
civ-specific Castle-Age version, then disabled the original tech 47 via a `type=102`
command in the TT effect. Techs 188 (Bombard Cannon), 64 (Bombard Tower), and 37
(Cannon Galleon) all have tech 47 in their `required_techs` — with 47 disabled, their
prerequisite was never satisfied and they never fired.

**Fix:** Replaced the handler entirely. The correct mechanism mirrors how Bohemians
actually work in the DAT: Chemistry (47) already has `required_techs=[103, 800],
count=1` (OR-logic). Tech 800 is a Bohemian-owned auto-fire that triggers at Castle
Age, satisfying Chemistry's OR-prereq without disabling 47. We clone techs 800 and
801 for the custom civ and add the 800-clone ID to Chemistry's free OR-prereq slot so
Chemistry unlocks at Castle Age for that civ only. Chemistry 47 is never disabled.

**Commit:** (2026-07-07)

---

## 2026-07-07 — Bonus #283 Chemistry still locked behind Imperial Age after handler rewrite

**Symptom:** After the handler rewrite above, Chemistry was still only researchable in
Imperial Age.

**Root cause:** The new handler called `_allocate_tech(dat, 800, ...)` to clone tech
800 but discarded the return value. The clone's new ID was never written into Chemistry
(47)'s `required_techs` list. The engine checks prereqs by exact tech ID — tech 800
was in Chemistry's list, but our clone (e.g. ID 1200) was not, so the clone's firing
never satisfied Chemistry's prereq for non-Bohemian civs.

**Fix:** Captured `new_800_id` from `_allocate_tech` and slotted it into the first
free `−1` entry in Chemistry's `required_techs` list. `required_tech_count` stays 1
(OR-logic already set); any of `[103, 800, new_800_id]` now satisfies it. Other civs
are unaffected because `new_800_id` is civ-specific and never fires for them.

**Commit:** (2026-07-07)

---

## 2026-07-03 — Bonus 35 (Infantry +20% HP) fires empty Castle/Imperial techs

**Symptom:** `diagnose_civ.py` reported bonus 35 allocating three techs (Feudal,
Castle, Imperial) but the Castle and Imperial copies had 0 commands and did nothing.

**Root cause:** `bonus_catalog_raw.json["civ"]["35"]` listed three Burmese tech IDs
`[416, 415, 391]`. Techs 415 and 391 are dead stubs in the Burmese tech tree with
`effect_id = -1` — they produce no effect when cloned. Only tech 416 (Feudal Age) has
a valid effect (effect 428: multiply infantry class HP by ×1.2).

**Fix:** Trimmed the catalog entry to `[416]`. The bonus is a flat one-time Feudal buff
("Infantry +20% HP starting in the Feudal Age"), not a per-age cumulative stack, so
the Castle and Imperial stubs were never supposed to do anything.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 280 (Folwark) allocates 7 extra empty/wrong techs

**Symptom:** `diagnose_civ.py` reported bonus 280 allocating 11 techs total; the first
4 worked correctly (techs 1532–1535, matching the Poles' Folwark chain) but 6 additional
copies (1536–1541) had 0 commands. A 7th extra slot matched tech 797 (Flemish Militia
Age4, Burgundians global tech) which was silently skipped as global.

**Root cause:** `bonus_catalog_raw.json["civ"]["280"]` listed
`[793, 794, 795, 796, 797, 798, 799, 818, 819, 820, 821]`. The first four (793–796) are
the correct Poles Folwark techs (Enable Folwark + 3 age upgrades). The remaining seven
were a mix of a Burgundians global tech (797) and blank "New Research" slots (798–821)
— likely effect IDs that were confused for tech IDs when the catalog was originally built.

**Fix:** Trimmed the catalog entry to `[793, 794, 795, 796]`. The Folwark chain
(Dark Age enable → Feudal/Castle/Imperial upgrades) is fully described by these four
Poles techs; no additional entries are needed.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Team bonus 30 (Military buildings +5 pop room) never applied

**Symptom:** Any civ with team bonus 30 ("Military buildings provide +5 population room")
reported N-1/N entries applied in `diagnose_civ.py`. The bonus was silently skipped.

**Root cause:** `bonus_catalog_raw.json["team"]["30"]` pointed to effect index 9
("Slavs Team Bonus"), which has 0 commands in the current DE DAT. This was the old
Slavs team bonus slot — it was emptied when AoE2 DE changed the Slavs team bonus to
"Farmers work 15% faster." Because the effect has no commands, `civ_appender.py`
skips it (`if not safe_cmds: continue`), so the bonus is never written to the mod.

**Fix:** Changed the catalog entry from `9` to `758` (effect "Slavic team bonus"),
which is the current live implementation: type=10 / C=21 / D=5.0 commands applied to
all age variants of Barracks, Archery Range, Stable, and Siege Workshop.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 300 (Camel Scouts in Feudal Age) produced 0-command tech

**Symptom:** Any civ with bonus 300 ("Can recruit Camel Scouts in Feudal Age") showed
a `→ 0 cmds` warning in `diagnose_civ.py`. Camel Scouts were not trainable.

**Root cause:** `bonus_catalog_raw.json["civ"]["300"]` listed `[235, 860, 858]`, derived
from the Gurjaras' implementation. Tech 235 ('Make Camels Available') is civ=-1 (global,
never cloned), tech 860 ('Upgrade Camel Scouts to Riders') is also global, and tech 858
('Camel Scout make avail', Gurjaras civ=42) has `effect_id=-1` — a dead stub that only
serves as a gate for tech 235 in the Gurjaras chain. None of these actually enable the
unit for a non-Gurjaras custom civ. Tech 235 is also globally disabled via "Disable
Regionals" (effect 79, type=102) and would need a type=8 opt-in in the TT anyway.

**Fix:** Removed the `civ` catalog entries and added bonus 300 to `ec_list` with a
single EC_ENABLE command (`type=2 A=1755 B=1 C=-1 D=0`) at `requires=[101]` (Feudal
Age). This creates a civ-specific auto-fire tech that directly enables unit 1755 (Camel
Scout) in Feudal Age. The global tech 860 (which upgrades Camel Scouts → Camel Riders
at Castle Age) continues to fire for all civs as a no-op for civs without Camel Scouts.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 55 (Stable units +1P armor Castle/Imperial) half-fired with 0 cmds

**Symptom:** `diagnose_civ.py` reported one of the two techs for bonus 55 as
`unit0 instant req:[0,0,0,0,0,0] → 0 cmds` and the other (Imperial Age) as
`auto-fire req:[103] → 1 cmds`. Castle Age armor was silently missing.

**Root cause:** `bonus_catalog_raw.json["civ"]["55"]` listed `[338, 552]`. Tech 338 is
a blank "New Research" placeholder (civ=0, eff=0, blank requirements) that cloned into
a useless 0-command tech. Tech 552 is the Persians' "Caravanserai (make avail)" tech
(EC_ENABLE unit 1754 at Imperial Age) — entirely unrelated to cavalry pierce armor.
Neither tech was correct; there is no single vanilla tech that adds pierce armor only
to stable units at Castle/Imperial age.

**Fix:** Cleared the `civ` catalog entry and added bonus 55 to `ec_list` with two
entries — `requires:[102]` and `requires:[103]` — each applying
`EC_ADD A=-1 B=12 C=8 D=1025.0` (cavalry class +1 pierce) and
`EC_ADD A=-1 B=47 C=8 D=1025.0` (light cavalry class +1 pierce). Unit classes 12
and 47 cover the full stable roster (knights, camels, scouts, elephants, steppe lancers).

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 26 (TC/Dock work rate) allocated empty trailing tech

**Symptom:** `diagnose_civ.py` reported one of the two bonus 26 techs as `unit0 instant req:[0,0,0,0,0,0] → 0 cmds`.

**Root cause:** `bonus_catalog_raw.json["civ"]["26"]` listed `[409, 412]`. Tech 409 is the correct Persian "C-Bonus, TC and Dock work rate" tech (civ=8, 8 commands covering TC×4 age variants and Dock×4 age variants in one Dark Age auto-fire tech). Tech 412 is a blank "New Research" placeholder (civ=0, eff=0) that clones into a 0-command instant tech.

**Fix:** Trimmed the catalog entry to `[409]`. The single Persian tech covers the full per-age progression for both building types.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 105 (Eco upgrades -33% food) produced 10 empty techs

**Symptom:** `diagnose_civ.py` reported all 10 bonus 105 techs as `auto-fire → 0 cmds`.

**Root cause:** `bonus_catalog_raw.json["civ"]["105"]` listed `[758–767]` — all ten Burgundian "requirement" gate techs (e.g., 'Feudal eco tech requirement', 'Heavy Plow requirement'). These are internal prerequisite stubs with `effect_id=-1`; they never produce any commands when cloned. The actual Burgundians food discount logic lives in their TT effect (effect 782) as direct `EC_TECH_COST type=101 C=2 D=0.6` commands — not in any auto-fire tech.

**Fix:** Cleared the `civ` catalog entry to `[]` and added bonus 105 to `ec_list` with `requires=[]` (fires at game start) applying `EC_TECH_COST type=101 B=0 C=2 D=0.667` (×0.667 ≈ −33% food) to all 16 standard eco upgrade tech IDs: Horse Collar(12), Heavy Plow(13), Crop Rotation(14 — wait, corrected below), Guilds(15), Caravan(48), Gold Mining(55), Gillnets(65), Gold Shaft Mining(182), Double-Bit Axe(202), Bow Saw(203), Wheelbarrow(213), Two-Man Saw(221), Hand Cart(249), Stone Mining(278), Stone Shaft Mining(279), Fishing Lines(906). This matches the Burgundians' own TT discount list.

**Limitation:** The "available one age earlier" portion of this bonus is not implemented. That mechanic requires modifying global tech `required_techs` arrays (e.g., removing the Castle Age prerequisite from Heavy Plow for this civ), which cannot be done via EC commands and would need a dedicated handler in `civ_appender.py`.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 318 (Start with Mule Cart) allocated one empty tech

**Symptom:** `diagnose_civ.py` reported one of the two bonus 318 techs as `unit0 instant req:[0,0,0,0,0,0] → 0 cmds`.

**Root cause:** `bonus_catalog_raw.json["civ"]["318"]` listed `[229, 925]`. Tech 229 is a blank "New Research" placeholder (civ=0, eff=0) — produces a 0-command instant tech. Tech 925 (civ=45/Georgians, eff=937, 2 cmds: EC_RESOURCE + type=7 spawn unit) was already working correctly.

**Fix:** Trimmed entry to `[925]`. The Mule Cart spawn tech fires at game start (auto-satisfies global prereqs 639 and 307). Whether the type=7 "spawn unit" command successfully creates a Mule Cart in-game requires in-game verification.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonuses 81/283/352 unsupported gate-stub mechanism; catalog cleared

**Symptom:** `diagnose_civ.py` reported dead-stub techs (0 cmds) for:
- **81** (No buildings required to age up) — tech 638, Khmer, eff=-1
- **283** (Chemistry + Hand Cannoneer in Castle Age) — techs 800 and 801, Bohemians, eff=-1
- **352** (Siege Engineers in Castle Age) — tech 978, Jurchens, eff=-1

**Root cause:** These bonuses use AoE2's "gate-stub" mechanism: the civ's gate tech has `eff=-1` (no commands) and fires automatically, satisfying one slot in a global tech's `required_techs` array (`required_tech_count=1`). For example, global Siege Engineers (tech 377) has `required_techs=[103, 978]` with `required_tech_count=1` — normally needs Imperial Age (103), but fires in Castle Age for Jurchens because their gate tech 978 satisfies the count early. When cloned, the gate tech gets a **new ID** the global tech doesn't reference, so it never satisfies the requirement.

**Fix:** Cleared all three catalog entries to `[]`. These bonuses are now silently skipped ("not in any catalog"). They require a custom handler in `civ_appender.py` to implement: either modifying global tech `required_techs` at build time or creating civ-specific clones of the gated global techs with different age requirements.

**Commit:** (2026-07-03)

---

## 2026-07-03 — [282] Winged Hussar: diagnostic false positive NO-BUTTON(time=1s)

**Symptom:** `diagnose_civ.py` flags bonus 282 tech 1774 with `⚠ NO-BUTTON(time=1s) → 3 cmds`.

**Root cause:** Source tech 791 (Poles, civ=38) has `research_locations[0] = (-1, 1)` — location=-1 (auto-fire, no button) but research_time=1. This is intentional vanilla Poles behavior: after entering Imperial Age, a 1-second delay fires the tech that sets Winged Hussar upgrade costs to 0. The diagnostic warns about any `location=-1 with time>0` as a potential misconfiguration, but this pattern is deliberate.

**Not a bug.** Both bonus 282 techs fire correctly — tech 1773 (2 cmds: disable Hussar, unlock Winged Hussar) and tech 1774 (3 cmds: set WH food/gold/time to 0) apply as expected.

---

<!-- 
  Template for new entries:

## 2026-07-03 — Vanilla UU Castle train-button hover shows wrong unit name

**Symptom:** A civ using a vanilla UU (e.g. Teutonic Knight) replacing a civ slot whose original UU had a different name (e.g. Ethiopians / Shotel Warrior) showed the replaced civ's unit name and description in the Castle train-button hover tooltip.

**Root cause:** `build_all.py` writes the UU display name to `dll_name + 10000` (tech tree) and `dll_name + DLL_HELP_OFFSET` (+100000) for vanilla UUs, but not to `dll_name + 21000` — the slot the Castle train-button hover reads from. KM-custom UUs had this covered via `ext_sid` in the `extra_unit_strings` path. For vanilla UUs the `+21000` slot was left unwritten, so the game fell back to whatever vanilla campaign/scenario string existed at that SID, which for the Ethiopians slot happened to be "Shotel Warrior (fragile infantry, high attack)".

**Fix:** Added `dll_name + 21000` write for both the normal and elite vanilla UU in the string block in `build_all.py`.

**Commit:** (2026-07-03)

---

<!-- 
## YYYY-MM-DD — Short description

**Symptom:** What the user saw / what broke in-game.

**Root cause:** What the code was actually doing wrong.

**Fix:** What was changed and why it works now.

**Commit:** `<hash>` (YYYY-MM-DD)

-->
