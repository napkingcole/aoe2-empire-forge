#!/usr/bin/env python3
"""
app.py — Flask web UI for the AoE2 DE Civ Builder.

Routes:
  GET  /              Upload page (step 1)
  POST /upload        Process uploaded KM JSON files → configure page
  GET  /configure     Drag-and-drop civ ordering + vanilla slot assignment (step 2)
  POST /build         Run the build pipeline → results page
  GET  /results       Per-civ bonus report + download link (step 3)
  GET  /download      Serve the built mod zip
"""

import contextlib
import io
import json
import os
import tempfile
import uuid
import zipfile
from pathlib import Path

from flask import (Flask, flash, redirect, render_template,
                   request, send_file, session, url_for)

from bonus_names import bonus_name, skip_reason
from build_all import (_build_combined_data_zip, _build_combined_ui_zip,
                       _ut_name, _ut_bonus_id, _BONUS_NAMES,
                       _UNIQUE_CASTLE_STRINGS, _UNIQUE_IMP_STRINGS)
from build_civ import (
    AI_PER_STUB, LANGUAGES, KM_TECHTREE_ORDER,
    _find_civ_slot, _civ_techtree_index, _civ_file_name,
    _decode_flag, _find_civ_techtrees_folder,
    _patch_per_civ_techtree, _canonical_techtree_id,
    _resolve_uu_info, _find_adjacent_json,
)
from civ_appender import (apply_civ,
                          _str_id, STRING_BASE, STRING_BLOCK_SIZE,
                          STR_CASTLE_UT, STR_IMPERIAL_UT,
                          DLL_CREATION_OFFSET, DLL_HELP_OFFSET, DLL_TECH_TREE_OFFSET)
from dat_reader import find_game_dat, load_dat

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

SESSIONS_DIR = Path(tempfile.gettempdir()) / "aoe2civbuilder"
SESSIONS_DIR.mkdir(exist_ok=True)


# ── Session helpers ───────────────────────────────────────────────────────────

def _session_dir() -> Path:
    sid = session.get("sid")
    if not sid:
        sid = str(uuid.uuid4())
        session["sid"] = sid
    d = SESSIONS_DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_vanilla_civs(dat_path: str) -> list[str]:
    """Load the list of playable vanilla civ names from the DAT (excludes Gaia)."""
    dat = load_dat(dat_path)
    return [c.name for c in dat.civs[1:]]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    dat_path = str(find_game_dat() or "")
    return render_template("index.html", dat_path=dat_path)


@app.route("/upload", methods=["POST"])
def upload():
    dat_path = request.form.get("dat_path", "").strip()
    dat_path_obj = Path(dat_path)
    if dat_path_obj.is_dir():
        # User pointed at the folder — try to find the DAT inside it.
        candidate = dat_path_obj / "empires2_x2_p1.dat"
        if candidate.exists():
            dat_path = str(candidate)
            dat_path_obj = candidate
        else:
            flash(f"That's a folder, not a DAT file. Point to empires2_x2_p1.dat directly.", "error")
            return redirect(url_for("index"))
    if not dat_path_obj.exists():
        flash(f"DAT file not found: {dat_path}", "error")
        return redirect(url_for("index"))

    files = request.files.getlist("civ_files")
    if not files or all(f.filename == "" for f in files):
        flash("Please select at least one civ JSON file.", "error")
        return redirect(url_for("index"))

    sd = _session_dir()
    session["dat_path"] = dat_path

    civs = []
    for f in files:
        if not f.filename or not f.filename.endswith(".json"):
            continue
        dest = sd / f.filename
        f.save(dest)
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
            bonus_list = (data.get("bonuses", [[]])[0]
                          if data.get("bonuses") else [])
            civs.append({
                "filename": f.filename,
                "name": (data.get("alias") or data.get("name")
                         or Path(f.filename).stem),
                "bonus_count": len(bonus_list),
            })
        except Exception as e:
            flash(f"Could not parse {f.filename}: {e}", "warning")

    if not civs:
        flash("No valid civ JSON files found.", "error")
        return redirect(url_for("index"))

    # Load vanilla civ list here (alongside file uploads) so configure loads instantly.
    vanilla_civs = []
    try:
        vanilla_civs = _get_vanilla_civs(dat_path)
    except Exception as e:
        flash(f"Could not read DAT file — check the path. ({e})", "error")
        return redirect(url_for("index"))

    session["civs"]         = civs
    session["vanilla_civs"] = vanilla_civs
    return redirect(url_for("configure"))


