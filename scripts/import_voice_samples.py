#!/usr/bin/env python3
"""Convert one villager voice clip per language into a browser-playable sample.

The wizard's Voice control plays a short clip when you pick a voice set, so the
choice stops being an abstract civ name.  The source is already in the repo:
voice_files/<lang>/ holds the game's Wwise .wem clips, keyed by exactly the
value the voice select uses (0-42).

Filenames are prefixed with a per-language code rather than a fixed one —
British is bvms1.wem, Chinese cvms1.wem, Indian invms1.wem, Roman rovms1.wem —
so the villager clip is found by pattern, not by name:

    <code>vms<n>.wem   villager, male, select     (preferred)
    <code>vfs<n>.wem   villager, female, select   (fallback)

Browsers can't decode Wwise Vorbis and neither can ffmpeg, so this needs
vgmstream:  brew install vgmstream

Output: static/audio/voice/<lang>.mp3  (43 files, a few KB each).  MP3 rather
than Ogg because Homebrew's ffmpeg is not always built with libvorbis, and
libmp3lame plays everywhere without container caveats.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "voice_files"
OUT = ROOT / "static" / "audio" / "voice"

# Hand-supplied single clips ("hello" lines), named after the civ:
#   ignore/voice_samples/armenians.ogg -> static/audio/voice/43.mp3
# These only feed the PICKER PREVIEW.  The mod build reads voice_files/<value>/
# and needs the game's real .wem files under the exact names the DAT references,
# so a clip here does not make a civ's voice work in-game.
SAMPLE_SRC = ROOT / "ignore" / "voice_samples"
SAMPLE_EXTS = {".ogg", ".wav", ".mp3", ".m4a", ".flac", ".opus"}

# Common RMS target for every clip, and the peak the limiter will not exceed.
# -20 dBFS sits comfortably above the quietest source (Slavic, -38.4) without
# demanding so much gain that the limiter has to work hard on it.
TARGET_DBFS = -20.0
PEAK_CEILING_DB = -1.0

# Preference order: male villager select, then female, then male move.
PATTERNS = (
    re.compile(r"^[a-z]+vms\d*\.wem$"),
    re.compile(r"^[a-z]+vfs\d*\.wem$"),
    re.compile(r"^[a-z]+vmm\d*\.wem$"),
)


def pick_clip(lang_dir: Path) -> Path | None:
    names = sorted(p.name for p in lang_dir.glob("*.wem"))
    for pattern in PATTERNS:
        for name in names:
            if pattern.match(name):
                return lang_dir / name
    return None


_MEAN_RE = re.compile(r"mean_volume:\s*(-?[\d.]+)")
_PEAK_RE = re.compile(r"max_volume:\s*(-?[\d.]+)")


def measure(path: Path) -> tuple[float, float] | None:
    """(mean dBFS, peak dBFS) via ffmpeg's volumedetect."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path),
                        "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    mean, peak = _MEAN_RE.search(r.stderr), _PEAK_RE.search(r.stderr)
    if not (mean and peak):
        return None
    return float(mean.group(1)), float(peak.group(1))


def convert(src: Path, dest: Path, vgmstream: str, target_dbfs: float) -> bool:
    """wem -> wav (vgmstream) -> loudness-matched mp3 (ffmpeg).

    The game's clips span ~24 dB of mean volume — the newest DLC civs were
    mastered far hotter than the originals — so they are matched to a common
    RMS target here.

    Deliberately NOT EBU R128 / `loudnorm`: that gates on 400 ms blocks and
    these clips run 0.27-0.64 s, so several are under a single block and the
    measurement is meaningless.  RMS + a lookahead limiter is the right tool at
    this length.  The limiter only engages on clips that need enough gain to
    push peaks past the ceiling, which is a handful of the quietest.
    """
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw.wav"
        wav = Path(td) / "mono.wav"
        r = subprocess.run([vgmstream, "-o", str(raw), str(src)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not raw.exists():
            print(f"  !  vgmstream failed on {src.name}: {r.stderr.strip()[:120]}")
            return False

        # Downmix to mono FIRST, then measure.  ffmpeg's stereo->mono downmix
        # normalises by 1/sqrt(2) rather than 1/2, so correlated channels come
        # out ~3 dB hotter — measuring the stereo source and encoding with
        # `-ac 1` silently overshoots the target by that much.
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(raw), "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not wav.exists():
            print(f"  !  mono downmix failed on {src.name}: {r.stderr.strip()[:120]}")
            return False

        stats = measure(wav)
        if stats is None:
            print(f"  !  could not measure {src.name}; copying at source level")
            af = "anull"
        else:
            mean, _peak = stats
            # alimiter's `limit` is LINEAR (0.0625-1), not dB, and its `level`
            # option defaults to true — which auto-renormalises the output back
            # to full scale and quietly undoes the ceiling.  Both must be set
            # explicitly or peaks come out at 0 dBFS.
            limit = 10 ** (PEAK_CEILING_DB / 20)
            af = (f"volume={target_dbfs - mean:.2f}dB,"
                  f"alimiter=limit={limit:.4f}:level=disabled")

        # Already mono — no -ac here, or the downmix gain would apply twice.
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(wav), "-af", af,
             "-c:a", "libmp3lame", "-q:a", "6", str(dest)],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  !  ffmpeg failed on {src.name}: {r.stderr.strip()[:120]}")
            return False
    return True


def _have_encoder(name: str) -> bool:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                       capture_output=True, text=True)
    return any(line.split()[1:2] == [name] for line in r.stdout.splitlines() if line.startswith(" A"))


