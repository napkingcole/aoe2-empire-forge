"""
Guard against writing dead resource ids from the bonus catalog.

EC_RESOURCE addresses ~284 named player attributes, but a chunk of that table
is inert — the AoE2DE UGC guide documents 198/199/200 as "Unused Resource".
Writing one costs nothing at build time and fails silently at play time, which
is how bonuses 132, 238 and 240 shipped as no-ops.

Worse, all six of our "resources last longer" bonuses pair a productivity
multiplier with a compensating work-rate *penalty*. If the multiplier lands on
a dead id, the penalty still applies and the bonus is net harmful — the player
gathers slower for nothing. So a dead id here is not a missing feature, it is a
downgrade.

This test is dependency-free by design (no DAT load): it compares the catalog
against llm/vanilla_resource_writes.json, a snapshot of every resource id some
shipping vanilla effect writes. Regenerate that snapshot after a game update
with scripts/probe_resource_attrs.py.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# EC_RESOURCE (1) and EC_RESOURCE_MULTIPLY (6), plus TEAM/ENEMY/NEUTRAL/GAIA
# scoped variants at +10/+20/+30/+40.
RESOURCE_EC_TYPES = frozenset({b + o for b in (1, 6) for o in (0, 10, 20, 30, 40)})

# Ids we write that no vanilla effect writes, but which the UGC guide documents
# as real. Each needs an entry saying why it is allowed to be here.
ALLOWED_UNATTESTED = {
    195: "Construction Rate Modifier — documented, Spanish default 1.3 matches "
         "our bonus 127 exactly. Vanilla sets it as a civ starting resource "
         "rather than through a tech effect, so it never appears in the scan.",
    253: "Trade Stone Percent — documented, default 0. Used by bonus 326 "
         "(Trade yields stone). No vanilla civ has the bonus, hence no writer.",
}


def _fail(msg):
    print(f"  FAIL {msg}")
    return 1


def _ok(msg):
    print(f"  ok   {msg}")
    return 0


def main() -> int:
    errors = 0

    snap_path = ROOT / "llm" / "vanilla_resource_writes.json"
    if not snap_path.exists():
        return _fail(f"missing snapshot {snap_path.name}; "
                     "regenerate with scripts/probe_resource_attrs.py")
    attested = set(json.loads(snap_path.read_text())["vanilla_written"])

    names = json.loads((ROOT / "llm" / "resource_attrs.json").read_text())
    raw = json.loads((ROOT / "bonus_catalog_raw.json").read_text())
    bonus_names = json.loads((ROOT / "bonus_names.json").read_text())

    print("=== Catalog resource ids are attested in vanilla ===")

    # (bonus_id, is_team, resource_id)
    writes: list[tuple[str, bool, int]] = []
    for bid, groups in raw["ec_list"].items():
        for group in groups:
            for ec in group["ecs"]:
                if ec["type"] in RESOURCE_EC_TYPES:
                    writes.append((bid, False, ec["A"]))
    for bid, ecs in raw.get("team_ec_list", {}).items():
        for ec in ecs:
            if ec["type"] in RESOURCE_EC_TYPES:
                writes.append((bid, True, ec["A"]))

    if not writes:
        errors += _fail("found no resource writes at all — catalog failed to parse?")
    else:
        errors += _ok(f"{len(writes)} resource writes found across the catalog")

    bad = []
    for bid, is_team, rid in writes:
        if rid in attested or rid in ALLOWED_UNATTESTED:
            continue
        label = bonus_names.get(bid, "?") if not is_team else f"team bonus {bid}"
        bad.append((bid, rid, names.get(str(rid), f"<unnamed {rid}>"), label))

    if bad:
        for bid, rid, rname, label in sorted(set(bad)):
            errors += _fail(
                f"bonus {bid} writes resource {rid} ({rname}) — no vanilla "
                f"effect writes it, so this is likely inert.\n"
                f"       bonus: {label}\n"
                f"       If the id is real, add it to ALLOWED_UNATTESTED with a reason."
            )
    else:
        errors += _ok("every resource id written by the catalog is attested "
                      f"({len(ALLOWED_UNATTESTED)} documented exceptions allowed)")

    print("\n=== Allowlist is current ===")
    stale = [rid for rid in ALLOWED_UNATTESTED if rid in attested]
    if stale:
        for rid in stale:
            errors += _fail(f"resource {rid} is now attested in vanilla — "
                            "drop it from ALLOWED_UNATTESTED")
    else:
        errors += _ok("no allowlist entry has become redundant")

    unused = [rid for rid in ALLOWED_UNATTESTED
              if not any(w[2] == rid for w in writes)]
    if unused:
        for rid in unused:
            errors += _fail(f"resource {rid} is allowlisted but no bonus writes "
                            "it — drop it from ALLOWED_UNATTESTED")
    else:
        errors += _ok("every allowlist entry is still in use")

    print()
    if errors:
        print(f"{errors} check(s) failed.")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
