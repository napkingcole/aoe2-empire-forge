"""Format-agnostic civ_def accessors, over both civ_def formats.

apply_civ consumes two shapes of civ_def and is supposed to not care which:

    wizard  tree = {"units": [...], "buildings": [...], "techs": [...]}
            bonuses = [{"id": X, "multiplier": Y}, ...]
    KM      tree = [units, buildings, techs]
            bonuses = [civ, [uu_idx], castle_ut, imperial_ut, team]

Everything downstream reads through the accessors in civ_appender rather than
indexing civ_def itself, so those accessors are the whole compatibility layer.
A reader that handles only one shape is invisible until someone builds from
the other — which is how v2.0.0-beta.1.3 shipped a `_tree_unit_ids` that did
`tree[0]` on a dict and took down every build from a saved .civbuilder.json
with `KeyError: 0`.

The single-civ wizard path flattens the dict to a list before apply_civ ever
sees it (wizard_build._draft_to_civ_def), so it never noticed.  The multi-civ
upload path in app.py hands the saved JSON straight through, and that is the
format users actually keep on disk.  Hence this file.

    venv/bin/python tests/test_civ_def_formats.py
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from civ_appender import (  # noqa: E402
    _tree_unit_ids, get_civ_bonuses, get_team_bonuses, get_ut_entries,
    get_km_uu_index, _UNLOCK_UNIT_BONUSES,
)

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


def read_all(civ_def):
    """Every accessor, in one call.  Raising here is itself the failure."""
    return {
        "tree_units":  _tree_unit_ids(civ_def),
        "bonuses":     [list(e) for e in get_civ_bonuses(civ_def)],
        "team":        [list(e) for e in get_team_bonuses(civ_def)],
        "castle_ut":   [list(e) for e in get_ut_entries(civ_def, "castle_ut")],
        "imperial_ut": [list(e) for e in get_ut_entries(civ_def, "imperial_ut")],
        "km_uu":       get_km_uu_index(civ_def),
    }


# A unit whose presence in the tree derives an "Unlock ..." bonus, and one that
# derives nothing.  Pulled from the table rather than hardcoded so retiring a
# card can't leave this test asserting against an id that no longer unlocks.
UNLOCK_BID   = 405
UNLOCK_UNIT  = _UNLOCK_UNIT_BONUSES[UNLOCK_BID]["units"][0]
PLAIN_UNIT   = 74            # Militia — in no unlock spec
_ALL_UNLOCK_UNITS = {u for s in _UNLOCK_UNIT_BONUSES.values() for u in s["units"]}


# ── The same civ, written both ways ───────────────────────────────────────────
# Deliberately includes an unlock unit so the derived-bonus path runs on both
# sides: the derivation reads the tree, which is exactly where the formats differ.

WIZARD = {
    "format": "civbuilder_v1",
    "alias": "Format Test",
    "bonuses":      [{"id": 17, "multiplier": 2}, {"id": 39, "multiplier": 1}],
    "team_bonuses": [{"id": 3, "multiplier": 1}],
    "castle_ut":    {"effects": [{"id": 100, "multiplier": 1}]},
    "imperial_ut":  {"effects": [{"id": 200, "multiplier": 3}]},
    "unique_unit":  {"km_idx": 13},
    "tree": {
        "units":     [PLAIN_UNIT, 75, UNLOCK_UNIT],
        "buildings": [12, 70],
        "techs":     [22, 23],
    },
}

KM = {
    "alias": "Format Test",
    "bonuses": [
        [[17, 2], [39, 1]],     # [0] civ bonuses
        [13],                   # [1] KM unique unit index
        [[100, 1]],             # [2] castle UT
        [[200, 3]],             # [3] imperial UT
        [[3, 1]],               # [4] team bonuses
    ],
    "tree": [
        [PLAIN_UNIT, 75, UNLOCK_UNIT],
        [12, 70],
        [22, 23],
    ],
}


print("=== The same civ in both formats reads identically ===")
try:
    w, k = read_all(WIZARD), read_all(KM)
except Exception as exc:                                    # noqa: BLE001
    check("accessors run on both formats", False, f"{type(exc).__name__}: {exc}")
    w = k = None

if w is not None:
    for key in w:
        check(f"{key} agrees across formats", w[key] == k[key],
              f"wizard={w[key]!r} km={k[key]!r}")
    check(f"unlock bonus {UNLOCK_BID} derived from the tree, both formats",
          [UNLOCK_BID, 1] in w["bonuses"] and [UNLOCK_BID, 1] in k["bonuses"],
          f"wizard={w['bonuses']!r} km={k['bonuses']!r}")


# ── The exact beta.1.3 regression ─────────────────────────────────────────────
# get_civ_bonuses calls _tree_unit_ids unconditionally, before any unlock-unit
# matching, so the dict-tree crash did not need an unlock unit to fire.  Pin the
# no-unlock case too or a fixture that happens to contain one hides the bug.

print("\n=== Dict tree is read, not indexed ===")
for label, units in (("with an unlock unit", [PLAIN_UNIT, UNLOCK_UNIT]),
                     ("with no unlock units", [PLAIN_UNIT])):
    civ = {"bonuses": [{"id": 17, "multiplier": 1}],
           "tree": {"units": units, "buildings": [12], "techs": [22]}}
    try:
        got = read_all(civ)
        ok, extra = got["tree_units"] == set(units), ""
    except Exception as exc:                                # noqa: BLE001
        ok, extra = False, f"{type(exc).__name__}: {exc}"
    check(f"dict tree {label}", ok, extra)


# ── Real files on disk ────────────────────────────────────────────────────────
# The formats are not hypothetical: both are committed here.  Sweeping the real
# corpus catches a schema drift that a hand-written fixture would not.

print("\n=== Saved civ files sweep ===")
CORPUS = sorted(
    p for p in list(ROOT.glob("*.civbuilder.json"))
      + list((ROOT / "my_civs").glob("*.json"))
      + list((ROOT / "civbuilder_civs").glob("*.json"))
    if p.is_file()
)
check("corpus is non-empty", CORPUS, "no saved civ files found to sweep")

seen_shapes = set()
bad = []
for path in CORPUS:
    try:
        civ_def = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:                                # noqa: BLE001
        bad.append(f"{path.name}: unreadable — {type(exc).__name__}")
        continue
    tree = civ_def.get("tree")
    seen_shapes.add(type(tree).__name__)
    before = copy.deepcopy(civ_def)
    try:
        got = read_all(civ_def)
    except Exception as exc:                                # noqa: BLE001
        bad.append(f"{path.name}: {type(exc).__name__}: {exc}")
        continue
    # A civ with units in its tree must report them; an empty set here means the
    # accessor silently fell through its format branches, which is the failure
    # mode that reads as "no derived unlocks" instead of as an error.
    declared = set(tree.get("units", []) if isinstance(tree, dict)
                   else (tree[0] if isinstance(tree, list) and tree else []))
    if declared and got["tree_units"] != declared:
        bad.append(f"{path.name}: tree units {got['tree_units']} != {declared}")
    # Accessors are reads.  get_civ_bonuses appends derived unlocks to its own
    # return value; if that append lands in civ_def instead, the derivation goes
    # sticky and survives a tech-tree change it should have been recomputed from.
    if civ_def != before:
        bad.append(f"{path.name}: accessors mutated civ_def")

check(f"{len(CORPUS)} saved civ files x 6 accessors", not bad, "; ".join(bad[:6]))
check("corpus covers both tree shapes", {"dict", "list"} <= seen_shapes,
      f"only saw {sorted(seen_shapes)} — a format is no longer represented on disk")


# ── Degenerate input degrades, never crashes ──────────────────────────────────
# get_civ_bonuses is on every read path, and civ_defs arrive from user uploads
# and hand edits.  Its contract is to return something empty-ish for junk, not
# to take the build down with it.

print("\n=== Malformed civ_defs degrade quietly ===")
MALFORMED = {
    "empty dict":            {},
    "tree absent":           {"bonuses": [{"id": 17}]},
    "tree None":             {"tree": None},
    "tree empty dict":       {"tree": {}},
    "tree empty list":       {"tree": []},
    "tree dict, units None": {"tree": {"units": None}},
    "tree dict, no units":   {"tree": {"buildings": [12]}},
    "tree list, too short":  {"tree": [[74]]},
    "tree list of scalars":  {"tree": [74, 75, 76]},
    "tree wrong type":       {"tree": "nope"},
    "bonuses None":          {"bonuses": None, "tree": {"units": [74]}},
    "bonuses empty":         {"bonuses": [], "tree": {"units": [74]}},
    "bonus entry empty":     {"bonuses": [[], [17, 1]], "tree": {"units": [74]}},
    "km bonuses truncated":  {"bonuses": [[[17, 1]]], "tree": [[74], [], []]},
    "ut None":               {"castle_ut": None, "imperial_ut": None},
}
for label, civ_def in MALFORMED.items():
    try:
        read_all(civ_def)
        ok, extra = True, ""
    except Exception as exc:                                # noqa: BLE001
        ok, extra = False, f"{type(exc).__name__}: {exc}"
    check(label, ok, extra)


# ── Derivation stays derived ──────────────────────────────────────────────────
# The unlock cards are computed from the tree on every read rather than stored,
# so that swapping tech-tree templates can never strand a card the tree no
# longer justifies.  That only holds if the read leaves civ_def alone.

print("\n=== Derived unlocks are recomputed, not stored ===")
for label, civ_def in (("wizard", copy.deepcopy(WIZARD)), ("km", copy.deepcopy(KM))):
    first = get_civ_bonuses(civ_def)
    check(f"{label}: derived on first read", [UNLOCK_BID, 1] in [list(e) for e in first])

    # Drop the unlock unit; the card must go with it.
    if isinstance(civ_def["tree"], dict):
        civ_def["tree"]["units"] = [PLAIN_UNIT]
    else:
        civ_def["tree"][0] = [PLAIN_UNIT]
    after = [list(e) for e in get_civ_bonuses(civ_def)]
    check(f"{label}: dropped from the tree → card gone",
          not (_ALL_UNLOCK_UNITS and [UNLOCK_BID, 1] in after), f"still {after!r}")

    # A card the user ticked by hand is theirs to keep, unlock unit or not.
    ticked = copy.deepcopy(civ_def)
    if isinstance(ticked["bonuses"], list) and ticked["bonuses"] \
            and isinstance(ticked["bonuses"][0], dict):
        ticked["bonuses"].append({"id": UNLOCK_BID, "multiplier": 1})
    else:
        ticked["bonuses"][0].append([UNLOCK_BID, 1])
    got = [list(e) for e in get_civ_bonuses(ticked)]
    check(f"{label}: explicit card survives, exactly once",
          got.count([UNLOCK_BID, 1]) == 1, f"{got!r}")


print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
