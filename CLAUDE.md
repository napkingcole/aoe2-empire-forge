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

**Unit attribute IDs (c parameter for EC_SET/ADD/MULTIPLY):** `10`=HP, `11`=LOS, `13`=work rate, `100`=attack.

**Standard resource IDs (a for EC_RESOURCE):** `0`=food, `1`=wood, `2`=stone, `3`=gold.

### Critical Quirks (always apply)

1. **EC_RESOURCE b=-1 trickle** requires `tech.repeatable = 1`. Our `_make_tech` defaults to 0 — set it explicitly for any UT with a trickle effect.

2. **unit.enabled does not control trainability.** EC_ENABLE b=0/1 is a visibility flag only. Trainability is controlled by whether the unit's make-avail tech is in the type=102 disable list (or missing from the type=8 unlock list for opt-in units).

3. **EC_UPGRADE does not redirect placements.** It converts existing instances only. For placement redirection (e.g. 2×2 farms), modify unit data directly on the original unit slot.

4. **Battering Ram orphan pattern.** Unit 1258 (BTRAM base) is what trains — not unit 35 (Battering Ram). Tech 162 makes 1258 available; tech 712 upgrades the line. To remove rams from a civ, exclude unit 1258 from tree[0].

5. **Opt-in techs need type=8.** Battle Elephants, Elephant Archers, and similar units are globally disabled and not in any civ's type=102 pool. They require an explicit type=8 command in the civ's TT effect to appear.

6. **Empty research_locations crashes silently.** Always provide at least one `ResearchLocation(location_id=-1, research_time=0)` for auto-fire techs.

7. **String IDs: use 79xxx+ range** for custom button labels. Overriding vanilla 7xxx IDs affects the "research complete" toast but not in-game panel buttons.

### Key Files
- `civ_appender.py` — main dat-writing logic; bonus handlers, TT effect building, tech allocation
- `bonus_catalog.py` — bonus ID → EC list definitions
- `bonus_catalog_raw.json` — raw bonus data sourced from KM
- `CivTechTrees/` — per-civ JSON files (tree + bonus IDs)
- `llm/` — deep modding reference (read for details beyond this summary)
- `llm/modding-notes.md` — extended reference from the companion custom mod project (new unit creation, hotkeys, debugging patterns, civ slot table)