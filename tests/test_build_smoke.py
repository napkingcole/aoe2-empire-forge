#!/usr/bin/env python3
"""Does a build actually complete?  DAT-gated, runs by default.

Everything else in tests/ is a pure data check — none of it builds a civ.  On
2026-09-02 that gap let a NameError reach the branch that broke *every* build
while the suite still reported all green, perfectly honestly: it was checking
things that were genuinely fine.  A later `.strip()` crash on any civ with a
blank unique-unit name got through the same hole.

So this runs one civ end to end — apply_civ, the stat overrides, string
building, CivTechTrees patching, zip packaging — and asserts the result looks
like a mod.  ~28s, of which ~17s is loading the DAT.

Scope, deliberately:
  * ONE civ, ONE route.  "Do the two routes agree?" is a different question and
    belongs to test_route_roundtrip.py, which sweeps the whole saved corpus.
  * The civ is synthesised here rather than read from my_civs/, so the test does
    not depend on user files that come and go, and so it can deliberately
    exercise the paths that have broken before.
  * Assertions read the produced zip and its strings file.  Re-parsing the built
    DAT would double the runtime for little extra signal.

    venv/bin/python tests/test_build_smoke.py
"""
import collections
import contextlib
import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat                      # noqa: E402
from civ_schema import to_draft                           # noqa: E402
from wizard_build import build_wizard_mod                 # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


# ── The civ under test ───────────────────────────────────────────────────────
# Chosen to walk the machinery that has actually broken, not to be minimal:
#   bonus 139  catalog techs           -> _allocate_tech
#   bonus 404  createCivBonus handler  -> _add_auto_fire_tech
#   bonus 105  ec_list + structural    -> _apply_early_eco_shims / _add_alt_prereq
#   bonus 282  downstream re-pointing  -> _add_alt_prereq on tech 786
#   UU         cost override adding a resource the unit does not already charge
#              (the 3-slot case), and a null name/description (the .strip() case)
#   castle UT  Anarchy, so the UU gains a second train location
#   tree       pruned, so the disable sweep and the protected set both run
#   monk_skin  set, so _copy_monk_skin runs
#   1021       a unique building we cannot grant, which must be dropped
CIV = {
    "format": "empireforge_v2",
    "schema_version": 2,
    "alias": "Smoke Test Civ",
    "tagline": "tests/test_build_smoke.py",
    "description": "",
    "architecture": 1,
    "language": 4,
    "wonder_model": -1,
    "castle_model": -1,
    "emblem": "",
    "monk_skin": 5,
    "hero_unit": None,
    "second_uu": None,
    "unique_unit": {
        "km_idx": 4, "vanilla_id": None,
        "name": None, "description": None,          # must not crash on null
        "overrides": {"cost_wood": 65, "cost_gold": 30,
                      "train_base": 60, "train_elite": 60},
        "advanced_flags": {},
    },
    "bonuses": [{"id": i, "multiplier": 1} for i in (139, 404, 105, 282)],
    "team_bonuses": [{"id": 30, "multiplier": 1}],
    "castle_ut": {
        "mode": "custom", "vanilla_id": None, "name": "Smoke Anarchy",
        "description": "Unique unit can be created at the Barracks.",
        "cost": {"food": 300, "wood": 0, "stone": 0, "gold": 200}, "time": 40,
        "effects": [{"id": 12, "multiplier": 1}],
    },
    "imperial_ut": {
        "mode": "custom", "vanilla_id": None, "name": "Smoke Imperial",
        "description": "Placeholder.",
        "cost": {"food": 500, "wood": 0, "stone": 0, "gold": 300}, "time": 60,
        "effects": [{"id": 35, "multiplier": 1}],
    },
    "unit_overrides": [], "button_moves": [], "free_techs": [],
}


