#!/usr/bin/env python3
"""Unit previews: the SLD decoder (game_sprites) and its timing rules.

Part 1 needs no game: it builds a one-frame SLD in memory with known blocks —
a solid DXT1 block, a three-colour block whose fourth colour is transparent,
a skipped block, a BC4 player-colour mask — under both header lengths the
game ships (16, and 14 in 431 files), and checks the pixels exactly.
Part 2 (DAT-gated) renders real units: the agreed facing, frame counts and
Normal-speed timing from the DAT, and the Enhanced Graphics preference.

    venv/bin/python tests/test_game_sprites.py
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                          # noqa: E402
import game_sprites as gs                                   # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def layer(body: bytes) -> bytes:
    data = struct.pack("<I", 4 + len(body)) + body
    return data + b"\0" * (-len(data) % 4)


def make_sld(header_len: int) -> bytes:
    """One 12x4 frame, hotspot (2, 3): main layer box (0,0)-(12,4) = 3 blocks.
    Commands: draw 1, skip 1, draw 1.  Block A solid red (four-colour mode,
    every index 0); block C three-colour mode, every index 3 = transparent.
    Player mask over the same box: block A full (255) — skip — C none."""
    red = rgb565(255, 0, 0)
    block_a = struct.pack("<HHI", red, 0, 0)                     # c0 > c1, index 0 -> red
    block_c = struct.pack("<HHI", 0, red, 0xFFFFFFFF)            # c0 <= c1, index 3 -> clear
    main = (struct.pack("<HHHHBB", 0, 0, 12, 4, 0, 0) + struct.pack("<H", 2)
            + bytes([0, 1, 1, 1]) + block_a + block_c)
    full = bytes([255, 0]) + b"\0" * 6                          # BC4: every index 0 -> 255
    none = bytes([0, 0]) + b"\0" * 6
    player = struct.pack("<BB", 0, 0) + struct.pack("<H", 2) + bytes([0, 1, 1, 1]) + full + none
    frame = struct.pack("<HHHHBBH", 12, 4, 2, 3, 0x01 | 0x10, 0, 0) + layer(main) + layer(player)
    header = b"SLDX" + struct.pack("<HHHH", 4, 1, 0, header_len) + b"\0" * (header_len - 12)
    return header + frame


print("=== the decoder, on a file made here ===")
for header_len in (16, 14):
    data = make_sld(header_len)
    frames = gs.frame_index(data)
    check(f"[{header_len}-byte header] one 12x4 frame, hotspot (2, 3)",
          len(frames) == 1 and (frames[0]["w"], frames[0]["h"], frames[0]["hot"]) == (12, 4, (2, 3)), frames)
    img, hot = gs.render_frame(data, 0)
    a, b, c = img[:, 0:4], img[:, 4:8], img[:, 8:12]
    check(f"[{header_len}] a drawn block is opaque", (a[..., 3] == 255).all(), a[..., 3])
    check(f"[{header_len}] ...and, wholly player colour, painted Player 1 Blue (from red's brightness)",
          (a[..., 2] > a[..., 0]).all(), a[0, 0])
    check(f"[{header_len}] a skipped block stays empty", (b == 0).all())
    check(f"[{header_len}] DXT1 colour 3 in three-colour mode is transparent", (c[..., 3] == 0).all(), c[0, 0])

try:
    gs.frame_index(b"")
    check("...ValueError for an empty file", False)
except ValueError:
    check("...ValueError for an empty file", True)

print("\n=== real units (DAT-gated) ===")
from dat_reader import find_game_dat, load_dat            # noqa: E402
dat_path = find_game_dat()
if dat_path is None or gs.graphics_folder(dat_path) is None:
    print("  skip  no game install with sprites found")
else:
    dat = load_dat(str(dat_path))
    units = dat.civs[0].units
    q = units[1817]                                           # Qizilbash Warrior
    for kind in gs.ANIMATIONS:
        g = dat.graphics[gs.unit_graphic(q, kind)]
        frames, ms = gs.unit_frames(dat, dat_path, q, kind)
        check(f"Qizilbash {kind}: all {g.frame_count} frames", len(frames) == g.frame_count, len(frames))
        check(f"Qizilbash {kind}: {ms} ms a frame = the DAT's {g.frame_duration * 1000:.1f} at Normal speed (÷1.7)",
              ms == round(g.frame_duration * 1000 / gs.NORMAL_SPEED))
    sprite = gs.find_sprite(dat_path, dat.graphics[q.standing_graphic[0]].file_name)
    has_x2 = (gs.graphics_folder(dat_path) / (dat.graphics[q.standing_graphic[0]].file_name[:-3] + "_x2.sld")).exists()
    check("the Enhanced Graphics _x2 sprite is used when the game has it",
          sprite is not None and sprite.name.endswith("_x2.sld") == has_x2, sprite)
    still = gs.still_webp(dat, dat_path, q)
    check("a still renders", still is not None and len(still) > 1000, len(still or b""))
    for uid, name in ((1222, "Sharkatzor (a graphic with deltas)"), (844, "Admiral Yi (a ship)"),
                      (2612, "War Dog"), (1690, "Warwolf Trebuchet")):
        check(f"{name} renders", gs.still_webp(dat, dat_path, units[uid]) is not None)

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
