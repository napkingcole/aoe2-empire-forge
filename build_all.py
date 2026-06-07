#!/usr/bin/env python3
"""
build_all.py — Build a multi-civ mod from a config JSON.

Usage:
    python build_all.py wololo_warlords_config.json
    python build_all.py wololo_warlords_config.json --dat /path/to/empires2_x2_p1.dat
    python build_all.py wololo_warlords_config.json --out my_mod.zip

Config format (see wololo_warlords_config.json for example):
    {
      "mod_name": "Wololo Warlords",
      "prefix":   "wololo_warlords",     // output zip prefix (optional)
      "civs": [
        { "json": "my_civs/foo.json", "replace": "celts" },
        ...
      ]
    }
"""

import argparse
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from dat_reader import find_game_dat, load_dat, dat_info
from civ_appender import apply_civ
from build_civ import (
    AI_PER_STUB, LANGUAGES,
    _find_civ_slot, _civ_techtree_index, _civ_file_name,
    _decode_flag,
    _find_techtree_json, _find_civ_techtrees_folder, _find_adjacent_json,
    _patch_techtree_entry, _patch_per_civ_techtree,
    _canonical_techtree_id,
)


def _build_combined_data_zip(dat,
                              tt_bytes: bytes | None,
                              button_pngs: dict[str, bytes],
                              per_civ_tt: dict[str, bytes]) -> bytes:
    """Serialize the modified DAT + all supporting data-side assets."""
    with tempfile.NamedTemporaryFile(suffix=".dat", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        dat.save(tmp_path)
        dat_bytes = Path(tmp_path).read_bytes()
    finally:
        os.unlink(tmp_path)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("resources/_common/dat/empires2_x2_p1.dat", dat_bytes)
        if tt_bytes is not None:
            zf.writestr("resources/_common/dat/civTechTrees.json", tt_bytes)
        for name, data in per_civ_tt.items():
            zf.writestr(f"resources/_common/dat/CivTechTrees/{name}", data)
        for fname, png in button_pngs.items():
            zf.writestr(
                f"resources/_common/wpfg/resources/civ_techtree/{fname}", png)
    return buf.getvalue()


def _build_combined_ui_zip(ai_stubs: dict[str, bytes],
                            button_pngs: dict[str, bytes],
                            combined_strings: dict[str, str]) -> bytes:
    """Package all UI assets for every civ into one ui zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, data in ai_stubs.items():
            zf.writestr(path, data)
        for fname, png in button_pngs.items():
            zf.writestr(
                f"resources/_common/wpfg/resources/civ_techtree/{fname}", png)
            zf.writestr(
                f"widgetui/textures/ingame/icons/civ_techtree_buttons/{fname}",
                png)
            # Civ selection screen portrait + lobby preview icon.
            # Both use widgetui/textures/menu/civs/{civname}.png (same 104x104 emblem,
            # matching KM's convention). Only the base variant, no hover/pressed.
            if "_hover" not in fname and "_pressed" not in fname:
                civ_fn = fname.removeprefix("menu_techtree_")
                zf.writestr(f"widgetui/textures/menu/civs/{civ_fn}", png)
        for lang, content in combined_strings.items():
            zf.writestr(
                f"resources/{lang}/strings/key-value/"
                f"key-value-modded-strings-utf8.txt",
                content.encode("utf-8"),
            )
    return buf.getvalue()


def build_mod(config_path: Path, dat_path: Path, out_path: Path) -> None:
    config    = json.loads(config_path.read_text(encoding="utf-8"))
    mod_name  = config.get("mod_name", "Custom Mod")
    civ_defs  = config.get("civs", [])

    print(f"Mod: {mod_name!r}  ({len(civ_defs)} civs)")
    print(f"Loading DAT: {dat_path}")
    dat  = load_dat(dat_path)
    info = dat_info(dat)
    print(f"  {info['num_civs']} civs, {info['num_units_per_civ']} units/civ, "
          f"{info['num_techs']} techs, {info['num_effects']} effects")

    # Load civTechTrees.json once; patch all civ entries into it.
    tt_path = _find_techtree_json(dat_path)
    tt_data: dict | None = None
    if tt_path and tt_path.exists():
        try:
            with open(tt_path, encoding="utf-8") as f:
                tt_data = json.load(f)
        except Exception as e:
            print(f"  WARNING: Could not load civTechTrees.json: {e}")

    ct_folder = _find_civ_techtrees_folder(dat_path)

    # Accumulated UI assets across all civs.
    ai_stubs:   dict[str, bytes] = {}
    button_pngs: dict[str, bytes] = {}
    per_civ_tt: dict[str, bytes] = {}
    string_lines: dict[str, list[str]] = {lang: [] for lang in LANGUAGES}

    for entry in civ_defs:
        json_path    = Path(entry["json"])
        replace_name = entry["replace"]

        if not json_path.exists():
            print(f"  ERROR: {json_path} not found — skipping")
            continue

        civ_def = json.loads(json_path.read_text(encoding="utf-8"))
        alias   = civ_def.get("alias", json_path.stem)

        slot = _find_civ_slot(dat, replace_name)
        if slot is None:
            print(f"  ERROR: No civ named {replace_name!r} in DAT — skipping {alias!r}")
            continue

        ui_civ_name = dat.civs[slot].name
        tt_idx      = _civ_techtree_index(ui_civ_name)
        name_sid    = 10271 + tt_idx if tt_idx is not None else 10271

        print(f"\n  [{slot}] {replace_name!r} → {alias!r}  (string ID {name_sid})")

        # Apply civ to DAT (modifies dat in place).
        apply_civ(dat, civ_def, target_slot=slot)

        # Strings: one line per civ per language (all langs get same English text).
        # Description string ID follows KM's offset: 120150 - 10271 = 109879 above name_sid.
        description = civ_def.get("description", "")
        for lang in LANGUAGES:
            string_lines[lang].append(f'{name_sid} "{alias}"')
            string_lines[lang].append(
                f'{name_sid + 80000} "Click to play as {alias}."')
            if description:
                string_lines[lang].append(
                    f'{name_sid + 109879} "{description} Civilization"')

        # Button PNGs (104×104 civ picker emblem).
        flag_png = _decode_flag(civ_def)
        if flag_png:
            fn = _civ_file_name(ui_civ_name)
            for variant in ("", "_hover", "_pressed"):
                button_pngs[f"menu_techtree_{fn}{variant}.png"] = flag_png

        # AI stubs.
        ai_name = f"{alias} AI (pre-alpha)"
        ai_stubs[f"resources/_common/ai/{ai_name}.ai"]  = b""
        ai_stubs[f"resources/_common/ai/{ai_name}.per"] = AI_PER_STUB

        # civTechTrees.json — patch in place.
        if tt_data is not None:
            changed = _patch_techtree_entry(tt_data, ui_civ_name, civ_def)
            if changed == -1:
                print(f"    WARNING: {ui_civ_name!r} not found in civTechTrees.json")
            else:
                print(f"    civTechTrees.json: {changed} nodes updated")

        # Per-civ CivTechTrees JSON.
        if ct_folder:
            vanilla_tt_name = _canonical_techtree_id(ui_civ_name)
            per_civ_path = ct_folder / f"{vanilla_tt_name}.json"
            if per_civ_path.exists():
                patched = _patch_per_civ_techtree(per_civ_path, civ_def)
                if patched is not None:
                    per_civ_tt[f"{vanilla_tt_name}.json"] = patched

    # Serialize civTechTrees.json after all patches.
    tt_bytes = (json.dumps(tt_data, separators=(",", ":")).encode("utf-8")
                if tt_data is not None else None)

    # Combine string lines per language.
    combined_strings = {
        lang: "\n".join(lines) + "\n"
        for lang, lines in string_lines.items()
        if lines
    }

    print(f"\nBuilding combined mod zip → {out_path}")
    prefix = config.get("prefix", mod_name.lower().replace(" ", "_"))
    data_zip = _build_combined_data_zip(dat, tt_bytes, button_pngs, per_civ_tt)
    ui_zip   = _build_combined_ui_zip(ai_stubs, button_pngs, combined_strings)

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as outer:
        outer.writestr(f"{prefix}-data.zip", data_zip)
        outer.writestr(f"{prefix}-ui.zip",   ui_zip)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"  → {out_path}  ({size_mb:.1f} MB)")
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a multi-civ AoE2 DE mod from a config JSON."
    )
    parser.add_argument("config", help="Path to mod config JSON")
    parser.add_argument("--dat",  help="Path to empires2_x2_p1.dat (auto-detected if omitted)")
    parser.add_argument("--out",  help="Output zip filename")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}")
        sys.exit(1)

    dat_path = Path(args.dat) if args.dat else find_game_dat()
    if not dat_path:
        print("ERROR: Could not auto-detect game DAT. Use --dat /path/to/dat")
        sys.exit(1)

    config   = json.loads(config_path.read_text(encoding="utf-8"))
    prefix   = config.get("prefix", config.get("mod_name", "mod").lower().replace(" ", "_"))
    out_path = Path(args.out) if args.out else Path(f"{prefix}.zip")

    build_mod(config_path, dat_path, out_path)


if __name__ == "__main__":
    main()
