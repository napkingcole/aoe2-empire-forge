"""
wizard_build.py — build pipeline for the single-civ New Civ wizard.

Mirrors the per-civ logic in build_all.py's big loop, but reads everything
from a wizard draft dict instead of a KM JSON file on disk.
"""

import io
import json
import re
import zipfile
from pathlib import Path

from build_all import (
    _build_combined_data_zip,
    _build_combined_ui_zip,
    _ut_name,
    _BONUS_NAMES,
    _VANILLA_CIV_DESCRIPTIONS,
    DLL_CREATION_OFFSET,
    DLL_HELP_OFFSET,
    DLL_TECH_TREE_OFFSET,
)
from build_civ import (
    AI_PER_STUB,
    LANGUAGES,
    KM_TECHTREE_ORDER,
    _find_civ_slot,
    _civ_techtree_index,
    _canonical_techtree_id,
    _resolve_uu_info,
    _patch_per_civ_techtree,
    _find_adjacent_json,
    _find_civ_techtrees_folder,
    _decode_flag,
)
from civ_appender import apply_civ, assign_all_languages
from civ_overrides import _apply_uu_overrides, _apply_hero_unit, _override_ut_costs
from dat_reader import load_dat


# ── Draft → civ_def ──────────────────────────────────────────────────────────

def _draft_to_civ_def(draft: dict) -> dict:
    """Convert wizard draft JSON to the civ_def format expected by apply_civ."""
    civ_bonuses = [
        [b["id"], b.get("multiplier", 1)]
        for b in draft.get("bonuses", [])
    ]

    uu = draft.get("unique_unit") or {}
    km_idx   = uu.get("km_idx")
    uu_slot  = [km_idx] if km_idx is not None else []

    castle_effects = [
        [e["id"], e.get("multiplier", 1)]
        for e in (draft.get("castle_ut") or {}).get("effects", [])
    ]
    imp_effects = [
        [e["id"], e.get("multiplier", 1)]
        for e in (draft.get("imperial_ut") or {}).get("effects", [])
    ]

    # Support both new array form (team_bonuses) and old single form (team_bonus)
    team_bonuses_list = draft.get("team_bonuses") or []
    if not team_bonuses_list and draft.get("team_bonus"):
        team_bonuses_list = [draft["team_bonus"]]
    team_slot = [[tb["id"], tb.get("multiplier", 1)] for tb in team_bonuses_list]

    civ_def: dict = {
        "alias":        draft.get("alias", "Custom Civ"),
        "description":  draft.get("tagline", ""),
        "architecture": draft.get("architecture", 2),
        "language":     draft.get("language", 0),
        "wonder":       draft.get("wonder", -1),
        "castle":       draft.get("castle", -1),
        "bonuses": [civ_bonuses, uu_slot, castle_effects, imp_effects, team_slot],
        "tree": [
            (draft.get("tree") or {}).get("units", []),
            (draft.get("tree") or {}).get("buildings", []),
            (draft.get("tree") or {}).get("techs", []),
        ],
    }

    # UU name override — passed under unique_unit.name so km_custom_uu can
    # pick it up for custom presets; vanilla UU names come from the DAT.
    if uu.get("name"):
        civ_def["unique_unit"] = {"name": uu["name"]}

    # Add hero unit ID to the trainable units list so it appears in the tech tree
    hero_id = (draft.get("hero_unit") or {}).get("base_unit_id")
    if hero_id is not None and hero_id not in civ_def["tree"][0]:
        civ_def["tree"][0] = list(civ_def["tree"][0]) + [hero_id]

    # Emblem: wizard stores a data-URI under draft.emblem;
    # _decode_flag expects it under civ_def["customFlagData"].
    emblem = draft.get("emblem", "")
    if emblem and emblem.startswith("data:image"):
        civ_def["customFlagData"] = emblem

    return civ_def


# ── Main build function ──────────────────────────────────────────────────────

