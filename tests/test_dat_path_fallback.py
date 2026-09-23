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

# NOTE ON CROSS-VERSION TESTING.  The checks below are written to assert against
# whatever DAT is installed, so they pass either side of a patch — but that also
# means running them once proves only one branch.  To exercise the other, point
# EMPIREFORGE_DAT at a DAT from before the content in question:
#
#     EMPIREFORGE_DAT="$PWD/ignore/6-6-26/empires2_x2_p1.dat" ./tests/run_all.sh
#
# That copy is clean vanilla from before Viking Sagas (60 civs, 1409 effects),
# which is exactly the shape of a player who has not updated.  Worth keeping:
# once the installed DAT is updated there is no way back to it.
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


def _roster_for_test(path):
    from build_civ import civ_roster
    return civ_roster(str(path))


def _probe_team_effect(bonus_id):
    from bonus_catalog import team_bonus_tech
    return team_bonus_tech(bonus_id)


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
from civ_appender import (_KM_CASTLE_UT_TECHS,    # noqa: E402
                          _KM_UU_TECHS as _KM_UU_TECHS_FOR_TEST,
                          _KM_UU_NAMES as _KM_UU_NAMES_FOR_TEST)
expected = {i for i, t in _KM_CASTLE_UT_TECHS.items() if tech_has_effect(dat_path, t)}
check("every preset whose tech is implemented is still offered", ids == expected,
      f"missing: {sorted(expected - ids)}  unexpected: {sorted(ids - expected)}")

# Without a readable DAT the catalog must still answer, rather than hiding
# everything because it could not check.  (The resolver falls back to detection,
# so this lands on the installed DAT rather than on nothing — either way the
# route must not come back empty.)
res = client.get("/api/builder/ut/catalog", query_string={"dat_path": "/nope/x.dat"})
check("an unreadable dat_path still returns a catalog",
      res.status_code == 200 and len(res.get_json()["castle"]) > 40)

print("\n=== the UU catalog applies the same rule ===")
# A vanilla UU is built by cloning its make-avail and elite techs, so one whose
# techs are empty placeholders in this DAT cannot be built.  The three Viking
# Sagas units are empty slots for anyone who has not updated.
uu = client.get("/api/builder/uu/catalog",
                query_string={"dat_path": str(dat_path)}).get_json()
offered = {u["km_idx"] for u in uu}
check("the UU catalog is not empty", len(offered) > 60, f"{len(offered)} entries")

buildable = {i for i, pair in _KM_UU_TECHS_FOR_TEST.items()
             if all(tech_has_effect(dat_path, t) for t in pair)}
unbuildable = set(_KM_UU_TECHS_FOR_TEST) - buildable
check("no vanilla UU whose techs are empty here is offered",
      not (offered & unbuildable),
      f"offered anyway: {sorted((offered & unbuildable))}")
check("every vanilla UU that IS buildable here is still offered",
      not (buildable - offered - {47, 75}),      # 47/75 are the known unsupported pair
      f"missing: {sorted(buildable - offered - {47, 75})}")
# KM-custom units are built from a base unit, not a DAT tech, so the filter must
# not touch them.
custom = set(_KM_UU_NAMES_FOR_TEST) - set(_KM_UU_TECHS_FOR_TEST) - {47, 75}
check("KM-custom UUs are untouched by the filter", custom <= offered,
      f"wrongly hidden: {sorted(custom - offered)}")

print("\n=== the identity page reads the player's roster, not a frozen list ===")
# Wonder, castle and voice pickers are built from the civ list.  That list used
# to be our bundled civilizations.json, so it stuck at 53 civs and the three
# Viking Sagas civs did not exist in the wizard at all — the same class of bug
# as the frozen KM_TECHTREE_ORDER.
meta = client.get("/api/builder/meta",
                  query_string={"dat_path": str(dat_path)}).get_json()
roster_names = {c["name"] for c in _roster_for_test(dat_path)[1:]
                if c.get("era", "base") != "antiquity"}
