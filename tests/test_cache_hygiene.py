#!/usr/bin/env python3
"""Old caches are pruned at startup, and the browser never keeps old assets.

A player's first launch of 2.7.0-preview.1 showed old assets: Flask sent our
JS/CSS with no Cache-Control, so the browser could reuse last version's files
on a heuristic from Last-Modified.  Static files now revalidate and carry
?v=<version>; game art revalidates too (its URL stays the same when the
renderer changes).  Every renamed cache folder (icons, icons-rgb, previews-v1..)
and all but the newest parsed-DAT indexes are deleted at startup.

    venv/bin/python tests/test_cache_hygiene.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["EMPIREFORGE_DATA_DIR"] = tempfile.mkdtemp()

import app as webapp                       # noqa: E402
from version import __version__            # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


print("browser caching")
c = webapp.app.test_client()
page = c.get("/").get_data(as_text=True)
check("static URLs carry the version", f"?v={__version__}" in page)
r = c.get("/static/data/bonus_cards.json")
check("static files revalidate (max-age=0)", "max-age=0" in r.headers.get("Cache-Control", ""), r.headers.get("Cache-Control"))
etag = r.headers.get("ETag")
check("...answered 304 when unchanged", etag and c.get("/static/data/bonus_cards.json",
                                                       headers={"If-None-Match": etag}).status_code == 304)
src = (ROOT / "app.py").read_text(encoding="utf-8")
check("game art revalidates too (no day-long max_age left)", "max_age=86400" not in src)

print("startup pruning")
cache = webapp._cache_dir()
for name in ("icons", "icons-rgb", "icons-blue", "previews-v1", "previews-v3",
             f"previews-{webapp._PREVIEW_VERSION}", "unrelated"):
    (cache / name / "g").mkdir(parents=True)
    (cache / name / "g" / "1.webp").write_bytes(b"x")
(cache / "uu_stats_abc.json").write_text("{}", encoding="utf-8")
dat_cache = Path(os.environ["EMPIREFORGE_DATA_DIR"]) / "dat_cache"
dat_cache.mkdir()
now = time.time()
for i in range(12):
    f = dat_cache / f"{i:02d}.json"
    f.write_text("{}", encoding="utf-8")
    os.utime(f, (now - 1000 + i, now - 1000 + i))      # 11 newest .. 00 oldest
(dat_cache / "half.tmp").write_text("", encoding="utf-8")
removed = webapp.prune_caches()
left = {d.name for d in cache.iterdir()}
check("old icon and preview folders are gone", not {"icons", "icons-rgb", "previews-v1", "previews-v3"} & left, sorted(left))
check("the current ones stay", {"icons-blue", f"previews-{webapp._PREVIEW_VERSION}"} <= left)
check("other files and folders are left alone", {"unrelated", "uu_stats_abc.json"} <= left)
kept = sorted(f.name for f in dat_cache.iterdir())
check("the 8 most recently used DAT indexes stay", kept == [f"{i:02d}.json" for i in range(4, 12)], kept)
check("a half-written one goes", not (dat_cache / "half.tmp").exists())
check("it says what it removed", len(removed) == 4 + 4 + 1, removed)
check("a second run removes nothing", webapp.prune_caches() == [])

print("a DAT index read is a use")
import dat_lazy                            # noqa: E402
f = dat_cache / "04.json"
f.write_text('{"version": %d}' % dat_lazy.CACHE_VERSION, encoding="utf-8")
os.utime(f, (now - 5000, now - 5000))
dat_lazy._read_cache("04")
check("reading it refreshes its mtime", f.stat().st_mtime > now - 10)

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
