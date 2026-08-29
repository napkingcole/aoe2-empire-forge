#!/usr/bin/env python3
"""Normalise gathered scene-unit art (Monks, starting Scouts) into static/img/scene/.

Each unit slot in the identity scene takes TWO variants, because one image
can't do both jobs:

    scene   the in-game sprite cut out on its patch of grass — stands in the
            scene next to the buildings
    picker  the standard square in-game button icon — used in the picker grid

Drop sources in, named by what they are, and this maps them onto the numeric
filenames the wizard loads:

    ignore/monk_art/european.png          -> static/img/scene/monks/monk_1.webp
    ignore/monk_art/icons/european.png    -> static/img/scene/monks/icons/monk_1.webp
    ignore/scout_art/eagle_scout.png      -> static/img/scene/scouts/scout_751.webp
    ignore/scout_art/icons/eagle_scout.png-> static/img/scene/scouts/icons/scout_751.webp

Slugs are matched loosely: case, spaces, hyphens and underscores are ignored,
and common aliases are accepted (muslim -> Middle Eastern, inca -> Andean,
eagle -> Eagle Scout).  Unrecognised names are reported rather than guessed at.

IMPORTANT: existing outputs are skipped, so *replacing* art needs --force.
Run with no arguments to see what is still missing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  ./venv/bin/pip install Pillow")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from civ_appender import MONK_SKIN_OPTIONS  # noqa: E402
from app import _SCOUT_OPTIONS              # noqa: E402

SCENE_IMG = ROOT / "static" / "img" / "scene"

MAX_HEIGHT = 256
QUALITY = 82

# Alternative names, so a sensibly-named capture just works.
ALIASES = {
    # monks
    "catholic": "european", "western": "european", "latin": "european",
    "byzantine": "orthodox", "slavic": "orthodox",
    "muslim": "middleeastern", "islamic": "middleeastern", "saracen": "middleeastern",
    "persian": "middleeastern", "me": "middleeastern",
    "tengri": "centralasian", "mongol": "centralasian", "steppe": "centralasian",
    "hindu": "southasian", "indian": "southasian", "buddhist": "southasian",
    "asian": "eastasian",
    "meso": "mesoamerican", "aztec": "mesoamerican", "mayan": "mesoamerican",
    "inca": "andean", "incan": "andean", "southamerican": "andean",
    "spanish": "mediterranean",
    "ethiopian": "african",
    # scouts
    "scout": "scoutcavalry", "horse": "scoutcavalry", "default": "scoutcavalry",
    "eagle": "eaglescout", "eaglewarrior": "eaglescout",
    "camel": "camelscout",
    "champi": "champirunner", "champirunner": "champirunner",
}

# (key, options, source dir, output dir stem)
KINDS = {
    "monk":  (MONK_SKIN_OPTIONS, ROOT / "ignore" / "monk_art",  SCENE_IMG / "monks",  "monk"),
    "scout": (_SCOUT_OPTIONS,    ROOT / "ignore" / "scout_art", SCENE_IMG / "scouts", "scout"),
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def build_lookup(options) -> dict[str, tuple[int, str]]:
    table: dict[str, tuple[int, str]] = {}
    for opt in options:
        table[slug(opt["label"])] = (opt["value"], opt["label"])
        table[str(opt["value"])] = (opt["value"], opt["label"])
    for alias, canonical in ALIASES.items():
        if canonical in table:
            table.setdefault(alias, table[canonical])
    return table


def import_kind(kind: str, force: bool) -> tuple[int, list[str]]:
    options, src_root, out_root, stem = KINDS[kind]
    table = build_lookup(options)
    written, unknown = 0, []

    variants = (("scene", src_root, out_root),
                ("picker", src_root / "icons", out_root / "icons"))

    for name, src_dir, out_dir in variants:
        out_dir.mkdir(parents=True, exist_ok=True)
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.iterdir()):
            if src.suffix.lower() not in {".png", ".webp", ".jpg", ".jpeg"}:
                continue
            hit = table.get(slug(src.stem))
            if not hit:
                unknown.append(f"{kind}/{name}/{src.name}")
                continue
            value, label = hit
            dest = out_dir / f"{stem}_{value}.webp"
            if dest.exists() and not force:
                continue
            im = Image.open(src).convert("RGBA")
            if im.height > MAX_HEIGHT:
                im = im.resize((round(im.width * MAX_HEIGHT / im.height), MAX_HEIGHT),
                               Image.LANCZOS)
            im.save(dest, "WEBP", quality=QUALITY, method=6)
            print(f"  [{kind} {name}] {src.name}  ->  {stem}_{value}.webp   ({label})")
            written += 1

    return written, unknown


def report(kind: str) -> None:
    options, _src, out_root, stem = KINDS[kind]
    for name, out_dir in (("scene", out_root), ("picker", out_root / "icons")):
        have = [o for o in options if (out_dir / f"{stem}_{o['value']}.webp").exists()]
        missing = [o for o in options if o not in have]
        print(f"  {kind:<5} {name:<7} {len(have)}/{len(options)}"
              + ("" if not missing else
                 "   missing: " + ", ".join(o["label"] for o in missing)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", nargs="?", choices=sorted(KINDS), default=None,
                    help="import only monks or only scouts (default: both)")
    ap.add_argument("--force", action="store_true",
                    help="re-encode even if the output already exists "
                         "(needed when REPLACING art, not just adding)")
    args = ap.parse_args()

    kinds = [args.kind] if args.kind else sorted(KINDS)
    total, unknown = 0, []
    for kind in kinds:
        w, u = import_kind(kind, args.force)
        total += w
        unknown += u

    print(f"\n{total} imported")
    for kind in kinds:
        report(kind)

    if unknown:
        print(f"\nUnrecognised filenames: {', '.join(unknown)}")
        for kind in kinds:
            names = ", ".join(slug(o["label"]) for o in KINDS[kind][0])
            print(f"  valid {kind} names: {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
