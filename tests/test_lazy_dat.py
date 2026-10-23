#!/usr/bin/env python3
"""Lazy DAT loading (dat_lazy) writes exactly what a full parse writes.

load_dat leaves each civ's units as raw bytes until something reads them, and
writes untouched civs straight back from those bytes.  That is only safe if the
result is byte-identical to genieutils' own full parse-and-save, so that is the
assertion: for an untouched DAT, and for a real build.  DAT-gated; the slowest
file in the suite, so tests/run_tests.py starts it first.

    venv/bin/python tests/test_lazy_dat.py
"""
import contextlib
import copy
import io
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["EMPIREFORGE_DATA_DIR"] = tempfile.mkdtemp()      # a cold offset cache

from dat_reader import find_game_dat, load_dat              # noqa: E402
from genieutils.datfile import DatFile                       # noqa: E402
from civ_appender import apply_civ                           # noqa: E402
import dat_lazy                                              # noqa: E402

failures = 0


def check(label, ok, detail=""):
    global failures
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        failures += 1
        if detail:
            print(f"       {detail}")


path = find_game_dat()
if path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

first = load_dat(path)                                       # full parse, writes the cache
t = time.perf_counter()
lazy = load_dat(path)
took = time.perf_counter() - t
parsed = [i for i, c in enumerate(lazy.civs) if c.units.materialized]
check(f"a second load uses the offset cache and parses no civ ({took:.1f}s)",
      not parsed and took < 6, parsed)

eager = DatFile.parse(str(path))
# The reference every comparison below uses.  Computed once: serializing a
# full parse is slow, and the test used to redo it (and re-parse the DAT just
# to get it back) four times.
EAGER_BYTES = eager.to_bytes()
check("an untouched DAT saves byte-identical to a full parse", lazy.to_bytes() == EAGER_BYTES)
check("so does the first (cache-writing) load", first.to_bytes() == EAGER_BYTES)
del first                                 # each DAT is ~0.5 GB; keep only what is still read

clone = copy.deepcopy(lazy.civs[1])
check("copying an untouched civ copies its bytes, not its units",
      not clone.units.materialized and len(clone.units) == len(eager.civs[1].units))
check("...and the copy reads back the same units",
      clone.units[38].hit_points == eager.civs[1].units[38].hit_points)

# Two threads reading one civ at once must not fill its list twice.
shared = load_dat(path)
threads = [threading.Thread(target=lambda: shared.civs[5].units[0]) for _ in range(8)]
for th in threads:
    th.start()
for th in threads:
    th.join()
check("concurrent first reads parse a civ once", len(shared.civs[5].units) == len(eager.civs[5].units))

# One unit at a time: the shape of "for civ in dat.civs: civ.units[X] = ...",
# which km_custom_uu and the Royal/Imperial unit setups use on every civ.
probe = load_dat(path).civs[7].units
_ = probe[38].hit_points
check("reading one unit parses just that unit", not probe.materialized and len(probe._over) == 1)
last, want = probe[-1], eager.civs[7].units[-1]
check("a negative index reads the last unit",
      (last is None) == (want is None) and (last is None or last.name == want.name))
n = len(probe)
probe.append(None)
check("appending keeps the list unparsed and counts the new entry",
      not probe.materialized and len(probe) == n + 1)

one = load_dat(path)
for dat in (one, eager):                 # identical edits: a copied unit in every civ, one HP change
    for civ in dat.civs:
        civ.units.append(copy.deepcopy(civ.units[4]))
    dat.civs[7].units[38].hit_points += 7
check("per-unit edits and appends save byte-identical to the same edits on a full parse",
      one.to_bytes() == eager.to_bytes())
check("...without parsing any civ in full", not any(c.units.materialized for c in one.civs))
del one, eager, shared, probe, clone

# A real build: header edits, a cloned civ, unit edits, appended techs/effects.
CIV = {"alias": "LazyProbe", "architecture": 6, "language": 3,
       "bonuses": [{"id": b, "multiplier": 2} for b in (55, 102, 249, 441)],
       "team_bonuses": [{"id": 7, "multiplier": 1}],
       "unique_unit": {"km_idx": 11},
       "tree": {"units": [4, 7, 38, 39, 74, 280, 2485], "buildings": [12, 87, 101, 82], "techs": []}}
outs = []
for make in (lambda: load_dat(path), lambda: DatFile.parse(str(path))):
    dat = make()
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, copy.deepcopy(CIV), target_slot=3)
    outs.append(dat.to_bytes())
    del dat
check("a full apply_civ build saves byte-identical, lazy vs eager", outs[0] == outs[1])

# Saving: level-3 raw deflate (dat_lazy.SAVE_LEVEL) — any level inflates to
# the same bytes — and the mod zip stores the already-compressed DAT as is.
import zipfile                                               # noqa: E402
import zlib                                                  # noqa: E402
from build_all import _build_combined_data_zip               # noqa: E402
saved = dat_lazy.save_bytes(lazy)
check("the saved DAT inflates to exactly the bytes a full parse writes",
      zlib.decompress(saved, wbits=-15) == EAGER_BYTES)
with zipfile.ZipFile(io.BytesIO(_build_combined_data_zip(lazy, {}, {}))) as zf:
    info = zf.getinfo("resources/_common/dat/empires2_x2_p1.dat")
    check("the mod zip stores the DAT uncompressed, and it reads back intact",
          info.compress_type == zipfile.ZIP_STORED
          and zlib.decompress(zf.read(info), wbits=-15) == EAGER_BYTES)

# A stand-in for DatFile.parse: that it is called is the whole fallback, and a
# real full parse here cost ~20s of the test's run time.
os.environ["EMPIREFORGE_EAGER_DAT"] = "1"
_real_datfile, calls = dat_lazy.DatFile, []
dat_lazy.DatFile = type("DatFileProbe", (), {"parse": staticmethod(lambda p: calls.append(p) or "eager")})
try:
    check("EMPIREFORGE_EAGER_DAT=1 falls back to the plain parse",
          dat_lazy.parse(path) == "eager" and calls == [str(path)], calls)
finally:
    dat_lazy.DatFile = _real_datfile

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