offered_civs = {o["label"] for o in meta["civs"]}
check("every playable civ in this DAT's roster is offered",
      roster_names <= offered_civs | {""},
      f"missing: {sorted(roster_names - offered_civs)}")
check("...and no Chronicles civ leaks in",
      not (offered_civs & {"Achaemenids", "Athenians", "Spartans",
                           "Macedonians", "Thracians", "Puru"}),
      f"leaked: {sorted(offered_civs & {'Achaemenids','Athenians','Spartans'})}")

# Architecture and Monk options must each name a real partition in this DAT:
# an option whose representative civ does not actually carry that icon_set or
# Monk would copy the wrong art silently.
from civ_appender import _ARCH_REP_CIVS, MONK_SKIN_OPTIONS   # noqa: E402

# Judge the OFFERED options, not the raw tables: Viking Sagas added a thirteenth
# architecture and an eleventh Monk, so on an older DAT those options are
# correctly filtered out rather than pointing at art that does not exist yet.
offered_arch = {a["value"] for a in meta["architectures"]}
dat_sets = {c.icon_set for c in _probe_dat.civs[1:]}
check("every offered architecture names a civ that really has that icon_set",
      all(_probe_dat.civs[_ARCH_REP_CIVS[v - 1]].icon_set == v for v in offered_arch),
      str([(v, _probe_dat.civs[_ARCH_REP_CIVS[v - 1]].name,
            _probe_dat.civs[_ARCH_REP_CIVS[v - 1]].icon_set)
           for v in sorted(offered_arch)
           if _probe_dat.civs[_ARCH_REP_CIVS[v - 1]].icon_set != v]))
check("every icon_set this DAT uses is offered", dat_sets <= offered_arch,
      f"uncovered: {sorted(dat_sets - offered_arch)}")
check("...and nothing is offered that this DAT does not have",
      offered_arch <= dat_sets, f"phantom: {sorted(offered_arch - dat_sets)}")

# Every Monk partition is offered except the Chronicles one, which is blacklisted.
_monk_groups = {}
for _i, _c in enumerate(_probe_dat.civs):
    if _i == 0:
        continue
    _u = _c.units[125] if _c.units and len(_c.units) > 125 else None
    if _u:
        _monk_groups.setdefault(_u.standing_graphic, []).append(_i)
_offered_monks = {o["value"] for o in meta["monk_skins"]}
_CHRONICLES = {46, 47, 48, 54, 55, 56}
_unoffered = [m for m in _monk_groups.values() if not (_offered_monks & set(m))]
check("every Monk partition is offered except the Chronicles one",
      all(set(m) <= _CHRONICLES for m in _unoffered),
      f"unoffered non-Chronicles partitions: {[m for m in _unoffered if not set(m) <= _CHRONICLES]}")
check("...and each offered Monk covers a distinct partition",
      len({tuple(m) for o in _offered_monks
           for m in _monk_groups.values() if o in m}) == len(_offered_monks),
      f"{len(_offered_monks)} options collapse to fewer partitions")
check("...and no Monk option is offered that this DAT cannot supply",
      all(any(o in m for m in _monk_groups.values()) for o in _offered_monks))

print("\n=== the bonus catalog only offers what this DAT can implement ===")
# Third place this rule lives, after unique techs and unique units.  A civ bonus
# is built by cloning its techs' effect commands, so the twelve Viking Sagas
# cards are inert on a DAT from before the DLC.  Only bonuses that HAVE techs
# are judged: plenty are implemented from `ec_list` and carry none, and hiding
# those would empty the picker.
import json                                                      # noqa: E402
from bonus_catalog import civ_bonus_techs, team_bonus_ec_list     # noqa: E402

bc = client.get("/api/builder/bonuses/catalog",
                query_string={"dat_path": str(dat_path)}).get_json()
