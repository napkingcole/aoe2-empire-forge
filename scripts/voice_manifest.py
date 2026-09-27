#!/usr/bin/env python3
"""Which voice .wem files each civ needs, and which of them we are missing.

    venv/bin/python scripts/voice_manifest.py                # what's missing
    venv/bin/python scripts/voice_manifest.py --all          # every civ
    venv/bin/python scripts/voice_manifest.py --value 59     # one civ
    venv/bin/python scripts/voice_manifest.py --check        # verify what we have

A civ's voice needs two things, and only one of them is code: the DAT SoundItem
remap (`assign_all_languages`) and the physical .wem files, which
`_build_combined_ui_zip` copies out of `voice_files/<value>/` into the UI mod at
`resources/_common/drs/sounds/`.  Without the files the engine falls back to
Wwise bank routing and the civ speaks with its slot's original voice.

`voice_files/` is a byte-identical copy of KrakenMeister's
`public/vanillaFiles/voiceFiles/` — 43 folders, values 0-42.  Nothing was ever
extracted here, which is why every civ added since his snapshot (Armenians,
Georgians, the Chinese DLC four, the South American three, and now the Viking
Sagas three) has no voice option: there was no source, not a missing feature.

The names below are read from the DAT, so they are the names the engine will
actually look for.  The DAT stores them as `.wav`; the file on disk is the same
stem with `.wem`.

WHERE THE VANILLA FILES LIVE (checked 2026-09-23, so nobody repeats the hunt).
NOT in the Wwise packages.  The whole `resources/_common/wwise/` tree — 20 .pck
files, 2.2 GB — holds 7528 entries, only 1519 of them non-localized, which is
not enough for even the 43 old civs at ~58 clips each.  Parsing them (they are
standard AKPK: header, language map, then bank/stream/external tables of
`id, block, size, offset, lang`) and matching by content finds nothing, because
the game has also re-encoded since KM's snapshot: his clips are Wwise Vorbis at
22 kHz, a few KB each, while everything in the packages now is Opus at 48 kHz
and ~10x larger.  No FNV-1/FNV-1a variant of the clip names hits a package id
either.

Every civ-bound `SoundItem` carries a `resource_id` in the 5501-9159 range,
numbered sequentially per civ (Japanese `jvmb.wav` is 5501, `jvmfa.wav` 5502).
That looks like a DRS id, but the shipped `resources/_common/drs/` has no
`sounds/` folder at all — it holds gamedata_x2, graphics, interface and
small-trees.  `drs/sounds/` is a path the engine checks for OVERRIDES, which is
why our mods work; vanilla playback does not come from there.

THE AUDIO IS IN THE BANKS (the 2026-09-23 view; see SUPERSEDED below).
The clips are embedded inside
the Wwise banks rather than the stream tables: `Base.pck` bank 232745270 is
149 MB holding 6150 embedded media at ~10 KB median, exactly the profile of
one-second unit barks, and 9776 across all banks.  They extract fine — the DIDX
chunk gives offset and size for each.

What does not exist anywhere in the shipped files is a NAME.  The banks carry
only `BKHD` + `DIDX` + `DATA`: no `STID`, no `HIRC` name table, and the install
ships no `SoundbanksInfo.xml`.  The media ids are opaque 32-bit values spanning
47786 to 1073577617 with no relationship to the DAT's resource ids, and no
FNV-1 or FNV-1a variant of a clip name (bare, +.wav, +.wem, upper, play_ prefix)
matches one — tested against both the package entry ids and the embedded media
ids, which are separate id spaces.

The audio DOES extract, and it can be identified — for clips we already have.
Decoding both sides (vgmstream + ffmpeg) and correlating a coarse RMS envelope
matches KM's clips to bank indices essentially perfectly: **2432 of 2434 known
clips at >0.98**, most at 1.000.  So anything we hold a reference for can be
located in the bank and re-extracted at the current quality (Opus 48 kHz rather
than KM's Vorbis 22 kHz).

What that CANNOT do is name a clip we have no reference for, and that is exactly
the thirteen civs.  Three independent routes were tried and all are dead:

  * Structure.  Indices do not group by civ (Britons span 556-4420) and are not
    monotonic by civ for any clip type — DIDX is ordered by media id, which is
    effectively random.  Nothing to extrapolate from.  (It does confirm a known
    quirk: Goths and Teutons share one voice set, and so share indices.)
  * Per-DLC banks.  Every DLC .pck bank holds ~60-90 clips at a ~0.12 s median:
    UI blips and footsteps, not speech.  No DLC ships a civ voice set.
  * Hashing.  With 2422 ground-truth (name, media_id) pairs in hand, seven
    schemes were tested — FNV-1 and FNV-1a over the bare name, +.wav, +.wem,
    uppercase, and a 30-bit mask.  **Zero hits.**  The ids come from the Wwise
    project, not the filename.

SUPERSEDED 2026-09-25 — the names ARE recoverable, just not from a hash.
The same bank carries a HIRC event graph (the "no HIRC" above was wrong), and
every voice line is a switch container on a 64-state civ switch whose state ids
are FNV-1 hashes of the civ names.  `scripts/voice_wwise.py` walks it and
extracts all 13 missing civs; the history above is kept for the dead ends.

"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat            # noqa: E402
from build_civ import civ_roster                          # noqa: E402

VOICE_DIR = ROOT / "voice_files"


def civ_sound_names(dat) -> dict[int, set[str]]:
    """civ slot -> the SoundItem filenames bound to it (vanilla slots only)."""
    out: dict[int, set[str]] = defaultdict(set)
    for sound in dat.sounds:
        for item in sound.items:
            civ = item.civilization
            if 0 < civ < 100:                 # 100+ is the remap scratch range
                out[civ].add(item.filename)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dat", help="DAT to read (default: detected install)")
    ap.add_argument("--all", action="store_true", help="list every civ, not just gaps")
    ap.add_argument("--value", type=int, help="just this voice value")
    ap.add_argument("--check", action="store_true",
                    help="verify the folders we DO have against the DAT")
    args = ap.parse_args()

    dat_path = args.dat or find_game_dat()
    if not dat_path:
        print("No DAT found — pass --dat.")
        return 1
    dat = load_dat(str(dat_path))
    roster = civ_roster(str(dat_path))
    names = civ_sound_names(dat)

    def on_disk(value: int) -> set[str]:
        d = VOICE_DIR / str(value)
        if not d.is_dir():
            return set()
        return {f.name for f in d.iterdir() if f.suffix == ".wem"}

    rows = []
    for slot in range(1, len(roster)):
        value = slot - 1
        if args.value is not None and value != args.value:
            continue
        # Chronicles civs are blacklisted from the wizard entirely, so their
        # voices are not a gap — listing them would overstate the work.
        if roster[slot].get("era") == "antiquity":
            continue
        wanted = {Path(n).stem + ".wem" for n in names.get(slot, set())}
        have = on_disk(value)
        rows.append((value, roster[slot]["name"], wanted, have))

    if args.check:
        print("Folders we have, checked against what the DAT asks for:\n")
        bad = 0
        for value, civ, wanted, have in rows:
            if not have:
                continue
            missing, extra = wanted - have, have - wanted
            status = "ok" if not missing else f"MISSING {len(missing)}"
            if missing:
                bad += 1
            print(f"  {value:<4} {civ:<14} on disk {len(have):<4} wanted {len(wanted):<4} {status}")
            if missing:
                print(f"        {sorted(missing)[:8]}")
            if extra:
                print(f"        (+{len(extra)} on disk the DAT never names — harmless)")
        print(f"\n{bad} folder(s) short of what the DAT names.")
        if bad:
            print("Shortfalls are expected: KM's snapshot predates clips DE has")
            print("added since (the vpfm*/vpfs* priest lines). A civ still speaks")
            print("— the engine falls back to Wwise routing per missing file.")
        return 0

    gaps = [r for r in rows if not r[3]]
    show = rows if args.all else gaps
    print(f"{len(gaps)} civ(s) have no voice files at all.\n")
    for value, civ, wanted, have in show:
        mark = "" if have else "   <-- no folder"
        print(f"voice_files/{value}/   {civ}   {len(wanted)} files{mark}")
        for n in sorted(wanted):
            print(f"    {n}")
        print()
    if not args.all and gaps:
        print("Copy each civ's files into the folder named above; the Voice")
        print("dropdown is driven by folder contents, so they appear with no")
        print("code change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