@app.route("/configure")
def configure():
    civs         = session.get("civs")
    vanilla_civs = session.get("vanilla_civs", [])
    if not civs:
        return redirect(url_for("index"))

    # Auto-assign: each uploaded civ gets the next available vanilla slot.
    defaults = {
        c["filename"]: vanilla_civs[i] if i < len(vanilla_civs) else ""
        for i, c in enumerate(civs)
    }

    return render_template("configure.html", civs=civs,
                           vanilla_civs=vanilla_civs, defaults=defaults)


@app.route("/build", methods=["POST"])
def build():
    dat_path = session.get("dat_path")
    civs_meta = {c["filename"]: c for c in session.get("civs", [])}
    sd = _session_dir()

    ordered = request.form.getlist("civ_order[]")
    if not ordered:
        flash("No civs in build order — did JavaScript run?", "error")
        return redirect(url_for("configure"))

    mod_name = request.form.get("mod_name", "Custom Civs").strip() or "Custom Civs"

    dat = load_dat(dat_path)
    dat_path_obj = Path(dat_path)

    ct_folder = _find_civ_techtrees_folder(dat_path_obj)

    ai_stubs:    dict[str, bytes] = {}
    button_pngs: dict[str, bytes] = {}
    per_civ_tt:  dict[str, bytes] = {}
    string_lines: dict[str, list[str]] = {lang: [] for lang in LANGUAGES}
    build_results = []
    # Maps DAT slot -> (name_string_id, uu_icon_id) for civilizations.json
    # patching (civ-picker name + unique-unit thumbnail). Mirrors build_all.py.
    civs_overrides: dict[int, dict] = {}

    # Fixed, non-per-civ strings for bonus 308/309/310's shared unit slots.
    # Mirrors build_all.py's identical block.
    from civ_appender import FIXED_UNIT_NAME_STRINGS
    for lang in LANGUAGES:
        for sid, text in FIXED_UNIT_NAME_STRINGS:
            string_lines[lang].append(f'{sid} "{text}"')

    # Pre-compute which techtree positions will be replaced so we can skip
    # writing vanilla names for them.  AoE2 DE key-value files are
    # first-definition-wins — writing "Britons" first then "Horsey Boys" second
    # would leave the vanilla name in place.
    replaced_tt_positions: set[int] = set()
    for _fn in ordered:
        _replace = request.form.get(f"replace_{_fn}", "").strip()
        if not _replace:
            continue
        _slot = _find_civ_slot(dat, _replace)
        if _slot is None:
            continue
        _tti = _civ_techtree_index(dat.civs[_slot].name)
        if _tti is not None:
            replaced_tt_positions.add(_tti)

    # Write vanilla civ name strings upfront, skipping replaced positions.
    for i, vanilla_name in enumerate(KM_TECHTREE_ORDER):
        if i in replaced_tt_positions:
            continue
        sid = 10271 + i
        for lang in LANGUAGES:
            string_lines[lang].append(f'{sid} "{vanilla_name}"')
            string_lines[lang].append(f'{sid + 80000} "Click to play as {vanilla_name}."')

    for fn in ordered:
        replace = request.form.get(f"replace_{fn}", "").strip()
        meta = civs_meta.get(fn)
        if not meta or not replace:
            continue

        civ_path = sd / fn
        if not civ_path.exists():
            build_results.append({"name": meta["name"], "replace": replace,
                                  "error": f"Uploaded file missing: {fn}"})
            continue

        civ_def = json.loads(civ_path.read_text(encoding="utf-8"))
        slot = _find_civ_slot(dat, replace)
        if slot is None:
            build_results.append({"name": meta["name"], "replace": replace,
                                  "error": f"Vanilla civ '{replace}' not found in DAT"})
            continue

        # Capture the vanilla civ name BEFORE apply_civ renames the slot.
        ui_civ_name = dat.civs[slot].name

        log_buf = io.StringIO()
        with contextlib.redirect_stdout(log_buf):
            result = apply_civ(dat, civ_def, target_slot=slot)
        result["replace"] = replace
        result["log"]     = log_buf.getvalue()
        build_results.append(result)

        alias = result["alias"]
        tt_idx   = _civ_techtree_index(ui_civ_name)
        name_sid = 10271 + tt_idx if tt_idx is not None else 10271

        _bonuses_raw = civ_def.get("bonuses", [])

        # Resolve UT names from KM bonus IDs.
        castle_ut_bid  = _ut_bonus_id(civ_def, 2)
        imp_ut_bid     = _ut_bonus_id(civ_def, 3)
        castle_ut_name = _ut_name(castle_ut_bid, castle=True)
        imp_ut_name    = _ut_name(imp_ut_bid, castle=False)
        # Enrich result with UT names for CivTechTrees node label updates.
        result["castle_ut_name"] = castle_ut_name
        result["imp_ut_name"]    = imp_ut_name

        # Real existing-id pool slots (civ_appender.CAMPAIGN_STRING_POOL) —
        # NOT the old high-range _str_id fallback, which never worked in-game.
        castle_ut_sid = result.get("castle_ut_sid") or _str_id(slot, STR_CASTLE_UT)
        imp_ut_sid    = result.get("imp_ut_sid")    or _str_id(slot, STR_IMPERIAL_UT)
        castle_ut_desc_sid = result.get("castle_ut_desc_sid") or castle_ut_sid
        imp_ut_desc_sid    = result.get("imp_ut_desc_sid")    or imp_ut_sid

        # Resolve the custom UU info (unit ID, icon, name) for string writes + techtree.
        uu_info = _resolve_uu_info(civ_def, dat, slot, result)
        # See build_all.py's identical block for why civilizations.json's own
        # UU metadata block (unique_unit_id/elite_unique_unit_id/
        # unique_unit_string_ids/unique_unit_upgrade_id) needs explicit
        # retargeting — it's a separate block from the per-unit DAT strings
        # and is otherwise left pointing at the overwritten civ's original UU.
        civs_overrides[slot] = {
            "name_sid": name_sid,
            "icon_id": uu_info["icon_id"] if uu_info else None,
            "uu_unit_id":    uu_info["unit_id"]  if uu_info else None,
            "uu_elite_id":   uu_info["elite_id"] if uu_info else None,
            "uu_upgrade_tech_id": result.get("km_uu_elite_tech_id"),
            "uu_name_sid":   uu_info["dll_name"] if uu_info else None,
            "uu_desc_sid":   uu_info["dll_help"] if uu_info else None,
        }
        # Also look up the elite unit's dll_name for string writes.
        uu_elite_dll: int | None = None
        uu_elite_name: str | None = None
        if uu_info:
            elite_uid = uu_info.get("elite_id")
            if elite_uid is not None and elite_uid != uu_info["unit_id"]:
                try:
                    eu = dat.civs[slot].units[elite_uid]
                    uu_elite_dll  = eu.language_dll_name
                    uu_elite_name = f"Elite {uu_info['name']}"
                except (IndexError, AttributeError):
                    pass

        # Build civ selection screen description with bonuses + UT names.
        description   = civ_def.get("description", "")
        civ_bonuses   = (_bonuses_raw[0]
                         if _bonuses_raw and isinstance(_bonuses_raw[0], list)
                         else [])
        team_bonus_entries = (_bonuses_raw[4]
                              if len(_bonuses_raw) > 4 and isinstance(_bonuses_raw[4], list)
                              else [])
        desc_parts = [f'{description} civilization' if description else f'{alias} civilization']
        desc_parts.append(" \\n\\n")
        for entry in civ_bonuses:
            if not isinstance(entry, list):
                continue
            bid  = str(entry[0])
            mult = entry[1] if len(entry) > 1 else 1
            txt  = _BONUS_NAMES.get(bid, "")
            if not txt:
                continue
            suffix = f" [x{mult}]" if mult > 1 else ""
            desc_parts.append(f"• {txt}{suffix} \\n")
        desc_parts.append("\\n<b>Unique Unit:<b> \\n")
        uu_display = uu_info["name"] if uu_info else "Unique Unit"
        desc_parts.append(f"{uu_display} \\n")
        desc_parts.append("\\n<b>Unique Techs:<b> \\n")
        desc_parts.append(f"• {castle_ut_name} \\n")
        desc_parts.append(f"• {imp_ut_name} \\n")
        if team_bonus_entries:
            desc_parts.append("\\n<b>Team Bonus:<b> \\n")
            for entry in team_bonus_entries:
                if not isinstance(entry, list):
                    continue
                bid = str(entry[0])
                txt = _BONUS_NAMES.get(bid, "")
                if txt:
                    desc_parts.append(f"• {txt} \\n")
        full_desc = "".join(desc_parts)

        for lang in LANGUAGES:
            string_lines[lang].append(f'{name_sid} "{alias}"')
            string_lines[lang].append(
                f'{name_sid + 80000} "Click to play as {alias}."')
            string_lines[lang].append(
                f'{name_sid + 109879} "{full_desc}"')
            # In-game Castle UT button: name_sid covers the label;
            # name_sid+DLL_CREATION_OFFSET/+DLL_TECH_TREE_OFFSET are what the
            # tech's language_dll_description/tech_tree fields actually point
            # at (vanilla offset convention — see
            # civ_appender._creation_sid/_tech_tree_sid) and MUST be written
            # explicitly, or the engine falls back to whatever vanilla
            # content already lives at that id instead of leaving it blank
            # (confirmed live — a Castle UT button showed an unrelated
            # campaign dialogue line at name+1000 until this was added).
            string_lines[lang].append(f'{castle_ut_sid} "{castle_ut_name}"')
            string_lines[lang].append(
                f'{castle_ut_sid + DLL_CREATION_OFFSET} "Research {castle_ut_name}"')
            string_lines[lang].append(
                f'{castle_ut_desc_sid} '
                f'"Research <b>{castle_ut_name}<b> (<cost>)\\n{castle_ut_name}"')
            string_lines[lang].append(
                f'{castle_ut_sid + DLL_TECH_TREE_OFFSET} "{castle_ut_name}"')
            # In-game Imperial UT button
            string_lines[lang].append(f'{imp_ut_sid} "{imp_ut_name}"')
            string_lines[lang].append(
                f'{imp_ut_sid + DLL_CREATION_OFFSET} "Research {imp_ut_name}"')
            string_lines[lang].append(
                f'{imp_ut_desc_sid} '
                f'"Research <b>{imp_ut_name}<b> (<cost>)\\n{imp_ut_name}"')
            string_lines[lang].append(
                f'{imp_ut_sid + DLL_TECH_TREE_OFFSET} "{imp_ut_name}"')
            # Bonus-specific research buttons (Imperial Scorpion, Royal Battle
            # Elephant, Royal Lancer — bonuses 308/309/310). Mirrors
            # build_all.py's identical block — this was previously missing
            # here entirely, leaving these buttons blank when built via the
            # web app.
            for ext in result["bonus_results"].get("extra_tech_strings", []):
                sid, name = ext["sid"], ext["name"]
                string_lines[lang].append(f'{sid} "{name}"')
                string_lines[lang].append(f'{sid + DLL_CREATION_OFFSET} "Research {name}"')
                string_lines[lang].append(
                    f'{sid + DLL_HELP_OFFSET} "Research <b>{name}<b> (<cost>)"')
                string_lines[lang].append(f'{sid + 150000} "{name}"')
            # KM-custom UU units' OWN name/help strings — see build_all.py's
            # identical block for why this is separate from the dll_name+10000
            # tech-tree-viewer block right below.
            for ext in result["bonus_results"].get("extra_unit_strings", []):
                # sid+DLL_CREATION_OFFSET (name+1000) is what the engine
                # actually reads for the Castle "create unit" button/elite
                # tech description — must be written explicitly, same
                # reasoning as the Castle/Imperial UT block above. desc_sid
                # (=sid+DLL_HELP_OFFSET, computed by civ_appender) is the
                # full tooltip.
                sid, name = ext["sid"], ext["name"]
                string_lines[lang].append(f'{sid} "{name}"')
                string_lines[lang].append(
                    f'{sid + DLL_CREATION_OFFSET} "Create {name}"')
                help_text = ext.get("help_text", name)
                desc_sid = ext.get("desc_sid", sid)
                string_lines[lang].append(f'{desc_sid} "{help_text}"')
                # The Castle "create unit" button's EXTENDED hover tooltip
                # for a UNIT is read from name+21000, NOT name+100000 — see
                # build_all.py's identical block / civ_appender.
                # _extended_tooltip_sid's docstring for how this was found.
                if "ext_sid" in ext:
                    string_lines[lang].append(
                        f'{ext["ext_sid"]} "{ext.get("ext_text", name)}"')
            # UU name strings for civ selection tech tree display.
            if uu_info:
                uu_dll = uu_info["dll_name"]
                string_lines[lang].append(f'{uu_dll + 10000} "{uu_display}"')
                string_lines[lang].append(f'{uu_dll + DLL_HELP_OFFSET} "{uu_display}"')
            if uu_elite_dll and uu_elite_name:
                string_lines[lang].append(f'{uu_elite_dll + 10000} "{uu_elite_name}"')
                string_lines[lang].append(f'{uu_elite_dll + DLL_HELP_OFFSET} "{uu_elite_name}"')

        flag_png = _decode_flag(civ_def)
        if flag_png:
            # Use canonical civTechTrees name (e.g. "britons") not DAT internal
            # name (e.g. "british") — game loads icons by canonical name.
            fn_img = _canonical_techtree_id(ui_civ_name).lower()
            for variant in ("", "_hover", "_pressed"):
                button_pngs[f"menu_techtree_{fn_img}{variant}.png"] = flag_png

        ai_name = f"{alias} AI (pre-alpha)"
        ai_stubs[f"resources/_common/ai/{ai_name}.ai"]  = b""
        ai_stubs[f"resources/_common/ai/{ai_name}.per"] = AI_PER_STUB

        if ct_folder:
            vanilla_tt_name = _canonical_techtree_id(ui_civ_name)
            per_civ_path = ct_folder / f"{vanilla_tt_name}.json"
            if per_civ_path.exists():
                patched = _patch_per_civ_techtree(per_civ_path, civ_def, dat, slot,
                                                    civ_result=result)
                if patched is not None:
                    per_civ_tt[f"{vanilla_tt_name}.json"] = patched

    # Fill in vanilla per-civ CivTechTrees JSONs for every unmodified civ.
    # AoE2 DE (post 2026-06-02 patch) uses per-civ files exclusively — if any are
    # missing, the game falls back to the vanilla global and ignores all our patches.
    if ct_folder:
        for json_file in sorted(ct_folder.glob("*.json")):
            if json_file.name not in per_civ_tt:
                per_civ_tt[json_file.name] = json_file.read_bytes()

    # Tie-break MUST be insertion order, not the line's own text — see
    # build_all.py's identical sort (which has this fix already; app.py was
    # missing it). Sorting ties alphabetically silently breaks "first-
    # definition-wins" whenever two different call sites write different
    # text to the SAME id (e.g. a bare unit name from the tech-tree-viewer
    # block + a richer formatted tooltip from extra_unit_strings) — confirmed
    # via a live build that this exact collision can shadow Gendarme's help
    # text. In the current code the richer line happens to be appended
    # first, so this is currently a latent-risk fix rather than the active
    # cause of any reported symptom, but matching build_all.py's safety net
    # costs nothing and removes the dependency on append-order staying lucky.
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

    # Generate civilizations.json with updated names + UU icon paths for
    # replaced civs. Required since the 2026-06-06 patch — AoE2 DE now
    # validates this file's entry count against the DAT civ count and
    # silently drops modded-strings civ-picker overrides without it.
    civs_json_bytes: bytes | None = None
    base_civs_json = _find_adjacent_json(dat_path_obj, "civilizations.json")
    if base_civs_json is None or not base_civs_json.exists():
        base_civs_json = Path(__file__).parent / "civilizations.json"
    if base_civs_json.exists() and civs_overrides:
        try:
            with open(base_civs_json, encoding="utf-8") as f:
                civ_list = json.load(f).get("civilization_list", [])
            for slot_idx, ov in civs_overrides.items():
                if slot_idx >= len(civ_list):
                    continue
                entry = civ_list[slot_idx]
                entry["name_string_id"] = ov["name_sid"]
                icon_id = ov.get("icon_id")
                if icon_id is not None:
                    entry["unique_unit_image_paths"] = [
                        f"/resources/uniticons/{icon_id:03d}_50730.png"
                    ]
                uu_unit_id = ov.get("uu_unit_id")
                if uu_unit_id is not None:
                    entry["unique_unit_id"] = uu_unit_id
                    if ov.get("uu_elite_id") is not None:
                        entry["elite_unique_unit_id"] = ov["uu_elite_id"]
                    if ov.get("uu_upgrade_tech_id") is not None:
                        entry["unique_unit_upgrade_id"] = ov["uu_upgrade_tech_id"]
                    if ov.get("uu_name_sid") is not None:
                        name_sid_uu = ov["uu_name_sid"]
                        # See build_all.py's identical block — prefer the
                        # explicit desc sid (real id for both vanilla and
                        # KM-custom UUs); the +DLL_HELP_OFFSET fallback only
                        # reliably works for the vanilla path.
                        desc_sid_uu = ov.get("uu_desc_sid") or (name_sid_uu + DLL_HELP_OFFSET)
                        entry["unique_unit_string_ids"] = [
                            {"name": name_sid_uu, "description": desc_sid_uu}
                        ]
            civs_json_bytes = json.dumps(
                {"civilization_list": civ_list}, separators=(",", ":")
            ).encode("utf-8")
        except Exception as e:
            print(f"WARNING: Could not generate civilizations.json: {e}")

    prefix   = mod_name.lower().replace(" ", "_")
    data_zip = _build_combined_data_zip(dat, button_pngs, per_civ_tt, mod_name=mod_name,
                                        civs_json_bytes=civs_json_bytes)
    ui_zip   = _build_combined_ui_zip(ai_stubs, button_pngs, combined_strings, mod_name=mod_name)

    out_path = sd / f"{prefix}.zip"
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as outer:
        outer.writestr(f"{prefix}-data.zip", data_zip)
        outer.writestr(f"{prefix}-ui.zip",   ui_zip)

    # Store results in a file — logs make them too large for a cookie session.
    results_path = sd / "results.json"
    results_path.write_text(json.dumps(build_results), encoding="utf-8")

    session["results_path"] = str(results_path)
    session["out_file"]     = str(out_path)
    session["out_name"]     = f"{prefix}.zip"
    return redirect(url_for("results"))


@app.route("/results")
def results():
    results_path = session.get("results_path")
    build_results = []
    if results_path and Path(results_path).exists():
        build_results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    has_download  = bool(session.get("out_file") and
                         Path(session["out_file"]).exists())
    out_name      = session.get("out_name", "mod.zip")
    return render_template("results.html", results=build_results,
                           has_download=has_download, out_name=out_name,
                           bonus_name=bonus_name, skip_reason=skip_reason)


@app.route("/download")
def download():
    out_file = session.get("out_file")
    out_name = session.get("out_name", "mod.zip")
    if not out_file or not Path(out_file).exists():
        flash("No output file available — please build first.", "error")
        return redirect(url_for("results"))
    return send_file(out_file, as_attachment=True, download_name=out_name)


@app.route("/reset")
def reset():
    session.clear()
    return redirect(url_for("index"))


# ── Dev server entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import threading
    import webbrowser

    def _open_browser():
        webbrowser.open("http://127.0.0.1:8080")

    threading.Timer(1.0, _open_browser).start()
    app.run(debug=False, port=8080)
