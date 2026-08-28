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

## Notes

- Neither test touches the DAT, so both run in about a second.
- `test_civtechtrees.py` prints a `note` line for three known-dead entries in
  `_OPT_IN_UNIT_NODE_SOURCES` (1133, 1371, 1302). Those are reported rather than
  asserted — see the comment there for why they never resolve.
- Tech ids and unit ids share a namespace in these files (13 is Heavy Plow *and*
  Fishing Ship; 279 is Stone Shaft Mining *and* Scorpion), so anything matching
  on node id must also filter on `Use Type` / `use_type`. Both tests do.
