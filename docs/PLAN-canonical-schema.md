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

| Entry point | Input | Shape at `apply_civ` |
|---|---|---|
| `app.py:1759` `/builder/build` | live draft from the browser | `_draft_to_civ_def` → **KM** |
| `app.py:543` `_run_build_job` | uploaded `.civbuilder.json` | **schema**, unconverted |
| `build_all.py:485` | `my_civs/*.json` | **KM** |
| `build_all.py:485` | a `.civbuilder.json` | `civ_schema.to_draft` → **draft** (dict-shaped) |

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