civ_offered = {b["id"] for b in bc["civ"]}
team_offered = {b["id"] for b in bc["team"]}
check("the bonus catalog is not empty", len(civ_offered) > 300,
      f"{len(civ_offered)} civ bonuses")

all_names = json.loads((ROOT / "bonus_names.json").read_text())
dead = set()
for k in all_names:
    techs = civ_bonus_techs(int(k)) or []
    if techs and not any(tech_has_effect(dat_path, int(x)) for x in techs):
        dead.add(int(k))
check("no civ bonus whose every tech is empty here is offered",
      not (civ_offered & dead),
      f"offered anyway: {sorted(civ_offered & dead)[:8]}")
# ...and the rule must not be hiding bonuses that carry no techs at all.
techless = {int(k) for k in all_names if not (civ_bonus_techs(int(k)) or [])}
check("bonuses implemented without techs are untouched",
      len(techless & civ_offered) > 20,
      f"only {len(techless & civ_offered)} of {len(techless)} techless bonuses offered")

# Team bonuses copy a vanilla effect wholesale, so an effect this DAT lacks
# means a dead card — unless a team_ec_list entry stands in.
team_names_j = json.loads((ROOT / "team_bonus_names.json").read_text())
dead_team = set()
for k in team_names_j:
    ei = _probe_team_effect(int(k))
    if ei is None:
        continue
    live = 0 <= ei < len(_probe_dat.effects) and bool(_probe_dat.effects[ei].effect_commands)
    if not live and not team_bonus_ec_list(int(k)):
        dead_team.add(int(k))
check("no team bonus whose effect is missing or empty here is offered",
      not (team_offered & dead_team),
      f"offered anyway: {sorted(team_offered & dead_team)}")

print("\n=== UU picker icons are derived, and never point at a missing file ===")
# An icon entry naming a PNG that is not there renders as a broken image; None
# renders as no image, which is what an un-illustrated unit should look like.
_icon_dir = ROOT / "uniticons"
broken = [(u["km_idx"], u["icon"]) for u in uu
          if u["icon"] and not (_icon_dir / Path(u["icon"]).name).exists()]
check("no offered UU points at a missing icon file", not broken,
      f"broken: {broken[:6]}")
check("...and the ones that do have art still show it",
      sum(1 for u in uu if u["icon"]) > 60,
      f"only {sum(1 for u in uu if u['icon'])} have icons")

# The derivation replaces hand-listing only because it reproduces every
# hand-listed vanilla entry exactly.  If a future unit breaks that rule this
# fails here rather than silently showing the wrong portrait.
import re                                                        # noqa: E402
_blk = re.search(r'_ICON_MAP: dict\[int, str\] = \{(.*?)\n    \}',
                 (ROOT / "app.py").read_text(), re.S).group(1)
_hand = {int(a): b for a, b in re.findall(r'(\d+):\s*"([^"]+)"', _blk)}


def _derived_icon(km_idx):
    t1 = _KM_UU_TECHS_FOR_TEST[km_idx][0]
    if not tech_has_effect(dat_path, t1):
        return None
    for c in _probe_dat.effects[_probe_dat.techs[t1].effect_id].effect_commands:
        if c.type in (2, 3):
            uid = int(c.a)
            u = next((cv.units[uid] for cv in _probe_dat.civs
                      if cv.units and len(cv.units) > uid and cv.units[uid]), None)
            ic = getattr(u, "icon_id", -1) if u else -1
            return f"{ic:03d}_50730.png" if isinstance(ic, int) and ic >= 0 else None
    return None


vanilla_hand = {k: v for k, v in _hand.items() if k in _KM_UU_TECHS_FOR_TEST}
wrong = {k: (v, _derived_icon(k)) for k, v in vanilla_hand.items()
         if _derived_icon(k) is not None and _derived_icon(k) != v}
check(f"all {len(vanilla_hand)} hand-listed vanilla icons match the derivation",
      not wrong, f"differ: {list(wrong.items())[:4]}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
