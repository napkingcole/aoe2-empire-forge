#!/usr/bin/env python3
"""The civ roster comes from the player's files, not a list we freeze.

`KM_TECHTREE_ORDER` was a hardcoded 59-name snapshot, and every DLC made it
wronger.  Viking Sagas (2026-09-22) took the game to 63 civs: Saxons,
Varangians and Danes resolved to index `None`, and a civ replacing one of them
wrote its name to the `10271` fallback — **which is Britons**.

`civilizations.json`, shipped beside the player's DAT, already carries
everything we hardcoded: `internal_name`, `tech_tree_name` (the CivTechTrees
filename) and `name_string_id` outright — so even the `10271 + index`
arithmetic becomes a lookup.  Reading it is what lets the app absorb a DLC the
day it lands, which is the point of reading live files rather than shipping a
copy of them.

**Key the lookup on the SLOT, never the name.**  The DAT and civilizations.json
disagree on several names — DAT `Mayan` vs `Mayans`, `British` vs `Britons`,
`French` vs `Franks` — but entry N of civilizations.json *is* DAT slot N.

That naming gap was already causing a silent bug: `_DAT_TO_TECHTREE_ID` mapped
Mayan → `MAYA` while the shipped file is **MAYANS.json**, and the per-civ
tech-tree patch is guarded by `if per_civ_path.exists()`.  Replacing the Mayans
quietly shipped an unpatched tech tree, with no warning anywhere.

Runs without the game DAT — the bundled civilizations.json is enough.

    venv/bin/python tests/test_civ_roster.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_civ import (civ_roster, civ_slot_info, civ_name_sid,      # noqa: E402
                       _canonical_techtree_id, _civ_techtree_index,
                       KM_TECHTREE_ORDER)

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


print("=== the roster loads from civilizations.json ===")
roster = civ_roster()
bundled = json.loads((ROOT / "civilizations.json").read_text())["civilization_list"]
check("one entry per civ slot", len(roster) == len(bundled),
      f"{len(roster)} vs {len(bundled)}")
check("slot 0 is Gaia", roster[0]["name"] == "Gaia", roster[0])
check("slot 1 is Britons with sid 10271",
      roster[1]["name"] == "Britons" and roster[1]["name_sid"] == 10271, roster[1])
check("every entry carries a techtree id",
      all(e["techtree_id"] for e in roster[1:]),
      [e for e in roster[1:] if not e["techtree_id"]][:3])

print("\n=== slot beats name, because the two files disagree ===")
# The DAT calls these one thing and civilizations.json another.  Slot lookup has
# to win, or the filename and the name string both land on the wrong civ.
MISMATCHED = [(1, "British", "BRITONS"), (2, "French", "FRANKS"),
              (7, "Byzantine", "BYZANTINES"), (16, "Mayan", "MAYANS")]
for slot, dat_name, expected in MISMATCHED:
    got = _canonical_techtree_id(dat_name, None, slot=slot)
    check(f"slot {slot}: DAT {dat_name!r} -> {expected}", got == expected, f"got {got!r}")

check("Mayan resolves to MAYANS, the file that actually ships",
      _canonical_techtree_id("Mayan", None, slot=16) == "MAYANS",
      "MAYA.json does not exist; the per-civ tech tree patch is guarded by "
      ".exists(), so this silently shipped an unpatched tree")
check("...and the file it names is really there",
      (ROOT / "CivTechTrees" / "MAYANS.json").exists())
check("...while the name the frozen table produced is not",
      not (ROOT / "CivTechTrees" / "MAYA.json").exists())

print("\n=== no regression for the civs that already worked ===")
# Every civ in the frozen list must still get the sid it always got.
for i, name in enumerate(KM_TECHTREE_ORDER):
    slot = i + 1                      # the list omits Gaia
    want = 10271 + i
    got = civ_name_sid(name, None, slot=slot)
    if got != want:
        check(f"{name} keeps sid {want}", False, f"got {got}")
        break
else:
    check(f"all {len(KM_TECHTREE_ORDER)} frozen-list civs keep their sid", True)

print("\n=== it degrades instead of breaking ===")
missing = civ_roster("/nonexistent/path/empires2_x2_p1.dat")
check("an unreadable DAT path still yields a roster", len(missing) > 50,
      f"{len(missing)} entries")
check("a slot past the end returns None rather than raising",
      civ_slot_info(9999) is None)
check("an unknown civ name returns None rather than guessing",
      civ_name_sid("Definitely Not A Civ") is None)
check("the frozen list is still reachable as the last-resort fallback",
      _civ_techtree_index("Britons") == 0)

print("\n=== and it absorbs civs the frozen list never had ===")
# Only meaningful against an updated install; skips cleanly otherwise.
dlc = ROOT / "9-22-26 update" / "empires2_x2_p1.dat"
if dlc.exists():
    r = civ_roster(str(dlc))
    check("the DLC roster is longer than the frozen list",
          len(r) - 1 > len(KM_TECHTREE_ORDER),
          f"{len(r)-1} civs vs {len(KM_TECHTREE_ORDER)} names")
    for slot, name, sid in ((60, "Saxons", 10330), (61, "Varangians", 10331),
                            (62, "Danes", 10332)):
        got = civ_name_sid(name, str(dlc), slot=slot)
        check(f"{name} (slot {slot}) gets its own sid {sid}, not Britons' 10271",
              got == sid, f"got {got}")
else:
    print("  skip  no updated DAT present (game data is gitignored)")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
