"""Unit previews: frames of a unit's in-game sprite, read from the player's game.

DE draws units from `.sld` files in `<game>/resources/_common/drs/graphics/`
(`<file_name>.sld` for the graphic the DAT names; the Enhanced Graphics pack
adds a sharper `_x2` twin, preferred when present).  SLD v4, as documented by
openage (doc/media/sld-files.md):

  header   "SLDX" u16 version (4), u16 frames, u16, u16 header length, ...
           — the header length is 16 in most files but 14 in 431 of the
           15,484 in the game (the elite Huskarl and Genoese Crossbowman);
           frames start there.  Two files are empty.
  frame    u16 width, height, hotspot x, y; u8 layer flags; u8; u16 index
  layers   in flag-bit order: 0x01 main, 0x02 shadow, 0x04 outline,
           0x08 damage mask, 0x10 player-colour mask.  Each: u32 length
           (including itself, padded to 4), then
             main/shadow/outline: u16 x1, y1, x2, y2; u8 flags; u8
             damage/player:       u8 flags; u8   (the main layer's box)
           u16 command count; (u8 skip, u8 draw) pairs over 4x4 blocks in
           row order; then the drawn blocks — DXT1 (main, damage) or BC4
           (shadow, player) at 8 bytes each.  flags & 0x80: skipped blocks keep
           the previous frame's pixels.
  The outline layer (0x04) has a different layout; previews don't need it.

Frames run angle by angle, frame_count per angle; angle 0 faces east and they
go clockwise, so south-west — the facing previews use — is angle 6 of 16.
Timing: the DAT's frame_duration is at game speed 1.0; "Normal" is 1.7.  Judge
speed in a browser: macOS Preview plays animated WebP slowly.

Agreed with the user 2026-10-21/22: facing south-west, Player 1 Blue, every
animation at its own DAT timing ÷ 1.7 with all its frames — except one whose
frames would be under MIN_FRAME_MS, which browsers slow down (see there).
"""
import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image

from game_art import player_tint

NORMAL_SPEED = 1.7
# Browsers play a frame of 10 ms or less as 100 ms (Chrome, and Firefox below
# ~20 ms), so the Ninja's and War Penguin's walks — 17 ms in the DAT, 10 ms at
# Normal speed — crawled.  Faster animations drop frames evenly instead, so a
# loop still takes as long as in the game.
MIN_FRAME_MS = 20
SOUTH_WEST = 6                      # of 16 angles; 0 = east, clockwise
_SOLID = 48                         # alpha that counts when cropping (shadow specks don't)
_MAIN, _SHADOW, _OUTLINE, _DAMAGE, _PLAYER = 0x01, 0x02, 0x04, 0x08, 0x10
_ORDER = [(_MAIN, "main", True), (_SHADOW, "shadow", True), (_OUTLINE, "outline", True),
          (_DAMAGE, "damage", False), (_PLAYER, "player", False)]
_DXT1_LAYERS = {"main", "damage"}


# ── Block decoders ────────────────────────────────────────────────────────────

