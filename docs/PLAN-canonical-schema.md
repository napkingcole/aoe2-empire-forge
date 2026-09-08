# Making the schema canonical

**Status:** proposed, not started
**Written:** 2026-08-31, against `v2.0.0-beta.1.3`
**Prerequisite:** the quick fixes below are already landed on `feature/ui-builder`

---

## The problem

`apply_civ` accepts two in-memory civ_def shapes and does not know which it will get:

```
KM      tree    = [units, buildings, techs]
        bonuses = [civ, [uu_idx], castle_ut, imperial_ut, team]

schema  tree    = {"units": [...], "buildings": [...], "techs": [...]}
        bonuses = [{"id": X, "multiplier": Y}, ...]
```

Which shape arrives depends on which door the civ came through, not on what the user saved:

Referenced by function name, not line number — the numbers in the first draft of this plan had
all rotted by the 2026-09-08 sweep.

| Entry point | Input | Shape at `apply_civ` |
|---|---|---|
| `app.py` `/builder/build` | live draft from the browser | `_draft_to_civ_def` → **KM** |
| `app.py` `_run_build_job` | uploaded `.civbuilder.json` | **schema**, unconverted |
| `build_all.py` `build_all()` | `my_civs/*.json` | **KM** |
| `build_all.py` `build_all()` | a `.civbuilder.json` | `civ_schema.to_draft` → **draft** (dict-shaped) |
| `templates/builder_landing.html` Edit Civ | a `.civbuilder.json` | **schema written straight to localStorage as the draft** — see below |

**The fifth door is in the browser**, and `normalize()` — a Python function — can never reach it.
Edit Civ writes the saved file into localStorage with no conversion, so `builder.js` then applies
*draft* migrations to a *schema* file. Until that door converts, `from_draft` must keep writing
both spellings of every key `builder.js` reads (see Step 4).

So the same civ takes different shapes depending on route. Every bug in this area has been one
reader picking the wrong one of two live answers:

- `_tree_unit_ids` doing `tree[0]` on a dict — **shipped in beta.1.3**, broke every upload build
- bonus handler 221 doing `_tree_list[0]` on a dict — same crash, never reported
- `build_all.py:545` reading `bonuses[1][0]` for the UU index in a function that had started
  receiving both shapes
- `diagnose_civ.py` reading all five KM slots directly, reporting `(none)` for every schema civ

The accessors in `civ_appender` absorb the difference, which is why this is survivable. But the
format boundary lives *inside* the build logic instead of at the entrance, so every new reader is
a chance to get it wrong again. The lint (`tests/test_no_direct_civdef_reads.py`) makes that
chance visible; it does not remove it.

## The decision

**The schema (`empireforge_v2`) becomes canonical.** It is the format users save, the one the
wizard and UI already speak, and the one the on-disk corpus is written in. KM becomes purely an
*import* format: converted once at the door, never seen downstream.

This is the opposite of today, where `_draft_to_civ_def`'s docstring calls KM "the civ_def format
expected by `apply_civ`."

## Three shapes, not two

Worth being explicit, because the plan hinges on it:

| Shape | Lives where | Notes |
|---|---|---|
| **draft** | browser localStorage, `/builder/build` POST body | wizard's working state; keys come and go as the user edits |
| **schema** | `.civbuilder.json` on disk | `civ_schema.from_draft` / `to_draft` convert to and from draft |
| **KM civ_def** | `my_civs/*.json`, and `_draft_to_civ_def`'s output | legacy |

`draft` and `schema` look alike to `apply_civ` — both dict `tree`, both dict `bonuses` — which is
why the accessors only face a 2-way split. They are still distinct types with a real converter
between them, and conflating them is how `build_all.py:462` ended up calling something
`_schema_to_draft` and then feeding the *draft* to `apply_civ`.

So the wizard door needs a genuine `draft → schema` normalizer, not a passthrough.
`civ_schema.from_draft` already is one — it is simply not on that path today.

## Target

```
draft            ─ from_draft ──┐
schema (on disk) ───────────────┼─→  normalize()  ─→  schema  ─→  apply_civ
KM file          ─ _km_to_draft ┘        │
                    → from_draft         └── fills defaults, drops nulls
```

One function, `normalize(raw) -> schema`, at all four entry points. It does two jobs at once:

1. **Shape** — detect the input format, convert to schema.
2. **Defaults** — every optional key present with a real value, never `null`, never absent.

Job 2 is the part that pays down the `or {}` debt. Today `civ_schema` writes `"hero_unit": None`
straight to disk (`:141`, `:246`), which is why real saved files carry nulls for `second_uu`,
`monk_skin_unit`, `monastery_skin_building`, `hero_unit`, `starting_scout`, and `monk_skin`. Every
downstream reader then needs `or {}` to survive. If `normalize` guarantees the shape, those guards
and the accessor layer both become **deletable** rather than permanent.

