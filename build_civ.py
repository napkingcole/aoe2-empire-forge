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
from civ_appender import apply_civ, _KM_UU_TECHS, _KM_UU_NAMES

# Languages KM ships string files for.
LANGUAGES = ["br", "de", "en", "es", "fr", "hi", "it", "jp",
             "ko", "ms", "mx", "tr", "tw", "vi", "zh"]

AI_PER_STUB = b"; Civbuilder generated AI File\n; Feel free to edit as you please\n"

# Ordered list of civ names by dat slot position: index N = dat slot N+1 (Gaia is slot 0).
# name_string_id = 10271 + N, description_string_id = 10271 + N + 109879.
# Vanilla civs (0-44) match the base-game civTechTrees.json ordering.
# KM custom civs (45-55) and SA DLC civs (56-58) continue in dat-slot order.
KM_TECHTREE_ORDER = [
    # Vanilla civs — positions 0-44, dat slots 1-45
    "Britons", "Franks", "Goths", "Teutons", "Japanese", "Chinese",
    "Byzantines", "Persians", "Saracens", "Turks", "Vikings", "Mongols",
    "Celts", "Spanish", "Aztecs", "Maya", "Huns", "Koreans", "Italians",
    "Hindustanis", "Inca", "Magyars", "Slavs", "Portuguese", "Ethiopians",
    "Malians", "Berbers", "Khmer", "Malay", "Burmese", "Vietnamese",
    "Bulgarians", "Tatars", "Cumans", "Lithuanians", "Burgundians",
    "Sicilians", "Poles", "Bohemians", "Dravidians", "Bengalis",
    "Gurjaras", "Romans", "Armenians", "Georgians",
    # KM custom civs — positions 45-55, dat slots 46-56
    "Achaemenids", "Athenians", "Spartans",
    "Shu", "Wu", "Wei", "Jurchens", "Khitans",
    "Macedonians", "Thracians", "Puru",
    # South American DLC civs — positions 56-58, dat slots 57-59
    "Muisca", "Mapuche", "Tupi",
]


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
    """Decode customFlagData base64 PNG/JPG and return PNG bytes, or None if absent."""
    import io
    raw = civ_def.get("customFlagData", "")
    if not raw:
        return None
    # Strip data-URI prefix for any image format.
    for prefix in ("data:image/png;base64,", "data:image/jpeg;base64,",
                   "data:image/jpg;base64,"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    try:
        img_bytes = base64.b64decode(raw)
    except Exception:
        return None
    # If not already PNG, convert via Pillow.
    if not img_bytes.startswith(b'\x89PNG'):
        try:
            from PIL import Image
            buf = io.BytesIO()
            Image.open(io.BytesIO(img_bytes)).save(buf, format="PNG")
            img_bytes = buf.getvalue()
        except Exception:
            return None
    return img_bytes


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


def _uu_actual_unit_id(dat, make_avail_tech_id: int) -> int:
    """Return the unit ID enabled by a make-avail tech's EC_ENABLE command, or tech_id as fallback."""
    if 0 <= make_avail_tech_id < len(dat.techs):
        eff_id = dat.techs[make_avail_tech_id].effect_id
        if 0 <= eff_id < len(dat.effects):
            for ec in dat.effects[eff_id].effect_commands:
                if ec.type == 2 and ec.b == 1:  # EC_ENABLE, enabled=1
                    return ec.a
    return make_avail_tech_id


def _uu_actual_elite_id(dat, elite_tech_id: int, base_unit_id: int) -> int:
    """Return the upgraded-to unit ID from an elite upgrade tech's EC_UPGRADE command, or base_unit_id as fallback."""
    if 0 <= elite_tech_id < len(dat.techs):
        eff_id = dat.techs[elite_tech_id].effect_id
        if 0 <= eff_id < len(dat.effects):
            for ec in dat.effects[eff_id].effect_commands:
                if ec.type == 3 and ec.a == base_unit_id:  # EC_UPGRADE from base
                    return ec.b
    return base_unit_id


def _resolve_uu_info(civ_def: dict, dat, slot: int) -> dict | None:
    """Return {unit_id, elite_id, icon_id, dll_name, name} for the civ's KM UU, or None."""
    bonuses = civ_def.get("bonuses", [])
    uu_refs = bonuses[1] if len(bonuses) > 1 else []
    km_uu_idx = uu_refs[0] if uu_refs and isinstance(uu_refs[0], int) else None
    if km_uu_idx is None:
        return None
    pair = _KM_UU_TECHS.get(km_uu_idx)
    if not pair:
        return None
    # pair[0]/pair[1] are TECH indices; extract actual unit IDs from the techs' EC commands.
    unit_id  = _uu_actual_unit_id(dat, pair[0])
    elite_id = _uu_actual_elite_id(dat, pair[1], unit_id)
    try:
        u = dat.civs[slot].units[unit_id]
        return {
            "unit_id":  unit_id,
            "elite_id": elite_id,
            "icon_id":  u.icon_id,
            "dll_name": u.language_dll_name,
            "name":     _KM_UU_NAMES.get(km_uu_idx, "Unique Unit"),
        }
    except (IndexError, AttributeError):
        return None


def _patch_per_civ_techtree(civ_json_path: Path, civ_def: dict,
                             dat=None, slot: int | None = None,
                             civ_result: dict | None = None) -> bytes | None:
    """
    Patch a per-civ CivTechTrees JSON file (game's native format, one file per civ).

    The game reads CivTechTrees/{CIV_NAME}.json for the in-game tech tree viewer.
    Sets each node's "Node Status" based on civ_def tree arrays.  When dat+slot
    are provided, also re-targets the UniqueUnit node to the custom civ's UU
    (updates Node ID, Picture Index, Name/Help String IDs).  When civ_result is
    provided, also re-targets the Castle/Imperial UT Research nodes to the newly
    appended UT techs so the tech tree viewer shows the correct custom UTs.
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

    uu_unit_info: dict | None = None
    if dat is not None and slot is not None:
        uu_unit_info = _resolve_uu_info(civ_def, dat, slot)

    STATUS_OK  = "ResearchedCompleted"
    STATUS_OFF = "NotAvailable"

    # Pre-scan: collect all UniqueUnit Node IDs so we can distinguish castle UU
    # nodes from upgrade-chain nodes (e.g. Hindustanis' Imperial Camel Rider has
    # Link ID=330 pointing to Heavy Camel Rider — NOT another UniqueUnit — and
    # should not be patched with the custom civ's castle UU).
    def _collect_uu_node_ids(obj: object) -> set[int]:
        ids: set[int] = set()
        if isinstance(obj, dict):
            if obj.get("Node Type") == "UniqueUnit":
                nid = obj.get("Node ID")
                if nid is not None:
                    ids.add(int(nid))
            for v in obj.values():
                ids |= _collect_uu_node_ids(v)
        elif isinstance(obj, list):
            for item in obj:
                ids |= _collect_uu_node_ids(item)
        return ids

    _all_uu_node_ids: set[int] = _collect_uu_node_ids(data)

    # Index UniqueUnit nodes in encounter order so we can assign regular/elite.
    _uu_node_counter: list[int] = [0]

    def _patch_uu_node(node: dict) -> None:
        """Retarget a UniqueUnit node to the custom civ's UU (regular or elite).

        Skips nodes whose original Link ID points to a non-UniqueUnit (these are
        upgrade-chain results like Imperial Camel Rider, not castle UU nodes).
        """
        if uu_unit_info is None:
            return
        orig_link = node.get("Link ID")
        if orig_link is not None and int(orig_link) > 0 and int(orig_link) not in _all_uu_node_ids:
            node["Node Status"] = STATUS_OFF  # upgrade-chain UU from replaced civ; hide it
            return
        idx = _uu_node_counter[0]
        _uu_node_counter[0] += 1

        if idx == 0:
            # Regular unit node.
            unit_id  = uu_unit_info["unit_id"]
            icon_id  = uu_unit_info["icon_id"]
            dll_name = uu_unit_info["dll_name"]
            name     = uu_unit_info["name"]
            node["Link ID"] = -1
        else:
            # Elite unit node — use the actual elite unit ID resolved from the upgrade tech.
            elite_id = uu_unit_info.get("elite_id", uu_unit_info["unit_id"])
            try:
                eu = dat.civs[slot].units[elite_id]
                icon_id  = eu.icon_id
                dll_name = eu.language_dll_name
            except (IndexError, AttributeError):
                icon_id  = uu_unit_info["icon_id"]
                dll_name = uu_unit_info["dll_name"]
            unit_id  = elite_id
            name     = f"Elite {uu_unit_info['name']}"
            node["Link ID"] = uu_unit_info["unit_id"]
            # Update Trigger Tech ID to our new allocated elite upgrade tech so
            # the tech-tree panel tracks the correct research state.
            if _km_uu_elite_tech_id >= 0:
                node["Trigger Tech ID"] = _km_uu_elite_tech_id

        node["Node ID"]        = unit_id
        node["Picture Index"]  = icon_id
        node["Name String ID"] = dll_name + 10000
        node["Help String ID"] = dll_name + 100000
        node["Name"]           = name
        node["Node Status"]    = STATUS_OK

    # The KM UU elite upgrade tech ID allocated by civ_appender for this civ.
    # Used to set Trigger Tech ID on the elite UniqueUnit node so the tech-tree
    # panel correctly tracks when the elite unit is unlocked.
    _km_uu_elite_tech_id = (civ_result or {}).get("km_uu_elite_tech_id", -1)

    # Pre-compute UT retargeting info from civ_result (if available).
    _orig_castle_ut_tid = (civ_result or {}).get("orig_castle_ut_tech_id")
    _orig_imp_ut_tid    = (civ_result or {}).get("orig_imp_ut_tech_id")
    _new_castle_ut_tid  = (civ_result or {}).get("castle_ut_tech_id")
    _new_imp_ut_tid     = (civ_result or {}).get("imp_ut_tech_id")
    _castle_ut_sid      = (civ_result or {}).get("castle_ut_sid")
    _imp_ut_sid         = (civ_result or {}).get("imp_ut_sid")
    _castle_ut_name     = (civ_result or {}).get("castle_ut_name", "")
    _imp_ut_name        = (civ_result or {}).get("imp_ut_name", "")

    def patch_nodes(nodes: list) -> int:
        changed = 0
        for node in nodes:
            use_type  = node.get("Use Type", "")
            node_type = node.get("Node Type", "")
            node_id   = node.get("Node ID", -1)

            if node_type == "UniqueUnit" and uu_unit_info is not None:
                _patch_uu_node(node)
                changed += 1
                continue  # status already set inside _patch_uu_node

            # Retarget vanilla Castle/Imperial UT Research nodes to our new UT techs.
            # Point Name/Help string IDs directly at the UT's base sid and
            # base+100000 (matches what build_all.py writes to the strings file
            # under the high-range UT block).
            if (use_type == "Tech" and node_type == "Research"
                    and node.get("Building ID") == 82):
                if node_id == _orig_castle_ut_tid and _new_castle_ut_tid is not None:
                    node["Node ID"] = _new_castle_ut_tid
                    if _castle_ut_sid:
                        node["Name String ID"] = _castle_ut_sid
                        node["Help String ID"] = _castle_ut_sid + 100000
                    if _castle_ut_name:
                        node["Name"] = _castle_ut_name
                    node["Node Status"] = STATUS_OK
                    changed += 1
                    continue
                if node_id == _orig_imp_ut_tid and _new_imp_ut_tid is not None:
                    node["Node ID"] = _new_imp_ut_tid
                    if _imp_ut_sid:
                        node["Name String ID"] = _imp_ut_sid
                        node["Help String ID"] = _imp_ut_sid + 100000
                    if _imp_ut_name:
                        node["Name"] = _imp_ut_name
                    node["Node Status"] = STATUS_OK
                    changed += 1
                    continue

            if use_type == "Building":
                ok = node_id in building_ids
            elif use_type == "Tech":
                ok = node_id in tech_ids
            else:
                ok = node_id in unit_ids
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
    "mayan":       "MAYA",
    "magyars":     "MAGYAR",      # KM_TECHTREE_ORDER uses plural; lookup key is singular
    "hindustanis": "INDIANS",     # DAT renamed civ; file is still INDIANS.json + indians.png
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
    # Build lookup by canonical civTechTrees ID → index.
    lookup: dict[str, int] = {name.upper(): i for i, name in enumerate(KM_TECHTREE_ORDER)}
    # Extra aliases for names that differ between dat, user input, and KM_TECHTREE_ORDER.
    lookup["INCAS"]    = lookup["INCA"]    # dat uses "Incas"; list uses "Inca"
    lookup["MAGYAR"]   = lookup["MAGYARS"] # dat uses "Magyars"; civTechTrees uses "Magyar"
    lookup["MAYANS"]   = lookup["MAYA"]    # historical alias; also matches old KM naming
    lookup["INDIANS"]  = lookup["HINDUSTANIS"]  # historical alias pre-rename
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
    civ_index = apply_civ(dat, civ_def, target_slot=target_slot)["civ_index"]
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
