#!/usr/bin/env python3
"""Install detection beyond the default folders, and the remembered path.

Detection only knew Steam's default folder and two fixed Microsoft paths on C:,
so a Steam library on a second drive, or an Xbox app install on D:, meant typing
the path — and typing it again every launch, since nothing kept it (the session
key is new each launch).  Players got stuck there (2026-10-29).

Built on fake drives in a temp folder, so it runs on any machine; that it finds
a real Windows install is still for a Windows run to show.

    venv/bin/python tests/test_dat_detection.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="ef_detect_"))
os.environ["EMPIREFORGE_DATA_DIR"] = str(TMP / "appdata")
os.environ.pop("EMPIREFORGE_DAT", None)

import dat_reader                                  # noqa: E402
from dat_reader import (DAT_REL, find_game_dat, install_candidates,  # noqa: E402
                        remember_dat_path, saved_dat_path, steam_library_dirs)

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


def fake_dat(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dat")
    return path


C, D, E = TMP / "C", TMP / "D", TMP / "E"
for d in (C, D, E):
    d.mkdir()

print("=== Steam libraries on other drives ===")
steam = C / "Program Files (x86)" / "Steam"
lib = D / "SteamLibrary"
(steam / "steamapps").mkdir(parents=True)
(steam / "steamapps" / "libraryfolders.vdf").write_text(
    '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"%s"\n'
    '\t\t"apps"\n\t\t{\n\t\t\t"813780"\t\t"123"\n\t\t}\n\t}\n}\n' % (steam, lib), encoding="utf-8")
libs = steam_library_dirs([steam])
check("the library on the second drive is listed", lib in libs, libs)
check("Steam's own folder is listed once", libs.count(steam) == 1, libs)

win_vdf = TMP / "winsteam"
(win_vdf / "steamapps").mkdir(parents=True)
(win_vdf / "steamapps" / "libraryfolders.vdf").write_text(
    '"libraryfolders"\n{\n\t"1"\n\t{\n\t\t"path"\t\t"D:\\\\SteamLibrary"\n\t}\n}\n', encoding="utf-8")
win_libs = [str(p) for p in steam_library_dirs([win_vdf])]
check("Windows paths are unescaped (D:\\\\SteamLibrary -> D:\\SteamLibrary)",
      "D:\\SteamLibrary" in win_libs, win_libs)
check("a Steam root with no libraryfolders.vdf is still tried",
      steam_library_dirs([E / "nosteam"]) == [E / "nosteam"])

steam_dat = fake_dat(lib / "steamapps/common/AoE2DE" / DAT_REL)
check("the AoE2 DAT in that library is a candidate",
      steam_dat in install_candidates([C, D, E], [steam]))

print("\n=== Xbox app installs on any drive ===")
steam_dat.unlink()
fake_dat(E / "XboxGames" / "Age of Mythology Retold" / "Content" / "game.dat")
xbox_dat = fake_dat(E / "XboxGames" / "Age of Empires II- Definitive Edition" / "Content" / DAT_REL)
cands = install_candidates([C, D, E], [steam])
check("an Xbox install on E: is found whatever the game folder is called", xbox_dat in cands, cands)
check("other Xbox games are not candidates",
      not any("Mythology" in str(c) for c in cands), cands)

print("\n=== old Microsoft Store installs ===")
apps = C / "Program Files" / "WindowsApps"
old = fake_dat(apps / "Microsoft.MSPhoenix_100.2.1_x64__8wekyb3d8bbwe" / DAT_REL)
new = fake_dat(apps / "Microsoft.MSPhoenix_101.103.4_x64__8wekyb3d8bbwe" / DAT_REL)
cands = install_candidates([C, D, E], [steam])
check("the newest Store version comes before an older one",
      new in cands and old in cands and cands.index(new) < cands.index(old))

print("\n=== find_game_dat: saved path, then detection ===")
dat_reader.STEAM_DAT_CANDIDATES = []
dat_reader._drive_roots = lambda: [C, D, E]
dat_reader._steam_roots = lambda: [steam]
check("nothing saved: detection finds the Xbox install", find_game_dat() == xbox_dat, find_game_dat())

custom = fake_dat(TMP / "Games" / "AoE2" / DAT_REL)
remember_dat_path(custom)
settings = TMP / "appdata" / "settings.json"
check("remembering writes the settings file",
      json.loads(settings.read_text(encoding="utf-8")).get("dat_path") == str(custom))
check("the saved path wins over detection", find_game_dat() == custom, find_game_dat())

custom.unlink()
check("a saved path that has gone falls through to detection",
      saved_dat_path() is None and find_game_dat() == xbox_dat, find_game_dat())

settings.write_text("{not json", encoding="utf-8")
check("a corrupt settings file is ignored", find_game_dat() == xbox_dat, find_game_dat())
settings.write_text('["a list"]', encoding="utf-8")
remember_dat_path(xbox_dat)
check("and remembering over it repairs it", saved_dat_path() == xbox_dat, saved_dat_path())

os.environ["EMPIREFORGE_DAT"] = str(new)
check("EMPIREFORGE_DAT still beats everything", find_game_dat() == new, find_game_dat())
os.environ.pop("EMPIREFORGE_DAT")

print("\n=== the app remembers a path the player gave it ===")
os.environ["EMPIREFORGE_DAT"] = str(TMP / "none")  # no startup prewarm of a fake DAT
import app as appmod                               # noqa: E402
os.environ.pop("EMPIREFORGE_DAT")

appmod.app.config["TESTING"] = True
client = appmod.app.test_client()
typed = fake_dat(TMP / "Typed" / DAT_REL)
typed.write_bytes(b"\0" * (2 * 1024 * 1024))       # validate-dat wants more than 1 MB
res = client.get("/api/builder/validate-dat", query_string={"dat_path": f'"{typed}"'})
check("validate-dat accepts it", res.get_json().get("ok") is True, res.get_json())
check("and it is remembered for next launch", saved_dat_path() == typed, saved_dat_path())
check("so detection now returns it", find_game_dat() == typed, find_game_dat())

typed2 = fake_dat(TMP / "Typed2" / DAT_REL)
client.post("/upload", data={"dat_path": str(typed2.parent)})
check("Build Mod remembers a pasted folder as the DAT inside it",
      saved_dat_path() == typed2, saved_dat_path())

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
