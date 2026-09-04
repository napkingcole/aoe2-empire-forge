This directory, /aoe2civbuilder/, is a civilization builder for the PC game Age of Empires 2:Definitive Edition. Krakenmeister's ("KM") civ builder served as inspiration, but it has become stale and unmaintained. For that reason, we are using Python and Genieutils Python port to create a new civilization builder.

Right now, there are two phases:
1. Utilizing KM's generated civilization JSON files to create stable mods for the community to use, and

2. Building out a full UI, utilizing Flask as a web application/app for users to create civilization names, architecture sets, tech trees, unique units, bonuses, and unique techs, and generate a game mod, right from their own computer, so there is no reliance on a third party service.

---

## LLM Modding Reference

The `llm/` directory contains comprehensive AoE2 DE dat modding documentation. Read those files when working on bonus handlers, tech tree logic, unit enabling, or resource effects. What follows is the always-in-context summary of the most critical facts.

### EffectCommand Quick Reference

| Constant     | type | a            | b                        | c           | d          |
|--------------|------|--------------|--------------------------|-------------|------------|
| EC_SET       | 0    | unit_id      | -1                       | attribute   | value      |
| EC_RESOURCE  | 1    | resource_id  | 0=set / 1=add / -1=trickle | -1        | amount     |
| EC_ENABLE    | 2    | unit_id      | 1=show / 0=hide          | -1          | 0.0        |
| EC_UPGRADE   | 3    | from_unit    | to_unit                  | -1          | 0.0        |
| EC_ADD       | 4    | unit_id      | -1                       | attribute   | delta      |
| EC_MULTIPLY  | 5    | unit_id      | -1                       | attribute   | multiplier |
| EC_TECH_COST | 101  | tech_id      | resource(0-3)            | 0=set/1=add | value     |
| EC_TECH_TIME | 103  | tech_id      | -1                       | 0=set       | seconds    |
| unlock tech  | 8    | (copy from vanilla) | ...             | ...         | ...        |
| disable tech | 102  | -1           | -1                       | -1          | float(tech_id) |

**Unit attribute IDs (c parameter for EC_SET/ADD/MULTIPLY):** `0`=HP, `1`=LOS, `9`=attack, `13`=work rate. See `llm/effect_commands.md` for the full table.

**Standard resource IDs (a for EC_RESOURCE):** `0`=food, `1`=wood, `2`=stone, `3`=gold.

### Critical Quirks (always apply)

1. **EC_RESOURCE b=-1 trickle** requires `tech.repeatable = 1`. Our `_make_tech` defaults to 0 — set it explicitly for any UT with a trickle effect.

2. **unit.enabled does not control trainability.** EC_ENABLE b=0/1 is a visibility flag only. Trainability is controlled by whether the unit's make-avail tech is in the type=102 disable list (or missing from the type=8 unlock list for opt-in units).

3. **EC_UPGRADE redirects the build/train button only if the target already has a train_location.** It always converts existing instances; whether *new* ones come out upgraded depends on the target unit's `creatable.train_locations[0]` pointing at the same `(building, button)` slot as the source. Vanilla City Wall (370) has no train location at all, so upgrading to it silently does nothing until you copy Fortified Wall's — see the bonus 400 handler (confirmed in-game 2026-08-26). When the target can't own a button (e.g. 2×2 farms), modify unit data directly on the original unit slot instead.

4. **Battering Ram orphan pattern.** Unit 1258 (BTRAM base) is what trains — not unit 35 (Battering Ram). Tech 162 makes 1258 available; tech 712 upgrades the line. To remove rams from a civ, exclude unit 1258 from tree[0].

5. **Opt-in techs need type=8.** Battle Elephants, Elephant Archers, and similar units are globally disabled and not in any civ's type=102 pool. They require an explicit type=8 command in the civ's TT effect to appear.

6. **Empty research_locations crashes silently.** Always provide at least one `ResearchLocation(location_id=-1, research_time=0)` for auto-fire techs.

7. **Hero one-at-a-time is attributes 126/127, not `hero_mode`.** `hero_mode=1` only grants hero status (gold border, regen, conversion immunity). The cap is `EC_SET(unit, c=126, d=1)` + `EC_ADD(unit, c=127, d=4)` in the hero's make-avail tech — 127 flag `4` = limited but retrainable after death, `2` = never retrainable. See `llm/advanced_techniques.md`'s "Hero Units (One-at-a-Time)" (confirmed in-game 2026-08-26).

