#!/usr/bin/env python3
"""A renamed vanilla unique unit is renamed for THIS civ only — on all three routes.

A vanilla UU's strings are the game's, shared with the civ that really owns it.
The routes wrote the new name over them, so a Ghulam renamed "Qurchi" was Qurchi
for the Hindustanis too, while the Elite upgrade (its own vanilla ids, which no
route wrote) still read "Elite Ghulam" (a Discord user's Safavids, 2026-10-10).

civ_appender._own_renamed_uu_strings moves this civ's unit, elite unit and
private elite-upgrade tech to pool string ids; the routes write there.  Checks:
  - the Hindustanis' Ghulam keeps the game's ids, and no route writes them
  - the custom civ's unit / elite unit / elite tech use pool ids with our text
  - a description-only change still names the unit (a pool id with nothing
    written shows campaign dialogue)
  - an unchanged vanilla UU keeps the game's own ids
DAT-gated, ~2 min.

    venv/bin/python tests/test_renamed_vanilla_uu.py
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

from dat_reader import find_game_dat, load_dat              # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

import app as webapp                                        # noqa: E402
import build_all                                            # noqa: E402
from civ_appender import _CAMPAIGN_POOL_SET                 # noqa: E402
from civ_schema import to_draft                             # noqa: E402
from wizard_build import build_wizard_mod                   # noqa: E402

GHULAM, ELITE_GHULAM = 1747, 1749
HINDUSTANIS = "Hindustanis"


def civ(alias, name="", desc=""):
    return {"format": "empireforge_v2", "schema_version": 2, "alias": alias,
            "tagline": "", "description": "", "architecture": 1, "language": 0,
            "bonuses": [], "team_bonuses": [], "custom_bonuses": [],
            "unique_unit": {"km_idx": 19, "vanilla_id": None, "name": name,
                            "description": desc, "overrides": {}, "advanced_flags": {}},
            "tree": {"units": [], "buildings": [], "techs": []},
            "unit_overrides": [], "button_moves": [], "free_techs": []}


def unpack(zbytes: bytes, tmp: Path):
    """(DatFile, {sid: text}) from a mod zip's bytes."""
    outer = zipfile.ZipFile(io.BytesIO(zbytes))
    dz = zipfile.ZipFile(io.BytesIO(outer.read(next(n for n in outer.namelist() if n.endswith("-data.zip")))))
    uz = zipfile.ZipFile(io.BytesIO(outer.read(next(n for n in outer.namelist() if n.endswith("-ui.zip")))))
    (tmp / "m.dat").write_bytes(dz.read(next(n for n in dz.namelist() if n.endswith(".dat"))))
    sp = next(n for n in uz.namelist() if n.endswith("key-value-modded-strings-utf8.txt") and "/en/" in n)
    strings = {}
    for ln in uz.read(sp).decode("utf-8").splitlines():
        m = re.match(r'^(\d+)\s+"(.*)"$', ln.strip())
        if m:
            strings[int(m.group(1))] = m.group(2)
    return load_dat(str(tmp / "m.dat")), strings


