"""Unit-voice clips, read out of the player's own game install.

A voice needs BOTH the DAT SoundItem remap (`assign_all_languages`) and the
.wem files in the mod's `drs/sounds/` — without the files the engine plays the
replaced slot's own voice (confirmed in-game 2026-09-25).  The clips live in
the game's Wwise banks, and `voice_wwise_map.json` names every one of them by
media id, so the app ships no game audio: it reads the player's `wwise/` folder
at build time.  That also keeps an unmaintained exe working across patches —
see `scripts/voice_wwise.py` for how the map is built, and when it needs a
rebuild.

Every clip the map names sits in `Base.pck` (0.5 s to index), so the other
packages are only scanned when a patch has moved something out of it.
"""
from __future__ import annotations

import json
import mmap
import os
import struct
from pathlib import Path

ROOT = Path(__file__).parent
MAP_PATH = ROOT / "voice_wwise_map.json"
# A dev checkout's copy of the game's wwise/ folder (gitignored, never bundled):
# lets a Mac with no game install build voices from the same banks Windows has.
_DEV_WWISE = ROOT / "ignore" / "wwise"

_map_cache: dict | None = None


def voice_map() -> dict[str, dict]:
    """Civ name -> {"value": language value, "files": {stem: media id}, ...}."""
    global _map_cache
    if _map_cache is None:
        _map_cache = json.loads(MAP_PATH.read_text(encoding="utf-8"))["civs"]
    return _map_cache


def voice_values() -> set[int]:
    """Every language value the map can extract — what the Voice picker offers."""
    return {int(e["value"]) for e in voice_map().values()}


def find_wwise_dir(dat_path: str | Path | None) -> Path | None:
    """The game's wwise/ folder for this DAT, or None.

    The DAT is `<game>/resources/_common/dat/empires2_x2_p1.dat` on Steam and
    Xbox alike, so the banks are four levels up.  `EMPIREFORGE_WWISE` overrides
    it, the way `EMPIREFORGE_DAT` overrides the DAT.
    """
    candidates: list[Path] = []
    override = os.environ.get("EMPIREFORGE_WWISE")
    if override:
        candidates.append(Path(override).expanduser())
    if dat_path:
        parents = Path(dat_path).resolve().parents
        if len(parents) > 3:
            candidates.append(parents[3] / "wwise")
    candidates.append(_DEV_WWISE)
    for c in candidates:
        if (c / "Base.pck").is_file():
            return c
    return None


def media_index(pcks: list[Path]) -> dict[int, tuple[Path, int, int]]:
    """media id -> (package, absolute offset, size) for every embedded clip."""
    out: dict[int, tuple[Path, int, int]] = {}
    for pck in pcks:
        with open(pck, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            i = m.find(b"BKHD")
            while i != -1:
                j = i + 8 + struct.unpack_from("<I", m, i + 4)[0]
                if m[j:j + 4] == b"DIDX":
                    size = struct.unpack_from("<I", m, j + 4)[0]
                    data = j + 8 + size
                    if m[data:data + 4] == b"DATA":
                        for k in range(size // 12):
                            mid, off, sz = struct.unpack_from("<III", m, j + 8 + k * 12)
                            out.setdefault(mid, (pck, data + 8 + off, sz))
                i = m.find(b"BKHD", i + 4)
    return out


def voice_clips(values: set[int], dat_path: str | Path | None
                ) -> tuple[dict[int, dict[str, bytes]], list[int], Path | None]:
    """Extract the .wem clips for each language value from the player's banks.

    Returns `(clips, missing, wwise_dir)`: `clips[value]` maps a file stem to
    its bytes, and `missing` lists the values that could not be delivered —
    no wwise folder, a value the map does not know, or a patch that changed
    the bank under the map.  The caller warns; a missing voice falls back to
    the replaced slot's own, it does not break the mod.
    """
    by_value = {int(e["value"]): e for e in voice_map().values()}
    wanted = {v: by_value[v] for v in values if v in by_value}
    missing = sorted(v for v in values if v not in by_value)
    wwise = find_wwise_dir(dat_path)
    if wwise is None:
        return {}, sorted(values), None

    need = {mid for e in wanted.values() for mid in e["files"].values()}
    bank = media_index([wwise / "Base.pck"])
    if need - bank.keys():
        rest = sorted(p for p in wwise.rglob("*.pck") if p.name != "Base.pck")
        for mid, loc in media_index(rest).items():
            bank.setdefault(mid, loc)

    clips: dict[int, dict[str, bytes]] = {}
    handles: dict[Path, object] = {}
    try:
        for value, entry in sorted(wanted.items()):
            if any(mid not in bank for mid in entry["files"].values()):
                missing.append(value)
                continue
            out: dict[str, bytes] = {}
            for stem, mid in entry["files"].items():
                pck, off, size = bank[mid]
                f = handles.get(pck) or handles.setdefault(pck, open(pck, "rb"))
                f.seek(off)
                out[stem] = f.read(size)
            clips[value] = out
    finally:
        for f in handles.values():
            f.close()
    return clips, sorted(missing), wwise
