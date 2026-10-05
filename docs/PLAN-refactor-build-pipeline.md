# One build pipeline, a bonus-handler registry, and the assumptions under them

Drafted 2026-10-05 from the 10,000-foot review (see "Findings" at the end).
Nothing here is started. Every phase is **behaviour-preserving unless it says
otherwise**, and proves it with the Phase 0 harness — the same method that
landed the lazy DAT loader: build the old way and the new way, compare bytes.

## Before anything: this morning's checkpoint

1. **Test `perf/dat-load-speed` in-game** with `my_civs/QA_perf_mod.zip` (QA1
   replacing Huns, QA2 replacing Hindustanis — both already passed on 2.4.0, so
   any difference is the loader or the packaging):
   - the mod loads at all (new: DAT at zlib level 3, stored uncompressed in the zip);
   - both civs play as before — a spot check of #46–#49 is enough.
   - Optionally run the app from this branch: the first DAT load is ~18s and
     writes `~/Library/Application Support/EmpireForge/dat_cache/`; every build
     after that should feel near-instant.
2. **If it passes:** merge `perf/dat-load-speed` to `main`. Then merge `main`
   into `feature/chronicles-bonuses` (it touches `civ_appender.py` heavily —
   unlock specs, `_is_enable`, the planner — so it must land before Phase 4
   rewrites the bonus handler, not after).
3. **Release decision** (yours): ship 2.5.0 = perf + Chronicles once Chronicles
   finishes its in-game round, or perf alone first. The refactor below works
   on a branch from `main` either way.
4. **Check `futuravailableunits.json`** (finding A1) — needs your install, so
   it is a morning task: compare `resources/_common/dat/futuravailableunits.json`
   in the game folder against the repo copy.

## Phase 0 — a golden-output harness (do first; it guards everything after)

`tests/test_route_roundtrip.py` hashes techs, effects, unit tables and
resources. It does **not** see strings, the F2 tree files, `civilizations.json`
or anything else in the zips — the surfaces Phase 2 moves.

Build `tests/golden_builds.py`:

- **Inputs:** every repo civ (`*.civbuilder.json`, `civbuilder_civs/`) plus
  `my_civs/` when present, each with a fixed replace target.
- **For each civ × each route** (web `_run_build_job`, wizard
  `build_wizard_mod`, CLI `build_mod`): build, then hash **every file in both
  inner zips** — the DAT by its *inflated* bytes (so the zlib level never
  matters), each strings file per language, each CivTechTrees JSON, the PNGs.
- `--baseline` writes `tests/golden/<dat-sha1>.json`; the default run diffs
  against it and prints **which file** of **which route** changed for which civ.
- Cost: with the lazy loader a build is ~3–5s, so 3 routes × ~30 civs is
  ~5–8 minutes. Opt-in (`GOLDEN=1`), like `ROUNDTRIP=1`.

**The first run is itself a finding:** where routes disagree today, that is a
behaviour difference Phase 2 must *decide*, not preserve. Known already:
`uberdudes` differs between routes (pre-existing), and the
`tagline`/`description` split. Record each difference with the route that is
right — default rule: **the web route is canonical**, because it is the one
players use.

Also add a **per-bonus golden**: apply each catalog bonus id alone to one slot
and hash the DAT. ~440 bonuses × ~1–2s ≈ 10 minutes. This is Phase 4's safety
net — every block moved out of `_create_bonus_handler` must leave its own hash
unchanged.

## Phase 1 — quick wins and the unverified assumptions (small, independent)

Each is its own commit; none should move a golden hash unless noted.

1. **Delete the dead `build_civ` build path** — `main`, `_build_data_zip`,
   `_build_ui_zip` (~230 lines, no callers). `build_civ.py` stays as the
   library it already is (roster, tree patching, flags).
2. **Stale comments:** `app.py:1316` (Chronicles models "not available" —
   disproven for buildings by the Fortified Outpost test; wonders untested) and
   `builder.js:921` (describes a slot ≥ 52 filter the code no longer has).
3. **Pin `flask` and `pillow`** to the versions in the current venv, so the next
   exe build can't pick up a breaking release.
4. **String-pool test:** every id in `CAMPAIGN_STRING_POOL` (and the +1000 /
   +21000 / +150000 derivatives we rely on) still exists in the current
   `vanilla/key-value` file. Viking Sagas already removed two; this makes the
   next DLC's removals a red test instead of a blank tooltip.
5. **Bundled data freshness:** tests that read `CivTechTrees/` should read the
   folder beside the DAT under test (`EMPIREFORGE_DAT`), with the bundled copy
   only as a fallback — the bundled June copy is why #46 was invisible to the
   suite. Refresh the bundled `CivTechTrees/` and `civilizations.json` from the
   current install (DLC files are Microsoft's: keep them out of git per
   `.gitignore` — decide whether the bundled fallbacks should exist at all).
6. **`futuravailableunits.json`** — depending on the morning check: ship the
   player's own file (as `civilizations.json` already does), or stop shipping it.
   *Moves the golden hash of that one file, intentionally.*
7. **Prune `_BUILD_JOBS`** (keep the last N, or drop finished jobs after an hour).
8. `_DAT_OBJ_CACHE` keyed by path → key by path + mtime, so a game patch while
   the app runs is picked up.

## Phase 2 — one build pipeline

