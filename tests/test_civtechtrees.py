"""In-game tech tree (F2 viewer) checks for the regional resource buildings.

build_civ._apply_regional_camp_swaps reshapes the replaced civ slot's
CivTechTrees/<CIV>.json so the viewer matches the civ actually being played:
it injects the Settlement / Folwark / Mule Cart node when the file lacks one,
repoints the camps' techs onto it, and folds everything back when the custom
civ uses the standard camps instead.

Unlike the wizard's tree JSONs these files are flat and self-positioning (no
grid coordinates — the game lays out from Building ID + Age ID), which is why
injecting a node works at all.

    venv/bin/python tests/test_civtechtrees.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_civ import (  # noqa: E402
    _apply_regional_camp_swaps, _CAMP_TECH_HOME, _REGIONAL_CAMP_SWAPS,
    _FARM_NODE_ID, _OPT_IN_UNIT_NODE_SOURCES,
)

CIVDIR = ROOT / "CivTechTrees"
CAMPS = {68, 562, 584}          # Mill, Lumber Camp, Mining Camp
SETTLEMENT, FOLWARK, MULE = 2556, 1734, 1808
BASE = {50, 12, 87}             # a few unrelated buildings every civ has
failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


def load(name):
    with open(CIVDIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def parents(data):
    """tech Node ID → Building ID, for the ten camp techs only."""
    return {n["Node ID"]: n.get("Building ID")
            for n in data.get("civ_techs_units", [])
            if n.get("Use Type") == "Tech" and n.get("Node ID") in _CAMP_TECH_HOME}


def bldg(data, node_id):
    return next((n for n in data.get("civ_techs_buildings", [])
                 if n.get("Node ID") == node_id and n.get("Use Type") == "Building"), None)


def expected_parent(nid, ids):
    """Where camp tech `nid` should end up given the selected building ids."""
    home = _CAMP_TECH_HOME[nid]
    for bid, spec in _REGIONAL_CAMP_SWAPS.items():
        if bid in ids and home in spec["replaces"]:
            return bid
    return home


def assert_placement(data, ids, label):
    p = parents(data)
    wrong = {nid: got for nid, got in p.items() if got != expected_parent(nid, ids)}
    check(f"{label}: every camp tech on the right building", not wrong, str(wrong))
    for bid in _REGIONAL_CAMP_SWAPS:
        node = bldg(data, bid)
        if bid in ids:
            check(f"{label}: {_REGIONAL_CAMP_SWAPS[bid]['name']} present and available",
                  node is not None and node["Node Status"] == "ResearchedCompleted")
        elif node is not None:
            check(f"{label}: {_REGIONAL_CAMP_SWAPS[bid]['name']} hidden",
                  node["Node Status"] == "NotAvailable")


print("\n=== Franks slot, each regional building in turn ===")
for bid, spec in _REGIONAL_CAMP_SWAPS.items():
    data = load("FRANKS")
    ids = BASE | {bid} | (CAMPS - set(spec["replaces"]))
    n = len(data["civ_techs_buildings"])
    _apply_regional_camp_swaps(data, ids, CIVDIR)
    check(f"{spec['name']}: node injected", len(data["civ_techs_buildings"]) == n + 1)
    assert_placement(data, ids, spec["name"])

print("\n=== Franks slot, Folwark + Mule Cart together (they don't overlap) ===")
data = load("FRANKS")
ids = BASE | {FOLWARK, MULE}
_apply_regional_camp_swaps(data, ids, CIVDIR)
assert_placement(data, ids, "Folwark+Mule")
check("Mill techs on the Folwark", parents(data)[14] == FOLWARK)
check("Lumber techs on the Mule Cart", parents(data)[202] == MULE)
check("Mining techs on the Mule Cart", parents(data)[55] == MULE)
check("Farm hangs off the Folwark", bldg(data, _FARM_NODE_ID)["Building ID"] == FOLWARK)

print("\n=== Farm placement follows whoever owns the Mill ===")
for ids, want, label in (
    (BASE | CAMPS, 68, "standard camps → Mill"),
    (BASE | {SETTLEMENT}, 50, "Settlement → its own root"),
    (BASE | {FOLWARK}, FOLWARK, "Folwark → the Folwark"),
    (BASE | {MULE, 68}, 68, "Mule Cart only → still the Mill"),
):
    data = load("FRANKS")
    _apply_regional_camp_swaps(data, ids, CIVDIR)
    check(label, bldg(data, _FARM_NODE_ID)["Building ID"] == want,
          str(bldg(data, _FARM_NODE_ID)["Building ID"]))

print("\n=== Franks slot, nothing selected (must be untouched) ===")
data = load("FRANKS")
raw = json.dumps(data, sort_keys=True)
changed = _apply_regional_camp_swaps(data, BASE | CAMPS, CIVDIR)
check("no-op", changed == 0 and json.dumps(data, sort_keys=True) == raw)

print("\n=== Native slots keep their own building ===")
for civ, bid in (("MAPUCHE", SETTLEMENT), ("POLES", FOLWARK), ("ARMENIANS", MULE)):
    data = load(civ)
    spec = _REGIONAL_CAMP_SWAPS[bid]
    ids = BASE | {bid} | (CAMPS - set(spec["replaces"]))
    _apply_regional_camp_swaps(data, ids, CIVDIR)
    assert_placement(data, ids, f"{civ} keeps {spec['name']}")

print("\n=== Native slots reverted to standard camps ===")
for civ, bid in (("MAPUCHE", SETTLEMENT), ("POLES", FOLWARK), ("ARMENIANS", MULE)):
    data = load(civ)
    before = {(n.get("Node ID"), n.get("Building ID")) for n in data["civ_techs_units"]}
    _apply_regional_camp_swaps(data, BASE | CAMPS, CIVDIR)
    assert_placement(data, BASE | CAMPS, f"{civ} reverted")
    lost = [nid for nid, b in before
            if b == bid and not any(n.get("Node ID") == nid for n in data["civ_techs_units"])]
    check(f"{civ}: no unit disappeared from the viewer", not lost, str(lost))

print("\n=== Every civ file x every selection combination ===")
combos = [
    frozenset(CAMPS),
    frozenset({SETTLEMENT}),
    frozenset({FOLWARK, 562, 584}),
    frozenset({MULE, 68}),
    frozenset({FOLWARK, MULE}),
]
bad = []
for path in sorted(CIVDIR.glob("*.json")):
    with open(path, encoding="utf-8") as f:
        baseline = sorted(parents(json.load(f)))
    for combo in combos:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ids = BASE | set(combo)
        try:
            _apply_regional_camp_swaps(data, ids, CIVDIR)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{path.name} {sorted(combo)}: {type(e).__name__} {e}")
            continue
        p = parents(data)
        if sorted(p) != baseline:
            bad.append(f"{path.name} {sorted(combo)}: camp techs {baseline} → {sorted(p)}")
        for nid, got in p.items():
            if got != expected_parent(nid, ids):
                bad.append(f"{path.name} {sorted(combo)}: tech {nid} on {got}")
        for bid in _REGIONAL_CAMP_SWAPS:
            node = bldg(data, bid)
            if bid in ids and node is None:
                bad.append(f"{path.name} {sorted(combo)}: no {bid} node")
            if bid not in ids and node is not None and node["Node Status"] != "NotAvailable":
                bad.append(f"{path.name} {sorted(combo)}: {bid} left visible")
        # Every building that ends up owning a tech must actually exist as a node.
        for nid, host in p.items():
            if bldg(data, host) is None:
                bad.append(f"{path.name} {sorted(combo)}: tech {nid} on absent node {host}")
n = len(list(CIVDIR.glob("*.json")))
check(f"{n} civ files x {len(combos)} combinations", not bad, "; ".join(bad[:6]))

print("\n=== Regional unit node sources resolve ===")
bad = []
for uid, sources in _OPT_IN_UNIT_NODE_SOURCES.items():
    found = False
    for fname in sources:
        p = CIVDIR / fname
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            src = json.load(f)
        for key in ("civ_techs_units", "civ_techs_buildings"):
            if any(n.get("Node ID") == uid and n.get("Node Type") == "RegionalUnit"
                   for n in src.get(key, [])):
                found = True
    if not found:
        bad.append(f"{uid} ({', '.join(sources)})")
# Pre-existing gap, reported not asserted: these entries never match because the
# node is a UniqueUnit (Dragon Ship 1302) or has no node of its own at all
# (1133 / 1371 — the elite upgrade is folded into the base node's Link ID).
print("  note  unresolved entries (pre-existing): " + ("; ".join(bad) or "none"))
check("every resolvable opt-in unit still resolves",
      all(int(b.split()[0]) in {1133, 1371, 1302} for b in bad), "; ".join(bad))

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
