"""A civ with no unique unit must still build.  DAT-gated.

Every saved civ in the corpus picks a unique unit, so the round-trip harness and
the build smoke test both walk the KM UU branches every single time.  That left
the no-UU path completely uncovered, and it is a path real users reach — nothing
forces a civ to have a unique unit.

It bit us on 2026-09-08: removing the unreachable from-scratch UU block also
removed the `uu_id, elite_uu_id = -1, -1` initialisation that lived in it, while
the UT substitution blocks and apply_civ's result dict still read those names on
every path.  Any civ without a UU raised UnboundLocalError.  Same shape as the
2026-09-02 NameError in BUGFIXES.md: a deletion left a reference behind, and the
suite stayed green because no fixture exercised the branch.

Also covers the hidden-card ids: hiding a bonus card is a *display* decision, so
a saved civ still carrying one of the superseded unlock ids must keep building.
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat   # noqa: E402
from civ_appender import apply_civ               # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


def civ_def(bonuses, uu_slot):
    return {
        "alias": "No UU Probe", "description": "", "architecture": 2, "language": 0,
        "wonder": -1, "castle": -1,
        # bonuses = [civ, [uu_idx], castle_ut, imperial_ut, team]
        "bonuses": [bonuses, uu_slot, [], [], []],
        "tree": [[], [], []],
    }


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

dat = load_dat(dat_path)
print("=== a civ with no unique unit ===")

def build(label, cd, slot):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res = apply_civ(dat, cd, target_slot=slot)
        check(label, True)
        return res
    except Exception as exc:                            # noqa: BLE001
        check(label, False, f"{type(exc).__name__}: {exc}")
        return None

res = build("no UU at all (empty uu slot) builds", civ_def([], []), 5)
if res is not None:
    check("result reports no UU rather than a stale id",
          res.get("uu_id", -1) < 0 and res.get("elite_uu_id", -1) < 0,
          f"uu_id={res.get('uu_id')} elite_uu_id={res.get('elite_uu_id')}")

build("no UU, with a civ bonus", civ_def([[139, 1]], []), 6)

print("\n=== superseded unlock ids still build (hiding is display-only) ===")
# old id -> the modern _UNLOCK_UNIT_BONUSES card that replaced it on screen
for slot, (old, new) in enumerate(((193, 414), (355, 407), (361, 412)), start=7):
    build(f"hidden id {old} still builds", civ_def([[old, 1]], []), slot)
    build(f"replacement id {new} builds",  civ_def([[new, 1]], []), slot + 3)

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
