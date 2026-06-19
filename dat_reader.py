"""
dat_reader.py — Load and inspect an AoE2 DE DAT file.

Auto-detects the Steam/Xbox Game Pass installation on Mac and Windows.
Call load_dat() to get a DatFile object ready for modification.
"""

import sys
from pathlib import Path

from genieutils.datfile import DatFile

STEAM_DAT_CANDIDATES = [
    # macOS — Steam
    Path.home() / "Library/Application Support/Steam/steamapps/common/AoE2DE"
    / "resources/_common/dat/empires2_x2_p1.dat",
    # dev reference copy (sibling aoe2/ directory — convenient for local testing)
    Path(__file__).parent.parent / "aoe2/dat-file-6-2-26/empires2_x2_p1.dat",  # VER 8.9 Jun 6
    Path(__file__).parent.parent / "aoe2/base/empires2_x2_p1.dat",
    Path(__file__).parent.parent / "aoe2/base-dat/empires2_x2_p1.dat",
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


def find_game_dat() -> Path | None:
    """Return the path to the installed game DAT, or None if not found."""
    for candidate in STEAM_DAT_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def load_dat(path: str | Path) -> DatFile:
    """Parse and return a DatFile from the given path."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DAT file not found: {path}")
    return DatFile.parse(str(path))


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