`_draft_to_civ_def` does not disappear — it **inverts**. Today it is `draft → KM`. It becomes
unnecessary on the build path, and if anything still needs KM output (a KM export feature), it
becomes `schema → KM` and lives next to the importer.

## Sequence

Each step is independently landable and leaves the tree green.

### 0 — Baseline (done)

`tests/test_route_roundtrip.py --baseline` captured hashes for all 15 saved civs across both
routes, committed as `tests/route_hashes.json`. Every later step re-runs `--check`; **a step that
changes any hash is not a refactor, it is a behavior change** and needs justifying or reverting.

The baseline was taken *after* the quick fixes, so it encodes correct behavior, not the beta.1.3
bug.

### 1 — `normalize()` exists, nothing calls it

Add `civ_schema.normalize(raw) -> schema`: format-detect (`is_empireforge` / `is_km_format`),
convert, fill defaults. Add a `DEFAULTS` table naming every optional key and its empty value.

Unit-test it directly against the corpus. No production caller yet, so this cannot regress
anything. Round-trip hashes unchanged by construction.

Three constraints on the `DEFAULTS` table, from the 2026-09-08 sweep:

- **`castle_ut` / `imperial_ut` `time` and `cost` must distinguish absent from zero.** Defaulting
  them to `0` bakes in "free, instant UT" for every civ that never set them — `_override_ut_costs`
  writes `resource_costs` unconditionally, so an absent cost and an all-zero cost are the same
  thing to it today. This is the clearest case in the codebase where "fill every optional key with
  its empty value" is the wrong rule (finding 5).
- **`unique_unit.base_unit_id` is not in the canonical shape** — settled 2026-09-08 by deleting
  the unreachable from-scratch UU path it gated, so there is nothing left for a default to wake
  up. `second_uu` builds on `km_custom_uu.append_km_custom_uu` instead (finding 6).
- **`tagline` / `description` collapse to one key here** — this is the natural place for it
  (finding 2).

### 2 — Entry points adopt it, one at a time

In increasing order of blast radius:

1. `build_all.py:462` — CLI, no users mid-beta
2. `diagnose_civ.py` — diagnostic only
3. `app.py:543` `_run_build_job` — the upload path
4. `app.py:1759` `/builder/build` — the wizard path, highest traffic

After each, run `--check`. The wizard door is last because it is the one that currently converts
to KM; adopting `normalize` there is what actually flips the canonical shape.

### 3 — Delete the KM branches

Only once every door normalizes. In order:

1. Drop the KM fallbacks from `get_civ_bonuses`, `get_team_bonuses`, `get_ut_entries`,
   `get_km_uu_index`, `_tree_unit_ids`, `_tree_building_ids` — they become dead.
2. Drop `_apply_tree_wiring`'s list branch and `build_civ._tree_sets`'s.
3. Drop the `or {}` guards that `normalize`'s defaults now make redundant.
4. Shrink `ALLOWED` in the lint to just the converters. The accessors stop being a compatibility
   layer and become plain field access — at which point deleting them entirely is on the table.

Each deletion is verified by `--check` staying identical, not by reasoning.

### 4 — Fix the null emission at source

`civ_schema.from_draft` stops writing `null` for absent optional keys — omit them, or write the
default. Regenerate the corpus, confirm hashes unchanged, and the JSON files stop carrying the
nulls that made the guards necessary.

**Two hard constraints (finding 7).** The `wonder`/`castle` duplication alongside
`wonder_model`/`castle_model` in `from_draft` is **load-bearing, not redundancy**: Edit Civ loads
the schema into localStorage without `to_draft`, and `builder.js` only knows the unsuffixed
spellings. Removing it silently drops the user's Castle and Wonder from the review screen and the
build. And writing `"wonder": null` rather than omitting the key breaks `_draft_to_civ_def`, whose
fallback is a plain `.get` default and therefore None-blind. Change
`templates/builder_landing.html` to convert first, or leave both spellings in place.

## The pass-through keys (resolved 2026-08-31)

`monk_skin` is fully live and unrelated to the other two: written at `builder.js:375`, restored on
load at `builder.js:3604`, consumed at `civ_appender:3515` → `_copy_monk_skin`.

The others had **zero writers and zero readers** anywhere — no Python, no `builder.js`. They
existed only in `civ_schema`'s pass-through lists, documented as "Phase-Two keys ... passed
through unchanged so future handlers can act on them," and the pass-through was what materialized
them as `null` on every save.

| Key | Decision |
|---|---|
| `monk_skin_unit` | **Dropped.** Superseded by `monk_skin`, which already covers the picker. Removed from both pass-through lists; round-trip hashes unchanged. |
| `monastery_skin_building` | **Kept.** Planned for the next update — a real feature, not dead weight. |
| `second_uu` | **Kept.** Deliberate placeholder, not yet implemented. |

For the two that stay, `normalize` should give them a real default rather than `null`, preserving
the forward-declaration intent without emitting the nulls that force `or {}` guards downstream.

## Mid-beta safety

**Safe to land now** (already done):

