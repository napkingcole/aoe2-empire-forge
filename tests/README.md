# Tests

```
./tests/run_all.sh
```

Dependency-free on purpose: plain scripts, no pytest, no `node_modules`. The
Python side needs the project venv (for `genieutils`); the runner picks it up
automatically. Adding a test means dropping a file in here and adding a `run`
line to `run_all.sh`.

## Why these exist

The expensive way to find a bug in this project is to package a mod, move it to
a Windows box, launch AoE2, start a game and look. These cover the parts that
can be checked without any of that — the tech tree the wizard *draws* and the
tech tree the game *ships*, both of which are pure data transforms.

They earn their keep by sweeping **every civ against every option combination**.
Almost every bug they have caught was a single civ out of 54 behaving unlike the
other 53, which is exactly what spot-checking misses:

- `POLES` ships no Mill column in either data set — the Folwark replaced it — so
  switching a Poles-slot civ back to the standard camps dropped Horse Collar,
  Heavy Plow and Crop Rotation on the floor.
- `BURGUNDIANS` put their fishing techs in a column of their own, shifting the
  whole Dock one column right, so the Cannon Galleon wraps to column 1 instead
  of sitting in column 6 like everyone else.
- `DRAVIDIANS` park the Thirisadai in the cell the siege-ship variant wants.
- Folding a regional column back rebuilt the camps from an empty source, blanking
  their techs on every layout that was already using the standard camps.

The other cheap-to-check surface is the **civ_def format split**. Two shapes of
civ_def reach `apply_civ` — the wizard's dicts and the older KM lists — and the
accessors in `civ_appender` are the entire compatibility layer between them. A
reader written against one shape works fine until someone builds from the other,
which is a release boundary, not a code path you stumble into locally.

## What each file covers

**`test_editor_layout.js`** — loads `static/aoe2techtree/js/main.js` into Node
with the browser globals stubbed, then calls its transforms directly.

- `_applyBuildingVariantLayout`: Settlement / Folwark / Mule Cart against the
  standard Mill, Lumber Camp and Mining Camp. Folwark + Mule Cart may be active
  together (they replace different camps); the Settlement takes all three and so
  evicts both. Sweeps 54 layouts x 5 combinations.
- `_applySiegeShipLayout`: the Dock's siege ship, which belongs to the wizard's
  picker rather than to the tree. Sweeps 54 layouts x 5 ship choices.
- Click semantics: eviction, coexistence, locked nodes, hint text.

The core invariant in both sweeps: **no node is lost, duplicated, or left
pointing at a column that disagrees about owning it**, and every item in
`units_techs` has exactly one grid cell.

**`test_civtechtrees.py`** — runs `build_civ._apply_regional_camp_swaps` over all
59 files in `CivTechTrees/` x 5 combinations. Same invariant, plus: every
building that ends up owning a tech has to actually exist as a node in the file.

**`test_civ_def_formats.py`** — the format-agnostic accessors in `civ_appender`
(`_tree_unit_ids`, `get_civ_bonuses`, `get_team_bonuses`, `get_ut_entries`,
`get_km_uu_index`), over both civ_def shapes.

- Writes one civ twice, wizard and KM, and asserts all six accessors return the
  same thing. Anything that reads civ_def directly instead of through these will
  drift out from under this check, which is the point.
- Sweeps the 15 saved civ files committed to the repo (`*.civbuilder.json`,
  `my_civs/`, `civbuilder_civs/`) through every accessor, and asserts the corpus
  still contains both shapes — a fixture set that quietly becomes all-wizard
  stops testing the split.
- Malformed input degrades rather than crashes: absent / `null` / empty / wrongly
  typed `tree` and `bonuses`. These accessors sit on every read path and their
  input arrives from user uploads and hand edits.
- The derived "Unlock ..." cards (405-417) are recomputed from the tree on each
  read, never written back into civ_def — drop the unit and the card goes with
  it; a hand-ticked card survives and is not duplicated.

Both bugs it has caught so far were the same mistake at different sites:
`civ_def["tree"][0]` on a dict (`KeyError: 0`, shipped in v2.0.0-beta.1.3), and
`civ_def.get("bonuses", [])` returning `None` for a key present with a `null`
value, so the `len()` on the next line raised.

## Notes

- No test touches the DAT, so they all run in about a second.
- `test_civtechtrees.py` prints a `note` line for three known-dead entries in
  `_OPT_IN_UNIT_NODE_SOURCES` (1133, 1371, 1302). Those are reported rather than
  asserted — see the comment there for why they never resolve.
- Tech ids and unit ids share a namespace in these files (13 is Heavy Plow *and*
  Fishing Ship; 279 is Stone Shaft Mining *and* Scorpion), so anything matching
  on node id must also filter on `Use Type` / `use_type`. Both tests do.