def _tree():
    """Full union tree minus the regional halves, then pruned a little.

    Mirrors what the wizard seeds a blank civ with, so the disable sweep sees a
    realistic input rather than a hand-picked list that might dodge it.
    """
    import json
    data = json.loads((ROOT / "static/aoe2techtree/data/data.json").read_text())
    units, bldgs, techs = set(), set(), set()
    for cv in data["civs"].values():
        units.update(cv.get("Unit", []))
        bldgs.update(cv.get("Building", []))
        techs.update(cv.get("Tech", []))
    main = (ROOT / "static/aoe2techtree/js/main.js").read_text()
    regional = set(map(int, re.search(
        r"const _REGIONAL_UNIT_IDS = new Set\(\[([^\]]*)\]\)",
        main).group(1).replace(" ", "").split(",")))
    units -= regional
    units -= {125}                    # Monk: make the sweep disable something
    techs -= {55, 278}                # Gold/Stone Mining: ditto

    # Drop the regional resource buildings (Settlement / Folwark / Mule Cart),
    # matching what _filterFullTree seeds a real blank civ with.
    #
    # This is load-bearing, not tidiness.  The 2026-09-02 NameError lived in the
    # loop over exactly those three, behind a short-circuiting `and` that only
    # evaluated when the building was ABSENT from tree[1].  A tree carrying all
    # three never reaches it — so a smoke civ built from the raw union passes
    # happily with the bug reintroduced.  Verified both ways.
    swaps = set(map(int, re.findall(
        r"\bid:\s*(\d+)",
        re.search(r"const _REGIONAL_BUILDING_SWAPS = \[(.*?)\n\];", main, re.S).group(1))))
    bldgs -= swaps

    # The civ-unique buildings (Feitoria and friends) are deliberately LEFT in —
    # that is the shape of a draft saved before _filterFullTree learned to strip
    # them, and the build must drop them rather than light them up in the viewer.
    return {"units": sorted(units), "buildings": sorted(bldgs), "techs": sorted(techs)}


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found — run build_civ.py once to set one up")
    sys.exit(0)

CIV["tree"] = _tree()
print(f"=== one civ, end to end, DAT {Path(dat_path).name} ===")

log = io.StringIO()
try:
    with contextlib.redirect_stdout(log):
        blob = build_wizard_mod(to_draft(CIV), str(dat_path), "bohemians")
except Exception as exc:                                   # noqa: BLE001
    import traceback
    print("  FAIL build raised — the pipeline is broken, not just drifted")
    print("       " + "".join(traceback.format_exception_only(type(exc), exc)).strip())
    print(log.getvalue()[-2000:])
    sys.exit(1)

check("build completed without raising", True)

# ── The zip is shaped like a mod ─────────────────────────────────────────────
outer = zipfile.ZipFile(io.BytesIO(blob))
inner = outer.namelist()
data_zip = next((n for n in inner if n.endswith("-data.zip")), None)
ui_zip = next((n for n in inner if n.endswith("-ui.zip")), None)
check("contains a data zip and a ui zip", data_zip and ui_zip, str(inner))

dz = zipfile.ZipFile(io.BytesIO(outer.read(data_zip)))
dat_entry = next((n for n in dz.namelist() if n.endswith(".dat")), None)
check("data zip carries a DAT", dat_entry is not None)
check("DAT is a plausible size (>5 MB)",
      dat_entry and dz.getinfo(dat_entry).file_size > 5_000_000,
      f"{dz.getinfo(dat_entry).file_size if dat_entry else 0} bytes")
check("data zip carries the patched CivTechTrees",
      any("CivTechTrees" in n and n.endswith(".json") for n in dz.namelist()))

# ── The strings file ─────────────────────────────────────────────────────────
uz = zipfile.ZipFile(io.BytesIO(outer.read(ui_zip)))
sp = next((n for n in uz.namelist()
           if n.endswith("key-value-modded-strings-utf8.txt") and "/en/" in n), None)
check("ui zip carries English strings", sp is not None)

rows = []
for line in uz.read(sp).decode("utf-8").splitlines():
    m = re.match(r'^(\d+)\s+"(.*)"$', line.strip())
    if m:
        rows.append((int(m.group(1)), m.group(2)))
check("strings file is populated", len(rows) > 50, f"{len(rows)} lines")

# One id must not carry two different definitions — which of them the engine
# picks is undocumented, so it silently decides what a player sees.
dupes = {sid for sid, n in collections.Counter(s for s, _ in rows).items() if n > 1}
check("no string id is written twice", not dupes, f"duplicated: {sorted(dupes)}")

# The unique unit asked for a resource it does not natively charge.  If the
# 3-slot merge regresses, the tooltip quotes the vanilla cost instead.
cost_lines = [t for _, t in rows if "Costs:" in t]
check("unique unit tooltip quotes the overridden cost",
      any("65W" in t and "30G" in t for t in cost_lines),
      f"cost lines: {cost_lines[:3]}")

# ── The build log says the structural work happened ──────────────────────────
out = log.getvalue()
drop_line = next((ln for ln in out.splitlines() if "cannot grant" in ln), "")
check("Feitoria (1021) is dropped, not honoured", "1021" in drop_line,
      f"drop line was: {drop_line.strip()!r}")

for needle, why in (
    ("Early eco upgrades:",         "bonus 105's shim allocation should run"),
    ("Winged Hussar:",              "bonus 282 should re-point tech 786"),
    ("Unticked entities:",          "the disable sweep should act on the pruned tree"),
    ("Monk skin:",                  "a monk skin was selected"),
):
    check(why, needle in out, f"log did not mention {needle!r}")

check("no soft-limit warning on the tech tree effect",
      "WARNING: Tech tree effect" not in out)

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(0 if not failures else 1)