- The null guards and KM-only straggler fixes. Pure bug fixes, no shape change, hashes unchanged.
- `test_civ_def_formats.py`, `test_no_direct_civdef_reads.py` — tests only.
- `test_route_roundtrip.py` + baseline — opt-in, skipped by default.

**Safe mid-beta:**

- **Step 1** (`normalize` with no callers). Additive, unreachable from production.
- **Step 2.1–2.2** (`build_all`, `diagnose_civ`). Neither is on a user path; `build_all` is the CLI
  and `diagnose_civ` is a dev tool.

**Wait for a version bump:**

- **Step 2.3–2.4** (the two `app.py` doors). These are the paths every beta user hits. Even a
  hash-identical change moves the format boundary under the live build routes, and a mistake
  breaks mod generation for everyone, not one civ. Land on `v2.0.1-beta.2` or later with the
  round-trip check green.
- **Step 3** (deleting KM branches). Irreversible in the sense that a KM file that slips past a
  door with no fallback crashes instead of degrading. Needs step 2 to have been in users' hands
  long enough to trust.
- **Step 4** (changing what gets written to disk). Alters the saved file format. Old files must
  still load — `normalize` covers that — but new files become unreadable to older builds, so it
  is a format-version event. Bump `SCHEMA_VER` and gate on it.

**The mid-beta rule:** anything that only *adds* a path is fine now; anything that changes or
removes a path users are already on waits for the bump.

## Why this is worth doing

The accessors are load-bearing today and will stay load-bearing forever unless the shapes actually
converge. Testing them — which is what we just did — makes the current state safe. It does not
make it simpler. Normalizing at the door is what lets the compatibility layer be deleted rather
than maintained, and the round-trip hashes are what make deleting it a mechanical, verifiable
operation rather than a leap.

---

## Sweep findings — 2026-09-08

Audit only; no code changed. Written against `v2.0.1` on `main`, after the bugfix batch
landed. The brief was: before any migration step begins, look for *other* instances of the
class of bug that bit us three times (one field, two shapes, two readers) — not only the
sites this plan already catalogues.

The `tree`-as-list-vs-dict bug itself is clean. Every positional `tree[N]` / `bonuses[N]` read
in the tree is inside an allowlisted accessor or converter, and `test_no_direct_civdef_reads.py`
passes. What the sweep found instead are **eight other fields with the same disease** — one
field, two names or two shapes, and readers that disagree — none of which the existing lint or
the round-trip hash can see.

Ranked by risk. "Silent" below always means *no crash, wrong output*.

### 1 — Edit Civ silently wipes both unique techs on any file without `_draftVer`  ⚠ HIGH, live

**Where:** `templates/builder_landing.html:80` → `static/js/builder.js:22-36`

`builder_landing.html:80` writes the saved `.civbuilder.json` **straight into localStorage as
the draft** — no `to_draft`, no Python, no normalization of any kind. `builder.js` then runs its
draft migrations against it, and the first one is:

```js
if ((draft._draftVer || 0) < 2) {
  if (draft.castle_ut)   draft.castle_ut.effects   = [];
  if (draft.imperial_ut) draft.imperial_ut.effects = [];
```

`from_draft` writes `_draftVer` (`civ_schema.py:229`) precisely to prevent this, but **every
saved civ file in this repo lacks the key** — all 7 (`uberdudes`, `super_civ`, `EXAMPLE`, and
the four `my_civs/probe_*`), and every `civbuilder_v1` file by definition, since they predate
it. `builder_landing.html:77` explicitly accepts `civbuilder_v1`.

**Failure scenario:** user opens Edit Civ, picks the `.civbuilder.json` they saved last month,
clicks through to Build. Both UTs still have their name, description, cost and research time —
only `effects` was emptied — so the review screen, the Castle button, the F2 viewer and the
civ-picker blurb all look correct. The built civ has two unique techs that **do nothing**. No
error anywhere.

**Structural consequence for this plan:** the Target diagram lists four entry points. This is a
**fifth**, it is in the browser, and `normalize()` — a Python function — can never reach it.
Any plan that makes the schema canonical has to say what happens on the localStorage door,
because today that door applies *draft* migrations to a *schema* file.

**Mid-beta:** the guard is safe to land now (treat a payload carrying `format` but no
`_draftVer` as current, in `builder_landing.html` or at the top of `builder.js`). Additive,
no schema change, no hash movement. *Deleting* the migrations waits for a bump.

### 2 — `tagline` vs `description`: same file, two different civ-picker blurbs by route  ⚠ HIGH, live

**Where:** `static/js/builder.js:239` · `wizard_build.py:76,222` · `app.py:739` ·
`build_all.py:567` · `app.py:1959`

The wizard only ever writes `draft.tagline` (`builder.js:239`); **nothing anywhere writes
`draft.description`**. The three build doors then disagree about which key holds it:

