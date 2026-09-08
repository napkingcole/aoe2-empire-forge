"""Both build routes must produce the same civ.  DAT-gated, opt-in.

A saved civ reaches apply_civ as two different in-memory shapes depending on
which door it came through:

    wizard route  schema -> to_draft -> _draft_to_civ_def  ->  KM shape
    upload route  schema -------------------------------->  schema shape

Same file, same civ, two shapes.  That split is why v2.0.0-beta.1.3 could ship
a `tree[0]` crash that never fired for anyone testing from the wizard: only the
upload door delivers the dict.  This test builds every saved civ down both
routes and hashes the result, so the routes cannot drift apart silently.

It is also the harness for the schema-canonical refactor: capture hashes with
`--baseline`, migrate, then re-run and diff.  A no-op refactor leaves every
hash unchanged — but only over the surface `digest` actually covers, so read
what it hashes before trusting a green run to mean "nothing changed".

Unlike most of tests/, this needs the real game DAT and takes ~80s, so
run_all.sh leaves it opt-in behind ROUNDTRIP=1 (it also skips itself cleanly if
no DAT is found).  Two loads total — one per route, reused across all civs —
because load_dat alone is ~17s.

This is a DRIFT check.  "Does a build complete at all?" is a different question
and belongs to test_build_smoke.py, which runs by default at ~25s.

    venv/bin/python tests/test_route_roundtrip.py             # compare routes
    venv/bin/python tests/test_route_roundtrip.py --baseline  # write hashes
    venv/bin/python tests/test_route_roundtrip.py --check     # diff vs baseline
"""
import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat          # noqa: E402
from civ_appender import apply_civ                      # noqa: E402
from civ_schema import to_draft, is_empireforge         # noqa: E402
from wizard_build import _draft_to_civ_def              # noqa: E402
from build_civ import _resolve_uu_info                  # noqa: E402
from civ_overrides import (_override_ut_costs, _apply_uu_overrides,   # noqa: E402
                           _refresh_uu_tooltips, _apply_hero_unit)

BASELINE = ROOT / "tests" / "route_hashes.json"
failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


# apply_civ clones civ 1 as its template and writes it into the target slot, so
# building *into* slot 1 would make the next civ clone the previous civ's
# leftovers.  Give each civ its own slot and leave slot 1 alone — that is what
# lets one DAT load serve the whole corpus.
#
# Slots are derived from the DAT rather than named: the internal names are not
# the display ones ("French", not "Franks"; no "Indians" at all), and a
# hardcoded list silently degrades to NO_SLOT as the game adds civs.
def slot_pool(dat):
    return [i for i in range(2, len(dat.civs)) if dat.civs[i].name != "Gaia"]


def corpus():
    """Every saved civ file in the repo, both formats."""
    seen, out = set(), []
    for p in (sorted(ROOT.glob("*.civbuilder.json"))
              + sorted((ROOT / "my_civs").glob("*.json"))
              + sorted((ROOT / "civbuilder_civs").glob("*.json"))):
        if p.is_file() and p.name not in seen:
            seen.add(p.name)
            out.append(p)
    return out


def _seq(obj, attr, fields):
    """repr of `fields` across obj.attr, or None when the block is absent."""
    block = getattr(obj, attr, None)
    if block is None:
        return None
    return tuple(tuple(getattr(x, f, None) for f in fields) for x in block)


def _unit_fp(u):
    """Fingerprint the per-unit fields the build pipeline actually writes.

    Architecture and the six monk-skin fields (CLAUDE.md quirk 12), Castle 82 /
    Wonder 276, `enabled`, the UU and hero stat overrides, and the per-train-
    location costs and times of quirk 14.
    """
    if u is None:
        return None
    t50, cre, bird = (getattr(u, a, None) for a in ("type_50", "creatable", "bird"))
    return (
        getattr(u, "enabled", None), getattr(u, "disabled", None),
        getattr(u, "hit_points", None), getattr(u, "speed", None),
        getattr(u, "line_of_sight", None),
        getattr(u, "standing_graphic", None), getattr(u, "dying_graphic", None),
        getattr(u, "icon_id", None), getattr(u, "base_id", None),
        getattr(u, "language_dll_name", None),
        getattr(u, "language_dll_creation", None),
        getattr(u, "language_dll_help", None),
        getattr(getattr(u, "dead_fish", None), "walking_graphic", None),
        getattr(t50, "attack_graphic", None), getattr(t50, "max_range", None),
        getattr(t50, "displayed_attack", None),
        getattr(t50, "displayed_reload_time", None),
        getattr(t50, "displayed_melee_armour", None),
        getattr(t50, "blast_attack_level", None),
        getattr(t50, "bonus_damage_resistance", None),
        _seq(t50, "attacks", ("class_", "amount")),
        getattr(cre, "displayed_pierce_armour", None),
        getattr(cre, "hero_mode", None), getattr(cre, "max_charge", None),
        getattr(cre, "recharge_rate", None),
        _seq(cre, "resource_costs", ("type", "amount", "flag")),
        _seq(cre, "train_locations", ("location_id", "button_id", "train_time")),
        _seq(bird, "tasks", ("proceeding_graphic_id",)),
    )


