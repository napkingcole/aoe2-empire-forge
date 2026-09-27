#!/usr/bin/env python3
"""Extract every civ's unit-voice .wem files straight from the game's Wwise banks.

    venv/bin/python scripts/voice_wwise.py extract --wwise <game>/wwise --civ Armenians
    venv/bin/python scripts/voice_wwise.py extract --wwise <game>/wwise --missing
    venv/bin/python scripts/voice_wwise.py extract --wwise <game>/wwise --all --fill
    venv/bin/python scripts/voice_wwise.py map --wwiser-xml dump.xml --sheet speech.csv

`extract` needs only the committed map (`voice_wwise_map.json`) and the game's
`wwise/` folder.  `map` rebuilds that file after a patch or DLC and needs two
third-party inputs, described below.

WHY THIS EXISTS.  A voice needs the DAT SoundItem remap AND the .wem files in
the mod's `drs/sounds/` — without the files the engine plays the slot's own
voice (confirmed in-game 2026-09-25).  `voice_files/` began as a byte copy of
KrakenMeister's 43 folders, so every civ added since had no voice.  The
2026-09-23 attempt (see `voice_manifest.py`) concluded the audio could not be
named.  That was wrong: the names are recoverable from the bank's event graph.

HOW THE ENGINE PICKS A CLIP.  `Base.pck` bank 232745270 carries both the audio
(DIDX/DATA) and a HIRC object graph.  Every unit-voice line is a Wwise *switch
container* on one switch group, 1977672554, which has 64 states — one per civ.
Each state's id is the FNV-1 hash of the lower-cased civ name ("armenians",
"hindustanis", "saxons"), so states are named by hashing, not guessed.  Under
each state sits a random container of Sound objects, and each Sound names the
embedded media id of one clip.

  civ state --(switch container for line L)--> random container --> N clips

Which DAT sound id a container serves is learned from the Britons branch: the
StepS/Forgotten Empires audio spreadsheet's "OLD Audio Sources - Speech" tab maps
DAT `resource_id` -> media id for civs up to the Lithuanians, which is enough to
label all 40 containers.  Within a line, clips pair with the DAT filenames in
order; variations of one line (vms1..vms4) may come out permuted, which the
engine cannot tell apart since it picks one at random.

VERIFIED 2026-09-25 against KM's files by duration (per line, as a multiset):
every civ 1-43 matches except Byzantines (18/53 — DE appears to have re-recorded
them; KM's copy is the older set) and one clip each for Chinese and Bulgarians.
Not covered by either source: the priestess lines (`vpfs*`/`vpfm*`) and the
villager attack grunts (`vma`/`vfa`), which have no container on this switch —
the engine falls back per file, as it already does for KM's folders.

WHAT THE GRAPH SAYS ABOUT THE NEWER CIVS (inferred, not yet heard in-game):
Shu, Wu, Wei and Jurchens route to exactly the Chinese clips, and Khitans to the
Mongol clips.  Their folders are therefore copies of those voices under the
civ's own filenames — faithful to the game, not a distinct voice.

BROKEN DAT NAMES.  The newest civs' DAT entries are placeholders the unmodded
game never reads (it plays through Wwise): the South American and Viking Sagas
civs point Build, Forage, Hunt, Chop, Mine and Repair at ONE file, and borrow
each other's (Saxons' female chop is "danevfl").  A folder can't hold six clips
under one name, so for those civs the map names every line canonically
("saxvml" = chop) and lists it under "lines"; `civ_appender.assign_all_languages`
rebuilds the sound items from it.  Found by ear 2026-09-25 — "VM Build is the
wood-chopper line".

REBUILDING THE MAP (`map`) needs:
  * a wwiser XML dump of the Base.pck banks.  wwiser (github.com/bnnm/wwiser)
    reads .bnk files, so split Base.pck at each BKHD first; `split_banks()` here
    does that.  Then: `python wwiser.py -d xml -dn dump <banks>/*.bnk`.
  * the spreadsheet tab as CSV: docs.google.com/spreadsheets/d/
    1bczdFQksnbLnjI5zAkw-mSpb9MnnxxEkHDiz1PftIHw — "OLD Audio Sources - Speech".
"""
from __future__ import annotations