| Door | Reads | Result for `uberdudes.civbuilder.json` |
|---|---|---|
| `/builder/build` | `draft["tagline"]` → `_draft_to_civ_def:76` → `civ_def["description"]` | `"Kick-ass civilization"` |
| `_run_build_job` (upload) | `civ_def["description"]` (`app.py:739`) — the schema's own, always `""` | `"Uberdudes civilization"` |
| `build_all.py` (CLI) | same (`build_all.py:567`) | `"Uberdudes civilization"` |

Verified against the real corpus: `uberdudes` gives `'Kick-ass'` vs `''`; `probe_tree` gives two
*different* non-empty strings (`'QA probe — tech tree disabling…'` vs `'Issues #29 #31…'`),
because the probes fill both keys.

**The KM importer inverts it.** `_km_to_draft` (`app.py:1959`) puts the KM file's description
into `description` and leaves `tagline` empty — so a KM-converted civ loses its description on
the *wizard* route and keeps it on the *upload* route. That inversion is the proof this is a
genuine two-names-one-field aliasing bug rather than two fields that happen to overlap.

**Failure scenario:** user exports their civ, re-uploads it (or shares it and someone else
builds it), and the civ-selection screen shows a generic `"<Alias> civilization"` instead of
their tagline. Silent.

**Mid-beta:** `build_all.py:567` is CLI-only → safe now. `app.py:739` is a live user door →
version bump, per the plan's own gating. The right end state is one key, decided in `normalize`.

### 3 — `build_all.py` throws away the user's UT names and descriptions  ⚠ HIGH, CLI only

**Where:** `build_all.py:490-496` vs `app.py:659-666` and `wizard_build.py:175-184`

Both app.py doors resolve UT names as `civ_def["castle_ut"]["name"] or _ut_name(bonus_id)`.
`build_all.py` never added the first half:

```python
castle_ut_name = _ut_name(castle_ut_bid, castle=True)   # bonus-table lookup only
```

`_ut_bonus_id` returns `entries[0][0]` — the *first effect's* UT slot id — so an Empire Forge
civ gets named after whatever effect happens to be first in the list. Measured on the corpus:

| File | User's name | `build_all.py` writes |
|---|---|---|
| `uberdudes` imperial | `Shock and Awe` | `Torsion Engines (increases blast radius of Siege Workshop units)` |
| `probe_tree` imperial | `Probe Imperial` | `Paper Money (Lumberjacks slowly generate gold in addition to wood)` |
| `probe_tree` castle | `Probe Anarchy` | `Anarchy (create Unique Unit at Barracks)` |

`castle_ut.description` / `imperial_ut.description` are not read at all on this path. The wrong
name propagates everywhere: the research-button label, `civ_result["castle_ut_name"]` →
`_patch_per_civ_techtree` node labels, the F2 viewer string, and the civ-picker bullet list.

**Mid-beta:** `build_all.py` is the CLI, not a user path — safe to fix now, and it belongs in the
same neighbourhood as Step 2.1.

### 4 — `test_route_roundtrip.py --check` cannot see most of what a migration would break  ⚠ HIGH, methodology

**Where:** `tests/test_route_roundtrip.py:82-101` (`digest`), `:128-131` (`run_route`)

This plan gates every migration step on "`--check` green ⇒ refactor, hash moved ⇒ behavior
change". That inference is weaker than it reads.

`digest()` hashes: `civ.name`, `civ.icon_set`, `civ.resources[263]`, each appended tech's
`(name, civ, effect_id, required_techs)`, each appended effect's commands, and the civ's TT
effect. It does **not** hash:

- any `dat.civs[slot].units[*]` mutation — architecture graphics, the six monk-skin fields
  (CLAUDE.md quirk 12), Castle unit 82, Wonder unit 276, `unit.enabled`, UU
  `train_locations` / `resource_costs`;
- `civ.resources[*]` other than 263;
- tech `resource_costs` and `research_time` — so `_override_ut_costs`' entire output;
- every generated string, and the patched `CivTechTrees` JSON.

And `run_route` calls **`apply_civ` alone**. `_override_ut_costs`, `_apply_uu_overrides`,
`_refresh_uu_tooltips`, `_apply_hero_unit`, `assign_all_languages`, `_patch_per_civ_techtree`
and the whole string block are outside the harness. Findings 2, 3, 5 and 8 are all invisible to
it, and so would be a `normalize()` that mishandled `monk_skin`, `castle`/`wonder`, `emblem`,
`architecture`, UT cost/time, UU overrides or the hero unit.

Two smaller defects in the same file:

- **`civ.name` is inert.** `apply_civ` with `overwrite` keeps the *vanilla* slot name
  (`civ_appender.py:3771`), so it is a per-slot constant. `alias` never enters the hash at all.
- **The baseline is stale.** `tests/route_hashes.json` has 15 civs; the corpus is now 19
  (the four `my_civs/probe_*.civbuilder.json` were added after the baseline).
  `run_all.sh` already says 19. `--check` surfaces that as a `note`, which is easy to wave
  through on the run where it also matters.