def build_wizard_mod(draft: dict, dat_path: str, replace_civ: str) -> bytes:
    """
    Build a complete mod zip from a wizard draft.

    Returns the outer zip bytes containing two inner zips:
        {prefix}-data.zip  — DAT + CivTechTrees + civilizations.json
        {prefix}-ui.zip    — language strings + emblems + voice files + AI stubs
    """
    civ_def  = _draft_to_civ_def(draft)
    alias    = civ_def["alias"]
    mod_name = f"{alias}"
    prefix   = re.sub(r"[^A-Za-z0-9_-]", "_", alias).lower() or "custom_civ"

    dat_path_obj = Path(dat_path)
    ct_folder    = _find_civ_techtrees_folder(dat_path_obj)

    base_civs_json = _find_adjacent_json(dat_path_obj, "civilizations.json")
    if base_civs_json is None or not base_civs_json.exists():
        base_civs_json = Path(__file__).parent / "civilizations.json"

    dat = load_dat(dat_path)

    # ── Find replacement slot ────────────────────────────────────────────────
    slot = _find_civ_slot(dat, replace_civ)
    if slot is None:
        raise ValueError(f"Cannot find a civ named {replace_civ!r} in the DAT file.")

    ui_civ_name = dat.civs[slot].name
    tt_idx      = _civ_techtree_index(ui_civ_name)
    name_sid    = 10271 + tt_idx if tt_idx is not None else 10271

    # ── Apply civ to DAT ────────────────────────────────────────────────────
    civ_result = apply_civ(dat, civ_def, target_slot=slot)

    # Override UT costs and research time from wizard values
    _override_ut_costs(dat, civ_result, draft)

    # Apply UU stat overrides and advanced flags before string building
    uu_info = _resolve_uu_info(civ_def, dat, slot, civ_result)
    _apply_uu_overrides(dat, slot, uu_info, draft)
    _apply_hero_unit(dat, slot, draft)

    # ── Language (voice) assignment ─────────────────────────────────────────
    lang_val = civ_result["lang_val"]
    assign_all_languages(dat, [(civ_result["civ_index"], lang_val)])

    # ── String building ──────────────────────────────────────────────────────
    string_lines: dict[str, list[str]] = {lang: [] for lang in LANGUAGES}

    # UT display names — prefer wizard draft, fall back to _ut_name default
    castle_ut_name = (
        ((draft.get("castle_ut") or {}).get("name") or "").strip()
        or _ut_name(None, castle=True)
    )
    imp_ut_name = (
        ((draft.get("imperial_ut") or {}).get("name") or "").strip()
        or _ut_name(None, castle=False)
    )

    # UU info for icon + string IDs (resolved earlier, before _apply_uu_overrides)
    uu_override_name = (draft.get("unique_unit") or {}).get("name", "").strip()
    uu_override_desc = (draft.get("unique_unit") or {}).get("description", "").strip()

    # Extract training cost from the UU unit after apply_civ; append to description.
    _uu_cost_str: str = ""
    if uu_info and uu_info.get("unit_id") is not None:
        try:
            unit_obj = dat.civs[slot].units[uu_info["unit_id"]]
            _RES = {0: "F", 1: "W", 2: "S", 3: "G"}
            cost_parts = [
                f"{int(rc.amount)}{_RES[rc.type]}"
                for rc in unit_obj.creatable.resource_costs
                if rc.type in _RES and rc.amount > 0
            ]
            if cost_parts:
                _uu_cost_str = "Costs: " + " ".join(cost_parts)
        except Exception:
            pass
    uu_display = (
        uu_override_name or (uu_info["name"] if uu_info else "Unique Unit")
    )

    # civilizations.json override metadata
    civs_overrides: dict[int, dict] = {
        slot: {
            "name_sid":           name_sid,
            "icon_id":            uu_info["icon_id"] if uu_info else None,
            "uu_unit_id":         uu_info["unit_id"]  if uu_info else None,
            "uu_elite_id":        uu_info["elite_id"] if uu_info else None,
            "uu_upgrade_tech_id": civ_result.get("km_uu_elite_tech_id"),
            "uu_name_sid":        uu_info["dll_name"] if uu_info else None,
            "uu_desc_sid":        uu_info["dll_help"] if uu_info else None,
        }
    }

    # Build civ-picker description string
    tagline      = civ_def.get("description", "")
    civ_bonuses  = civ_def["bonuses"][0] if civ_def.get("bonuses") else []
    team_entries = civ_def["bonuses"][4] if len(civ_def.get("bonuses", [])) > 4 else []

    desc_parts = [f"{tagline} civilization" if tagline else f"{alias} civilization"]
    desc_parts.append("\\n\\n")
    bullets = []
    for entry in civ_bonuses:
        if not isinstance(entry, list):
            continue
        txt  = _BONUS_NAMES.get(str(entry[0]), "")
        mult = entry[1] if len(entry) > 1 else 1
        if txt:
            bullets.append(f"• {txt}" + (f" [x{mult}]" if mult > 1 else ""))
    desc_parts.append("\\n".join(bullets))
    desc_parts.append(f"\\n\\n<b>Unique Unit:<b> \\n{uu_display}")
    desc_parts.append(
        f"\\n\\n<b>Unique Techs:<b> \\n• {castle_ut_name}\\n• {imp_ut_name}"
    )
    if team_entries:
        tb_lines = [
            _BONUS_NAMES.get(str(e[0]), "")
            for e in team_entries if isinstance(e, list)
        ]
        tb_lines = [t for t in tb_lines if t]
        if tb_lines:
            desc_parts.append(f"\\n\\n<b>Team Bonus:<b> \\n{'; '.join(tb_lines)}")
    full_desc = "".join(desc_parts)
    while full_desc.endswith("\\n") or full_desc.endswith(" "):
        full_desc = full_desc[:-2] if full_desc.endswith("\\n") else full_desc.rstrip()

    castle_ut_sid      = civ_result["castle_ut_sid"]
    imp_ut_sid         = civ_result["imp_ut_sid"]
    castle_ut_desc_sid = civ_result["castle_ut_desc_sid"]
    imp_ut_desc_sid    = civ_result["imp_ut_desc_sid"]

    # Elite UU label for string writes
    uu_elite_dll:  int | None = None
    uu_elite_name: str | None = None
    if uu_info:
        elite_uid = uu_info.get("elite_id")
        if elite_uid is not None and elite_uid != uu_info["unit_id"]:
            try:
                uu_elite_dll  = dat.civs[slot].units[elite_uid].language_dll_name
                uu_elite_name = f"Elite {uu_display}"
            except (IndexError, AttributeError):
                pass

    for lang in LANGUAGES:
        # Civ name + click-to-play + description
        string_lines[lang].append(f'{name_sid} "{alias}"')
        string_lines[lang].append(f'{name_sid + 80000} "Click to play as {alias}."')
        string_lines[lang].append(f'{name_sid + 109879} "{full_desc}"')

        # UT name + tooltip strings
        for ut_sid, desc_sid, full_name in (
            (castle_ut_sid, castle_ut_desc_sid, castle_ut_name),
            (imp_ut_sid,    imp_ut_desc_sid,    imp_ut_name),
        ):
            short, _, paren = full_name.partition(" (")
            desc = paren.rstrip(")") if paren else ""
            string_lines[lang].append(f'{ut_sid} "{short}"')
            string_lines[lang].append(
                f'{ut_sid + DLL_CREATION_OFFSET} "Research {short}"')
            # The Castle UI reads name_sid+21000 for UT buttons (same slot as the
            # unit train-button widget). Override it so vanilla content at that
            # offset (e.g. 70202+21000=91202 "Click to enter a filename...") can't
            # bleed through and overwrite the correct UT name on screen.
            string_lines[lang].append(f'{ut_sid + 21000} "{short}"')
            help_body = f"Research <b>{short}<b> (<cost>)"
            if desc:
                help_body += f"\\n{desc}"
            string_lines[lang].append(f'{desc_sid} "{help_body}"')
            string_lines[lang].append(f'{ut_sid + DLL_TECH_TREE_OFFSET} "{short}"')

        # Extra tech strings (e.g. bonus-specific research buttons)
        for ext in civ_result["bonus_results"].get("extra_tech_strings", []):
            sid, name = ext["sid"], ext["name"]
            string_lines[lang].append(f'{sid} "{name}"')
            string_lines[lang].append(f'{sid + DLL_CREATION_OFFSET} "Research {name}"')
            string_lines[lang].append(
                f'{sid + DLL_HELP_OFFSET} "Research <b>{name}<b> (<cost>)"')
            string_lines[lang].append(f'{sid + 150000} "{name}"')

        # Extra unit strings (KM-custom UU names / Castle train-button text)
        for ext in civ_result["bonus_results"].get("extra_unit_strings", []):
            sid, name = ext["sid"], ext["name"]
            string_lines[lang].append(f'{sid} "{name}"')
            string_lines[lang].append(f'{sid + DLL_CREATION_OFFSET} "Create {name}"')
            help_text = ext.get("help_text", name)
            desc_sid_u = ext.get("desc_sid", sid)
            string_lines[lang].append(f'{desc_sid_u} "{help_text}"')
            if "ext_sid" in ext:
                string_lines[lang].append(
                    f'{ext["ext_sid"]} "{ext.get("ext_text", name)}"')

        # UU display name strings
        if uu_info:
            dll = uu_info["dll_name"]
            # Tech-tree viewer (cosmetic)
            string_lines[lang].append(f'{dll + 10000} "{uu_display}"')
            if uu_override_name:
                # In-game overrides: base name, create button text, castle hover tooltip, help
                desc_body = uu_override_desc or ""
                if _uu_cost_str:
                    desc_body = (desc_body + "\\n" + _uu_cost_str) if desc_body else _uu_cost_str
                string_lines[lang].append(f'{dll} "{uu_display}"')
                string_lines[lang].append(f'{dll + DLL_CREATION_OFFSET} "Create {uu_display}"')
                string_lines[lang].append(
                    f'{dll + 21000} "Create <b>{uu_display}<b>'
                    + (f'\\n{desc_body}' if desc_body else '')
                    + '"')
                string_lines[lang].append(f'{dll + DLL_HELP_OFFSET} "{uu_display}"')
            elif _uu_cost_str:
                # No name override but still write cost to the Castle hover tooltip
                string_lines[lang].append(
                    f'{dll + 21000} "Create <b>{uu_display}<b>\\n{_uu_cost_str}"')
                string_lines[lang].append(f'{dll + DLL_HELP_OFFSET} "{uu_display}"')
            else:
                string_lines[lang].append(f'{dll + DLL_HELP_OFFSET} "{uu_display}"')
        if uu_elite_dll and uu_elite_name:
            string_lines[lang].append(f'{uu_elite_dll + 10000} "{uu_elite_name}"')
            if uu_override_name:
                string_lines[lang].append(f'{uu_elite_dll} "{uu_elite_name}"')
                string_lines[lang].append(
                    f'{uu_elite_dll + DLL_CREATION_OFFSET} "Create {uu_elite_name}"')
                string_lines[lang].append(
                    f'{uu_elite_dll + 21000} "Create <b>{uu_elite_name}<b>"')
                string_lines[lang].append(
                    f'{uu_elite_dll + DLL_HELP_OFFSET} "{uu_elite_name}"')
            else:
                string_lines[lang].append(
                    f'{uu_elite_dll + DLL_HELP_OFFSET} "{uu_elite_name}"')

    # Vanilla civ-name + description fallbacks for all unmodified civs
    replaced_pos = {tt_idx} if tt_idx is not None else set()
    for i, vanilla_name in enumerate(KM_TECHTREE_ORDER):
        if i in replaced_pos:
            continue
        sid = 10271 + i
        for lang in LANGUAGES:
            string_lines[lang].append(f'{sid} "{vanilla_name}"')
            string_lines[lang].append(f'{sid + 80000} "Click to play as {vanilla_name}."')
    for i in range(min(len(KM_TECHTREE_ORDER), 45)):
        if i in replaced_pos:
            continue
        sid  = 120150 + i
        text = _VANILLA_CIV_DESCRIPTIONS.get(sid)
        if text:
            for lang in LANGUAGES:
                string_lines[lang].append(f'{sid} "{text}"')

    # Sort strings: numeric ID ascending, insertion-order tie-break
    def _sort_key(indexed_line: tuple[int, str]) -> tuple[int, int]:
        idx, line = indexed_line
        try:
            return (int(line.split(" ", 1)[0]), idx)
        except ValueError:
            return (10**9, idx)

    combined_strings = {
        lang: "\n".join(line for _, line in sorted(enumerate(lines), key=_sort_key)) + "\n"
        for lang, lines in string_lines.items()
        if lines
    }

    # ── Button PNGs (emblem) ─────────────────────────────────────────────────
    button_pngs: dict[str, bytes] = {}
    flag_png = _decode_flag(civ_def)
    if flag_png:
        fn = _canonical_techtree_id(ui_civ_name).lower()
        for variant in ("", "_hover", "_pressed"):
            button_pngs[f"menu_techtree_{fn}{variant}.png"] = flag_png

    # ── AI stubs ────────────────────────────────────────────────────────────
    ai_stubs: dict[str, bytes] = {
        f"resources/_common/ai/{alias} AI (pre-alpha).ai":  b"",
        f"resources/_common/ai/{alias} AI (pre-alpha).per": AI_PER_STUB,
    }

    # ── CivTechTrees JSON ────────────────────────────────────────────────────
    per_civ_tt: dict[str, bytes] = {}
    if ct_folder:
        vanilla_tt_name = _canonical_techtree_id(ui_civ_name)
        per_civ_path    = ct_folder / f"{vanilla_tt_name}.json"
        if per_civ_path.exists():
            civ_result["castle_ut_name"] = castle_ut_name
            civ_result["imp_ut_name"]    = imp_ut_name
            patched = _patch_per_civ_techtree(
                per_civ_path, civ_def, dat=dat, slot=slot, civ_result=civ_result
            )
            if patched:
                per_civ_tt[f"{vanilla_tt_name}.json"] = patched
        for json_file in sorted(ct_folder.glob("*.json")):
            if json_file.name not in per_civ_tt:
                per_civ_tt[json_file.name] = json_file.read_bytes()

    # ── civilizations.json patch ─────────────────────────────────────────────
    civs_json_bytes: bytes | None = None
    if base_civs_json and base_civs_json.exists() and civs_overrides:
        try:
            with open(base_civs_json, encoding="utf-8") as f:
                civ_list = json.load(f).get("civilization_list", [])
            for slot_idx, ov in civs_overrides.items():
                if slot_idx >= len(civ_list):
                    continue
                entry = civ_list[slot_idx]
                entry["name_string_id"] = ov["name_sid"]
                if ov.get("icon_id") is not None:
                    entry["unique_unit_image_paths"] = [
                        f"/resources/uniticons/{ov['icon_id']:03d}_50730.png"
                    ]
                uu_unit_id = ov.get("uu_unit_id")
                if uu_unit_id is not None:
                    entry["unique_unit_id"] = uu_unit_id
                    if ov.get("uu_elite_id") is not None:
                        entry["elite_unique_unit_id"] = ov["uu_elite_id"]
                    if ov.get("uu_upgrade_tech_id") is not None:
                        entry["unique_unit_upgrade_id"] = ov["uu_upgrade_tech_id"]
                    if ov.get("uu_name_sid") is not None:
                        desc_sid_uu = ov.get("uu_desc_sid") or (ov["uu_name_sid"] + DLL_HELP_OFFSET)
                        entry["unique_unit_string_ids"] = [
                            {"name": ov["uu_name_sid"], "description": desc_sid_uu}
                        ]
            civs_json_bytes = json.dumps(
                {"civilization_list": civ_list}, separators=(",", ":")
            ).encode("utf-8")
        except Exception as exc:
            print(f"  WARNING: Could not patch civilizations.json: {exc}")

    # ── Package ──────────────────────────────────────────────────────────────
    data_zip = _build_combined_data_zip(
        dat, button_pngs, per_civ_tt,
        mod_name=mod_name, civs_json_bytes=civs_json_bytes,
    )
    ui_zip = _build_combined_ui_zip(
        ai_stubs, button_pngs, combined_strings,
        mod_name=mod_name, lang_values={lang_val},
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as outer:
        outer.writestr(f"{prefix}-data.zip", data_zip)
        outer.writestr(f"{prefix}-ui.zip",   ui_zip)
    return buf.getvalue()
