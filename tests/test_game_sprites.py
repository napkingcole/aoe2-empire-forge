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

print("\n=== blocks kept from the previous frame, when the box moves ===")
# Frame 0 draws one solid block at (4,0)-(8,4).  Frame 1's box starts 4 px
# left, at (0,0)-(8,4), sets flag 0x80 and SKIPS both blocks: its second block
# is frame 0's, at the same canvas spot.  Honouring 0x80 only for an unchanged
# box left kept blocks transparent — square holes that looped (2026-10-22).
red = rgb565(255, 0, 0)
solid = struct.pack("<HHI", red, 0, 0)
f0 = struct.pack("<HHHHBBH", 8, 4, 0, 0, 0x01, 0, 0) + layer(
    struct.pack("<HHHHBB", 4, 0, 8, 4, 0, 0) + struct.pack("<H", 1) + bytes([0, 1]) + solid)
f1 = struct.pack("<HHHHBBH", 8, 4, 0, 0, 0x01, 0, 1) + layer(
    struct.pack("<HHHHBB", 0, 0, 8, 4, 0x80, 0) + struct.pack("<H", 1) + bytes([2, 0]))
two = b"SLDX" + struct.pack("<HHHH", 4, 2, 0, 16) + b"\0" * 4 + f0 + f1
img1, _ = gs.render_frame(two, 1)
check("the kept block comes through at its canvas position", (img1[:, 4:8, 3] == 255).all()
      and (img1[:, 4:8, 0] > 200).all(), str(img1[0, 4].tolist()))
check("...and the new box's other block stays empty", (img1[:, 0:4] == 0).all())

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
    # The Ninja's walk is 17 ms a frame in the DAT — 10 ms at Normal speed,
    # which browsers play as 100 ms.  Frames drop evenly instead; the stride
    # still takes as long as in the game.
    ninja = units[1145]
    g = dat.graphics[gs.unit_graphic(ninja, "walk")]
    frames, ms = gs.unit_frames(dat, dat_path, ninja, "walk")
    game_s = g.frame_count * g.frame_duration / gs.NORMAL_SPEED
    check(f"Ninja walk: no frame under {gs.MIN_FRAME_MS} ms ({ms} ms)", ms >= gs.MIN_FRAME_MS)
    check(f"...and the stride still takes the game's {game_s:.2f} s ({len(frames) * ms / 1000:.2f} s)",
          abs(len(frames) * ms / 1000 - game_s) < 0.03)
    sprite = gs.find_sprite(dat_path, dat.graphics[q.standing_graphic[0]].file_name)
    has_x2 = (gs.graphics_folder(dat_path) / (dat.graphics[q.standing_graphic[0]].file_name[:-3] + "_x2.sld")).exists()
    check("the Enhanced Graphics _x2 sprite is used when the game has it",
          sprite is not None and sprite.name.endswith("_x2.sld") == has_x2, sprite)
    still = gs.still_webp(dat, dat_path, q)
    check("a still renders", still is not None and len(still) > 1000, len(still or b""))
    for uid, name in ((1222, "Sharkatzor (a graphic with deltas)"), (844, "Admiral Yi (a ship)"),
                      (2612, "War Dog"), (1690, "Warwolf Trebuchet")):
        check(f"{name} renders", gs.still_webp(dat, dat_path, units[uid]) is not None)

    print("\n=== the identity scene, from the game ===")
    # Every option the wizard offers draws the game's own sprite (2026-10-23):
    # the bundled pictures had no art for 28 wonders or the South American
    # Town Center, and the cut-out Monks were blurry.
    from civ_appender import MONK_SKIN_OPTIONS, MONASTERY_SKIN_OPTIONS
    import app as webapp
    archs = sorted({c.icon_set for c in dat.civs[1:]})
    missing = [("architecture", v) for v in archs if gs.scene_still(dat, dat_path, "architecture", v) is None]
    missing += [(s, i - 1) for i in range(1, len(dat.civs)) for s in ("wonder", "castle")
                if gs.scene_still(dat, dat_path, s, i - 1) is None]
    missing += [("monastery_skin_building", o["value"]) for o in MONASTERY_SKIN_OPTIONS
                if gs.scene_still(dat, dat_path, "monastery_skin_building", o["value"]) is None]
    missing += [("monk_skin", o["value"]) for o in MONK_SKIN_OPTIONS
                if gs.scene_still(dat, dat_path, "monk_skin", o["value"]) is None]
    missing += [("starting_scout", o["value"]) for o in webapp._SCOUT_OPTIONS
                if gs.scene_still(dat, dat_path, "starting_scout", o["value"]) is None]
    check(f"every architecture ({len(archs)}), wonder, castle, Monastery, Monk and scout renders",
          not missing, missing[:6])
    # A Town Center is four units; the scene draws the game's whole-building
    # "Preview" sprite with the back piece's shadow under it.
    gid, under = gs._scene_graphic(dat, "architecture", 2)
    tc = gs.graphic_frames(dat, dat_path, gid, still=True, under=under)[0][0]
    bare = gs.graphic_frames(dat, dat_path, gid, still=True)[0][0]
    check("the Town Center carries its shadow", tc.size[0] >= bare.size[0] and tc.getbbox() is not None
          and sum(tc.getchannel("A").histogram()[1:]) > sum(bare.getchannel("A").histogram()[1:]))
    check("an unknown value is no art, not a crash", gs.scene_still(dat, dat_path, "wonder", 999) is None)
    # Faint shadow specks hundreds of pixels below the Persian and Varangian
    # wonders (alpha <= 37) stretched the crop: the scene showed them mostly
    # empty grass.  The crop counts solid pixels only.
    import numpy as np
    for name in ("Persians", "Varangians"):
        i = [c.name for c in dat.civs].index(name)
        a = np.array(gs.scene_still(dat, dat_path, "wonder", i - 1).getchannel("A"))
        solid = np.where(a.max(axis=1) >= gs._SOLID)[0]
        check(f"the {name}' wonder is cropped to the building (no empty band below)",
              a.shape[0] - 1 - solid.max() <= 12, f"{a.shape[0] - 1 - solid.max()} empty rows")
    check("buildings are stored at half size, units at full",
          gs.scene_still(dat, dat_path, "castle", 0).size[0] < 600
          and gs.scene_still(dat, dat_path, "monk_skin", 1).size == gs.unit_frames(
              dat, dat_path, dat.civs[1].units[125], "idle", still=True)[0][0].size)
    # The scene reserves each building's spot while it renders, sized from the
    # sprite headers alone: close to the real art, never far off.
    off = []
    for slot, value in (("wonder", 0), ("wonder", 7), ("architecture", 2), ("architecture", 12),
                        ("castle", 14), ("monastery_skin_building", 12), ("monk_skin", 1),
                        ("starting_scout", 1755)):
        est, real = gs.scene_size(dat, dat_path, slot, value), gs.scene_still(dat, dat_path, slot, value).size
        if any(abs(e - r) > max(10, 0.1 * r) for e, r in zip(est, real)):
            off.append((slot, value, est, real))
    check("the reserved size is within 10% of the art", not off, off)
    check("the Tupi wonder and the shrine are known to move; a castle doesn't",
          gs.scene_animated(dat, "wonder", [c.name for c in dat.civs].index("Tupi") - 1)
          and gs.scene_animated(dat, "monastery_skin_building", 12)
          and not gs.scene_animated(dat, "castle", 0))

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