def _dxt1(blocks: np.ndarray) -> np.ndarray:
    """(N, 8) uint8 -> (N, 4, 4, 4) RGBA.  Colour 3 is transparent in the
    three-colour mode (c0 <= c1)."""
    c = blocks[:, :4].view("<u2").astype(np.int32)
    bits = blocks[:, 4:].view("<u4")[:, 0].astype(np.uint64)

    def rgb(v):
        return np.stack([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63,
                         (v & 31) * 255 // 31], -1)
    a, b = rgb(c[:, 0]), rgb(c[:, 1])
    four = (c[:, 0] > c[:, 1])[:, None]
    pal = np.zeros((len(blocks), 4, 4), dtype=np.int32)
    pal[:, 0, :3], pal[:, 1, :3] = a, b
    pal[:, 2, :3] = np.where(four, (2 * a + b) // 3, (a + b) // 2)
    pal[:, 3, :3] = np.where(four, (a + 2 * b) // 3, 0)
    pal[:, :3, 3] = 255
    pal[:, 3, 3] = np.where(four[:, 0], 255, 0)
    idx = ((bits[:, None] >> (2 * np.arange(16, dtype=np.uint64))) & 3).astype(np.int64)
    px = np.take_along_axis(pal, idx[..., None].repeat(4, -1), 1)
    return px.reshape(-1, 4, 4, 4).astype(np.uint8)


def _bc4(blocks: np.ndarray) -> np.ndarray:
    """(N, 8) uint8 -> (N, 4, 4) uint8."""
    a0, a1 = blocks[:, 0].astype(np.int32), blocks[:, 1].astype(np.int32)
    bits = np.zeros(len(blocks), dtype=np.uint64)
    for k in range(6):
        bits |= blocks[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
    eight = (a0 > a1)[:, None]
    i = np.arange(8)
    p8 = ((8 - i) * a0[:, None] + (i - 1) * a1[:, None]) // 7
    p6 = ((6 - i) * a0[:, None] + (i - 1) * a1[:, None]) // 5
    pal = np.where(eight, p8, p6)
    pal[:, 0], pal[:, 1] = a0, a1
    pal[:, 6] = np.where(eight[:, 0], pal[:, 6], 0)
    pal[:, 7] = np.where(eight[:, 0], pal[:, 7], 255)
    idx = ((bits[:, None] >> (3 * np.arange(16, dtype=np.uint64))) & 7).astype(np.int64)
    return np.take_along_axis(pal, idx, 1).reshape(-1, 4, 4).astype(np.uint8)


# ── SLD ───────────────────────────────────────────────────────────────────────

def frame_index(data: bytes) -> list[dict]:
    """Headers only: per frame its offset, size, hotspot, layer flags, and
    whether any layer reuses the previous frame's pixels."""
    if len(data) < 16:
        raise ValueError("empty or truncated SLD file")
    sig, ver, n, _u, header = struct.unpack_from("<4sHHHH", data, 0)
    if sig != b"SLDX" or ver != 4:
        raise ValueError(f"not an SLD v4 file ({sig!r}, version {ver})")
    pos, out = header, []
    for _ in range(n):
        w, h, hx, hy, ftype, _u, _i = struct.unpack_from("<HHHHBBH", data, pos)
        start, p, reuses = pos, pos + 12, False
        for bit, name, has_box in _ORDER:
            if ftype & bit:
                (length,) = struct.unpack_from("<I", data, p)
                if name != "outline":
                    reuses |= bool(data[p + 4 + (8 if has_box else 0)] & 0x80)
                p += (length + 3) & ~3
        out.append({"offset": start, "w": w, "h": h, "hot": (hx, hy), "type": ftype, "reuses": reuses})
        pos = p
    return out


def _drawn_box(data: bytes, fr: dict) -> tuple | None:
    """The canvas box a frame's main and shadow layers cover, from their
    headers alone (the frame's own w/h is the whole, mostly empty, canvas)."""
    p, box = fr["offset"] + 12, None
    for bit, name, has_box in _ORDER:
        if not fr["type"] & bit:
            continue
        (length,) = struct.unpack_from("<I", data, p)
        if name == "main":
            b = struct.unpack_from("<HHHH", data, p + 4)
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
        p += (length + 3) & ~3
    return box


def _decode(data: bytes, fr: dict, prev: dict) -> dict:
    p, layers, main_box = fr["offset"] + 12, {}, None
    for bit, name, has_box in _ORDER:
        if not fr["type"] & bit:
            continue
        (length,) = struct.unpack_from("<I", data, p)
        q, nxt = p + 4, p + ((length + 3) & ~3)
        if name == "outline":
            p = nxt
            continue
        if has_box:
            x1, y1, x2, y2, flags, _ = struct.unpack_from("<HHHHBB", data, q)
            q += 10
            box = (x1, y1, x2, y2)
            if name == "main":
                main_box = box
        else:
            flags, _ = struct.unpack_from("<BB", data, q)
            q += 2
            box = main_box
        (ncmd,) = struct.unpack_from("<H", data, q)
        q += 2
        cmds = np.frombuffer(data, np.uint8, 2 * ncmd, q).reshape(-1, 2).astype(np.int64)
        q += 2 * ncmd
        bw, bh = (box[2] - box[0]) // 4, (box[3] - box[1]) // 4
        dxt = name in _DXT1_LAYERS
        img = np.zeros((bh * 4, bw * 4, 4) if dxt else (bh * 4, bw * 4), dtype=np.uint8)
        if flags & 0x80 and name in prev:
            # Skipped blocks keep the previous frame's pixels — in canvas terms:
            # the layer's box can move between frames.  Honouring this only for
            # an unchanged box left the kept blocks transparent: square holes
            # that looped with the animation (426 of 641 hero sprites use it).
            _copy_overlap(prev[name], box, img)
        if len(cmds) and bw:
            starts = np.cumsum(cmds[:, 0] + np.concatenate([[0], cmds[:-1, 1]]))
            drawn = np.concatenate([np.arange(s, s + d) for s, d in zip(starts, cmds[:, 1])])
            if len(drawn):
                blocks = np.frombuffer(data, np.uint8, 8 * len(drawn), q).reshape(-1, 8)
                px = _dxt1(blocks) if dxt else _bc4(blocks)
                by, bx = np.divmod(drawn, bw)
                view = img.reshape(bh, 4, bw, 4, *img.shape[2:]).swapaxes(1, 2)
                view[by, bx] = px
                img = view.swapaxes(1, 2).reshape(img.shape)
        layers[name] = (box, img)
        prev[name] = (box, img)
        p = nxt
    return layers


def _copy_overlap(previous: tuple, box: tuple, img: np.ndarray) -> None:
    """Copy the previous frame's layer pixels into `img` (at `box`) wherever
    the two boxes overlap on the canvas."""
    (px1, py1, px2, py2), pimg = previous
    x1, y1, x2, y2 = box
    ox1, oy1, ox2, oy2 = max(x1, px1), max(y1, py1), min(x2, px2), min(y2, py2)
    if ox1 < ox2 and oy1 < oy2:
        img[oy1 - y1:oy2 - y1, ox1 - x1:ox2 - x1] = pimg[oy1 - py1:oy2 - py1, ox1 - px1:ox2 - px1]


def render_frame(data: bytes, index: int, frames: list[dict] | None = None) -> tuple[np.ndarray, tuple]:
    """(RGBA canvas uint8, hotspot) for frame `index`: half-strength shadow,
    then the colour layer with its player-colour mask painted Player 1 Blue.
    Decodes from the nearest earlier frame that doesn't reuse its predecessor."""
    frames = frames or frame_index(data)
    start = index
    while start > 0 and frames[start]["reuses"]:
        start -= 1
    prev: dict = {}
    for i in range(start, index + 1):
        layers = _decode(data, frames[i], prev)
    fr = frames[index]
    canvas = np.zeros((fr["h"], fr["w"], 4), dtype=np.float32)
    if "shadow" in layers:
        (x1, y1, x2, y2), sh = layers["shadow"]
        canvas[y1:y2, x1:x2, 3] = sh.astype(np.float32) * 0.5
    if "main" in layers:
        (x1, y1, x2, y2), rgba = layers["main"]
        src = rgba.astype(np.float32)
        if "player" in layers:
            src[..., :3] = player_tint(src[..., :3], layers["player"][1].astype(np.float32)[..., None] / 255.0)
        region = canvas[y1:y2, x1:x2]
        a = src[..., 3:4] / 255.0
        region[..., :3] = src[..., :3] * a + region[..., :3] * (1 - a)
        region[..., 3:4] = np.maximum(region[..., 3:4], src[..., 3:4])
    return canvas.clip(0, 255).astype(np.uint8), fr["hot"]


# ── Units ─────────────────────────────────────────────────────────────────────

ANIMATIONS = ("idle", "walk", "attack")


def graphics_folder(dat_path) -> Path | None:
    parents = Path(dat_path).resolve().parents
    if len(parents) <= 3:
        return None
    folder = parents[3] / "resources" / "_common" / "drs" / "graphics"
    return folder if folder.is_dir() else None


def find_sprite(dat_path, file_name: str) -> Path | None:
    """The .sld for a DAT graphic's file name — the Enhanced Graphics `_x2`
    twin when the player has it, else the standard one."""
    folder = graphics_folder(dat_path) if dat_path and file_name else None
    if folder is None:
        return None
    names = [file_name[:-3] + "_x2", file_name] if file_name.endswith("_x1") else [file_name]
    for n in names:
        p = folder / f"{n}.sld"
        if p.is_file():
            return p
    return None


def unit_graphic(unit, kind: str) -> int:
    """The DAT graphic id for one of a unit's ANIMATIONS, or -1."""
    if kind == "idle":
        return unit.standing_graphic[0]
    if kind == "walk":
        return unit.dead_fish.walking_graphic if unit.dead_fish is not None else -1
    if kind == "attack":
        return unit.type_50.attack_graphic if unit.type_50 is not None else -1
    raise ValueError(kind)


def _layers(dat, graphic_id: int) -> list[tuple[int, int, int]]:
    """(graphic id, x offset, y offset) to draw, back to front: a graphic's
    deltas (Sharkatzor's shadow is one) and the graphic itself."""
    g = dat.graphics[graphic_id] if 0 <= graphic_id < len(dat.graphics) else None
    if g is None:
        return []
    out = []
    for d in g.deltas or []:
        gid = graphic_id if d.graphic_id < 0 else d.graphic_id
        if gid != graphic_id and 0 <= gid < len(dat.graphics) and dat.graphics[gid] and dat.graphics[gid].file_name:
            out.append((gid, d.offset_x, d.offset_y))
    if g.file_name:
        out.append((graphic_id, 0, 0))
    return out


class _Sprite:
    def __init__(self, path: Path):
        self.data = path.read_bytes()
        self.frames = frame_index(self.data)


def unit_frames(dat, dat_path, unit, kind: str, angle: int = SOUTH_WEST,
                still: bool = False) -> tuple[list[Image.Image], int] | None:
    """Every frame of one of a unit's animations at one facing, as RGBA images
    cropped to what any frame draws, and the frame time in ms at Normal speed.
    `still` stops after the first frame.  None when the game has no sprite."""
    return graphic_frames(dat, dat_path, unit_graphic(unit, kind), angle, still)


def graphic_frames(dat, dat_path, graphic_id: int, angle: int = SOUTH_WEST,
                   still: bool = False, under: tuple = (),
                   min_ms: int = MIN_FRAME_MS) -> tuple[list[Image.Image], int] | None:
    """unit_frames for any DAT graphic — one a unit's task plays (a Villager
    building), not only its idle, walk and attack.  `under` adds (graphic id,
    x, y) layers drawn first: a Town Center preview's shadow lives on another
    piece of the building (scene_art)."""
    parts = []
    for gid, ox, oy in (*under, *_layers(dat, graphic_id)):
        g = dat.graphics[gid]
        path = find_sprite(dat_path, g.file_name)
        if path is None:
            continue
        try:
            sprite = _Sprite(path)
        except (ValueError, struct.error):
            continue                                        # unreadable: no preview
        per = max(1, g.frame_count)
        angles = max(1, len(sprite.frames) // per)          # what the file stores
        a = round(angle * angles / 16) % angles
        parts.append((sprite, a * per, per, ox, oy))
    if not parts:
        return None
    g = dat.graphics[graphic_id]
    exact = g.frame_duration * 1000 / NORMAL_SPEED if g.frame_duration > 0 else 67.0
    step = 1 if still else max(1, math.ceil(min_ms / exact - 1e-9))
    picks = [0] if still else list(range(0, max(1, g.frame_count), step))
    ms = round(exact * step)

    # Composite each frame on a canvas centred on the hotspot, and keep only
    # the part it draws: a wonder's canvas is ~4000 px square, and holding 120
    # of them (the Tupi waterfall) took gigabytes.
    # Big enough for every frame drawn around its hotspot, and no bigger.
    size = 2 * max(max(f["hot"][0], f["w"] - f["hot"][0], f["hot"][1], f["h"] - f["hot"][1]) + abs(ox) + abs(oy)
                   for sprite, first, per, ox, oy in parts
                   for f in sprite.frames[first:first + per]) + 64
    kept, boxes = [], []
    for i in picks:
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        for sprite, first, per, ox, oy in parts:
            img, (hx, hy) = render_frame(sprite.data, first + (i % per), sprite.frames)
            canvas.alpha_composite(Image.fromarray(img, "RGBA"), (size // 2 - hx + ox, size // 2 - hy + oy))
        drawn = canvas.getbbox()
        kept.append((canvas.crop(drawn), drawn) if drawn else (None, None))
        # Crop to what is solidly drawn: a few near-invisible shadow specks far
        # below the Persian and Varangian wonders (alpha <= 37) stretched the
        # box by hundreds of pixels, so the scene showed them mostly empty space.
        solid = canvas.getchannel("A").point(lambda a: 255 if a >= _SOLID else 0).getbbox()
        if solid:
            boxes.append(solid)
    if not boxes:
        return None
    pad = 8
    box = (max(0, min(b[0] for b in boxes) - pad), max(0, min(b[1] for b in boxes) - pad),
           min(size, max(b[2] for b in boxes) + pad), min(size, max(b[3] for b in boxes) + pad))
    out = []
    for im, drawn in kept:
        frame = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
        if im is not None:
            frame.paste(im, (drawn[0] - box[0], drawn[1] - box[1]))   # paste clips what falls outside
        out.append(frame)
    return out, ms


def still_webp(dat, dat_path, unit) -> bytes | None:
    """The preview still: the first idle frame, facing south-west."""
    import io
    got = unit_frames(dat, dat_path, unit, "idle", still=True)
    if got is None:
        return None
    buf = io.BytesIO()
    got[0][0].save(buf, "WEBP", quality=85)
    return buf.getvalue()


def animation_webp(dat, dat_path, unit, kind: str) -> bytes | None:
    """A looping animated WebP of one of the unit's ANIMATIONS."""
    return graphic_webp(dat, dat_path, unit_graphic(unit, kind))


def graphic_webp(dat, dat_path, graphic_id: int, angle: int = SOUTH_WEST) -> bytes | None:
    """A looping animated WebP of any DAT graphic."""
    import io
    got = graphic_frames(dat, dat_path, graphic_id, angle)
    if got is None:
        return None
    frames, ms = got
    buf = io.BytesIO()
    frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=ms,
                   loop=0, quality=80, method=4)
    return buf.getvalue()


# ── The identity scene ───────────────────────────────────────────────────────
# Step 1's scene (static/css/scene.css): each slot's art, rendered from the
# player's game like the previews, so every piece is at the game's own scale
# and a civ a patch adds has art at once.  The images in static/img/scene are
# only the fallback for when the game isn't found.
# "building" is any building by unit id, for a card that changes how one looks
# (card 460 draws its Castle as the Wooden Fort, 2600).
SCENE_SLOTS = ("architecture", "wonder", "castle", "monastery_skin_building", "monk_skin", "starting_scout",
               "building")
_CASTLE, _WONDER, _MONK, _MONASTERY = 82, 276, 125, 104
# Buildings are stored at half the sprite's size: the scene shows them at about
# a quarter, so half is still sharp on a 2x screen, and an animated one (the
# Tupi waterfall) stays a few MB rather than tens.  builder.js
# _SCENE_BUILDING_SCALE undoes it, so every slot keeps the game's one scale.
SCENE_BUILDINGS = ("architecture", "wonder", "castle", "monastery_skin_building", "building")
SCENE_BUILDING_SCALE = 0.5
_SCENE_MIN_FRAME_MS = 66
# A Town Center is four units (back, main, centre, front — the annexes); the
# game also keeps the whole Castle Age one as a single "Preview" sprite, unit
# 484, whose shadow is a delta of the back piece, unit 141.
_TC_BACK, _TC_PREVIEW = 141, 484


def scene_still(dat, dat_path, slot: str, value: int) -> Image.Image | None:
    """One scene slot's art, facing south-west in Player 1 Blue.  Values are
    the wizard's: architecture = civ.icon_set; wonder and castle = DAT civ
    index - 1 (KM's convention); monk_skin and monastery_skin_building = DAT
    civ index (a scenario Monk's unit id past the civs); starting_scout and
    building = unit id."""
    got = _scene_frames(dat, dat_path, slot, value, still=True)
    return got[0][0] if got else None


def scene_animated(dat, slot: str, value: int) -> bool:
    """Whether a scene slot's building moves (the Tupi wonder's waterfall, the
    Central Asian shrine) — those take a minute to render, so the server shows
    the still first."""
    gid = _scene_graphic(dat, slot, value)[0]
    return (slot in SCENE_BUILDINGS and gid is not None and 0 <= gid < len(dat.graphics)
            and dat.graphics[gid] is not None and dat.graphics[gid].frame_count > 1)


def _scene_frames(dat, dat_path, slot: str, value: int, still: bool):
    """graphic_frames for a scene slot, buildings at SCENE_BUILDING_SCALE."""
    gid, under = _scene_graphic(dat, slot, value)
    if gid is None:
        return None
    # A building's animation (water, flags) reads fine at 15 fps, and that
    # keeps the Tupi waterfall's 120 frames to 40.
    got = graphic_frames(dat, dat_path, gid, still=still, under=under, min_ms=_SCENE_MIN_FRAME_MS)
    if got is None or slot not in SCENE_BUILDINGS:
        return got
    frames, ms = got
    return [f.resize((max(1, round(f.width * SCENE_BUILDING_SCALE)), max(1, round(f.height * SCENE_BUILDING_SCALE))),
                     Image.LANCZOS) for f in frames], ms


def _scene_graphic(dat, slot: str, value: int) -> tuple:
    """(graphic id, layers drawn under it) for a scene slot, or (None, ())."""
    civs = dat.civs
    under = ()
    if slot == "architecture":
        civ = next((c for c in civs[1:] if c.icon_set == value), None)
        if civ is None:
            return None, ()
        back = civ.units[_TC_BACK].standing_graphic[0]
        under = tuple(layer for layer in _layers(dat, back) if layer[0] != back)
        gid = civ.units[_TC_PREVIEW].standing_graphic[0]
    elif slot == "monk_skin" and value >= len(civs):
        # A scenario Monk (civ_appender.SCENARIO_MONK_SKINS): value is its unit id.
        units = civs[0].units
        if value >= len(units) or units[value] is None or units[value].class_ != 18:
            return None, ()
        gid = units[value].standing_graphic[0]
    elif slot in ("wonder", "castle", "monk_skin", "monastery_skin_building"):
        idx = value if slot in ("monk_skin", "monastery_skin_building") else value + 1
        if not 1 <= idx < len(civs):
            return None, ()
        unit = civs[idx].units[{"wonder": _WONDER, "castle": _CASTLE, "monk_skin": _MONK,
                                "monastery_skin_building": _MONASTERY}[slot]]
        gid = unit.standing_graphic[0]
    elif slot in ("starting_scout", "building"):
        units = civs[0].units
        if not 0 <= value < len(units) or units[value] is None:
            return None, ()
        if slot == "building" and units[value].type != 80:
            return None, ()
        gid = units[value].standing_graphic[0]
    else:
        return None, ()
    return gid, under


def scene_size(dat, dat_path, slot: str, value: int) -> tuple[int, int] | None:
    """Roughly the (width, height) scene_webp will have, from the sprites'
    frame headers alone — no pixels decoded — so the scene can reserve a
    building's footprint while it renders (the Villager works on the spot).
    Exact but for the solid-pixel crop, which only ever makes it smaller."""
    gid, under = _scene_graphic(dat, slot, value)
    if gid is None:
        return None
    box = None
    for g2, ox, oy in (*under, *_layers(dat, gid)):
        g = dat.graphics[g2]
        path = find_sprite(dat_path, g.file_name)
        if path is None:
            continue
        try:
            data = path.read_bytes()
            frames = frame_index(data)
            per = max(1, g.frame_count)
            angles = max(1, len(frames) // per)
            f = frames[(round(SOUTH_WEST * angles / 16) % angles) * per]
            drawn = _drawn_box(data, f)
        except (ValueError, struct.error):
            continue
        if drawn is None:
            continue
        hx, hy = f["hot"]
        b = (ox - hx + drawn[0], oy - hy + drawn[1], ox - hx + drawn[2], oy - hy + drawn[3])
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    if box is None:
        return None
    w, h = box[2] - box[0] + 16, box[3] - box[1] + 16
    if slot in SCENE_BUILDINGS:
        w, h = round(w * SCENE_BUILDING_SCALE), round(h * SCENE_BUILDING_SCALE)
    return w, h


def scene_webp(dat, dat_path, slot: str, value: int, still: bool = False) -> bytes | None:
    """The slot's art as WebP — animated when the building is (the Tupi
    wonder's waterfall, the Central Asian shrine), unless `still`."""
    import io
    got = _scene_frames(dat, dat_path, slot, value, still=still or slot not in SCENE_BUILDINGS)
    if got is None:
        return None
    frames, ms = got
    buf = io.BytesIO()
    if len(frames) > 1:
        frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=ms,
                       loop=0, quality=80, method=4)
    else:
        frames[0].save(buf, "WEBP", quality=88)
    return buf.getvalue()