8. **String IDs must be EXISTING vanilla ids — brand-new ids are silently ignored, no matter the range.** Allocate one id per unit/tech from `civ_appender.CAMPAIGN_STRING_POOL`; every other field is a fixed offset from it: `+1000`=creation/description, `+100000`=help (tech research-button tooltips only), `+150000`=tech_tree (techs only). A UNIT's Castle train-button hover tooltip needs a separate `+21000` write with NO corresponding DAT field at all — `language_dll_help`/`+100000` does not drive it. See `llm/advanced_techniques.md`'s "Language String Pitfalls" and [[project_string_id_engine_limit]] in memory for the full story.

    **Castle/Imperial UT stubs are the exception to `+100000`.** `_append_unique_tech_stubs` sets `lang_help = name_sid + 21000`, not `+100000`. So a UT's four live slots are `name_sid` (name), `+1000` (research-button LABEL — keep it short), `+21000` (hover tooltip), `+150000` (F2 viewer). Two traps: `civ_result["castle_ut_desc_sid"]` **is** `name_sid+1000`, so writing tooltip text there collides with the button label (fixed 2026-09-03 in wizard_build/app); and `civ_result["castle_ut_help_sid"]` — a 60000s `UT_HELP_POOL_OFFSET` id — is **not** what `language_dll_help` points at, so writing it does nothing. `build_all.py` still writes it, deliberately, as an inert leftover.