**Recommendation:** extend `digest()` (civ unit graphics fingerprint, full `civ.resources`,
tech costs/times, and ideally the string block by running one door end-to-end) and re-baseline
**before Step 1**, not after. Otherwise "hashes unchanged" is evidence about techs and effects
only, and every later step's justification inherits that gap. Tests-only, safe mid-beta.

Related coverage gap: `tests/test_build_smoke.py:156` builds via `build_wizard_mod(to_draft(CIV))`
— the **wizard route only**. Neither `_run_build_job` nor `build_all.py` is exercised by any test
that actually builds, which is why 2 and 3 survived.

### 5 — KM import produces free, instant unique techs  ⚠ MEDIUM

**Where:** `app.py:1936-1943` (`_km_to_draft._ut`) · `civ_overrides.py:44-56`
(`_override_ut_costs`) · `static/js/builder.js:2419,2666,2678-2684`

`_km_to_draft` emits `cost: {food:0, wood:0, stone:0, gold:0}` and `time: 0`.
`_override_ut_costs` applies **cost unconditionally** whenever the UT dict is non-empty, and
`time` whenever it is not `None`. So a KM-converted civ that is built without the user
re-visiting steps 6 and 7 gets both unique techs **free and 0-second research**.

The wizard makes this hard to notice: `_utDraft` (`builder.js:2419`) seeds `time: 60` only when
it *creates* the object, and `initUTPanel` (`:2678-2684`) *displays* `cost[r] ?? 0` and
`ut.time ?? 60` without writing them back. The UI reads "60s"; the draft holds `0`.

Same function, second problem: `_km_to_draft._ut` writes **`"vanilla_id"`**, while every other
layer uses `vanilla_km_idx` (`civ_schema._ut` / `_ut_out`, `builder.js:2617`). Dead key.
`initUTPanel:2666` happens to self-heal by copying `effects[0].id`, so this is currently latent
rather than broken — but it is one rename away from mattering.

**Direct implication for Step 1:** the `DEFAULTS` table must **not** default `time` to `0` or
`cost` to all-zeros. That would bake "free instant UT" in for every civ that never set them.
`normalize` has to distinguish *absent* from *zero* here — this is the clearest case in the
codebase where "fill every optional key with its empty value" is the wrong rule.

**Mid-beta:** fixing `_km_to_draft` to carry real costs (or omit the keys) is behind the
converter page and safe now. Changing `_override_ut_costs` to skip an all-zero cost touches all
four doors → version bump.

### 6 — `unique_unit.base_unit_id` is dead; the from-scratch UU path is unreachable  ⚠ MEDIUM

> **Resolved 2026-09-08 — the path was deleted.** The description below is the state at sweep
> time; line references in it are stale. See "Finding 6 — the from-scratch UU path, deleted"
> near the end of this document.

**Where:** `civ_appender.py:3677`, `:3869`, `:4200-4208`

```python
has_custom_uu = (civ_def.get("unique_unit") or {}).get("base_unit_id") is not None
```

**No layer writes `unique_unit.base_unit_id`.** `builder.js` writes `unique_unit.km_idx`
(`base_unit_id` at `builder.js:1157` is the *hero*, a different object); `civ_schema`'s `uu_out`
carries `km_idx` / `vanilla_id` / `name` / `description` / `overrides` / `advanced_flags`;
`_draft_to_civ_def` narrows it further to `{name, description}`. So `_append_unique_units` and
the `_append_elite_upgrade_tech` call at `:3882` are dead on all four doors, and the
`"UU: skipped (no base_unit_id)"` log line reads as a warning about a path that cannot run.

Not a bug today. It matters because **`second_uu` is being kept as a placeholder**: if it is
implemented as `{"base_unit_id": ...}`, or if `normalize`'s DEFAULTS table materializes
`base_unit_id` on `unique_unit`, this path wakes up and starts cloning a Militia into every
civ. Worth an explicit decision in Step 1 rather than a discovery in Step 4.

### 7 — `castle`/`wonder` vs `castle_model`/`wonder_model`: three ladders that must agree  ⚠ MEDIUM, latent

**Where:** `civ_appender.py:3795,3806` · `civ_schema.py:136-137` · `wizard_build.py:83-84`

Three independent fallbacks, written at three different times, using **two different tests**:

```python
civ_appender  castle_raw = civ_def.get("castle") if "castle" in civ_def else civ_def.get("castle_model", -1)
civ_schema    "wonder":   s["wonder"] if "wonder" in s else s.get("wonder_model", -1)
wizard_build  "wonder":   draft.get("wonder", draft.get("wonder_model", -1))
```

The first two are **absence**-based and survive a `null`. The third is a plain `.get` default,
which is **None-blind**: a key present with `null` returns `None` and the `*_model` fallback
never fires. They agree today only because the entire on-disk corpus has `castle`/`wonder`
*absent* with `*_model` present (verified — all three doors resolve `uberdudes` to
`castle=2, wonder=31`), and because current `from_draft` deliberately writes **both** spellings
(`civ_schema.py:239-242`).

