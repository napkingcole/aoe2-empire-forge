#!/usr/bin/env python3
"""Unique-tech descriptions reach the civ selection screen on BOTH build routes.

The game keeps "Research Name (description)" at a UT's name id + 1000, and the
civ selection text lists each UT as "Name (description)" — every one of its 116
real unique techs does.  We wrote the bare name, so custom civs listed
"Upgrade 1, Upgrade 2" where the Romans list "Ballistas (Scorpions attack +33%
faster; ...)".

There are THREE copies of this writer: the wizard's (wizard_build), the CLI's
(build_all.build_mod) and the web Build Mod page's (app._run_build_job).  The
wizard's was fixed first; build_all never read the description field; and the
web page — the route actually used — still listed bare names after both were
fixed, and never listed custom bonus cards at all.  Each was reported in-game.
tests/test_build_smoke.py pins the wizard route; this pins the other two.
DAT-gated, ~60s.

    venv/bin/python tests/test_ut_description_routes.py
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_all import ut_name_and_desc, ut_selection_text   # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


# ── Pure ──────────────────────────────────────────────────────────────────────
check("a typed description is used as is",
      ut_name_and_desc("Gothikon", "And faster barracks") == ("Gothikon", "And faster barracks"))
check("a parenthetical typed into the name is used when the description is empty",
      ut_name_and_desc("Upgrade 1 (Cavalry attack faster)", "") == ("Upgrade 1", "Cavalry attack faster"))
check("with both, the name is kept whole — never drop what the player typed",
      ut_name_and_desc("Upgrade 1 (Cavalry)", "Faster") == ("Upgrade 1 (Cavalry)", "Faster"))
check("the selection form drops a closing full stop, as the game's does",
      ut_selection_text("Ballistas", "Scorpions attack +33% faster.") == "Ballistas (Scorpions attack +33% faster)")

# ── build_all route ───────────────────────────────────────────────────────────
from dat_reader import find_game_dat                       # noqa: E402

dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found — build_all route not exercised")
    sys.exit(1 if failures else 0)

import build_all                                           # noqa: E402

# Every route's strings pass through build_all.sanitize_kv_strings, which repairs
# raw newlines and quotes.  Record what it repairs: a route test must still fail
# when a route forgot _kv_text, or the safety net would hide the straggler.
_REPAIRED: list[int] = []
_real_sanitize = build_all.sanitize_kv_strings


def _recording_sanitize(content):
    out, repaired = _real_sanitize(content)
    _REPAIRED.extend(repaired)
    return out, repaired


build_all.sanitize_kv_strings = _recording_sanitize


def nothing_repaired(route: str) -> None:
    check(f"[{route}] the route escaped every player text itself (safety net idle)",
          not _REPAIRED, sorted(set(_REPAIRED))[:5])
    _REPAIRED.clear()

CIV = {
    "format": "empireforge_v2", "schema_version": 2,
    "alias": 'Route "Probe"', "tagline": "Two\nlines", "description": "",
    "share_description": "Shared\ntext",
    "architecture": 1, "language": 0, "wonder_model": -1, "castle_model": -1,
    "emblem": "", "monk_skin": None, "second_uu": None,
    # A named hero: its strings are pool ids, so a route that doesn't write them
    # shows campaign text — the CLI route did ("Prithviraj" / "Scots", 2026-10-09).
    "hero_unit": {"base_unit_id": 1966, "name": "Probe Hero", "description": "Leads\nthe probe"},
    # A UU description typed over several lines: a real newline written raw splits
    # its strings line, and the web route did (the Safavids civ, 2026-10-10).
    "unique_unit": {"km_idx": 0, "vanilla_id": None, "name": "Probe Unit",
                    "description": "HP 70 (80)\nAT 16 (18)",
                    "overrides": {}, "advanced_flags": {}},
    "bonuses": [], "team_bonuses": [],
    "custom_bonuses": [{"target": {"type": "group", "id": "cavalry"},
                        "effects": [{"attr": "hp", "op": "mul", "value": 20}]}],
    "castle_ut": {"mode": "custom", "vanilla_id": None, "name": "Probe Drill",
                  "description": "Siege moves 50% faster.",
                  "cost": {"food": 300, "wood": 0, "stone": 0, "gold": 200}, "time": 40,
                  "effects": [{"id": 12, "multiplier": 1}]},
    "imperial_ut": {"mode": "custom", "vanilla_id": None, "name": "Probe Quote",
                    "description": 'Says "hi"',
                    "cost": {"food": 500, "wood": 0, "stone": 0, "gold": 300}, "time": 60,
                    "effects": [{"id": 35, "multiplier": 1}]},
    "tree": {"units": [], "buildings": [], "techs": []},
    "unit_overrides": [], "button_moves": [], "free_techs": [],
}

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / "probe.json").write_text(json.dumps(CIV), encoding="utf-8")
    (tmp / "cfg.json").write_text(json.dumps(
        {"mod_name": "Route Probe", "civs": [{"json": str(tmp / "probe.json"), "replace": "Britons"}]}), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        build_all.build_mod(tmp / "cfg.json", dat_path, tmp / "out.zip")
    outer = zipfile.ZipFile(tmp / "out.zip")
    ui = next(n for n in outer.namelist() if n.endswith("-ui.zip"))
    uz = zipfile.ZipFile(io.BytesIO(outer.read(ui)))
    sp = next(n for n in uz.namelist()
              if n.endswith("key-value-modded-strings-utf8.txt") and "/en/" in n)
    lines = uz.read(sp).decode("utf-8").splitlines()
    texts = [m.group(1) for ln in lines if (m := re.match(r'^\d+\s+"(.*)"$', ln.strip()))]
    bl_lines = lines



def raw_lines_of(zip_path: Path) -> list[str]:
    outer = zipfile.ZipFile(zip_path)
    ui = next(n for n in outer.namelist() if n.endswith("-ui.zip"))
    uz = zipfile.ZipFile(io.BytesIO(outer.read(ui)))
    sp = next(n for n in uz.namelist()
              if n.endswith("key-value-modded-strings-utf8.txt") and "/en/" in n)
    return uz.read(sp).decode("utf-8").splitlines()


def strings_of(zip_path: Path) -> list[str]:
    return [m.group(1) for ln in raw_lines_of(zip_path)
            if (m := re.match(r'^\d+\s+"(.*)"$', ln.strip()))]


def well_formed(route: str, lines: list[str]) -> None:
    """Every line is `ID "text"`: a stray line means user text broke the file."""
    bad = [ln for ln in lines if ln.strip() and not re.match(r'^\d+\s+".*"$', ln.strip())]
    check(f"[{route}] every strings line is ID \"text\" (multi-line UU description escaped)",
          not bad, bad[:3])


def route_checks(route: str, texts: list[str]) -> None:
    check(f"[{route}] 'Research Name (description)' at +1000",
          "Research Probe Drill (Siege moves 50% faster)" in texts,
          [t for t in texts if t.startswith("Research Probe")])
    civ_text = next((t for t in texts if "Unique Techs" in t and "Probe Drill" in t), "")
    check(f"[{route}] civ selection text lists 'Name (description)'",
          "• Probe Drill (Siege moves 50% faster)" in civ_text, civ_text[-300:])
    check(f"[{route}] a quote in a description is escaped, not ending the string",
          'Probe Quote (Says \\"hi\\")' in civ_text, civ_text[-200:])
    check(f"[{route}] custom bonus cards are listed in the civ text",
          "Cavalry: +20% HP" in civ_text, civ_text[:300])
    check(f"[{route}] the hero's name and 'Create' label are written",
          "Probe Hero" in texts and "Create Probe Hero" in texts,
          [t for t in texts if "Hero" in t][:4])


route_checks("build_all", texts)
well_formed("build_all", bl_lines)
nothing_repaired("build_all")

# ── The web Build Mod page (app._run_build_job) — a third copy of the writer ──
# Fixing the two above left this one listing bare names; reported in-game.
import app as webapp                                       # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    sd = Path(tmp)
    (sd / "probe.json").write_text(json.dumps(CIV), encoding="utf-8")
    webapp._BUILD_JOBS["route-probe"] = {"lines": [], "done": False, "error": None}
    with contextlib.redirect_stdout(io.StringIO()):
        webapp._run_build_job("route-probe", sd, str(dat_path),
                              {"probe.json": {"filename": "probe.json", "name": "Route Probe"}},
                              ["probe.json"], {"probe.json": "Britons"}, "Route Probe")
    check("[web] the build job finished without error",
          not webapp._BUILD_JOBS["route-probe"].get("error"), webapp._BUILD_JOBS["route-probe"].get("error"))
    zips = list(sd.glob("*.zip"))
    if zips:
        route_checks("web", strings_of(zips[0]))
        well_formed("web", raw_lines_of(zips[0]))
    nothing_repaired("web")

# ── The Builder's Build button (wizard_build.build_wizard_mod) ────────────────
from civ_schema import to_draft                            # noqa: E402
from wizard_build import build_wizard_mod                  # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    with contextlib.redirect_stdout(io.StringIO()):
        zbytes = build_wizard_mod(to_draft(json.loads(json.dumps(CIV))), str(dat_path), "Britons")
    (Path(tmp) / "w.zip").write_bytes(zbytes)
    wiz = strings_of(Path(tmp) / "w.zip")
    well_formed("wizard", raw_lines_of(Path(tmp) / "w.zip"))
    nothing_repaired("wizard")
    check("[wizard] the hero's name and 'Create' label are written",
          "Probe Hero" in wiz and "Create Probe Hero" in wiz, [t for t in wiz if "Hero" in t][:4])

# ── Every free-text field, hostile: a newline and a quote in each, all routes ──
# The sweep the Safavids bug asked for: any field a route writes without
# _kv_text shows up as a repair, whichever route and whichever field it is.
NASTY = json.loads(json.dumps(CIV))
_t = 'x "q"\ny'
NASTY.update(alias="Nasty " + _t, tagline=_t, description=_t)
NASTY["unique_unit"].update(name="UU " + _t, description=_t)
for k in ("castle_ut", "imperial_ut"):
    NASTY[k].update(name=k + " " + _t, description=_t)
NASTY["hero_unit"].update(name="Hero " + _t, description=_t)
_REPAIRED.clear()
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / "probe.json").write_text(json.dumps(NASTY), encoding="utf-8")
    (tmp / "cfg.json").write_text(json.dumps(
        {"mod_name": "Nasty", "civs": [{"json": str(tmp / "probe.json"), "replace": "Britons"}]}), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        build_all.build_mod(tmp / "cfg.json", dat_path, tmp / "out.zip")
    nothing_repaired("build_all, every text field")
    webapp._BUILD_JOBS["nasty"] = {"lines": [], "done": False, "error": None}
    with contextlib.redirect_stdout(io.StringIO()):
        webapp._run_build_job("nasty", tmp, str(dat_path),
                              {"probe.json": {"filename": "probe.json", "name": "Nasty"}},
                              ["probe.json"], {"probe.json": "Britons"}, "Nasty")
    check("[web, every text field] the build job finished without error",
          not webapp._BUILD_JOBS["nasty"].get("error"), webapp._BUILD_JOBS["nasty"].get("error"))
    nothing_repaired("web, every text field")
    with contextlib.redirect_stdout(io.StringIO()):
        build_wizard_mod(to_draft(json.loads(json.dumps(NASTY))), str(dat_path), "Britons")
    nothing_repaired("wizard, every text field")

print()
if failures:
    print(f"{failures} check(s) FAILED")
    sys.exit(1)
print("All checks passed.")
