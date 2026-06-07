#!/usr/bin/env python3
"""
build_civ.py — CLI: given a civ JSON + game DAT, produce a mod zip.

Usage:
    python build_civ.py my_civ.json
    python build_civ.py my_civ.json --dat /path/to/empires2_x2_p1.dat
    python build_civ.py my_civ.json --replace saracens
    python build_civ.py my_civ.json --dat /path/to/dat --out my_mod.zip

--replace <vanilla_civ>  Overwrite the named vanilla civ's slot instead of
                         appending a new one.  The name must match exactly
                         (case-insensitive) a civ name in the DAT, e.g.:
                         "saracens", "britons", "franks".
                         UI assets (emblems, buttons) will use the vanilla
                         civ's filename so the game's selection screen works.
"""

import argparse
import base64
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from dat_reader import find_game_dat, load_dat, dat_info
from civ_appender import apply_civ

# Languages KM ships string files for.
LANGUAGES = ["br", "de", "en", "es", "fr", "hi", "it", "jp",
             "ko", "ms", "mx", "tr", "tw", "vi", "zh"]

AI_PER_STUB = b"; Civbuilder generated AI File\n; Feel free to edit as you please\n"


def _civ_file_name(civ_name: str) -> str:
    """'Stompy Bois' → 'stompy_bois'  (matches KM / game file naming)."""
    return civ_name.lower().replace(" ", "_")


def _find_civ_slot(dat, name: str) -> int | None:
    """Return the index of the civ whose name matches (case-insensitive), or None."""
    name_lower = name.lower()
    for i, civ in enumerate(dat.civs):
        if civ.name.lower() == name_lower:
            return i
    return None


def _decode_flag(civ_def: dict) -> bytes | None:
    """Decode customFlagData base64 PNG, or return None if absent."""
    raw = civ_def.get("customFlagData", "")
    if not raw:
        return None
    if raw.startswith("data:image/png;base64,"):
        raw = raw[len("data:image/png;base64,"):]
    try:
        return base64.b64decode(raw)
    except Exception:
        return None