**This sits directly on Step 4's path.** Step 4 says `from_draft` should "omit absent optional
keys, or write the default". Either half breaks something:

- write `"wonder": null` → `wizard_build.py:83` drops the Wonder choice, silently, on the
  highest-traffic door. Same failure the comment right above it already documents for the
  missing-key case — the null case was never covered.
- drop the duplicated `wonder`/`castle` as "redundant" → **Edit Civ breaks**, because
  `builder_landing.html:80` loads the schema into localStorage *without* `to_draft`, and
  `builder.js` only knows the `wonder`/`castle` spellings. The user's Castle and Wonder
  disappear from the review screen and from the build.

The duplication at `civ_schema.py:239-242` is **load-bearing, not redundancy**. Its comment says
so; the plan's Step 4 does not acknowledge it. Version bump either way.

### 8 — Route-specific string divergences between the two doors  ⚠ LOW

Same civ, two doors, different text. None visible to the round-trip hash.

- **Team-bonus text uses different tables.** `app.py:766` reads `_TEAM_BONUS_NAMES`;
  `wizard_build.py:239` reads `_BONUS_NAMES` for the same entries.
- **`app.py:818`** writes the *long* `imp_ut_name` (parenthetical and all) to
  `imp_ut_sid + DLL_TECH_TREE_OFFSET`, while the Castle UT six lines up (`:805`) writes
  `castle_ut_name_short`. Asymmetric within one function.
- **Hero hover:** `app.py:783` appends a cost line; `wizard_build.py:298` does not.
- **UU rename detection:** `app.py:876` also compares against `_KM_UU_NAMES`;
  `wizard_build.py:381` keys only on `uu_override_name`.

Each is a small independent fix, but collectively they are the reason "both doors build the
same civ" is not currently true, and they will keep drifting while the string block exists in
two copies. Worth folding into the Step 2.3/2.4 window rather than fixing piecemeal.

### 9 — Hygiene and stale references  ⚠ LOW

- **Line numbers in this plan have drifted.** `app.py:543` `_run_build_job` → **`:552`**;
  `app.py:1759` `/builder/build` → **`:1801`**; `build_all.py:485` → **`:486`**;
  `build_all.py:545` → **`:550`**. `build_all.py:462` is still accurate.
- **The lint's scope is narrower than it looks.** `test_no_direct_civdef_reads.py:113` globs
  `ROOT/*.py` only — `tests/`, `scripts/` and all JavaScript are unscanned. Checked by hand this
  sweep: clean. Worth stating in the file so nobody assumes coverage it does not have.
- **`to_draft` and `from_draft` are not inverses for falsey flags.** `to_draft:65,120` strips
  values that are `None` *or* `False`; `from_draft:222-223,212` strips only `None`. Every current
  consumer in `civ_overrides.py` uses truthiness or `is not None`, so this is benign — but
  draft→schema→draft is not an identity, and `normalize` should pick one rule explicitly.
- **`to_draft` has no `team_bonus` (singular) fallback**, although `_draft_to_civ_def:70` and
  `builder.js:24` both migrate it. Only reachable for a hand-written file; noted for completeness.
- **`civ_schema.py`'s module docstring is stale** — it still describes the format as
  `civbuilder_v1` and says "build_all.py detects `"format": "civbuilder_v1"`", while
  `FORMAT_KEY` has been `empireforge_v2` since SCHEMA_VER 2.
- **Three more zero-reader pass-throughs.** The plan's pass-through table covers `monk_skin_unit`,
  `monastery_skin_building` and `second_uu`. `unit_overrides`, `button_moves` and `free_techs`
  are in exactly the same position (`civ_schema.py:155-157,261-263`) — no writer, no reader,
  anywhere. They default to `[]` rather than `None`, so they do not add to the null debt, but
  they belong in the same table and the same decision.

### Suggested ordering relative to the existing plan

Safe to land now, and all three make the migration itself safer:

1. **Finding 1** — the Edit Civ `_draftVer` guard. Live data loss; JS-only; no schema change.
2. **Finding 4** — widen `digest()` and re-baseline **before Step 1**, so that every later
   "hashes unchanged" claim actually covers the surface the steps touch.
3. **Findings 3 and 5** — `build_all.py` UT names, `_km_to_draft` UT costs. CLI and importer
   only; neither is on a user build path.

Feed into Step 1's design rather than fixing separately:

- **Finding 5** — `DEFAULTS` must distinguish absent from zero for `castle_ut.time` / `cost`.
- **Finding 6** — ~~decide explicitly whether `unique_unit.base_unit_id` exists in the canonical
  shape~~ **Decided 2026-09-08: it does not.** The key and the path it gated are deleted, so
  `DEFAULTS` has nothing to accidentally wake up.
- **Finding 2** — `normalize` is the natural place to collapse `tagline`/`description` to one key.

Add to the plan as an explicit constraint:

- **Finding 7** — the `wonder`/`castle` duplication in `from_draft` is load-bearing for the
  localStorage door and must not be removed in Step 4 without changing `builder_landing.html`
  first.
