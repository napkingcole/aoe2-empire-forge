"""
dat_reader.py — Load and inspect an AoE2 DE DAT file.

Auto-detects the Steam/Xbox Game Pass/Microsoft Store installation on Mac and Windows.
Call load_dat() to get a DatFile object ready for modification.
"""

import json
import os
import re
import sys
from pathlib import Path

from genieutils.datfile import DatFile

STEAM_DAT_CANDIDATES = [
    # macOS — Steam
    Path.home() / "Library/Application Support/Steam/steamapps/common/AoE2DE"
    / "resources/_common/dat/empires2_x2_p1.dat",
    # dev: a full Windows install copied to the Mac (2026-10-21), the one
    # source on this machine.  Everything else — strings, CivTechTrees,
    # civilizations.json, voice banks — is found relative to the DAT, so a
    # DAT-only copy never behaved like a player's; those candidates (../aoe2/)
    # were removed.  EMPIREFORGE_DAT still points a run at any other DAT.
    Path.home() / "Age of Empires 2/resources/_common/dat/empires2_x2_p1.dat",
    # Windows — Steam (32-bit Program Files)
    Path("C:/Program Files (x86)/Steam/steamapps/common/AoE2DE"
         "/resources/_common/dat/empires2_x2_p1.dat"),
    # Windows — Steam (64-bit Program Files)
    Path("C:/Program Files/Steam/steamapps/common/AoE2DE"
         "/resources/_common/dat/empires2_x2_p1.dat"),
    # Windows — Xbox Game Pass
    Path("C:/XboxGames/Age of Empires II Definitive Edition/Content"
         "/resources/_common/dat/empires2_x2_p1.dat"),
]


DAT_REL = Path("resources/_common/dat/empires2_x2_p1.dat")
_SETTINGS = "settings.json"


def _settings_path() -> Path:
    from custom_bonus import data_dir          # lazy: custom_bonus is heavier
    return data_dir() / _SETTINGS


def saved_dat_path() -> Path | None:
    """The DAT the player last pointed Empire Forge at, if it is still there."""
    try:
        raw = json.loads(_settings_path().read_text(encoding="utf-8")).get("dat_path")
    except (OSError, ValueError, AttributeError):
        return None
    p = Path(raw) if isinstance(raw, str) and raw else None
    return p if p is not None and p.is_file() else None


def remember_dat_path(dat_path: str | Path) -> None:
    """Keep a working DAT path for the next launch.

    The session can't hold it: the secret key is new every launch, and a
    browser draft lives on one port.  So a player whose install detection
    misses typed the path again every time.  Best effort — failing to save
    must never fail the page that called it.
    """
    try:
        f = _settings_path()
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        if data.get("dat_path") == str(dat_path):
            return
        data["dat_path"] = str(dat_path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _drive_roots() -> list[Path]:
    """Every drive on Windows (C:\\, D:\\, ...); nothing elsewhere."""
    if sys.platform != "win32":
        return []
    if hasattr(os, "listdrives"):                  # Python 3.12+
        try:
            return [Path(d) for d in os.listdrives()]
        except OSError:
            pass
    return [Path(f"{c}:/") for c in "CDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{c}:/").exists()]


