"""Load a DAT without parsing every civ's units up front.

Parsing dominates every build: 63 civs x 2,750 unit slots is ~137,000 units
read field by field in pure Python — ~16 of the ~18 seconds `DatFile.parse`
takes (measured 2026-10-04).  A build touches a handful of civs.

So a civ is read in two parts.  Its header (name, tech tree and team bonus
effect ids, resources, architecture) is parsed as usual; its units stay as raw
bytes in a `LazyUnits` list.  Indexing one unit parses just that unit (most
"for civ in dat.civs: civ.units[X]..." code touches one unit per civ);
iterating parses the whole civ.  `LazyCiv.to_bytes` writes every untouched
unit straight back from its bytes.  genieutils round-trips all 63 civs byte-for-byte, so the
saved DAT is identical to one written from a full parse — the tests compare
exactly that.

Where a civ (and each unit) ENDS is not recorded in the file, and finding it
means parsing.  The first load of a given DAT therefore parses everything (as
before) and caches every civ's and unit's byte offsets — plus each unit's train
locations, which the button planner's hotkey vote reads for all 63 civs — under
the DAT's SHA-1; every later load, in any process, just slices.

`EMPIREFORGE_EAGER_DAT=1` turns all of this off — the plain genieutils parse.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import zlib
from copy import deepcopy
from pathlib import Path

from genieutils.civ import Civ
from genieutils.common import ByteHandler
from genieutils.datfile import DatFile
from genieutils.effect import Effect
from genieutils.graphic import Graphic
from genieutils.playercolour import PlayerColour
from genieutils.randommaps import RandomMaps
from genieutils.sound import Sound
from genieutils.tech import Tech
from genieutils.techtree import TechTree
from genieutils.terrainblock import TerrainBlock
from genieutils.terrainrestriction import TerrainRestriction
from genieutils.unit import Unit
from genieutils.unitheaders import UnitHeaders
from genieutils.versions import Version

CACHE_VERSION = 2
# One lock for every parse: the web app shares a parsed DAT across request
# threads, and two threads filling the same list would duplicate it.
_LOCK = threading.RLock()


class LazyUnits(list):
    """A civ's unit list that parses one unit at a time.

    Indexing a single unit parses just that unit; assigning or appending one
    records an override.  Anything that needs the whole list (iterating,
    slicing, sorting, ...) parses the rest once and it becomes an ordinary
    list.  Until then, untouched units are written back from their raw bytes.
    """

    __slots__ = ("_raw", "_n", "_version", "_pointers", "_starts", "_over",
                 "_extra", "_origin", "_summary")

    def __init__(self, raw, n, version, starts, origin, summary):
        super().__init__()
        self._raw = raw              # unit pointers + unit records; None once fully parsed
        self._n = n
        self._version = version
        self._starts = starts        # per index: offset of the unit in raw, or -1 if none
        self._pointers = None
        self._over: dict = {}        # index -> Unit | None, parsed or assigned
        self._extra: list = []       # appended units
        self._origin = origin        # which civ's bytes these are (survives copying)
        self._summary = summary      # cached train locations of the untouched units

    @property
    def materialized(self) -> bool:
        return self._raw is None

    def _unit_end(self, i):
        for j in range(i + 1, self._n):
            if self._starts[j] >= 0:
                return self._starts[j]
        return len(self._raw)

    def _parse_one(self, i):
        start = self._starts[i]
        if start < 0:
            return None
        bh = ByteHandler(memoryview(self._raw)[start:])
        bh.version = self._version
        return Unit.from_bytes(bh)

    def _load(self) -> None:
        """Parse everything; become a plain list."""
        if self._raw is None:
            return
        with _LOCK:
            if self._raw is None:
                return
            units = [self._over[i] if i in self._over else self._parse_one(i) for i in range(self._n)]
            list.extend(self, units + self._extra)
            self._raw = None
            self._over, self._extra, self._starts, self._summary = {}, [], None, None

    def __len__(self):
        return self._n + len(self._extra) if self._raw is not None else list.__len__(self)

    def __bool__(self):
        return len(self) > 0

    def _index(self, key):
        i = key + len(self) if key < 0 else key
        if not 0 <= i < len(self):
            raise IndexError("list index out of range")
        return i

    def __getitem__(self, key):
        if self._raw is not None and isinstance(key, int):
            i = self._index(key)
            if i >= self._n:
                return self._extra[i - self._n]
            if i not in self._over:
                with _LOCK:
                    if self._raw is None:                 # parsed fully meanwhile
                        return list.__getitem__(self, key)
                    if i not in self._over:
                        self._over[i] = self._parse_one(i)
            return self._over[i]
        self._load()
        return list.__getitem__(self, key)

    def __setitem__(self, key, value):
        if self._raw is not None and isinstance(key, int):
            i = self._index(key)
            if i >= self._n:
                self._extra[i - self._n] = value
            else:
                self._over[i] = value
            return
        self._load()
        list.__setitem__(self, key, value)

    def append(self, value):
        if self._raw is not None:
            self._extra.append(value)
        else:
            list.append(self, value)

    def extend(self, values):
        if self._raw is not None:
            self._extra.extend(list(values))
        else:
            list.extend(self, values)

    def __deepcopy__(self, memo):
        if self._raw is not None:
            c = LazyUnits(self._raw, self._n, self._version, self._starts, self._origin, self._summary)
            c._over = {i: deepcopy(u, memo) for i, u in self._over.items()}
            c._extra = [deepcopy(u, memo) for u in self._extra]
            return c
        return [deepcopy(u, memo) for u in self]

    def __copy__(self):
        self._load()
        return list(self)

    def __reduce_ex__(self, protocol):
        self._load()
        return (list, (list(self),))

    def __repr__(self):
        if self._raw is not None:
            return f"<LazyUnits {len(self)} units, {len(self._over)} parsed>"
        return list.__repr__(self)

    def section_bytes(self, civ) -> bytes:
        """Unit count, pointers and records — what Civ.to_bytes writes after icon_set."""
        if not self._over and not self._extra:
            return civ.write_int_16(self._n) + self._raw
        units_out, data = [], []
        for i in range(self._n):
            if i in self._over:
                u = self._over[i]
                units_out.append(u)
                if u is not None:
                    data.append(u.to_bytes(self._version))
            elif self._starts[i] >= 0:
                units_out.append(True)
                data.append(self._raw[self._starts[i]:self._unit_end(i)])
            else:
                units_out.append(None)
        for u in self._extra:
            units_out.append(u)
            if u is not None:
                data.append(u.to_bytes(self._version))
        return b"".join([civ.write_int_16(len(units_out)),
                         civ.write_int_32_array([0 if u is None else 1 for u in units_out]),
                         *data])


def _materializing(name):
    base = getattr(list, name)

    def method(self, *args, **kwargs):
        self._load()
        return base(self, *args, **kwargs)
    method.__name__ = name
    return method


for _name in ("__delitem__", "__iter__", "__reversed__",
              "__contains__", "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__",
              "__add__", "__radd__", "__iadd__", "__mul__", "__rmul__", "__imul__",
              "insert", "pop", "remove", "index", "count",
              "sort", "reverse", "clear", "copy"):
    if hasattr(list, _name):
        setattr(LazyUnits, _name, _materializing(_name))


def train_locations(units):
    """(building, button, hot_key) for every train location of every unit in a
    civ's unit list — without parsing a lazy list's untouched units, whose
    train locations come from the offset cache instead."""
    if isinstance(units, LazyUnits) and units._raw is not None:
        for i, b, btn, hk in units._summary:
            if i not in units._over:
                yield b, btn, hk
        live = [u for u in units._over.values()] + list(units._extra)
    else:
        live = units
    for u in live:
        if u is not None and u.creatable is not None:
            for tl in u.creatable.train_locations:
                yield tl.unit_id, tl.button_id, tl.hot_key_id


class LazyCiv(Civ):
    """A Civ whose units may still be raw bytes.  Header fields are always live,
    so editing one (icon_set, resources, ...) is written normally."""

    __slots__ = ()

    def to_bytes(self, version: Version) -> bytes:
        units = self.units
        if not isinstance(units, LazyUnits) or units.materialized:
            return Civ.to_bytes(self, version)
        return b"".join([
            self.write_int_8(self.player_type),
            self.write_debug_string(self.name),
            self.write_int_16(len(self.resources)),
            self.write_int_16(self.tech_tree_id),
            self.write_int_16(self.team_bonus_id),
            self.write_float_array(self.resources),
            self.write_int_8(self.icon_set),
            units.section_bytes(self),
        ])


def _read_civ_header(bh: ByteHandler) -> tuple[dict, int]:
    """Civ.from_bytes up to (and including) the unit count."""
    player_type = bh.read_int_8()
    name = bh.read_debug_string()
    resources_size = bh.read_int_16()
    tech_tree_id = bh.read_int_16()
    team_bonus_id = bh.read_int_16()
    resources = bh.read_float_array(resources_size)
    icon_set = bh.read_int_8()
    units_size = bh.read_int_16()
    return (dict(player_type=player_type, name=name, tech_tree_id=tech_tree_id,
                 team_bonus_id=team_bonus_id, resources=resources, icon_set=icon_set),
            units_size)


def _cache_path(digest: str) -> Path:
    from custom_bonus import data_dir
    return data_dir() / "dat_cache" / f"{digest}.json"


def _read_cache(digest: str) -> dict | None:
    try:
        d = json.loads(_cache_path(digest).read_text(encoding="utf-8"))
        return d if d.get("version") == CACHE_VERSION else None
    except (OSError, ValueError):
        return None


def _write_cache(digest: str, cache: dict) -> None:
    try:
        p = _cache_path(digest)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": CACHE_VERSION, **cache}), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass          # a cache that can't be written just means the next load parses fully


def _read_units_recording(bh: ByteHandler, n: int) -> tuple[list, list[int], list]:
    """Parse a civ's units as genieutils does, noting where each one starts
    (relative to the pointer array) and its train locations."""
    region = bh.offset
    pointers = bh.read_int_32_array(n)
    units, starts, summary = [], [], []
    for i in range(n):
        if pointers[i]:
            starts.append(bh.offset - region)
            u = Unit.from_bytes(bh)
            if u.creatable is not None:
                summary.extend([i, tl.unit_id, tl.button_id, tl.hot_key_id]
                               for tl in u.creatable.train_locations)
        else:
            starts.append(-1)
            u = None
        units.append(u)
    return units, starts, summary


# zlib level for a DAT we write.  genieutils uses the default (6): 6.6s and
# 12.0 MB for today's DAT.  Level 3 is 2.5s and 14.0 MB — the game inflates
# any level the same way, and ~4s off every build was judged worth 2 MB.
SAVE_LEVEL = 3


def save_bytes(dat: DatFile, level: int = SAVE_LEVEL) -> bytes:
    """The compressed DAT, as DatFile.save would write it (raw deflate)."""
    return zlib.compress(dat.to_bytes(), level=level, wbits=-15)


def parse(path: str | Path) -> DatFile:
    """DatFile.parse, with lazily parsed civ units (see the module docstring)."""
    if os.environ.get("EMPIREFORGE_EAGER_DAT"):
        return DatFile.parse(str(path))
    content = Path(path).read_bytes()
    digest = hashlib.sha1(content).hexdigest()
    data = memoryview(zlib.decompress(content, wbits=-15))
    cache = _read_cache(digest)

    bh = ByteHandler(data)
    # The same order as genieutils' DatFile.from_bytes — only the civ loop differs.
    version = bh.read_string(8)
    bh.version = Version(version)
    terrain_restrictions_size = bh.read_int_16()
    terrains_used_1 = bh.read_int_16()
    float_ptr_terrain_tables = bh.read_int_32_array(terrain_restrictions_size)
    terrain_pass_graphic_pointers = bh.read_int_32_array(terrain_restrictions_size)
    terrain_restrictions = bh.read_class_array_with_param(TerrainRestriction, terrain_restrictions_size,
                                                          terrains_used_1)
    player_colours = bh.read_class_array(PlayerColour, bh.read_int_16())
    sounds = bh.read_class_array(Sound, bh.read_int_16())
    graphics_size = bh.read_int_16()
    graphic_pointers = bh.read_int_32_array(graphics_size)
    graphics = bh.read_class_array_with_pointers(Graphic, graphics_size, graphic_pointers)
    terrain_block = bh.read_class(TerrainBlock)
    random_maps = bh.read_class(RandomMaps)
    effects = bh.read_class_array(Effect, bh.read_int_32())
    unit_headers = bh.read_class_array(UnitHeaders, bh.read_int_32())

    civs_size = bh.read_int_16()
    if cache is not None and len(cache.get("civ_ends", ())) != civs_size:
        cache = None                         # a cache from some other file; ignore it
    civs: list[Civ] = []
    fresh = {"civ_ends": [], "unit_starts": [], "train_locations": []}
    for i in range(civs_size):
        header, units_size = _read_civ_header(bh)
        if cache is not None:
            end = cache["civ_ends"][i]
            raw = bytes(data[bh.offset:end])
            bh.offset = end
            civs.append(LazyCiv(units=LazyUnits(raw, units_size, bh.version, cache["unit_starts"][i],
                                                i, cache["train_locations"][i]), **header))
        else:
            units, starts, summary = _read_units_recording(bh, units_size)
            civs.append(LazyCiv(units=units, **header))
            fresh["civ_ends"].append(bh.offset)
            fresh["unit_starts"].append(starts)
            fresh["train_locations"].append(summary)

    techs = bh.read_class_array(Tech, bh.read_int_16())
    tail = [bh.read_int_32() for _ in range(7)]
    tech_tree = bh.read_class(TechTree)
    if cache is None:
        _write_cache(digest, fresh)

    return DatFile(
        version=version,
        float_ptr_terrain_tables=float_ptr_terrain_tables,
        terrain_pass_graphic_pointers=terrain_pass_graphic_pointers,
        terrain_restrictions=terrain_restrictions,
        player_colours=player_colours,
        sounds=sounds,
        graphics=graphics,
        terrain_block=terrain_block,
        random_maps=random_maps,
        effects=effects,
        unit_headers=unit_headers,
        civs=civs,
        techs=techs,
        time_slice=tail[0],
        unit_kill_rate=tail[1],
        unit_kill_total=tail[2],
        unit_hit_point_rate=tail[3],
        unit_hit_point_total=tail[4],
        razing_kill_rate=tail[5],
        razing_kill_total=tail[6],
        tech_tree=tech_tree,
    )