- **Finding 1** — the Target diagram needs a fifth entry point.

### 10 — `_apply_uu_overrides` crashes on a null UU override  ⚠ HIGH, live

Found while landing the fixes above, by the widened round-trip harness — the exact class of bug
finding 4 predicted the narrow hash was hiding.

**Where:** `civ_overrides.py` `_apply_uu_overrides`

Every stat read in that function is a *membership* test — `int(overrides[f"cost_{r}"]) for r in
_RES if f"cost_{r}" in overrides` — so a key present with `null` passes the test and reaches
`int(None)`. The function is written against `to_draft`'s documented "strip nulls so absence ==
no override" contract, but **only the wizard door goes through `to_draft`**. The upload door
hands it the raw schema, nulls intact.

**Failure scenario:** upload any `.civbuilder.json` carrying an explicit `"cost_food": null` under
`unique_unit.overrides` and the build dies with `TypeError: int() argument must be … not
'NoneType'`. `civbuilder_civs/EXAMPLE.json` — our own documented example file — is exactly such a
file, so "download the example, upload it" was a crash. Not silent, but live and on a user path.

Note `from_draft` strips nulls from `unique_unit.overrides` but **not** from
`hero_unit.overrides`; `_apply_hero_unit` survives only because it reads with
`.get(k) is not None` throughout. Two readers, two conventions, one of which was wrong.

**Fixed 2026-09-08** by restoring the contract at the top of `_apply_uu_overrides`. Pure null
guard, no shape change — the "safe to land now" category.

---

## Applied 2026-09-08

Landed on `main`. Version-bump-gated items were left alone per the mid-beta rule.

**Verification.** Fast suite and `test_build_smoke.py` green; `--check` green against a freshly
written baseline (~80s, 19 civs, both routes agreeing under the widened hash). Finding 1 was
verified in a real browser against `uberdudes.civbuilder.json`, whose imperial UT is
`mode: "custom"` with five multiplier-carrying effects: loaded through the Edit Civ door it now
keeps 1 and 5 effects with multipliers `[3,1,2,2,1]` intact, and the same file with its `format`
key removed — so the new guard cannot fire — still loses both (1→0, 5→0), which is the bug.
That negative control also corrected one claim: the v4 migration is guarded on `!mode`, so it
only misfiles a UT on a file old enough to predate the `mode` key, not on every file.

| Finding | Status |
|---|---|
| 1 — Edit Civ wipes UTs | **Fixed.** `builder.js` stamps `_draftVer` when the payload carries `format`. See the judgment call below. |
| 2 — `tagline`/`description` | **Fixed on all three doors** — `build_all.py` and `_run_build_job` both prefer `tagline` and fall back to `description` for KM imports, matching `_draft_to_civ_def`. Collapsing to one key is still normalize()'s job. |
| 3 — `build_all.py` UT names | **Fixed.** Now uses the user's name with the bonus-table lookup as fallback, matching both `app.py` doors. |
| 4 — harness blind spots | **Fixed.** `digest()` now covers the unit table, the full resource block, tech costs/times, and the four override passes. Re-baselined. |
| 5 — free/instant KM UTs | **Fixed.** `_override_ut_costs` now reads an all-zero cost and a non-positive time as *unset* rather than "free and instant", so a copied vanilla tech keeps its own. Also: `time` omitted from `_km_to_draft`, dead `vanilla_id` → `vanilla_km_idx`. |
| 6 — dead `base_unit_id` | **Resolved: deleted.** The from-scratch UU path is gone (136 lines). See below. |
| 7 — `castle`/`wonder` ladders | Folded into Step 4 as a hard constraint. No code change. |
| 8 — string divergences | **All four fixed** — see below. |
| 9 — hygiene | **Fixed.** `civ_schema` docstring, lint scope comment, and the plan's line-number references replaced with function names. |
| 10 — null UU override crash | **Fixed.** See above. |

**Correction to finding 5, and what it led to.** The sweep called the `_km_to_draft` fix "safe
now", which is true but narrower than it reads: `from_draft` and `to_draft` both do `int(x or 0)`
on `time`, so a save-and-reload re-materializes `time: 0`, and `cost` could not be fixed from the
importer at all. The importer-only fix would have held for a straight convert→build and silently
come undone on the next save. So `_override_ut_costs` was fixed directly instead: an all-zero
cost and a non-positive time now mean *unset*. Zero is not a usable signal anywhere in this
codebase — the wizard seeds a new UT with an all-zero cost, KM import emits zeros, and every save
round-trip re-materializes them — so the only sound reading is "leave what `apply_civ` produced".
A vanilla copy keeps its real cost and time; a synthesised custom UT keeps `_make_tech`'s
free/60s default, which is what it had anyway. The cost of this: a **deliberately** free UT is
not expressible until `normalize` can carry absent and zero apart. That is the finding-5
constraint on Step 1's `DEFAULTS` table, now with a live dependency on it.

