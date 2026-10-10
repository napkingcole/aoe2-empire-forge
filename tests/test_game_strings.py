#!/usr/bin/env python3
"""Display names come from the player's game strings, with ours as fallback.

The exe shipped without vanilla/key-value/ — never listed in the spec — so
_string_table() swallowed the OSError and returned nothing.  The custom bonus
picker drops every entry with no name, and a player's Unit tab came up with
six units (the hard-coded PICKER_NAMES) and two filter pills.  So:

  - the game's own key-value file is found from the DAT and read first;
  - ours is the fallback when the DAT isn't in a game layout;
  - every data file the runtime reads through Path(__file__).parent is in
    the PyInstaller spec, so the next one can't go missing silently.

    venv/bin/python tests/test_game_strings.py
"""
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import civ_appender as ca                                   # noqa: E402
import dat_reader                                           # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}{(' — ' + extra) if extra else ''}")


def fresh_table(last_loaded):
    dat_reader.last_loaded = last_loaded
    ca._vanilla_strings = None
    return ca._string_table()


print("game strings are found from the DAT and read first")
with tempfile.TemporaryDirectory() as tmp:
    game = Path(tmp) / "AoE2DE"
    dat = game / "resources" / "_common" / "dat" / "empires2_x2_p1.dat"
    dat.parent.mkdir(parents=True)
    dat.write_bytes(b"")
    kv = game / "resources" / "en" / "strings" / "key-value" / "key-value-strings-utf8.txt"
    kv.parent.mkdir(parents=True)
    kv.write_text('5083 "Archer from the game"\n', encoding="utf-8")

    check("find_game_strings walks from the DAT to resources/en",
          dat_reader.find_game_strings(dat) == kv.resolve(),
          str(dat_reader.find_game_strings(dat)))
    table = fresh_table(dat)
    check("the game's file wins over ours", table.get(5083) == "Archer from the game",
          repr(table.get(5083)))

    kv.unlink()
    check("no game file -> None", dat_reader.find_game_strings(dat) is None)
    table = fresh_table(dat)
    check("falls back to our copy", len(table) > 10000 and table.get(5083) == "Archer",
          f"{len(table)} strings, 5083={table.get(5083)!r}")

print("a DAT outside a game layout uses our copy")
with tempfile.TemporaryDirectory() as tmp:
    loose = Path(tmp) / "empires2_x2_p1.dat"
    loose.write_bytes(b"")
    table = fresh_table(loose)
    check("loose DAT -> bundled strings", table.get(5083) == "Archer", repr(table.get(5083)))

print("re-read when a different DAT is loaded")
with tempfile.TemporaryDirectory() as tmp:
    game = Path(tmp) / "AoE2DE"
    dat = game / "resources" / "_common" / "dat" / "empires2_x2_p1.dat"
    dat.parent.mkdir(parents=True)
    dat.write_bytes(b"")
    kv = game / "resources" / "en" / "strings" / "key-value" / "key-value-strings-utf8.txt"
    kv.parent.mkdir(parents=True)
    kv.write_text('5083 "Patched Archer"\n', encoding="utf-8")
    fresh_table(None)
    dat_reader.last_loaded = dat           # what load_dat records
    check("switches to the newly loaded game's strings",
          ca._string_table().get(5083) == "Patched Archer", repr(ca._string_table().get(5083)))

dat_reader.last_loaded = None
ca._vanilla_strings = None

print("every runtime data path is bundled in the exe")
spec = (ROOT / "aoe2civbuilder.spec").read_text(encoding="utf-8")
datas = [src for src, _ in re.findall(r"\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", spec)]
# Dev-only fallbacks: never present in a player's install, and their code
# copes with absence.
DEV_ONLY = {"AoE2-Civbuilder-main/public", "dat-file-6-2-26/empires2_x2_p1.dat"}
runtime = sorted(p for p in ROOT.glob("*.py"))
path_re = re.compile(r'Path\(__file__\)(?:\.resolve\(\))?\.parent((?:\s*/\s*"[^"]+")+)')
seen = set()
for py in runtime:
    for m in path_re.finditer(py.read_text(encoding="utf-8")):
        rel = "/".join(re.findall(r'"([^"]+)"', m.group(1)))
        if rel in DEV_ONLY or rel in seen:
            continue
        seen.add(rel)
        bundled = any(rel == d or rel.startswith(d.rstrip("/") + "/") for d in datas)
        check(f"{rel} ({py.name})", bundled, "not in aoe2civbuilder.spec datas")

print()
if failures:
    print(f"{failures} FAILED")
    sys.exit(1)
print("all passed")
