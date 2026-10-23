#!/usr/bin/env python3
"""Run the test files, several at a time.  Called by tests/run_all.sh.

    ./tests/run_all.sh                 everything, 6 at a time
    ./tests/run_all.sh --quick         data checks + build smoke + changed tests
    ./tests/run_all.sh --quick test_ambuscade.py   ...plus the files named
    ./tests/run_all.sh -j 1            one at a time (the old behaviour)

Deliberately dependency-free — plain scripts, no pytest, no node_modules.
Adding a test means adding a line to TESTS below.

Each file runs in its own process, and every test writes only inside its own
temp dir (checked 2026-10-21), so they are safe side by side.  One build test
peaks around 400 MB, which is what the default of 6 is sized against.

Timings are kept in tests/.timings.json (not committed): the slowest files
start first, so one long test doesn't begin last and hold up the whole run.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMINGS = ROOT / "tests" / ".timings.json"
PY = str(ROOT / "venv" / "bin" / "python") if (ROOT / "venv" / "bin" / "python").exists() else sys.executable

# (label, file, group).  Groups:
#   node       the editor's JavaScript (needs node)
#   data       pure data checks that never build a civ — seconds each
#   build      build at least one civ against the game DAT (SKIP_SMOKE=1 skips)
#   roundtrip  opt-in (ROUNDTRIP=1): all saved civs down both routes, ~80s
TESTS: list[tuple[str, str, str]] = [
    ("editor layout (node)",            "test_editor_layout.js",        "node"),
    ("blank-civ seed tree (node)",      "test_seed_tree.js",            "node"),
    ("unit exclusivity (node)",         "test_unit_exclusivity.js",     "node"),

    ("in-game tech tree (python)",      "test_civtechtrees.py",         "data"),
    ("civ_def formats (python)",        "test_civ_def_formats.py",      "data"),
    ("no direct civ_def reads",         "test_no_direct_civdef_reads.py", "data"),
    ("catalog resource ids",            "test_resource_ids.py",         "data"),
    ("civ roster",                      "test_civ_roster.py",           "data"),
    ("game strings + exe bundle",       "test_game_strings.py",         "data"),
    ("no blank unit icons",             "test_blank_uniticons.py",      "data"),
    ("button pages",                    "test_button_pages.py",         "build"),
    ("UT cost override",                "test_ut_cost_override.py",     "data"),
    ("multiplier scaling",              "test_multiplier_scaling.py",   "data"),
    ("explicit file encodings",         "test_explicit_encoding.py",    "data"),
    ("voices from the player's banks",  "test_voice_source.py",         "data"),
    ("armour class vs card text",       "test_armor_class_text.py",     "data"),
    ("relic bonus reaches the UU",      "test_relic_bonus_uu.py",       "build"),
    ("chronicles bonus cards",          "test_chronicles_bonuses.py",   "build"),
    ("bonus 54 fishermen",              "test_bonus_54_fishermen.py",   "data"),
    ("audit fixes (python)",            "test_audit_fixes.py",          "build"),
    ("team bonus catalog",              "test_team_bonus_catalog.py",   "build"),
    ("spawn scaling + UU flags",        "test_spawn_and_flags.py",      "build"),
    ("UT multiplier flags",             "test_ut_multiplier_flags.py",  "data"),
    ("hero catalog from the DAT",       "test_hero_catalog.py",         "data"),
    ("unit previews (SLD decoder)",     "test_game_sprites.py",         "data"),

    # Build tests: each builds at least one civ.  Build smoke runs in --quick
    # too, because a NameError that broke every build once reached the branch
    # with every data check still green.  Six of these sat in the data group
    # until 2026-10-21, when timings showed them setting the length of --quick.
    # Each skips itself cleanly when no DAT is found.
    ("lazy DAT loading",                "test_lazy_dat.py",             "build"),
    ("vanilla UU tooltips",             "test_uu_vanilla_hover.py",     "build"),
    ("renamed vanilla UU is this civ's only", "test_renamed_vanilla_uu.py", "build"),
    ("Donjon gets tower bonuses",       "test_donjon_towers.py",        "build"),
    ("Chronicles unique units",         "test_chronicles_uu.py",        "build"),
    ("build smoke (python)",            "test_build_smoke.py",          "build"),
    ("civ with no UU (python)",         "test_no_uu_civ.py",            "build"),
    ("unlock unit bonuses",             "test_unlock_unit_bonuses.py",  "build"),
    ("shared prereq bonuses",           "test_shared_prereq_bonuses.py", "build"),
    ("age-shift cards 221/247",         "test_age_shift_cards.py",      "build"),
    ("UT enable not misread as UU",     "test_ut_enable_misread.py",    "build"),
    ("Ambuscade: UU at the Archery Range", "test_ambuscade.py",         "build"),
    ("scenario units as UUs",           "test_scenario_uus.py",         "build"),
    ("custom UUs cost population",      "test_preset_population.py",    "build"),
    ("UU appearance (another's look)",  "test_uu_appearance.py",        "build"),
    ("bonus 105: every eco upgrade one age earlier", "test_early_eco_shims.py", "build"),
    ("retired cards are listed for removal (#78)", "test_retired_cards.py", "build"),
    ("Thracian bonuses 458/459",        "test_thracian_bonuses.py",     "build"),
    ("KM import tree gaps",             "test_km_import_gaps.py",       "build"),
    ("elephant bonuses",                "test_elephant_bonuses.py",     "build"),
    ("monk voice gender",               "test_monk_voice.py",           "build"),
    ("replaced civ leftovers",          "test_replaced_civ_leftovers.py", "build"),
    ("custom bonus targets",            "test_custom_bonus_targets.py", "build"),
    ("multi-target, team & UT cards",   "test_custom_bonus_multi.py",   "build"),
    ("UT preset pools",                 "test_ut_pools.py",             "build"),
    ("elite upgrade cost",              "test_elite_upgrade_cost.py",   "build"),
    ("unit line targets",               "test_unit_line_targets.py",    "build"),
    ("population limit bonus",          "test_pop_cap_bonus.py",        "build"),
    ("population space bonus",          "test_pop_space_bonus.py",      "build"),
    ("range, blast, conversion",        "test_range_blast_conversion.py", "build"),
    ("civ share summary",               "test_civ_summary.py",          "build"),
    ("dat_path fallback",               "test_dat_path_fallback.py",    "build"),
    ("issues 38-44 batch",              "test_issues_40_44.py",         "build"),
    ("custom bonus composer",           "test_custom_bonus.py",         "build"),
    ("custom bonus gating",             "test_custom_bonus_when.py",    "build"),
    ("civ build order",                 "test_civ_build_order.py",      "build"),
    ("fully-upgraded stats",            "test_fu_stats.py",             "build"),
    ("blank-civ seed (python)",         "test_full_seed.py",            "build"),
    ("Longship in the tree",            "test_longship_tree.py",        "build"),
    ("AI unique unit lines",            "test_unit_lines.py",           "build"),
    ("update check order",              "test_update_check.py",         "build"),
    ("Fortified Outpost target",        "test_fortified_outpost.py",    "build"),
    ("UT text, both routes",            "test_ut_description_routes.py", "build"),

    ("route round-trip (python)",       "test_route_roundtrip.py",      "roundtrip"),
]

# Always in --quick: every data check, plus one end-to-end build.
_QUICK_BUILD = {"test_build_smoke.py"}


def _changed_tests() -> set[str]:
    """Test files git sees as changed or new — the ones a change just touched."""
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--", "tests/"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {Path(line[3:].strip()).name for line in out.splitlines() if line[3:].strip()}


def _load_timings() -> dict[str, float]:
    try:
        return json.loads(TIMINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _run(label: str, file: str) -> tuple[str, str, bool, float, str]:
    cmd = ["node" if file.endswith(".js") else PY, str(Path("tests") / file)]
    start = time.monotonic()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return label, file, p.returncode == 0, time.monotonic() - start, p.stdout + p.stderr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-j", "--jobs", type=int, default=int(os.environ.get("TEST_JOBS", 6)))
    ap.add_argument("--quick", action="store_true",
                    help="data checks + build smoke + changed and named test files")
    ap.add_argument("files", nargs="*", help="test files to add (with --quick) or to run alone")
    args = ap.parse_args()

    known = {f for _, f, _ in TESTS}
    named = {Path(f).name for f in args.files}
    if unknown := named - known:
        print(f"!! not in tests/run_tests.py TESTS: {', '.join(sorted(unknown))}")
        return 1

    has_node = subprocess.run(["which", "node"], capture_output=True).returncode == 0
    skipped: list[str] = []
    chosen: list[tuple[str, str]] = []
    for label, file, group in TESTS:
        if group == "node" and not has_node:
            continue
        if named and not args.quick:
            keep = file in named
        elif args.quick:
            keep = group in ("node", "data") or file in _QUICK_BUILD or file in named \
                   or file in _changed_tests()
        elif group == "build" and os.environ.get("SKIP_SMOKE") == "1":
            skipped.append("build tests (SKIP_SMOKE=1 was set)")
            keep = False
        elif group == "roundtrip" and os.environ.get("ROUNDTRIP") != "1":
            skipped.append("route round-trip (ROUNDTRIP=1 to run, needs game DAT, ~80s)")
            keep = False
        else:
            keep = True
        if keep:
            chosen.append((label, file))

    # Slowest first, from the last run; unknown files count as slow.
    timings = _load_timings()
    chosen.sort(key=lambda t: -timings.get(t[1], 60.0))

    mode = "quick" if args.quick else "named" if named else "full"
    print(f"Running {len(chosen)} test files ({mode}), {args.jobs} at a time…\n")
    start = time.monotonic()
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for fut in as_completed([pool.submit(_run, label, file) for label, file in chosen]):
            label, file, ok, secs, output = fut.result()
            results.append((label, file, ok, secs))
            print(f"  {'PASS' if ok else 'FAIL'}  {secs:5.1f}s  {label}", flush=True)
            if not ok:
                print("\n".join(f"      │ {line}" for line in output.rstrip().splitlines()[-60:]), flush=True)
    wall = time.monotonic() - start

    timings.update({file: round(secs, 1) for _, file, _, secs in results})
    try:
        TIMINGS.write_text(json.dumps(timings, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass

    print()
    if not has_node:
        print("!! node not found — the three editor tests were not run")
    for s in sorted(set(skipped)):
        print(f"──── {s}: SKIPPED")
    slowest = sorted(results, key=lambda r: -r[3])[:8]
    print("Slowest: " + ", ".join(f"{Path(f).stem.removeprefix('test_')} {s:.0f}s" for _, f, _, s in slowest))
    failed = [label for label, _, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed in {wall:.0f}s "
          f"(the files' own times add up to {sum(r[3] for r in results):.0f}s)")
    if failed:
        print("FAILED: " + "; ".join(failed))
        print("Some test files FAILED.")
        return 1
    if not has_node:
        return 1
    print("All test files passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