def _build_ui_zip(civ_def: dict, ui_civ_name: str, name_string_id: int) -> bytes:
    """
    Build the UI inner zip in memory.

    ui_civ_name    — vanilla civ name used for filenames (e.g. 'Saracens').
    name_string_id — the language string ID the game reads for this civ's name.
                     Formula: 10271 + civTechTrees_index (KM convention).
                     We write the custom alias at that ID so the selection
                     screen shows the correct name.
    """
    alias    = civ_def.get("alias", "Custom Civ")
    fn       = _civ_file_name(ui_civ_name)
    flag_png = _decode_flag(civ_def)

    # Build string file content: civ name + "Click to play as…" tooltip.
    # 10271+N = name,  90271+N = tooltip  (KM convention from modStrings.js).
    tooltip_id = name_string_id + 80000
    string_content = (
        f'{name_string_id} "{alias}"\n'
        f'{tooltip_id} "Click to play as {alias}."\n'
    ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        # AI stubs — without these the AI complains on civ load.
        ai_name = f"{alias} AI (pre-alpha)"
        zf.writestr(f"resources/_common/ai/{ai_name}.ai", b"")
        zf.writestr(f"resources/_common/ai/{ai_name}.per", AI_PER_STUB)

        if flag_png:
            # Civ-picker button (104×104) — flag PNG is the right size for this slot.
            for variant in ("", "_hover", "_pressed"):
                fname = f"menu_techtree_{fn}{variant}.png"
                zf.writestr(
                    f"resources/_common/wpfg/resources/civ_techtree/{fname}",
                    flag_png,
                )
                zf.writestr(
                    f"widgetui/textures/ingame/icons/civ_techtree_buttons/{fname}",
                    flag_png,
                )
            # civ_emblems/{fn}.png is a 450×280 background overlay (score/loading
            # screen), NOT a badge.  Omit it — writing the 104×104 flag there
            # causes it to stretch into a giant emblem in the UI.
            # Phase 2: supply proper 450×280 artwork.

        # Language string files — all 15 langs get the same English strings.
        # Phase 2: proper per-language translations.
        for lang in LANGUAGES:
            zf.writestr(
                f"resources/{lang}/strings/key-value/key-value-modded-strings-utf8.txt",
                string_content,
            )

    return buf.getvalue()


def _find_adjacent_json(dat_path: Path, filename: str) -> Path | None:
    """Locate a JSON file (e.g. civTechTrees.json, civilizations.json) near the DAT."""
    candidates = [dat_path.parent / filename]
    p = dat_path.parent
    for _ in range(4):
        candidates.append(p / "resources/_common/dat" / filename)
        p = p.parent
    candidates += [
        Path.home() / "Library/Application Support/Steam/steamapps/common/AoE2DE"
        / "resources/_common/dat" / filename,
        Path("C:/Program Files (x86)/Steam/steamapps/common/AoE2DE"
             "/resources/_common/dat") / filename,
        Path("C:/Program Files/Steam/steamapps/common/AoE2DE"
             "/resources/_common/dat") / filename,
        Path("C:/XboxGames/Age of Empires II Definitive Edition/Content"
             "/resources/_common/dat") / filename,
        Path(__file__).parent / filename,  # bundled copy alongside this script
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _find_techtree_json(dat_path: Path) -> Path | None:
    """Try to locate civTechTrees.json near the given DAT path."""
    return _find_adjacent_json(dat_path, "civTechTrees.json")


def _find_civ_techtrees_folder(dat_path: Path) -> Path | None:
    """Locate the CivTechTrees/ folder (per-civ tech tree JSON files)."""
    candidates = [
        Path(__file__).parent / "CivTechTrees",  # bundled copy alongside script
        dat_path.parent / "CivTechTrees",
    ]
    p = dat_path.parent
    for _ in range(4):
        candidates.append(p / "resources/_common/dat/CivTechTrees")
        p = p.parent
    candidates += [
        Path.home() / "Library/Application Support/Steam/steamapps/common/AoE2DE"
        / "resources/_common/dat/CivTechTrees",
        Path("C:/Program Files (x86)/Steam/steamapps/common/AoE2DE"
             "/resources/_common/dat/CivTechTrees"),
        Path("C:/Program Files/Steam/steamapps/common/AoE2DE"
             "/resources/_common/dat/CivTechTrees"),
        Path("C:/XboxGames/Age of Empires II Definitive Edition/Content"
             "/resources/_common/dat/CivTechTrees"),
    ]
    for p in candidates:
        if p.exists() and p.is_dir():
            return p
    return None


def _patch_techtree_entry(data: dict, replaced_civ_id: str, civ_def: dict) -> int:
    """
    Patch a single civ entry inside an already-loaded civTechTrees.json dict.
    Returns the number of changed nodes, or -1 if the civ_id wasn't found.
    Mutates data in place — call json.dumps() when done with all civs.
    """
    tree = civ_def.get("tree", [[], [], []])
    unit_ids     = set(tree[0]) if len(tree) > 0 and isinstance(tree[0], list) else set()
    building_ids = set(tree[1]) if len(tree) > 1 and isinstance(tree[1], list) else set()
    tech_ids     = set(tree[2]) if len(tree) > 2 and isinstance(tree[2], list) else set()

    target_id = _canonical_techtree_id(replaced_civ_id)
    entry = None
    for civ in data.get("civs", []):
        if civ.get("civ_id", "").upper() == target_id:
            entry = civ
            break
    if entry is None:
        return -1

    STATUS_OK  = "ResearchedCompleted"
    STATUS_OFF = "NotAvailable"

    def patch_nodes(nodes: list) -> int:
        changed = 0
        for node in nodes:
            use_type = node.get("Use Type", "")
            node_id  = node.get("Node ID", -1)
            if use_type == "Building":
                ok = node_id in building_ids
            elif use_type == "Tech":
                ok = node_id in tech_ids
            else:
                ok = node_id in unit_ids
            new_status = STATUS_OK if ok else STATUS_OFF
            if node.get("Node Status") != new_status:
                node["Node Status"] = new_status
                changed += 1
        return changed

    changed  = patch_nodes(entry.get("civ_techs_buildings", []))
    changed += patch_nodes(entry.get("civ_techs_units",     []))
    return changed


def _patch_techtree_json(techtree_path: Path, replaced_civ_id: str,
                         civ_def: dict) -> bytes | None:
    """
    Load civTechTrees.json, patch the entry for replaced_civ_id, return bytes.
    Use _patch_techtree_entry directly when building multiple civs in one pass.
    """
    try:
        with open(techtree_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  WARNING: Could not read civTechTrees.json: {e}")
        return None

    changed = _patch_techtree_entry(data, replaced_civ_id, civ_def)
    if changed == -1:
        print(f"  WARNING: {replaced_civ_id!r} not found in civTechTrees.json — skipping display patch")
        return None

    print(f"  civTechTrees.json: {changed} node statuses updated for {replaced_civ_id}")
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def _patch_per_civ_techtree(civ_json_path: Path, civ_def: dict) -> bytes | None:
    """
    Patch a per-civ CivTechTrees JSON file (game's native format, one file per civ).

    The game reads CivTechTrees/{CIV_NAME}.json for the in-game tech tree viewer.
    This function takes the vanilla civ's JSON (e.g. SARACENS.json) and sets each
    node's "Node Status" based on the civ_def tree arrays, then returns the
    patched bytes to be included in the data zip as CivTechTrees/{same_name}.json.
    """
    try:
        with open(civ_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  WARNING: Could not read {civ_json_path.name}: {e}")
        return None

    tree = civ_def.get("tree", [[], [], []])
    unit_ids     = set(tree[0]) if len(tree) > 0 and isinstance(tree[0], list) else set()
    building_ids = set(tree[1]) if len(tree) > 1 and isinstance(tree[1], list) else set()
    tech_ids     = set(tree[2]) if len(tree) > 2 and isinstance(tree[2], list) else set()

    STATUS_OK  = "ResearchedCompleted"
    STATUS_OFF = "NotAvailable"

    def patch_nodes(nodes: list) -> int:
        changed = 0
        for node in nodes:
            use_type = node.get("Use Type", "")
            node_id  = node.get("Node ID", -1)
            if use_type == "Building":
                ok = node_id in building_ids
            elif use_type == "Tech":
                ok = node_id in tech_ids
            else:  # Unit
                ok = node_id in unit_ids
            # Buildings that are structurally required (e.g. Town Center) use
            # "ResearchRequired" not "ResearchedCompleted" — preserve that status.
            current = node.get("Node Status", "")
            if not ok:
                if current != STATUS_OFF:
                    node["Node Status"] = STATUS_OFF
                    changed += 1
            else:
                if current == STATUS_OFF:
                    node["Node Status"] = STATUS_OK
                    changed += 1
        return changed

    changed  = patch_nodes(data.get("civ_techs_buildings", []))
    changed += patch_nodes(data.get("civ_techs_units",     []))
    print(f"  CivTechTrees/{civ_json_path.name}: {changed} nodes updated")
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def _generate_civilizations_json(dat, replaced_index: int | None,
                                  civ_def: dict, ui_civ_name: str,
                                  name_string_id: int,
                                  base_civs_json_path: Path | None) -> bytes:
    """
    Generate a civilizations.json whose entry count exactly matches dat's civ count.

    AoE2 DE requires the mod to supply a civilizations.json when the DAT has a
    different civ count than the vanilla installation.  The entries are positional
    (index 0 = Gaia, index 1 = Britons, …) so we build from a base file and patch
    the replaced slot, then append stubs for any extra civs (KM custom civs).
    """
    base_entries: list[dict] = []
    if base_civs_json_path and base_civs_json_path.exists():
        with open(base_civs_json_path, encoding="utf-8") as f:
            base_entries = json.load(f).get("civilization_list", [])

    fn    = _civ_file_name(ui_civ_name)
    alias = civ_def.get("alias", "Custom Civ")

    # Only emit entries for civs that have a base entry (vanilla civs 0-45).
    # KM custom civs (46+) are omitted — the game accepts a shorter civs.json
    # as long as it's present and the described civs are valid.  (The Wololo
    # mod ships the same 46-entry file with its 57-civ DAT without DLC errors.)
    civ_list = []
    for i, civ in enumerate(dat.civs):
        if i >= len(base_entries):
            break  # stop at the last vanilla entry; omit KM-custom civs

        entry = dict(base_entries[i])  # copy vanilla entry

        if i == replaced_index:
            # Only patch the fields needed to display the custom name.
            # data_name, tech_tree_name, unique_unit_image_paths, and image
            # paths are left at their vanilla values intentionally:
            #   - data_name: game looks up resource files (AI, sound) by this key
            #   - unique_unit_image_paths: game crashes on null dereference if absent
            #   - tech_tree_name: must stay "SARACENS" so game loads SARACENS.json
            entry["internal_name"]  = alias
            entry["name_string_id"] = name_string_id

        civ_list.append(entry)

    return json.dumps({"civilization_list": civ_list},
                      separators=(",", ":")).encode("utf-8")


def _build_data_zip(dat, techtree_bytes: bytes | None = None,
                    civ_file_name: str = "", flag_png: bytes | None = None,
                    civs_json_bytes: bytes | None = None,
                    per_civ_techtree: tuple[str, bytes] | None = None) -> bytes:
    """Write the modified DAT (and optionally civTechTrees.json) into the data zip.

    Also mirrors the civ_techtree button PNGs into the data zip.  AoE2 DE loads
    the in-game civ icon from the data mod side (resources/_common/wpfg/...) in
    addition to the UI mod side, so both zips need the same images.

    per_civ_techtree — (filename, bytes) tuple for the per-civ CivTechTrees JSON,
                       e.g. ("SARACENS.json", b"...").  Goes into
                       resources/_common/dat/CivTechTrees/.
    """
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
        if techtree_bytes is not None:
            zf.writestr("resources/_common/dat/civTechTrees.json", techtree_bytes)
        if civs_json_bytes is not None:
            zf.writestr("resources/_common/dat/civilizations.json", civs_json_bytes)
        if per_civ_techtree is not None:
            pct_name, pct_bytes = per_civ_techtree
            zf.writestr(f"resources/_common/dat/CivTechTrees/{pct_name}", pct_bytes)
        if flag_png and civ_file_name:
            fn = civ_file_name
            for variant in ("", "_hover", "_pressed"):
                fname = f"menu_techtree_{fn}{variant}.png"
                zf.writestr(
                    f"resources/_common/wpfg/resources/civ_techtree/{fname}",
                    flag_png,
                )
    return buf.getvalue()


# DAT internal names that don't match civTechTrees.json civ_id by simple uppercasing.
# Maps lowercase DAT name → canonical civTechTrees civ_id (uppercase).
_DAT_TO_TECHTREE_ID: dict[str, str] = {
    "british":     "BRITONS",
    "french":      "FRANKS",
    "byzantine":   "BYZANTINES",
    "mayan":       "MAYANS",
    "hindustanis": "INDIANS",
    "magyars":     "MAGYAR",   # civTechTrees.json uses singular
}


def _canonical_techtree_id(civ_name: str) -> str:
    """Map a raw DAT civ name to the civTechTrees.json civ_id (uppercase)."""
    key = civ_name.lower().replace(" ", "_")
    return _DAT_TO_TECHTREE_ID.get(key, civ_name.upper().replace(" ", "_"))


def _civ_techtree_index(civ_name: str) -> int | None:
    """
    Return the 0-based index of this civ in civTechTrees.json, or None.
    The KM name-string formula is: 10271 + civTechTrees_index.
    civ_name should be the vanilla civ name (e.g. 'Saracens').
    """
    # KM-style ordering — matches techtreeNames in constants.js
    KM_TECHTREE_ORDER = [
        "britons", "franks", "goths", "teutons", "japanese", "chinese",
        "byzantines", "persians", "saracens", "turks", "vikings", "mongols",
        "celts", "spanish", "aztecs", "mayans", "huns", "koreans", "italians",
        "indians", "inca", "magyars", "slavs", "portuguese", "ethiopians",
        "malians", "berbers", "khmer", "malay", "burmese", "vietnamese",
        "bulgarians", "tatars", "cumans", "lithuanians", "burgundians",
        "sicilians", "poles", "bohemians", "dravidians", "bengalis",
        "gurjaras", "romans", "armenians", "georgians",
    ]
    # Build lookup by canonical civTechTrees ID → KM index.
    lookup: dict[str, int] = {name.upper(): i for i, name in enumerate(KM_TECHTREE_ORDER)}
    lookup["INCAS"]  = lookup["INCA"]    # civTechTrees uses INCAS; KM uses "inca"
    lookup["MAGYAR"] = lookup["MAGYARS"] # civTechTrees uses MAGYAR; KM uses "magyars"
    return lookup.get(_canonical_techtree_id(civ_name))


def write_mod_zip(dat, civ_def: dict, ui_civ_name: str,
                  name_string_id: int, out_path: Path, prefix: str,
                  techtree_bytes: bytes | None = None,
                  replaced_index: int | None = None,
                  base_civs_json_path: Path | None = None,
                  per_civ_techtree: tuple[str, bytes] | None = None) -> None:
    """
    Package the modified DAT + UI assets into the ageofempires.com mod zip:
        {prefix}.zip
        ├── {prefix}-data.zip   (DAT + civTechTrees.json + civilizations.json + PNGs)
        └── {prefix}-ui.zip     (emblems, buttons, AI stubs, strings)
    """
    fn       = _civ_file_name(ui_civ_name)
    flag_png = _decode_flag(civ_def)
    # civilizations.json: only needed when the DAT civ count differs from vanilla
    # (i.e. append mode).  In replace mode the count stays at 60 so the game uses
    # whichever civs.json the higher-priority mod provides — including the /aoe2
    # Wololo Warlords mod's version.  Emitting our own civs.json in replace mode
    # would override all other mods' UU icon paths, breaking every civ's portrait.
    civs_json_bytes = None
    if replaced_index is None:   # append mode only
        civs_json_bytes = _generate_civilizations_json(
            dat, replaced_index, civ_def, ui_civ_name, name_string_id, base_civs_json_path
        )
    data_zip = _build_data_zip(dat, techtree_bytes,
                               civ_file_name=fn, flag_png=flag_png,
                               civs_json_bytes=civs_json_bytes,
                               per_civ_techtree=per_civ_techtree)
    ui_zip   = _build_ui_zip(civ_def, ui_civ_name, name_string_id)

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as outer:
        outer.writestr(f"{prefix}-data.zip", data_zip)
        outer.writestr(f"{prefix}-ui.zip",   ui_zip)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"  → {out_path}  ({size_mb:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an AoE2 DE custom civ mod from a JSON definition."
    )
    parser.add_argument("civ_json",
                        help="Path to civ definition JSON (KM format or native)")
    parser.add_argument("--dat",
                        help="Path to game empires2_x2_p1.dat (auto-detected if omitted)")
    parser.add_argument("--replace",
                        metavar="VANILLA_CIV",
                        help="Overwrite this vanilla civ's slot (e.g. 'saracens')")
    parser.add_argument("--techtree",
                        metavar="PATH",
                        help="Path to civTechTrees.json (auto-detected if omitted)")
    parser.add_argument("--out",
                        help="Output zip filename (defaults to <alias>.zip)")
    args = parser.parse_args()

    # ── Load DAT ──────────────────────────────────────────────────────────────
    dat_path = Path(args.dat) if args.dat else find_game_dat()
    if not dat_path:
        print("ERROR: Could not auto-detect game DAT. Use --dat /path/to/empires2_x2_p1.dat")
        sys.exit(1)
    print(f"Loading DAT: {dat_path}")
    dat  = load_dat(dat_path)
    info = dat_info(dat)
    print(f"  {info['num_civs']} civs, {info['num_units_per_civ']} units/civ, "
          f"{info['num_techs']} techs, {info['num_effects']} effects")

    # ── Load civ definition ────────────────────────────────────────────────────
    civ_path = Path(args.civ_json)
    if not civ_path.exists():
        print(f"ERROR: Civ JSON not found: {civ_path}")
        sys.exit(1)
    with open(civ_path) as f:
        civ_def = json.load(f)
    alias = civ_def.get("alias", "Custom Civ")
    print(f"Civ definition: {alias!r}")

    # ── Resolve replace slot ───────────────────────────────────────────────────
    target_slot     = None
    ui_civ_name     = alias   # default: custom name for UI files (append mode)
    name_string_id  = 10271   # fallback; overridden below for replace mode

    if args.replace:
        target_slot = _find_civ_slot(dat, args.replace)
        if target_slot is None:
            names = [c.name for c in dat.civs]
            print(f"ERROR: No civ named {args.replace!r} found in DAT.")
            print(f"  Available civs: {', '.join(names)}")
            sys.exit(1)
        ui_civ_name = dat.civs[target_slot].name  # vanilla civ name for UI filenames
        print(f"  Replacing slot {target_slot}: {ui_civ_name!r}")

        tt_idx = _civ_techtree_index(ui_civ_name)
        if tt_idx is not None:
            name_string_id = 10271 + tt_idx
            print(f"  civTechTrees index {tt_idx} → name string ID {name_string_id}")
        else:
            print(f"  WARNING: {ui_civ_name!r} not in known techtree order; "
                  f"name string ID defaulting to {name_string_id}")

    # ── Apply civ ─────────────────────────────────────────────────────────────
    civ_index = apply_civ(dat, civ_def, target_slot=target_slot)
    total     = len(dat.civs)
    print(f"  Output: {total} civs total (custom civ at index {civ_index})")

    # ── Patch civTechTrees.json display (replace mode only) ───────────────────
    techtree_bytes = None
    if args.replace and ui_civ_name:
        tt_path = (Path(args.techtree) if args.techtree
                   else _find_techtree_json(dat_path))
        if tt_path and tt_path.exists():
            print(f"Patching civTechTrees.json: {tt_path}")
            techtree_bytes = _patch_techtree_json(tt_path, ui_civ_name, civ_def)
        else:
            print("  WARNING: civTechTrees.json not found — tech tree display will use vanilla layout")

    # ── Locate base civilizations.json for generating the required file ──────
    base_civs_json = _find_adjacent_json(dat_path, "civilizations.json")

    # ── Patch per-civ CivTechTrees JSON (replace mode only) ──────────────────
    per_civ_techtree: tuple[str, bytes] | None = None
    if args.replace and target_slot is not None:
        ct_folder = _find_civ_techtrees_folder(dat_path)
        if ct_folder:
            # Get the vanilla tech_tree_name from base civs.json (e.g. "SARACENS").
            # Fall back to uppercased civ name if unavailable.
            vanilla_tt_name = _canonical_techtree_id(ui_civ_name)
            if base_civs_json and base_civs_json.exists():
                try:
                    with open(base_civs_json, encoding="utf-8") as f:
                        base_entries = json.load(f).get("civilization_list", [])
                    if target_slot < len(base_entries):
                        vanilla_tt_name = base_entries[target_slot].get(
                            "tech_tree_name", vanilla_tt_name
                        )
                except Exception:
                    pass
            per_civ_path = ct_folder / f"{vanilla_tt_name}.json"
            if per_civ_path.exists():
                print(f"Patching CivTechTrees/{vanilla_tt_name}.json")
                patched = _patch_per_civ_techtree(per_civ_path, civ_def)
                if patched is not None:
                    per_civ_techtree = (f"{vanilla_tt_name}.json", patched)
            else:
                print(f"  WARNING: CivTechTrees/{vanilla_tt_name}.json not found "
                      f"in {ct_folder}")
        else:
            print("  WARNING: CivTechTrees/ folder not found — "
                  "per-civ tech tree not patched")

    # ── Package mod zip ───────────────────────────────────────────────────────
    safe_alias = alias.replace(" ", "_").lower()
    out_path   = Path(args.out) if args.out else Path(f"{safe_alias}.zip")
    print(f"Packaging → {out_path}")
    write_mod_zip(dat, civ_def, ui_civ_name, name_string_id, out_path,
                  prefix=safe_alias, techtree_bytes=techtree_bytes,
                  replaced_index=target_slot, base_civs_json_path=base_civs_json,
                  per_civ_techtree=per_civ_techtree)
    print("Done.")


if __name__ == "__main__":
    main()