def _civ_value_lookup() -> dict[str, tuple[int, str]]:
    """slug -> (voice value, civ name), from civilizations.json internal names."""
    import json
    civs = json.loads((ROOT / "civilizations.json").read_text())["civilization_list"]
    table: dict[str, tuple[int, str]] = {}
    for i, c in enumerate(civs):
        name = c.get("internal_name") or ""
        if i > 0 and name:
            table[re.sub(r"[^a-z0-9]", "", name.lower())] = (i - 1, name)
    return table


def import_samples(force: bool, target_dbfs: float) -> tuple[int, list[str]]:
    """Import hand-supplied single clips named after the civ (preview only)."""
    if not SAMPLE_SRC.is_dir():
        return 0, []
    table = _civ_value_lookup()
    written, unknown = 0, []
    for src in sorted(SAMPLE_SRC.iterdir()):
        if src.suffix.lower() not in SAMPLE_EXTS:
            continue
        hit = table.get(re.sub(r"[^a-z0-9]", "", src.stem.lower()))
        if not hit:
            unknown.append(src.name)
            continue
        value, name = hit
        dest = OUT / f"{value}.mp3"
        if dest.exists() and not force and dest.stat().st_mtime >= src.stat().st_mtime:
            continue
        # Same loudness treatment as the .wem-derived clips, so a hand-supplied
        # sample doesn't stand out as louder or quieter than its neighbours.
        stats = measure(src)
        af = ("anull" if stats is None else
              f"volume={target_dbfs - stats[0]:.2f}dB,"
              f"alimiter=limit={10 ** (PEAK_CEILING_DB / 20):.4f}:level=disabled")
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
             "-af", af, "-ac", "1", "-c:a", "libmp3lame", "-q:a", "6", str(dest)],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  !  ffmpeg failed on {src.name}: {r.stderr.strip()[:120]}")
            continue
        print(f"  [sample] {src.name}  ->  {value}.mp3   ({name})")
        written += 1
    return written, unknown


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-encode existing samples")
    ap.add_argument("--target-dbfs", type=float, default=TARGET_DBFS,
                    help=f"common RMS loudness target (default {TARGET_DBFS})")
    args = ap.parse_args()

    if not SRC.is_dir():
        sys.exit(f"No voice_files/ directory at {SRC}")

    vgmstream = shutil.which("vgmstream-cli") or shutil.which("vgmstream")
    if not vgmstream:
        sys.exit("vgmstream not found — install it with:  brew install vgmstream\n"
                 "(Browsers and ffmpeg both refuse Wwise Vorbis, so it's required.)")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found — install it with:  brew install ffmpeg")
    if not _have_encoder("libmp3lame"):
        sys.exit("This ffmpeg has no libmp3lame encoder.\n"
                 "Reinstall a full build:  brew reinstall ffmpeg")

    OUT.mkdir(parents=True, exist_ok=True)
    lang_dirs = sorted((p for p in SRC.iterdir() if p.is_dir() and p.name.isdigit()),
                       key=lambda p: int(p.name))

    written = skipped = 0
    missing: list[str] = []
    for lang_dir in lang_dirs:
        dest = OUT / f"{lang_dir.name}.mp3"
        if dest.exists() and not args.force:
            skipped += 1
            continue
        clip = pick_clip(lang_dir)
        if clip is None:
            missing.append(lang_dir.name)
            continue
        if convert(clip, dest, vgmstream, args.target_dbfs):
            written += 1

    sample_written, sample_unknown = import_samples(args.force, args.target_dbfs)
    written += sample_written

    made = sorted(OUT.glob("*.mp3"))
    total = sum(f.stat().st_size for f in made)
    print(f"{written} written, {skipped} up to date -> {OUT.relative_to(ROOT)} "
          f"({len(made)} files, {total / 1024:.0f} KB)")
    if missing:
        print(f"No villager clip found for language(s): {', '.join(missing)}")
    if sample_unknown:
        print(f"\nUnrecognised names in {SAMPLE_SRC.relative_to(ROOT)}: "
              + ", ".join(sample_unknown))
        print("  Name them after the civ, e.g. armenians.ogg, shu.ogg, tupi.ogg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