def build(route: str, c: dict, tmp: Path) -> bytes:
    (tmp / "c.json").write_text(json.dumps(c), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        if route == "build_all":
            (tmp / "cfg.json").write_text(json.dumps(
                {"mod_name": "R", "civs": [{"json": str(tmp / "c.json"), "replace": "Britons"}]}),
                encoding="utf-8")
            build_all.build_mod(tmp / "cfg.json", dat_path, tmp / "out.zip")
            return (tmp / "out.zip").read_bytes()
        if route == "web":
            webapp._BUILD_JOBS["r"] = {"lines": [], "done": False, "error": None}
            webapp._run_build_job("r", tmp, str(dat_path), {"c.json": {"filename": "c.json", "name": "R"}},
                                  ["c.json"], {"c.json": "Britons"}, "R")
            return next(p for p in tmp.glob("*.zip") if p.name != "out.zip").read_bytes()
        return build_wizard_mod(to_draft(json.loads(json.dumps(c))), str(dat_path), "Britons")


def slot_of(dat, name):
    return next(i for i, c in enumerate(dat.civs) if c.name.lower().startswith(name.lower()[:6]))


def elite_tech(dat, slot):
    for tid, t in enumerate(dat.techs):
        if t.civ == slot and 0 <= t.effect_id < len(dat.effects):
            if any(c.type == 3 and c.a == GHULAM and c.b == ELITE_GHULAM
                   for c in dat.effects[t.effect_id].effect_commands):
                return t
    return None


for route in ("build_all", "web", "wizard"):
    print(f"\n=== {route} ===")
    # ── renamed + re-described ────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dat, s = unpack(build(route, civ("Renamed", "Probe Qurchi", "Two\nlines"), tmp), tmp)
        hin, me = slot_of(dat, HINDUSTANIS), 1
        h_uu, h_el = dat.civs[hin].units[GHULAM], dat.civs[hin].units[ELITE_GHULAM]
        m_uu, m_el = dat.civs[me].units[GHULAM], dat.civs[me].units[ELITE_GHULAM]
        check(f"[{route}] the Hindustanis' Ghulam keeps the game's string ids",
              h_uu.language_dll_name not in _CAMPAIGN_POOL_SET
              and h_el.language_dll_name not in _CAMPAIGN_POOL_SET,
              (h_uu.language_dll_name, h_el.language_dll_name))
        vanilla_ids = {h_uu.language_dll_name, h_uu.language_dll_creation, h_uu.language_dll_help,
                       h_el.language_dll_name, h_el.language_dll_creation, h_el.language_dll_help}
        vanilla_ids |= {i + 21000 for i in (h_uu.language_dll_name, h_el.language_dll_name)}
        check(f"[{route}] no string the Hindustanis read is rewritten",
              not (vanilla_ids & set(s)), {i: s[i][:40] for i in vanilla_ids & set(s)})
        check(f"[{route}] this civ's Ghulam and Elite use pool ids",
              m_uu.language_dll_name in _CAMPAIGN_POOL_SET and m_el.language_dll_name in _CAMPAIGN_POOL_SET,
              (m_uu.language_dll_name, m_el.language_dll_name))
        check(f"[{route}] the unit is named, with its Create label",
              s.get(m_uu.language_dll_name) == "Probe Qurchi"
              and s.get(m_uu.language_dll_creation) == "Create Probe Qurchi",
              (s.get(m_uu.language_dll_name), s.get(m_uu.language_dll_creation)))
        check(f"[{route}] the unit's Castle hover tooltip is ours",
              "Probe Qurchi" in s.get(m_uu.language_dll_name + 21000, ""),
              s.get(m_uu.language_dll_name + 21000, "")[:80])
        et = elite_tech(dat, me)
        check(f"[{route}] the Elite upgrade is this civ's own tech", et is not None)
        if et is not None:
            check(f"[{route}] the Elite upgrade's button reads 'Elite Probe Qurchi'",
                  s.get(et.language_dll_name) == "Elite Probe Qurchi"
                  and "Elite Probe Qurchi" in s.get(et.language_dll_description, "")
                  and "Elite Probe Qurchi" in s.get(et.language_dll_help, ""),
                  (et.language_dll_name, s.get(et.language_dll_name),
                   s.get(et.language_dll_description), s.get(et.language_dll_help, "")[:60]))
    # ── description only ──────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dat, s = unpack(build(route, civ("DescOnly", "", "Only a description"), tmp), tmp)
        m_uu = dat.civs[1].units[GHULAM]
        check(f"[{route}] a description-only change still names the unit 'Ghulam'",
              m_uu.language_dll_name in _CAMPAIGN_POOL_SET and s.get(m_uu.language_dll_name) == "Ghulam",
              (m_uu.language_dll_name, s.get(m_uu.language_dll_name)))
    # ── unchanged ─────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dat, s = unpack(build(route, civ("Plain"), tmp), tmp)
        m_uu = dat.civs[1].units[GHULAM]
        check(f"[{route}] an unchanged Ghulam keeps the game's ids",
              m_uu.language_dll_name not in _CAMPAIGN_POOL_SET, m_uu.language_dll_name)

print()
if failures:
    print(f"{failures} check(s) FAILED")
    sys.exit(1)
print("All checks passed.")
