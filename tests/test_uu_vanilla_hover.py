#!/usr/bin/env python3
"""An unchanged vanilla unique unit keeps the game's own Castle tooltip.

Every route used to write "Create <b>Mangudai<b>\\nCosts: 55W 65G" over string
26108 — the game's tooltip for the Mangudai, with its description, upgrades and
a (<cost>) token drawn with resource icons.  The ids are the game's, so the
real Mongols lost theirs too (reported in-game 2026-10-05).  The writers now
leave them alone unless the unit was renamed or re-described — and still write
where the game's slot is not a tooltip at all (the Ratha's holds "Click to
remove this unit from the queue.").  All three routes.  DAT-gated, ~40s.

    venv/bin/python tests/test_uu_vanilla_hover.py
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

from dat_reader import find_game_dat                        # noqa: E402

failures = 0


def check(label, ok, detail=""):
    global failures
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        failures += 1
        if detail:
            print(f"       {detail}")


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)


def civ(km_idx, name=""):
    return {"format": "empireforge_v2", "schema_version": 2, "alias": "Hover Probe",
            "tagline": "", "description": "", "architecture": 1, "language": 0,
            "wonder_model": -1, "castle_model": -1, "emblem": "", "monk_skin": None,
            "hero_unit": None, "second_uu": None,
            "unique_unit": {"km_idx": km_idx, "vanilla_id": None, "name": name,
                            "description": "", "overrides": {}, "advanced_flags": {}},
            "bonuses": [], "team_bonuses": [], "custom_bonuses": [],
            "castle_ut": {"mode": "vanilla", "vanilla_km_idx": 0},
            "imperial_ut": {"mode": "vanilla", "vanilla_km_idx": 0},
            "tree": {"units": [4, 38, 74], "buildings": [12, 82, 87, 101], "techs": []},
            "unit_overrides": [], "button_moves": [], "free_techs": []}


def strings_of(blob: bytes) -> dict[int, str]:
    outer = zipfile.ZipFile(io.BytesIO(blob))
    ui = zipfile.ZipFile(io.BytesIO(outer.read(next(n for n in outer.namelist() if n.endswith("-ui.zip")))))
    sp = next(n for n in ui.namelist() if n.endswith("key-value-modded-strings-utf8.txt") and "/en/" in n)
    out = {}
    for line in ui.read(sp).decode("utf-8").splitlines():
        m = re.match(r'^(\d+)\s+"(.*)"$', line.strip())
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


def build_web(c) -> dict:
    import app as webapp
    with tempfile.TemporaryDirectory() as tmp:
        sd = Path(tmp)
        (sd / "c.json").write_text(json.dumps(c), encoding="utf-8")
        webapp._BUILD_JOBS["hover"] = {"lines": [], "done": False, "error": None}
        with contextlib.redirect_stdout(io.StringIO()):
            webapp._run_build_job("hover", sd, str(dat_path), {"c.json": {"filename": "c.json", "name": "Probe"}},
                                  ["c.json"], {"c.json": "Britons"}, "Hover Probe")
        return strings_of(next(sd.glob("*.zip")).read_bytes())


def build_cli(c) -> dict:
    import build_all
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "c.json").write_text(json.dumps(c), encoding="utf-8")
        (tmp / "cfg.json").write_text(json.dumps({"mod_name": "Hover", "civs": [{"json": str(tmp / "c.json"), "replace": "Britons"}]}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            build_all.build_mod(tmp / "cfg.json", dat_path, tmp / "out.zip")
        return strings_of((tmp / "out.zip").read_bytes())


def build_wizard(c) -> dict:
    from wizard_build import build_wizard_mod
    from civ_schema import to_draft
    with contextlib.redirect_stdout(io.StringIO()):
        return strings_of(build_wizard_mod(to_draft(c), str(dat_path), "britons"))


MANGUDAI, ELITE, RATHA = 5108, 5458, 21104           # their language_dll_name ids
for route, build in (("web", build_web), ("cli", build_cli), ("wizard", build_wizard)):
    s = build(civ(11))
    check(f"[{route}] an unchanged Mangudai leaves the game's tooltips alone",
          not {MANGUDAI + 21000, MANGUDAI + 100000, ELITE + 21000, ELITE + 100000} & s.keys(),
          {k: s[k][:50] for k in (MANGUDAI + 21000, MANGUDAI + 100000) if k in s})
    s = build(civ(80))
    check(f"[{route}] the Ratha, whose slot is not a tooltip, still gets one written",
          (RATHA + 21000) in s and "Ratha" in s[RATHA + 21000], s.get(RATHA + 21000))
    s = build(civ(11, name="Steppe Riders"))
    # A renamed vanilla UU writes to its own pool ids, not the game's (which the
    # Mongols' Mangudai still reads) — civ_appender._own_renamed_uu_strings.
    sid = next((k for k, v in s.items() if v == "Steppe Riders"), 0)
    tip = s.get(sid + 21000, "")
    check(f"[{route}] a renamed Mangudai still gets its own tooltip",
          "Steppe Riders" in tip, tip)
    check(f"[{route}] ...in the game's rich format (cost icons, stat line)",
          "(<cost>)" in tip and "<hp>" in tip, tip[:120])
    check(f"[{route}] ...and the Mongols' own Mangudai strings are untouched",
          not {MANGUDAI, MANGUDAI + 1000, MANGUDAI + 21000, MANGUDAI + 100000} & s.keys(),
          {k: s[k][:40] for k in (MANGUDAI, MANGUDAI + 21000) if k in s})
    h = civ(11)
    h["hero_unit"] = {"base_unit_id": 1966, "name": "QA Hero", "description": "Test hero"}
    s = build(h)
    sid = next((k for k, v in s.items() if v == "QA Hero"), None)
    check(f"[{route}] hero: +1000 is the short 'Create' label",
          sid is not None and s.get(sid + 1000) == "Create QA Hero", s.get((sid or 0) + 1000))
    tip = s.get((sid or 0) + 21000, "")
    check(f"[{route}] hero: tooltip is the base hero's, renamed, with our description",
          tip.startswith("Create <b>QA Hero<b> (<cost>)") and "Test hero" in tip and "<hp>" in tip
          and "Costs:" not in tip, tip[:140])

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
