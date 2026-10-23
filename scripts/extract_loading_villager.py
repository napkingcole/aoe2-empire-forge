#!/usr/bin/env python3
"""The loading spinner: a Villager hammering at a foundation, in Player 1 Blue,
facing south-west.  Rendered once from the game's own sprite and shipped as
static/img/villager-building.webp — it shows while the app is still finding
the game, so it can't be read from the player's files at that moment.

The graphic is the male builder's build task (action 101), read from the DAT
rather than hard-coded, so a patch that renumbers it is followed.

    venv/bin/python scripts/extract_loading_villager.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import game_sprites                                         # noqa: E402
from dat_reader import find_game_dat, load_dat              # noqa: E402

BUILDER, BUILD = 118, 101                                   # male Villager (builder), action "build"
OUT = ROOT / "static" / "img" / "villager-building.webp"


def main() -> None:
    dat_path = find_game_dat()
    if dat_path is None:
        sys.exit("No game DAT found.")
    dat = load_dat(str(dat_path))
    task = next(t for t in dat.civs[0].units[BUILDER].bird.tasks if t.action_type == BUILD)
    gid = task.proceeding_graphic_id                        # the hammering, not the seeding
    webp = game_sprites.graphic_webp(dat, dat_path, gid)
    if webp is None:
        sys.exit(f"No sprite for graphic {gid} ({dat.graphics[gid].file_name}).")
    OUT.write_bytes(webp)
    print(f"Wrote {OUT} ({len(webp) // 1024} KB) from graphic {gid} {dat.graphics[gid].file_name}")


if __name__ == "__main__":
    main()