9. **`tech.civ` gating is invisible to the tech-tree effect.** A tech whose `civ` is a real civ index (not `-1`) fires only for that civ — no type=8 unlock and no absence from the type=102 disable list will make it run for anyone else. This is why the regional *second* unique units (Bolas Rider, Xianbei Raider, Grenadier, Jian Swordsman, Temple Guard, Ibirapema, War Chariot, Mounted Trebuchet, Shrivamsha, Warrior Priest, Thirisadai, Legionary, Savar) appear enabled in the tech tree but can't be trained. The fix is `_allocate_tech(dat, tid, civ_index, seen)`, which deepcopies the tech + its effect and follows the `required_techs` chain; global (`civ=-1`) prerequisites are left alone. Exposed as the `_UNLOCK_UNIT_BONUSES` cards (405-417) rather than tech-tree nodes. Primary UUs go through the KM UU path instead and are already handled.

    **`_allocate_tech` only fixes the chain UPWARD. Anything downstream still names the original.** The copy lands at a new tech id, so a tech that listed the original as a prerequisite is unaffected and stays unsatisfiable. `_add_alt_prereq(dat, original_tid, new_tid)` is the other half: it writes the copy into a spare `required_techs` slot on every tech that named the original, leaving `required_tech_count` alone so the copy reads as one more way to satisfy the same requirement (other civs can't research a civ-gated copy, so they are unaffected). Two bonuses need it, and both were silently broken without it — 282 Winged Hussar (tech 786 wants 3 of `[115, 254, 788, 789]`; a custom civ has only 115+254, so the Hussar got disabled by the copied trigger and nothing replaced it) and 105 "eco upgrades one age earlier" (nine Burgundian `civ=36` shim techs listed as *alternative* prerequisites on Wheelbarrow, Gold Shaft, etc.). Both confirmed in-game 2026-09-04.

10. **A type=8 opt-in tech that is never type=102-disabled leaks to the AI.** 32 make-avail techs (Settlement 1353, Eagle Warrior 433, Elephant Archer 480, Steppe Lancer 714, Rocket Cart 979, Fire Lancer 981, camels 235, the Champi line, Dromon, Lou Chuan, Traction Trebuchet, …) are `civ=-1`, gated only on an age, and appear in **no** vanilla civ's type=102 list — the engine keeps them locked until a civ opts in with type=8. Humans never see a button because the per-civ CivTechTrees JSON has no node, but **the AI does not build from that JSON**, so a civ that neither unlocked nor disabled the tech gets the unit anyway (issues #15, #24: AI building Settlements beside Mills). `_lock_unclaimed_optin_techs` writes the explicit type=102. It must run AFTER `_apply_bonuses` — several bonus handlers add their own type=8, and a tech carrying both commands ends up disabled. Key it on stable tech properties (referenced by a type=8 anywhere + `civ == -1`), never on the observed type=102 pool, or one civ's fresh disables contaminate the next civ's risky set when `build_all` reuses a DatFile. Exempt the starting scout's make-avail tech (Incas start with a Champi Runner and do unlock tech 1350).

11. **Capture a graphic source civ BEFORE overwriting the target slot.** `apply_civ` clones civ 1 (Britons), writes it into the target slot, and only then copies architecture in. Looking the source up by index *after* the overwrite breaks whenever the civ replaces its own architecture representative — replacing Byzantines while choosing Mediterranean made `_copy_architecture(dat, 7, 7)` copy the half-built slot onto itself, silently leaving Britons architecture and `icon_set`. This was the real cause of issue #17. `_copy_architecture` / `_copy_monk_skin` now take Civ *objects* captured before the overwrite; the rebind leaves the original object alive, so no deepcopy is needed. Castle/Wonder were always safe — they read their source before the overwrite.

12. **Monk skin is a separate axis from architecture, and needs SIX fields — not just the standing pose.** The Monk partitions civs into 11 groups that cut across architecture sets (Britons and Goths share a Monk but not an architecture; Byzantines and Slavs likewise). Exactly three units carry it — `_MONK_SKIN_UNITS = (125, 134, 286)` — verified by comparing every unit's per-civ graphic partition against the Monk's. 125 and 286 ride along on `_ARCH_MOBILE_CLASSES`, but **134 (Monk carrying a relic) is class 11**, shared with projectiles, so it can't be swept in by class and needs `_ARCH_EXTRA_UNITS`. Without it a non-European civ's Monk reverted to the European pose the moment it picked up a relic.

    Diffing all 45 pairs of the 10 skin representatives gives the exact per-skin set: `standing_graphic`, `dying_graphic`, `icon_id`, `dead_fish.walking_graphic`, `type_50.attack_graphic`, `bird.tasks[*].proceeding_graphic_id`. Copying a subset produces a chimera, because `_copy_architecture` runs first and has already written the *walking* graphic — copying only standing/dying gave a Monk that idled in the chosen skin, walked in the architecture's, and kept the wrong Monastery icon (confirmed in-game 2026-09-04, fixed). Sounds (`selection_sound`, `bird.move_sound`, `wwise_*`) also vary between representatives but belong to the voice axis `assign_all_languages` owns — never copy them here. A civ with no explicit skin runs the same path against its architecture's civ, since `_copy_architecture` deliberately never touches `icon_id`.

13. **`civ.icon_set` is the DE architecture index, and `civ.resources[263]` is the starting scout.** Most buildings share one `standing_graphic` across every civ (Town Center 109, Barracks 12, House 70 are all identical) — the engine picks the art from `icon_set`, so copying graphics without it does nothing. Values match the wizard's architecture ids: 1=Central European, 2=Western European, 5=Mesoamerican, 6=Mediterranean, 12=South American. Scout values: 448 Scout Cavalry, 751 Eagle Scout, 1755 Camel Scout, 2550 Champi Runner; the unit need not be trainable by the civ (Incas start with a Champi Runner while training the Militia line).

14. **A unit has exactly 3 cost slots, and `train_time` is per train location.** `creatable.resource_costs` is a fixed 3-tuple, and most trainable units spend one slot on population (type 4, flag 0) — so a unit can charge **at most two spendable resources**. Merging a new resource into a unit that already costs two silently does nothing; treat the cost as a complete replacement, preserve non-spendable slots (type 4, and the rarer 214/215/501/514), and warn when the request needs more slots than exist. Separately, `train_time` lives on each `TrainLocation`, not on the unit, so a UU reachable from the Castle *and* an Anarchy Barracks slot *and* a Krepost has three independent copies — write all of them (issues #29/#35, both confirmed against a reporter's civ 2026-09-02).

15. **Disabling a tech-tree node needs the right one of three mechanisms, and the engine allows far more than vanilla does.** `_apply_tree_wiring` used to build its disable list only from techs some vanilla civ already switches off, so anything outside that pool was silently ignored no matter what the user unticked — Monks, Fish Traps, Gold/Stone Mining, Fishing Lines and Gillnets all sat in that blind spot. The engine has no such restriction: `type=102` takes any tech id (`_lock_unclaimed_optin_techs` already depends on that). Pick by what the DAT gives you:
    - **has a make-avail tech** (Monk 157, Fish Trap 357) → `type=102` it, but only when *every* unit that tech enables is also unticked, or a shared tech takes a kept unit down with it.
    - **no make-avail tech and ships enabled** (Militia 74, House 70, Fishing Ship 13) → nothing to disable; clear the civ's own `unit.enabled`.
    - **not an editor node at all** (Fish Trap 199 — no node in any shipped layout) → absence from the tree carries no intent, so it must NOT be swept; sweeping it removes Fish Traps from all 53 civs that have one. Needs an editor node before it can be disabled.

    The candidate universe is `_editor_nodes()` (parsed from `FULL.json`), because those are exactly the ids whose absence means "the user turned this off". `_PROTECTED_TECHS` (101/102/103 age advances), `_PROTECTED_BUILDINGS` (109 Town Center) and `_PROTECTED_UNITS` (83 Villager) are never disabled — the editor offers them but no playable civ wants them gone. Houses deliberately ARE removable (the Huns bonus is exactly that). Watch the ~189 effect-command cap: the sweep emits a command per unticked node, and `apply_civ` now surfaces the soft-limit warning to the user rather than only the console.

### Key Files
- `civ_appender.py` — main dat-writing logic; bonus handlers, TT effect building, tech allocation
- `bonus_catalog.py` — bonus ID → EC list definitions
- `bonus_catalog_raw.json` — raw bonus data sourced from KM
- `CivTechTrees/` — per-civ JSON files (tree + bonus IDs)
- `llm/` — deep modding reference (read for details beyond this summary)
- `llm/modding-notes.md` — extended reference from the companion custom mod project (new unit creation, hotkeys, debugging patterns, civ slot table)