Today: `app._run_build_job` (508 lines), `wizard_build.build_wizard_mod` (452),
`build_all.build_mod` (566). About half of each route's substantive lines appear
verbatim in another, and all three implement the same ten jobs (UT
labels/tooltips, extra tech/unit strings, voices, per-civ trees,
`civilizations.json`, button PNGs, AI stubs, UU tooltips, civ text). Every
string fix this autumn had to be made three times.

**Target:** a new module, `mod_build.py`:

```python
@dataclass
class CivInput:
    civ_def: dict          # already normalized (Phase 3 makes this the schema shape)
    replace: str           # vanilla civ to replace
    source_name: str       # for messages

def build_mod(civs: list[CivInput], dat_path, mod_name, progress=print) -> BuildResult:
    # load DAT -> apply_civ per civ -> strings (all languages) -> per-civ trees
    # -> civilizations.json -> voices -> assets -> data zip + UI zip
```

The routes become adapters: the web route parses uploads and reports progress
into `_BUILD_JOBS`; the wizard converts its draft; the CLI reads its config.

**Order:**
1. Write `mod_build.build_mod` by **extracting the web route's code** (the
   canonical behaviour), split into named steps (`_write_civ_strings`,
   `_write_tree_files`, ...).
2. Point the web route at it. Golden: web hashes unchanged.
3. Point the CLI at it. Golden: CLI hashes now **equal the web route's** —
   review each diff against the Phase 0 record; any that isn't listed there
   is a bug to stop on.
4. Same for the wizard.
5. Delete the three old bodies.

## Phase 3 — canonical schema, Step 1

`docs/PLAN-canonical-schema.md` Step 1 (`normalize()`) has not started.
With one pipeline, it has exactly one place to be called: the start of
`build_mod`. Follow that plan's own sequence and its sweep findings
(2026-09-08) — in particular finding 4, which Phase 0 now answers, and the
`DEFAULTS` caution in finding 5. `tagline`/`description` collapses to one key
here.

## Phase 4 — the bonus-handler registry

`_create_bonus_handler`: 1,121 lines, 45 `if bonus_id == …` blocks — 10 over 30
lines (City Walls 116, 221 at 79, 332 at 59, 283 at 56, 81 at 44, 103 at 43),
29 of 6–30 lines, 6 tiny. 30 `_add_auto_fire_tech` calls inside.

1. **Registry, no behaviour change:** each block becomes a function registered
   by id — `@bonus_handler(400)`. `_create_bonus_handler` becomes a lookup, and
   **`HANDLED_BONUS_IDS` becomes `set(_HANDLERS)`** — the hand-kept list and its
   sync test disappear. Per-bonus golden: every hash unchanged.
2. **Data over code:** blocks that only build a fixed command list and wrap it
   in an auto-fire tech belong in `bonus_catalog_raw.json`'s `ec_list`, where
   the multiplier scaling, effect-cap guard and tests already apply. Move them
   one at a time; per-bonus golden proves each. Keep in code only what needs
   the DAT at build time (unit data rewrites, civ-specific lookups, prerequisite
   rewiring).
3. Same treatment for any `if bonus_id in (...)` checks scattered outside the
   handler (`apply_civ`, `_apply_tree_wiring`) — list them first.

## Phase 5 — the remaining hand-kept lists

- `_BONUS_CAT_OVERRIDES` in `builder.js` (~120 ids) → a `"category"` field in
  `bonus_cards.json` / `team_bonus_cards.json`, next to the text it describes.
- `tests/test_seed_tree.js`'s copy of the unlock table → read it from the API
  fixture the way the app does.
- `_OPT_IN_UNIT_NODE_SOURCES`, KM id tables: a sync test each where a single
  source isn't possible.

## Out of scope for now

- Lazy graphics in `dat_lazy` (~0.6s of load; declined 2026-10-04).
- Splitting `builder.js` (4,170 lines) — worth it, but after Phase 5 removes the
  data that is mixed into it.
- `apply_civ` (598 lines) and `_apply_tree_wiring` (416) — natural follow-ups
  once Phase 4 has shown the pattern.

## Open questions for you

1. Ship the perf branch alone as 2.4.1, or together with Chronicles as 2.5.0?
2. `futuravailableunits.json`: once compared, ship the player's own or none?
3. Should the bundled `CivTechTrees/` / `civilizations.json` fallbacks exist at
   all, or should the app require the game's own copies?
4. Phase 2 canonical behaviour: OK to treat the web route as the reference
   wherever routes disagree?

## Findings this plan answers (review of 2026-10-04)

- **A1** Every mod ships the repo's `futuravailableunits.json` (2026-06-22,
  pre-Viking Sagas: no Saxons, Varangians, Danes). No record of why.
- **A2** Bundled fallbacks are stale (`CivTechTrees/` 2026-06-06,
  `civilizations.json` 2026-02-18) and tests read them.
- **A3** The string pool assumes vanilla campaign ids survive patches.
- **A4** Stale comments: `app.py:1316`, `builder.js:921`.
- **A5** `flask`, `pillow` unpinned; `_DAT_OBJ_CACHE` keyed by path;
  `_BUILD_JOBS` unbounded.
- **S1** Three build routes, ~50% verbatim overlap; a fourth, dead, in `build_civ`.
- **S2** Two civ_def shapes; `normalize()` not started.
- **S3** Hand-kept lists mirroring data held elsewhere.
- **S4** `_create_bonus_handler` 1,121 lines; `apply_civ` 598;
  `_apply_tree_wiring` 416; `builder.js` 4,170.
