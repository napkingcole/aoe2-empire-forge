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
hash unchanged.

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


def digest(dat, civ_def, slot):
    """Hash everything apply_civ produced for this civ.

    Covers the appended techs and effects plus the civ's own tech-tree effect —
    the commands that actually gate what the civ can train and research.
    """
    n_t, n_e = len(dat.techs), len(dat.effects)
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ_def, target_slot=slot)
    h = hashlib.sha256()
    civ = dat.civs[slot]
    h.update(repr((civ.name, civ.icon_set, civ.resources[263])).encode())
    for t in dat.techs[n_t:]:
        h.update(repr((t.name, t.civ, t.effect_id, t.required_techs)).encode())
    for e in dat.effects[n_e:]:
        h.update(repr([(c.type, c.a, c.b, c.c, c.d) for c in e.effect_commands]).encode())
    tt = dat.effects[civ.tech_tree_id]
    h.update(repr(sorted((c.type, c.a, c.b, c.c, c.d)
                         for c in tt.effect_commands)).encode())
    return h.hexdigest()


def run_route(dat, files, to_civ_def):
    """Build every civ into its own slot on one shared DAT.  name -> sha."""
    out = {}
    pool = slot_pool(dat)
    for i, path in enumerate(files):
        raw = json.loads(path.read_text(encoding="utf-8"))
        slot = pool[i % len(pool)]
        try:
            out[path.name] = digest(dat, to_civ_def(raw), slot)
        except Exception as exc:                        # noqa: BLE001
            out[path.name] = f"ERROR {type(exc).__name__}: {exc}"
    return out


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found — set one up or run build_civ.py once")
    sys.exit(0)

files = corpus()
print(f"=== {len(files)} saved civs, both routes, DAT {Path(dat_path).name} ===")

# The wizard door normalizes; the upload door does not.  Non-schema (KM) files
# only have one route, so they are hashed once and compared against themselves.
upload = run_route(load_dat(dat_path), files, lambda raw: raw)
wizard = run_route(load_dat(dat_path), files,
                   lambda raw: _draft_to_civ_def(to_draft(raw))
                   if is_empireforge(raw) else raw)

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