def _steam_roots() -> list[Path]:
    """Where Steam itself is installed: the registry, then the defaults."""
    roots: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except OSError:
            pass
        roots += [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
    elif sys.platform == "darwin":
        roots.append(Path.home() / "Library/Application Support/Steam")
    return roots


_VDF_PATH = re.compile(r'"path"\s+"([^"]*)"')


def steam_library_dirs(steam_roots: list[Path]) -> list[Path]:
    """Every Steam library, read from each root's steamapps/libraryfolders.vdf.

    A library on a second drive (D:\\SteamLibrary) is listed only there.
    """
    out: list[Path] = []
    for root in steam_roots:
        out.append(root)
        try:
            text = (root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out += [Path(m.replace("\\\\", "\\")) for m in _VDF_PATH.findall(text)]
    seen, uniq = set(), []
    for p in out:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def install_candidates(drives: list[Path], steam_roots: list[Path]) -> list[Path]:
    """Every DAT path worth checking, in the order they are tried.

    Steam libraries first (the common case), then Xbox app installs, which go
    to <drive>:\\XboxGames\\<game>\\Content on whichever drive the player chose,
    then the old Microsoft Store location.
    """
    cands = [lib / "steamapps/common/AoE2DE" / DAT_REL for lib in steam_library_dirs(steam_roots)]
    for d in drives:
        xbox = d / "XboxGames"
        if xbox.is_dir():
            cands += sorted(xbox.glob(f"*/Content/{DAT_REL.as_posix()}"))
    for d in drives:
        apps = d / "Program Files" / "WindowsApps"
        if apps.is_dir():
            for rel in (f"Microsoft.MSPhoenix_*/{DAT_REL.as_posix()}",
                        "Microsoft.MSPhoenix_*/resources_common/dat/empires2_x2_p1.dat"):
                cands += sorted(apps.glob(rel), reverse=True)   # highest version first
    return cands


def find_game_dat() -> Path | None:
    """Return the path to the installed game DAT, or None if not found.

    `EMPIREFORGE_DAT` overrides detection.  It exists so the test suite can be
    pointed at a DAT that is not the installed one — a DLC build lands as a
    folder of files well before it is the copy on disk, and the interesting
    assertions are exactly the ones that differ between versions.

    Then the path the player last gave us (`remember_dat_path`): with two
    installs it says which one they meant, and with an install detection
    misses it saves typing it every launch.
    """
    override = os.environ.get("EMPIREFORGE_DAT")
    if override:
        p = Path(override).expanduser()
        return p if p.exists() else None

    saved = saved_dat_path()
    if saved is not None:
        return saved
    for candidate in STEAM_DAT_CANDIDATES:
        if candidate.exists():
            return candidate
    try:
        for candidate in install_candidates(_drive_roots(), _steam_roots()):
            if candidate.is_file():
                return candidate
    except OSError:
        pass
    return None


def find_civtechtrees(dat_path: str | Path) -> Path | None:
    """Return the CivTechTrees folder next to the DAT file, or None if not found."""
    p = Path(dat_path).parent / "CivTechTrees"
    return p if p.is_dir() else None


def load_civ_era_exclusions(dat_path: str | Path) -> set[str] | None:
    """Read civilizations.json adjacent to the DAT and return internal_names of
    non-base (e.g. antiquity) civs to exclude from the replace-target list.
    Returns None if the file is absent or unparseable — caller should fall back
    to a hardcoded exclusion set."""
    import json
    civs_json = Path(dat_path).parent / "civilizations.json"
    try:
        data = json.loads(civs_json.read_text(encoding="utf-8"))
        return {
            c["internal_name"]
            for c in data.get("civilization_list", [])
            if c.get("era", "base") != "base"
        }
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError):
        return None


def find_game_strings(dat_path: str | Path | None) -> Path | None:
    """The game's English key-value strings for this DAT, or None.

    The DAT is `<game>/resources/_common/dat/empires2_x2_p1.dat` on Steam and
    Xbox alike, so the game root is three folders above its folder — the same
    walk voice_source.find_wwise_dir makes.  English whatever the player's
    language: every name in the UI and the build logs is English."""
    if not dat_path:
        return None
    parents = Path(dat_path).resolve().parents
    if len(parents) <= 3:
        return None
    p = parents[3] / "resources" / "en" / "strings" / "key-value" / "key-value-strings-utf8.txt"
    return p if p.is_file() else None


def find_unit_icon(dat_path: str | Path | None, icon_id: int) -> Path | None:
    """The game's own picture for a unit's `icon_id`, or None.

    DE keeps unit icons as 256x256 DDS textures in
    `<game>/widgetui/textures/ingame/units/{icon_id:03}_50730.DDS` — some files
    have a lower-case extension.  (`resources/_common/wpfg/resources/uniticons`
    holds only ~95 legacy PNGs.)  Same walk from the DAT as find_game_strings."""
    if not dat_path or icon_id is None or icon_id < 0:
        return None
    parents = Path(dat_path).resolve().parents
    if len(parents) <= 3:
        return None
    folder = parents[3] / "widgetui" / "textures" / "ingame" / "units"
    for ext in ("DDS", "dds"):
        p = folder / f"{icon_id:03d}_50730.{ext}"
        if p.is_file():
            return p
    return None


# The DAT most recently loaded — the game whose strings name its units.
last_loaded: Path | None = None


def load_dat(path: str | Path) -> DatFile:
    """Parse and return a DatFile from the given path.

    Civ units are parsed lazily (see dat_lazy) — ~1-2s instead of ~18s once a
    DAT has been seen.  The saved bytes are identical either way."""
    global last_loaded
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DAT file not found: {path}")
    import dat_lazy
    dat = dat_lazy.parse(path)
    last_loaded = path
    return dat


def dat_info(dat: DatFile) -> dict:
    """Return a summary dict describing the contents of a loaded DAT."""
    return {
        "num_civs":          len(dat.civs),
        "num_units_per_civ": len(dat.civs[0].units) if dat.civs else 0,
        "num_techs":         len(dat.techs),
        "num_effects":       len(dat.effects),
        "num_unit_headers":  len(dat.unit_headers),
        "civ_names":         [c.name for c in dat.civs],
    }


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else find_game_dat()
    if not path:
        print("Could not auto-detect game DAT. Pass path as argument.")
        sys.exit(1)
    print(f"Loading: {path}")
    dat = load_dat(path)
    info = dat_info(dat)
    print(f"  Civs:          {info['num_civs']}")
    print(f"  Units/civ:     {info['num_units_per_civ']}")
    print(f"  Techs:         {info['num_techs']}")
    print(f"  Effects:       {info['num_effects']}")
    print(f"  Unit headers:  {info['num_unit_headers']}")
    names = info["civ_names"]
    preview = ", ".join(names[:6]) + ("..." if len(names) > 6 else "")
    print(f"  Civ names:     {preview}")
