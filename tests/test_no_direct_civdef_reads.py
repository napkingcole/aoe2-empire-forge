"""Lint: nothing reads the shape-divergent civ_def keys except the accessors.

`tree` and `bonuses` are the two keys whose *shape* differs between the KM
format and Empire Forge's, so they are the two that a reader can get wrong:

    KM      tree = [units, buildings, techs]
            bonuses = [civ, [uu_idx], castle_ut, imperial_ut, team]
    schema  tree = {"units": [...], ...}
            bonuses = [{"id": X, "multiplier": Y}, ...]

`apply_civ` receives both shapes (see tests/test_civ_def_formats.py), so any
code that indexes these keys directly is correct for at most one of them.  The
accessors in civ_appender exist to be the single place that knows the
difference; this test enforces that they stay the *only* place.

Both bugs found so far were direct reads: `_tree_unit_ids` doing `tree[0]` on a
dict (v2.0.0-beta.1.3), and `build_all.py` reading `bonuses[1][0]` for the UU
index in a function that line 460 had started feeding schema-shaped civ_defs.

The allowlist is keyed on the enclosing **function**, not the file: the
accessors live in civ_appender.py alongside plenty of other code, and a file
allowlist would have let the original `tree[0]` regression straight through.

Known hole: this matches on the literal key in a subscript or `.get()`, so
aliasing (`d = civ_def; d["tree"]`) evades it.  It is a lint, not a proof.

    venv/bin/python tests/test_no_direct_civdef_reads.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The keys whose shape differs between formats.  Keys that exist in only one
# format (castle_ut.name, unique_unit.overrides, ...) are not listed: reading
# those directly is fine, because there is no second shape to get wrong.
DIVERGENT = {"tree", "bonuses"}

# Functions permitted to know about both shapes.  Everything here either *is*
# an accessor, or is a converter whose whole job is to translate one shape into
# the other.  Adding a name to this list widens the compatibility layer — do it
# deliberately, not to silence a failure.
ALLOWED = {
    # civ_appender.py — the accessors themselves
    "_tree_unit_ids", "_tree_building_ids", "get_civ_bonuses",
    "get_team_bonuses", "get_ut_entries", "get_km_uu_index",
    # readers that legitimately branch on shape
    "_apply_tree_wiring",           # civ_appender.py
    "_tree_sets",                   # build_civ.py
    # converters: shape translation is the point
    "_draft_to_civ_def",            # wizard_build.py  draft  -> KM civ_def
    "to_draft",                     # civ_schema.py    schema -> draft
    "from_draft",                   # civ_schema.py    draft  -> schema
    "_km_to_draft",                 # app.py           KM     -> draft
    "is_km_format",                 # civ_schema.py    format detection
}

# Files that are not part of the build pipeline.
SKIP_FILES = {"generate_ec_list.py"}

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


class Scan(ast.NodeVisitor):
    """Collect (file, line, function, key) for every direct read of a
    divergent key, tracking the innermost enclosing function as it walks."""

    def __init__(self, filename):
        self.filename = filename
        self.stack = []
        self.hits = []

    def _enter(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _enter
    visit_AsyncFunctionDef = _enter

    def _record(self, node, key):
        fn = self.stack[-1] if self.stack else "<module>"
        if fn not in ALLOWED:
            self.hits.append((self.filename, node.lineno, fn, key))

    def visit_Subscript(self, node):
        # civ_def["tree"] / data["bonuses"]
        if isinstance(node.slice, ast.Constant) and node.slice.value in DIVERGENT:
            self._record(node, node.slice.value)
        self.generic_visit(node)

    def visit_Call(self, node):
        # civ_def.get("tree") / civ_def.get("bonuses", default)
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in DIVERGENT):
            self._record(node, node.args[0].value)
        self.generic_visit(node)


print("=== Direct reads of shape-divergent civ_def keys ===")

sources = sorted(p for p in ROOT.glob("*.py") if p.name not in SKIP_FILES)
check("found source files to scan", sources, "no .py files at repo root")

hits = []
for path in sources:
    scan = Scan(path.name)
    scan.visit(ast.parse(path.read_text(encoding="utf-8")))
    hits.extend(scan.hits)

check(f"{len(sources)} files scanned, no unaudited direct reads",
      not hits,
      "; ".join(f"{f}:{ln} in {fn}() reads {k!r}" for f, ln, fn, k in hits[:8]))

if hits:
    print("\n  Route these through civ_appender's accessors — get_civ_bonuses,")
    print("  get_team_bonuses, get_ut_entries, get_km_uu_index, _tree_unit_ids —")
    print("  or, if the function genuinely needs to branch on shape, add it to")
    print("  ALLOWED in this file with a comment saying why.")
    for f, ln, fn, k in hits:
        print(f"    {f}:{ln}  {fn}()  reads {k!r}")

# An allowlist entry that no longer matches anything is stale: the function was
# renamed or deleted, and the next reader to take that name inherits a free pass.
print("\n=== Allowlist is current ===")
defined = set()
for path in sources:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
stale = sorted(ALLOWED - defined)
check("every allowlisted function still exists", not stale,
      f"stale entries: {', '.join(stale)}")

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