def digest(dat, civ_def, ov_src, slot):
    """Hash everything the build pipeline produced for this civ.

    apply_civ's appended techs and effects and the civ's own tech-tree effect,
    plus the four override passes every door runs after it — so UT cost/time,
    UU stats, tooltips and the hero unit are inside the hash rather than beside
    it — plus the civ's unit table and full resource block.

    The original version hashed techs and effects only, which left graphics,
    monk skin, unit enable flags, UT costs and UU stats invisible: exactly the
    surfaces the schema migration is most likely to disturb.  `civ.name` is
    deliberately absent — apply_civ with overwrite keeps the vanilla slot name,
    so it is a per-slot constant and hashing it proves nothing.
    """
    n_t, n_e = len(dat.techs), len(dat.effects)
    with contextlib.redirect_stdout(io.StringIO()):
        civ_result = apply_civ(dat, civ_def, target_slot=slot)
        # Mirror the doors: all three run these immediately after apply_civ, but
        # they do NOT agree on what they hand them.  The wizard door passes the
        # *draft* (wizard_build:158-165); the upload door and build_all pass the
        # *civ_def* (app:640-643, build_all:525-528).  Schema and draft happen to
        # spell castle_ut / unique_unit alike, which is the only reason one
        # reader survives both — the same one-field-two-shapes pattern this
        # plan exists to remove.  ov_src is whichever the modelled route sends.
        _override_ut_costs(dat, civ_result, ov_src)
        uu_info = _resolve_uu_info(civ_def, dat, slot, civ_result)
        _apply_uu_overrides(dat, slot, uu_info, ov_src)
        _refresh_uu_tooltips(dat, slot, civ_result)
        _apply_hero_unit(dat, slot, ov_src)
    h = hashlib.sha256()
    civ = dat.civs[slot]
    h.update(repr((civ.icon_set, tuple(civ.resources))).encode())
    for t in dat.techs[n_t:]:
        h.update(repr((t.name, t.civ, t.effect_id, t.required_techs)).encode())
        # tech.research_time and research_locations[*].research_time are
        # different fields — _override_ut_costs writes the former, the UT cost
        # API reads the latter — so hash both or a UT time change is invisible.
        h.update(repr((getattr(t, "research_time", None),
                       _seq(t, "resource_costs", ("type", "amount", "flag")),
                       _seq(t, "research_locations",
                            ("location_id", "research_time")))).encode())
    for e in dat.effects[n_e:]:
        h.update(repr([(c.type, c.a, c.b, c.c, c.d) for c in e.effect_commands]).encode())
    tt = dat.effects[civ.tech_tree_id]
    h.update(repr(sorted((c.type, c.a, c.b, c.c, c.d)
                         for c in tt.effect_commands)).encode())
    h.update(repr([_unit_fp(u) for u in civ.units]).encode())
    return h.hexdigest()


def run_route(dat, files, prepare):
    """Build every civ into its own slot on one shared DAT.  name -> sha.

    `prepare(raw)` returns the pair this route's door would produce:
    (civ_def for apply_civ, source object for the override passes).
    """
    out = {}
    pool = slot_pool(dat)
    for i, path in enumerate(files):
        raw = json.loads(path.read_text(encoding="utf-8"))
        slot = pool[i % len(pool)]
        try:
            civ_def, ov_src = prepare(raw)
            out[path.name] = digest(dat, civ_def, ov_src, slot)
        except Exception as exc:                        # noqa: BLE001
            out[path.name] = f"ERROR {type(exc).__name__}: {exc}"
    return out


def _wizard(raw):
    """The wizard door: schema -> draft -> KM civ_def, overrides read the draft."""
    if not is_empireforge(raw):
        return raw, raw
    d = to_draft(raw)
    return _draft_to_civ_def(d), d


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found — set one up or run build_civ.py once")
    sys.exit(0)

files = corpus()
print(f"=== {len(files)} saved civs, both routes, DAT {Path(dat_path).name} ===")

# The wizard door normalizes; the upload door does not.  Non-schema (KM) files
# only have one route, so they are hashed once and compared against themselves.
upload = run_route(load_dat(dat_path), files, lambda raw: (raw, raw))
wizard = run_route(load_dat(dat_path), files, _wizard)

errors = sorted(n for n, h in {**upload, **wizard}.items()
                if h.startswith("ERROR"))
check("every civ built on both routes", not errors,
      "; ".join(f"{n}={upload.get(n, wizard.get(n))}" for n in errors[:4]))

drift = sorted(n for n in upload if upload[n] != wizard[n])
check(f"{len(files)} civs: both routes agree", not drift, "; ".join(drift[:6]))
for name in drift:
    print(f"    {name}\n      upload={upload[name][:16]}  wizard={wizard[name][:16]}")

if "--baseline" in sys.argv:
    BASELINE.write_text(json.dumps(upload, indent=2, sort_keys=True) + "\n")
    print(f"\n  wrote baseline for {len(upload)} civs → {BASELINE.name}")
elif "--check" in sys.argv:
    print("\n=== Against baseline ===")
    if not BASELINE.exists():
        check("baseline exists", False, "run with --baseline first")
    else:
        old = json.loads(BASELINE.read_text())
        gone = sorted(set(old) - set(upload))
        new = sorted(set(upload) - set(old))
        changed = sorted(n for n in set(old) & set(upload) if old[n] != upload[n])
        check("no civ changed since baseline", not changed, "; ".join(changed[:6]))
        for n in changed:
            print(f"    {n}\n      was={old[n][:16]}  now={upload[n][:16]}")
        if gone or new:
            print(f"  note  corpus changed: +{len(new)} -{len(gone)} "
                  f"({', '.join((new + gone)[:4])})")

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