import argparse
import csv
import json
import mmap
import re
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MAP_PATH = ROOT / "voice_wwise_map.json"
VOICE_DIR = ROOT / "voice_files"

CIV_SWITCH_GROUP = 1977672554
CALIBRATION_CIV = 1                    # Britons: covered by the spreadsheet
# DAT name -> the name Wwise hashed, where they differ.
STATE_ALIASES = {"indians": "hindustanis"}
# Chronicles-only civs: never offered (see project_chronicles_dlc_blacklist).
SKIP_CIVS = {"achaemenids", "athenians", "spartans", "macedonians", "thracians", "puru"}


def fnv1(name: str) -> int:
    h = 2166136261
    for b in name.lower().encode():
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= b
    return h


def natural(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


# ── bank access ──────────────────────────────────────────────────────────────

def media_index(wwise_dir: Path) -> dict[int, tuple[Path, int, int]]:
    """media id -> (package, absolute offset, size) for every embedded clip."""
    out: dict[int, tuple[Path, int, int]] = {}
    for pck in sorted(wwise_dir.rglob("*.pck")):
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


def split_banks(pck: Path, out_dir: Path) -> list[Path]:
    """Write each soundbank embedded in `pck` as <bank id>.bnk, for wwiser."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with open(pck, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
        i = m.find(b"BKHD")
        while i != -1:
            bank_id = struct.unpack_from("<I", m, i + 12)[0]
            j = i
            while True:
                nxt = j + 8 + struct.unpack_from("<I", m, j + 4)[0]
                if nxt >= len(m) or m[nxt:nxt + 4] in (b"BKHD", b"RIFF") \
                        or not m[nxt:nxt + 4].isalpha():
                    j = nxt
                    break
                j = nxt
            path = out_dir / f"{bank_id}.bnk"
            path.write_bytes(m[i:j])
            written.append(path)
            i = m.find(b"BKHD", j)
    return written


# ── map: wwiser dump + spreadsheet -> voice_wwise_map.json ───────────────────

def load_graph(xml_path: Path) -> dict[int, dict]:
    """HIRC objects from a wwiser XML dump (several <root>s, one per bank)."""
    def vals(e, name):
        return [int(f.get("value")) for f in e.iter("field") if f.get("name") == name]

    text = xml_path.read_text(encoding="utf-8")
    text = "<all>" + re.sub(r"<\?xml[^>]*\?>", "", text) + "</all>"
    objs: dict[int, dict] = {}
    for items in ET.fromstring(text).iter("list"):
        if items.get("name") != "listLoadedItem":
            continue
        for e in items:
            kind = e.get("name", "")
            node = {"kind": kind, "children": vals(e, "ulChildID"),
                    "src": vals(e, "sourceID"), "group": vals(e, "ulGroupID")}
            if kind == "CAkSwitchCntr":
                node["switch"] = {
                    int(p.find("field[@name='ulSwitchID']").get("value")): vals(p, "NodeID")
                    for p in e.iter("object") if p.get("name") == "CAkSwitchPackage"}
            objs[vals(e, "ulID")[0]] = node
    return objs


def clips(graph: dict[int, dict], node: int) -> list[int]:
    o = graph.get(node)
    if not o:
        return []
    out = list(o["src"])
    for c in o["children"]:
        out += clips(graph, c)
    return out


def build_map(graph, dat, roster, sheet_csv: Path, bank: dict) -> dict:
    rid_to_media: dict[int, list[int]] = defaultdict(list)
    with open(sheet_csv, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            try:
                rid_to_media[int(float(row[0]))].append(int(float(row[1])))
            except (ValueError, IndexError):
                continue

    items = [(sid, it.civilization, it.filename.rsplit(".", 1)[0].lower(), it.resource_id)
             for sid, s in enumerate(dat.sounds) for it in s.items]

    # Lowest sound id wins: DE gave the priestess lines (597/598) the monk
    # lines' resource ids, and the monk containers belong to 423/424.
    media_line: dict[int, int] = {}
    for sid, civ, _, rid in sorted(items):
        if civ == CALIBRATION_CIV:
            for mid in rid_to_media.get(rid, []):
                media_line.setdefault(mid, sid)

    brit_state = fnv1(roster[CALIBRATION_CIV]["name"])
    containers: dict[int, list[int]] = defaultdict(list)       # dat sound id -> containers
    for cid, o in graph.items():
        if o["kind"] != "CAkSwitchCntr" or o["group"][:1] != [CIV_SWITCH_GROUP]:
            continue
        votes = Counter(media_line[m] for n in o["switch"].get(brit_state, [])
                        for m in clips(graph, n) if m in media_line)
        if len(votes) != 1:
            raise SystemExit(f"container {cid} does not map to one DAT line: {dict(votes)}")
        containers[next(iter(votes))].append(cid)

    # The canonical shape of each line, from the calibration civ: its codes with
    # the civ prefix stripped ("bvms1" -> "vms1"), in variant order.
    brit_prefix = "b"
    canon = {sid: [s[len(brit_prefix):] for s in sorted(
                {st for sd, c, st, _ in items if sd == sid and c == CALIBRATION_CIV}, key=natural)]
             for sid in containers}

    stems_of = defaultdict(lambda: defaultdict(set))           # civ -> sid -> stems
    for sid, civ, stem, _ in items:
        stems_of[civ][sid].add(stem)

    def prefix(civ: int) -> str:
        found = Counter(m.group(1) for stems in stems_of[civ].values() for s in stems
                        if (m := re.match(r"^([a-z]+?)(v[mfp]|k[ms]\d)", s)))
        return found.most_common(1)[0][0] if found else ""

    prefixes = {prefix(i): i for i, e in enumerate(roster) if i and e["name"]}
    codes = {code for line in canon.values() for code in line}

    def broken(civ: int, own: str) -> list[str]:
        """Ways this civ's DAT filenames can't carry its Wwise lines."""
        why = []
        line_of = defaultdict(set)
        for sid in containers:
            for s in stems_of[civ].get(sid, ()):
                line_of[s].add(sid)
        shared = sorted(s for s, sids in line_of.items() if len(sids) > 1)
        if shared:
            why.append(f"one file for several lines: {shared}")
        # Another civ's file = its prefix + a real line code ("danevfl").  A bare
        # prefix match is not enough: Aztecs' "vzpmm2" is an old typo, not Vikings'.
        foreign = sorted(s for s in line_of if not s.startswith(own)
                         and any(s.startswith(p) and s[len(p):] in codes
                                 for p in prefixes if p and p != own))
        if foreign:
            why.append(f"another civ's files: {foreign}")
        return why

    states = {s for ids in containers.values() for c in ids for s in graph[c]["switch"]}
    civs = {}
    for idx, entry in enumerate(roster):
        name = entry["name"]
        if idx == 0 or not name or name.lower() in SKIP_CIVS:
            continue
        state = fnv1(STATE_ALIASES.get(name.lower(), name))
        if state not in states:
            print(f"  {name}: no Wwise state — skipped")
            continue
        media_of: dict[int, list[int]] = {}
        for sid, cids in containers.items():
            media = []
            for c in cids:
                for n in graph[c]["switch"].get(state, []):
                    media += clips(graph, n)
            media_of[sid] = [m for m in dict.fromkeys(media) if m in bank]

        own = prefix(idx)
        why = broken(idx, own)
        files: dict[str, int] = {}
        entry_out: dict = {"value": idx - 1}
        if why:
            # The DAT's names are unusable (FE placeholders — the unmodded game
            # plays through Wwise and never reads them), so name every line
            # canonically and have assign_all_languages rebuild the items.
            lines = {}
            for sid, media in media_of.items():
                stems = [own + code for code in canon[sid]][:len(media)]
                if stems:
                    lines[str(sid)] = stems
                    files.update(zip(stems, media))
            entry_out["rebuild"] = why
            entry_out["lines"] = dict(sorted(lines.items(), key=lambda kv: int(kv[0])))
            print(f"  {name}: DAT names rebuilt — {'; '.join(why)}")
        else:
            for sid, media in media_of.items():
                for stem, mid in zip(sorted(stems_of[idx].get(sid, ()), key=natural), media):
                    files.setdefault(stem, mid)
        entry_out["files"] = dict(sorted(files.items()))
        civs[name] = entry_out
    return {"switch_group": CIV_SWITCH_GROUP, "civs": civs}


# ── extract: map + wwise folder -> voice_files/<value>/ ──────────────────────

def extract(wwise_dir: Path, names: list[str], overwrite: bool, fill: bool = False) -> int:
    vmap = json.loads(MAP_PATH.read_text(encoding="utf-8"))["civs"]
    bank = media_index(wwise_dir)
    if not bank:
        print(f"No embedded media found under {wwise_dir} — is that the game's wwise folder?")
        return 1

    def write(out: Path, files: dict[str, int]) -> None:
        for stem, mid in files.items():
            pck, off, size = bank[mid]
            with open(pck, "rb") as f:
                f.seek(off)
                (out / f"{stem}.wem").write_bytes(f.read(size))

    status = 0
    for name in names:
        entry = vmap[name]
        out = VOICE_DIR / str(entry["value"])
        have = {p.stem.lower() for p in out.glob("*.wem")} if out.is_dir() else set()
        if have and not (overwrite or fill):
            print(f"  {name}: voice_files/{entry['value']} exists — skipped "
                  "(--overwrite to replace, --fill to add what it lacks)")
            continue
        missing = [s for s, mid in entry["files"].items() if mid not in bank]
        if missing:
            print(f"  {name}: {len(missing)} clip(s) not in this install ({missing[:3]}…) "
                  "— a patch may have changed the bank; rebuild the map")
            status = 1
            continue
        out.mkdir(parents=True, exist_ok=True)
        if fill:
            # Add only what the folder lacks.  KM's folders miss clips the DAT
            # names with typos (Incas' "inmms1", Mayans' "mymma1"), and those
            # lines otherwise play the replaced slot's own voice.
            todo = {s: m for s, m in entry["files"].items() if s not in have}
            write(out, todo)
            if todo:
                print(f"  {name}: filled {sorted(todo)}")
            continue
        for stale in out.glob("*.wem"):         # a rebuilt map may rename files
            stale.unlink()
        write(out, entry["files"])
        print(f"  {name}: {len(entry['files'])} files -> voice_files/{entry['value']}")
    return status


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("extract", help="write voice_files/<value>/ from the game")
    ex.add_argument("--wwise", required=True, type=Path, help="the game's resources/_common/wwise")
    grp = ex.add_mutually_exclusive_group(required=True)
    grp.add_argument("--civ", action="append", help="civ name (repeatable)")
    grp.add_argument("--missing", action="store_true", help="every civ with no folder yet")
    grp.add_argument("--all", action="store_true", help="every civ in the map")
    ex.add_argument("--overwrite", action="store_true", help="replace existing folders")
    ex.add_argument("--fill", action="store_true",
                    help="only add clips an existing folder lacks; never replaces")

    mp = sub.add_parser("map", help="rebuild voice_wwise_map.json")
    mp.add_argument("--wwiser-xml", required=True, type=Path)
    mp.add_argument("--sheet", required=True, type=Path,
                    help='"OLD Audio Sources - Speech" tab as CSV')
    mp.add_argument("--wwise", required=True, type=Path)
    mp.add_argument("--dat", help="DAT to read (default: detected install)")

    sp = sub.add_parser("split", help="split a .pck into .bnk files for wwiser")
    sp.add_argument("pck", type=Path)
    sp.add_argument("out", type=Path)

    args = ap.parse_args()
    if args.cmd == "split":
        for p in split_banks(args.pck, args.out):
            print(p)
        return 0
    if args.cmd == "map":
        from dat_reader import find_game_dat, load_dat
        from build_civ import civ_roster
        dat_path = args.dat or find_game_dat()
        vmap = build_map(load_graph(args.wwiser_xml), load_dat(str(dat_path)),
                         civ_roster(str(dat_path)), args.sheet, media_index(args.wwise))
        MAP_PATH.write_text(json.dumps(vmap, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {MAP_PATH.name}: {len(vmap['civs'])} civs")
        return 0

    vmap = json.loads(MAP_PATH.read_text(encoding="utf-8"))["civs"]
    if args.civ:
        unknown = [c for c in args.civ if c not in vmap]
        if unknown:
            print(f"Not in the map: {unknown}.  Known: {', '.join(vmap)}")
            return 1
        names = args.civ
    elif args.missing:
        names = [n for n, e in vmap.items() if not (VOICE_DIR / str(e["value"])).is_dir()]
    else:
        names = list(vmap)
    return extract(args.wwise, names, args.overwrite, args.fill)


if __name__ == "__main__":
    sys.exit(main())
