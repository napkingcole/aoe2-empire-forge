#!/usr/bin/env python3
"""One-time import of Krakenmeister's building art into static/img/scene/.

KM's civ builder ships complete, consistently-rendered isometric art for the
three buildings the identity scene needs.  His index convention is the same one
we inherited (``value = dat_index - 1``, 0 = Britons), so ``castle_{N}`` maps
straight onto ``draft.castle`` with no lookup table:

    castles/castle_N.png    N = draft.castle    (50, 250x250)
    wonders/wonder_N.png    N = draft.wonder    (50, 2352x2352)
    architectures/tc_N.png  N = draft.architecture (11, 512x380)

The wonders are 99 MB of 2352px PNG at source, which is why they get resized;
everything lands as WebP under static/img/scene/ at roughly 2.4 MB total.

Also extracts KM's display-name arrays into static/data/scene_names.json so the
wizard can label a wonder by what it actually is ("Hagia Sophia") rather than by
whose it is ("Byzantines").

Re-runnable.  Skips files whose output is newer than the source unless --force.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  ./venv/bin/pip install Pillow")

ROOT = Path(__file__).resolve().parent.parent
KM = ROOT / "ignore" / "AoE2-Civbuilder-main"
KM_IMG = KM / "public" / "img"
KM_DATA = KM / "src" / "frontend" / "app" / "composables" / "useCivData.ts"

OUT_IMG = ROOT / "static" / "img" / "scene"
OUT_DATA = ROOT / "static" / "data" / "scene_names.json"

# (source subdir, stem, output subdir, index range, target width or None for native)
JOBS = [
    ("castles",       "castle", "castles", range(0, 50), None),
    ("wonders",       "wonder", "wonders", range(0, 50), 384),
    ("architectures", "tc",     "arch",    range(1, 13), 512),
]

QUALITY = 80

# Art KM never shipped, gathered by hand and named after the civ / architecture
# set rather than its index:  ignore/building_art/castles/muisca.webp etc.
# The three South American civs and the South American town centre postdate his
# snapshot, so they can only arrive this way.  Sizes match the KM jobs above so
# the two sources are indistinguishable in the scene.
EXTRA_SRC = ROOT / "ignore" / "building_art"
EXTRA_JOBS = [
    # (source subdir, stem, output subdir, max longest side, option source)
    ("castles", "castle", "castles", 250, "civ"),
    ("wonders", "wonder", "wonders", 384, "civ"),
    ("arch",    "tc",     "arch",    512, "arch"),
]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _option_lookup() -> dict[str, dict[str, int]]:
    """slug -> value, for civs (castle/wonder) and architectures (tc)."""
    sys.path.insert(0, str(ROOT))
    import json as _json
    civs = _json.loads((ROOT / "civilizations.json").read_text())["civilization_list"]
    from app import _ARCH_OPTIONS
    return {
        # civ option value is the DAT index minus one, matching draft.castle
        "civ": {_slug(c.get("internal_name") or ""): i - 1
                for i, c in enumerate(civs) if i > 0 and c.get("internal_name")},
        "arch": {_slug(o["label"]): o["value"] for o in _ARCH_OPTIONS},
    }


def convert_extras(force: bool = False) -> tuple[int, list[str]]:
    """Import hand-gathered art named by civ/architecture instead of by index."""
    if not EXTRA_SRC.is_dir():
        return 0, []
    lookup = _option_lookup()
    written, unknown = 0, []

    for sub, stem, dest_name, max_side, kind in EXTRA_JOBS:
        src_dir = EXTRA_SRC / sub
        if not src_dir.is_dir():
            continue
        dest_dir = OUT_IMG / dest_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        for src in sorted(src_dir.iterdir()):
            if src.suffix.lower() not in {".png", ".webp", ".jpg", ".jpeg"}:
                continue
            value = lookup[kind].get(_slug(src.stem))
            if value is None:
                unknown.append(f"{sub}/{src.name}")
                continue
            dest = dest_dir / f"{stem}_{value}.webp"
            if dest.exists() and not force and dest.stat().st_mtime >= src.stat().st_mtime:
                continue
            im = Image.open(src).convert("RGBA")
            if max(im.size) > max_side:
                scale = max_side / max(im.size)
                im = im.resize((round(im.width * scale), round(im.height * scale)),
                               Image.LANCZOS)
            im.save(dest, "WEBP", quality=QUALITY, method=6)
            print(f"  [extra] {sub}/{src.name}  ->  {stem}_{value}.webp  {im.size}")
            written += 1
    return written, unknown


def extract_names() -> dict[str, list[str]]:
    """Pull KM's display-name arrays out of useCivData.ts.

    Two wonder entries are double-quoted because they contain apostrophes
    ("Humayun's Tomb", "Jing'an Temple"), so both quote styles must be matched.
    """
    src = KM_DATA.read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    for name in ("wonders", "castles", "languages", "architectures"):
        m = re.search(rf"export const {name} = \[(.*?)\n\]", src, re.S)
        if not m:
            print(f"  !  could not find '{name}' array in useCivData.ts")
            continue
        items = []
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            q = re.match(r"""(['"])((?:[^\\]|\\.)*?)\1""", line)
            if q:
                items.append(q.group(2).replace("\\'", "'"))
        out[name] = items
    return out


def convert(force: bool = False) -> tuple[int, int, list[str]]:
    written = skipped = 0
    missing: list[str] = []

    for sub, stem, dest_name, rng, width in JOBS:
        src_dir = KM_IMG / sub
        dest_dir = OUT_IMG / dest_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        for i in rng:
            src = src_dir / f"{stem}_{i}.png"
            dest = dest_dir / f"{stem}_{i}.webp"
            if not src.exists():
                missing.append(f"{sub}/{stem}_{i}.png")
                continue
            if dest.exists() and not force and dest.stat().st_mtime >= src.stat().st_mtime:
                skipped += 1
                continue

            im = Image.open(src).convert("RGBA")
            if width and im.width > width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            im.save(dest, "WEBP", quality=QUALITY, method=6)
            written += 1

        got = len(list(dest_dir.glob(f"{stem}_*.webp")))
        total = sum(1 for _ in rng)
        size = sum(f.stat().st_size for f in dest_dir.glob("*.webp"))
        print(f"  {dest_name:8s} {got}/{total} files, {size / 1048576:.1f} MB"
              f"{f' @{width}px' if width else ' (native)'}")

    return written, skipped, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-encode even if up to date")
    args = ap.parse_args()

    if not KM_IMG.is_dir():
        sys.exit(f"KM art not found at {KM_IMG}\n"
                 f"Expected the vendored civbuilder checkout under ignore/.")

    print(f"Importing KM art  {KM_IMG}  ->  {OUT_IMG}")
    written, skipped, missing = convert(force=args.force)

    extra_written, extra_unknown = convert_extras(force=args.force)
    written += extra_written

    names = extract_names()
    OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_DATA.write_text(json.dumps(names, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  names    {OUT_DATA.relative_to(ROOT)}  "
          + ", ".join(f"{k}={len(v)}" for k, v in names.items()))

    total = sum(f.stat().st_size for f in OUT_IMG.rglob("*.webp"))
    print(f"\n{written} written, {skipped} up to date, {total / 1048576:.1f} MB total")

    if extra_unknown:
        print(f"\nUnrecognised names in {EXTRA_SRC.relative_to(ROOT)}: "
              + ", ".join(extra_unknown))
        print("  Name these after the civ (muisca.webp) or architecture set "
              "(south_american.webp).")
    if missing:
        print(f"\nMissing from KM's set ({len(missing)}) — drop hand-gathered art in "
              f"{EXTRA_SRC.relative_to(ROOT)}/<castles|wonders|arch>/ named after the civ:")
        for m in missing:
            print(f"  - {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
