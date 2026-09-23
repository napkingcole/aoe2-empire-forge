#!/usr/bin/env python3
"""The helper routes must find the DAT even when the draft has no path.  DAT-gated.

`civ_schema` strips `dat_path` when a civ is saved — correctly, since it is
specific to one machine and has no business travelling in a shared
`.civbuilder.json`.  So **every draft loaded from a saved civ arrives without
one**, and anything that reads only the request parameter gets nothing.

That is what broke unique-unit stats (reported 2026-09-21).  `/builder/build`
had always fallen back to `session["dat_path"]`, so builds kept working, while
`/api/builder/uu/catalog` returned `stats: null` for all 92 units with a 200 and
`_build_all_uu_stats` swallowed failures in a bare `except Exception: pass`.
The popup then read "No stats available" on every unit — indistinguishable from
units that genuinely have none.  Open a saved civ, lose the stats, keep building
fine: nothing connects those two facts from the outside.

These are the first route tests in the suite.  They exist because the bug was
not in the logic any existing test covers — it was in *where a route looks for
an input*, and two routes disagreeing about that is invisible until a user
notices a blank screen.

    venv/bin/python tests/test_dat_path_fallback.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat          # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

import app as appmod                          # noqa: E402

appmod.app.config["TESTING"] = True
client = appmod.app.test_client()


def stats_count(query=""):
    res = client.get(f"/api/builder/uu/catalog{query}")
    assert res.status_code == 200, res.status_code
    data = res.get_json()
    return len(data), sum(1 for u in data if u.get("stats"))


print("=== unique unit stats survive a draft with no dat_path ===")
total, with_stats = stats_count("")
check("no dat_path at all still returns stats", with_stats > 0,
      f"{with_stats}/{total} units had stats — this is the saved-civ case, and "
      f"0 here means every stat popup reads 'No stats available'")
check("and it is the whole catalog, not a handful", with_stats == total,
      f"{with_stats}/{total}")

_, empty_arg = stats_count("?dat_path=")
check("an empty dat_path parameter still returns stats", empty_arg == total,
      f"{empty_arg}/{total}")

_, stale = stats_count("?dat_path=/nonexistent/empires2_x2_p1.dat")
check("a stale dat_path falls through instead of winning", stale == total,
      f"{stale}/{total} — a moved install or hand-edited civ file must not "
      f"beat a working fallback")

from urllib.parse import quote               # noqa: E402

_, explicit = stats_count(f"?dat_path={quote(str(dat_path))}")
check("an explicit valid dat_path still works", explicit == total,
      f"{explicit}/{total}")

print("\n=== validate-dat answers a typed path specifically ===")
# Auto-detection only knows the default install locations, so anyone with the
# game on a second drive types the path by hand.  Until 2026-09-22 that produced
# no feedback whatsoever, and a correct path was indistinguishable from a wrong
# one — which is exactly how a user concluded a perfectly good path "didn't work".


def validate(path):
    res = client.get("/api/builder/validate-dat",
                     query_string={"dat_path": path})
    assert res.status_code == 200, res.status_code
    return res.get_json()


good = validate(str(dat_path))
check("a real DAT validates", good["ok"] is True, good)
check("and reports its size so the answer is legible", good.get("size_mb", 0) > 1, good)

folder = validate(str(Path(dat_path).parent))
check("a pasted FOLDER resolves to the DAT inside it", folder["ok"] is True, folder)
check("and hands back the corrected path",
      folder.get("dat_path", "").endswith("empires2_x2_p1.dat"), folder)

missing = validate(r"D:\SteamLibrary\steamapps\common\AoE2DE\resources\_common\dat\empires2_x2_p1.dat")
check("a path on an absent drive fails with a reason", missing["ok"] is False, missing)
check("and the reason names the drive rather than shrugging",
      "D:" in missing.get("reason", ""), missing)

wrong = validate(str(ROOT / "README.md"))
check("a file that is not the DAT fails by name", wrong["ok"] is False, wrong)
check("and says what it expected",
      "empires2_x2_p1.dat" in wrong.get("reason", ""), wrong)

blank = validate("")
check("an empty path fails rather than 500ing", blank["ok"] is False, blank)

print("\n=== the resolver prefers a real path over a broken one ===")
with appmod.app.test_request_context():
    resolved = appmod._resolve_dat_path("/nonexistent/empires2_x2_p1.dat")
    check("a missing arg path is discarded", Path(resolved).exists(),
          f"resolved to {resolved!r}")
    resolved2 = appmod._resolve_dat_path(None)
    check("no arg resolves by detection", Path(resolved2).exists(),
          f"resolved to {resolved2!r}")
    resolved3 = appmod._resolve_dat_path(str(dat_path))
    check("an explicit valid path is honoured", resolved3 == str(dat_path),
          f"resolved to {resolved3!r}")

print("\n=== every route reading dat_path goes through the resolver ===")
# The bug was two routes disagreeing about where to look.  Keep them agreeing.
#
# One route is deliberately exempt.  `/api/builder/validate-dat` exists to answer
# "is THIS path usable?" for a path the user just typed, so falling back to the
# session or to auto-detection would make it report success about a different
# file entirely — a wrong path would come back "Game files found".  Validating a
# candidate and consuming a DAT are opposite jobs; only the second one falls back.
EXEMPT_MARKERS = ('.strip().strip(\'"\')',)   # the validate-dat read
src = (ROOT / "app.py").read_text()
raw = [ln.strip() for ln in src.splitlines()
       if 'request.args.get("dat_path"' in ln
       and "_resolve_dat_path" not in ln
       and not any(m in ln for m in EXEMPT_MARKERS)]
check("no consuming route reads the dat_path parameter directly", not raw,
      "these bypass the fallback:\n       " + "\n       ".join(raw))

# ...and the exempt one must still exist, so the exemption cannot quietly become
# a hole that swallows a future route.
exempt_lines = [ln.strip() for ln in src.splitlines()
                if 'request.args.get("dat_path"' in ln
                and any(m in ln for m in EXEMPT_MARKERS)]
check("the validate-dat exemption matches exactly one route", len(exempt_lines) == 1,
      f"matched {len(exempt_lines)}: {exempt_lines}")

print("\n=== the UT catalog only offers what the player's DAT implements ===")
# A UT preset works by cloning a vanilla tech's effect commands, so a preset
# whose tech is an empty placeholder in THIS DAT would research and do nothing
# — the "a card that does nothing is worse than no card" rule, applied to a DAT
# the user has not updated yet.  Ordonnance Companies (castle 64) is tech 1496,
# a nameless empty slot until Viking Sagas fills it in.
ORDONNANCE, ORDONNANCE_TECH = 64, 1496


def castle_ids(path):
    res = client.get("/api/builder/ut/catalog", query_string={"dat_path": str(path)})
    assert res.status_code == 200, res.status_code
    return {e["id"] for e in res.get_json()["castle"]}


# load_dat is ~16s, so read it ONCE — the first draft of this called it per
# preset and took over five minutes.
_probe_dat = appmod._get_dat(str(dat_path))


def tech_has_effect(path, tech_id):
    d = _probe_dat
    if tech_id >= len(d.techs):
        return False
    eid = d.techs[tech_id].effect_id
    return 0 <= eid < len(d.effects) and bool(d.effects[eid].effect_commands)


ids = castle_ids(dat_path)
check("the catalog is not empty", len(ids) > 40, f"{len(ids)} entries")
# Whichever DAT is installed, the answer must MATCH that DAT rather than be
# hardcoded — so the test works either side of the patch.
implemented = tech_has_effect(dat_path, ORDONNANCE_TECH)
check(f"Ordonnance Companies offered == its tech is implemented here "
      f"({'implemented' if implemented else 'empty placeholder'})",
      (ORDONNANCE in ids) == implemented,
      f"offered={ORDONNANCE in ids}, tech {ORDONNANCE_TECH} implemented={implemented}")

# And the filter must be surgical: it is there to drop unimplemented presets,
# not to thin the catalog.  Every other preset whose tech IS implemented must
# survive it.
from civ_appender import _KM_CASTLE_UT_TECHS      # noqa: E402
expected = {i for i, t in _KM_CASTLE_UT_TECHS.items() if tech_has_effect(dat_path, t)}
check("every preset whose tech is implemented is still offered", ids == expected,
      f"missing: {sorted(expected - ids)}  unexpected: {sorted(ids - expected)}")

# Without a readable DAT the catalog must still answer, rather than hiding
# everything because it could not check.
res = client.get("/api/builder/ut/catalog", query_string={"dat_path": "/nope/x.dat"})
check("an unreadable dat_path still returns a catalog",
      res.status_code == 200 and len(res.get_json()["castle"]) > 40)

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
