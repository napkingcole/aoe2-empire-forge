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
src = (ROOT / "app.py").read_text()
raw = [ln.strip() for ln in src.splitlines()
       if 'request.args.get("dat_path"' in ln and "_resolve_dat_path" not in ln]
check("no route reads the dat_path parameter directly", not raw,
      "these bypass the fallback:\n       " + "\n       ".join(raw))

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