## Finding 8 — the four divergences, resolved

Each was decided by asking which door was right, then making the other match.

1. **Team-bonus name table — the serious one.** `wizard_build` looked team bonus ids up in
   `_BONUS_NAMES` (the *civ* bonus table) instead of `_TEAM_BONUS_NAMES`. These are separate
   namespaces: **all 83 team bonus ids resolve to different text in the civ table and none are
   absent**, so the lookup never returned "" and never hit the skip — every wizard-built civ
   shipped a confidently wrong team bonus on its selection screen. Fixed to read the team table.
2. **Imperial UT tech-tree string.** `app.py` wrote the *long* `imp_ut_name` (parenthetical and
   all) to `imp_ut_sid + DLL_TECH_TREE_OFFSET` while the Castle UT six lines above wrote the
   short form, and `wizard_build` wrote short for both. The F2 node wants the name alone; the
   long form was the outlier. Fixed to `imp_ut_name_short`.
3. **Hero hover cost line.** `app.py` appended one, `wizard_build` did not. Quoting the real cost
   is the established behavior for unit tooltips (it is what `_refresh_uu_tooltips` exists for,
   and the smoke test asserts it for the UU), so `wizard_build` gained it. Both doors now call
   the shared `uu_cost_text` helper, replacing `app.py`'s hand-rolled copy of the same loop.
4. **UU rename detection.** `app.py` treated a UU as renamed on an explicit override *or* a
   resolved name that no longer matched `_KM_UU_NAMES` — the second half is how a KM-custom
   preset reads. `wizard_build` keyed only on the override, so a preset UU kept its original DAT
   name in game while the wizard showed the new one. Fixed to the same test.

The string block still exists in two copies, so these will keep drifting until Steps 2.3/2.4
merge them. That is the argument for the merge, not a substitute for it.

## A coverage gap the corpus cannot close

The round-trip harness reported **no hash movement** from the finding-5 fix, and that is honest
rather than reassuring: nothing in the corpus reaches the path. All 14 Empire Forge UT slots
carry a real cost (the wizard's `selectVanillaTech` fills one in), and the 24 KM slots have no
`castle_ut`/`imperial_ut` dict at all, so `_override_ut_costs` skips them. There is no
KM-converted `.civbuilder.json` in the corpus, which is exactly the shape that produced the bug.

`tests/test_ut_cost_override.py` covers the rule directly with stand-in DAT/tech objects — fast,
DAT-free, and verified to fail (4 checks) with the old unconditional writer put back.

Widening `digest()` also turned up a blind spot in the widening itself: `tech.research_time` and
`research_locations[*].research_time` are different fields, `_override_ut_costs` writes the
former, and only the latter was hashed — so a UT time change was invisible to the harness that
was supposed to be watching for it. Both are hashed now, and the baseline was retaken.

## Finding 6 — the from-scratch UU path, deleted 2026-09-08

`_append_unique_units` → `_append_one_unit` → `_apply_uu_stats` → `_apply_unit_costs`, plus
`_append_elite_upgrade_tech`: 136 lines reachable only from a branch that was always false.

It was removed rather than kept as `second_uu` scaffolding, because
**`km_custom_uu.append_km_custom_uu` already is that machinery and is strictly more complete.**
Both append brand-new units to every civ's array and bake stats into the target civ only, but
the live one also creates the make-avail and elite-upgrade techs (the dead path's caller had to
bolt `_append_elite_upgrade_tech` on separately), derives its four string ids with the
`name_sid + 100000` arithmetic CLAUDE.md quirk 8 calls load-bearing, and handles Castle/Krepost
train locations and button placement. The dead path reads as an earlier draft of the same idea
that `km_custom_uu` superseded — `km_custom_uu` even carried a comment working around its button
convention, noting btn10 does not render correctly.

The risk in keeping it was not the 136 lines; it was that it is the first thing a search for
"how do I add a UU" finds, and it is the wrong answer. For `second_uu`, generalize
`append_km_custom_uu` to run twice with a second Castle button slot. A pointer to that now sits
on `civ_schema.to_draft`'s Phase-Two docstring.

Kept and untouched nearby, since they sit in the same region and are live: `_KM_CASTLE_UT_TECHS`,
`_KM_IMP_UT_TECHS`, `UU_SUBSTITUTION_TYPES`, `_MERCENARY_UU_SLOT` and `_setup_mercenary_uu_unit`.

**Judgment call on finding 1.** The guard treats any payload with a `format` key as current,
which means a genuinely old `civbuilder_v1` file whose UT effects really did use civ bonus ids no
longer gets them cleared. That is deliberate and consistent: `to_draft` already stamps
`_DRAFT_VER` for v1 and v2 files alike and passes their effect ids through unmapped, so every
Python door has always trusted them — the browser was the sole outlier, and it was destroying
data for the common case (all 7 saved files in the repo) to hedge against a rare one. No
v1→v2 effect-id remapper exists anywhere, so the wipe was not repairing those files either.
