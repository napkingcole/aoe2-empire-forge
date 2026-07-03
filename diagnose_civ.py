#!/usr/bin/env python3
"""
diagnose_civ.py — Diagnostic report for AoE2 civ builder JSON files.

Applies a civ (or every civ in a mod config) to the vanilla DAT in-place and
reports what was created: techs, effect commands, strings, and known-bad patterns.
Nothing is written to disk — the report goes to stdout only.

Usage:
  python3 diagnose_civ.py <civ.json> [--replace <VanillaCivName>] [--dat <dat>]
  python3 diagnose_civ.py --all <mod_config.json> [--dat <dat>]

Examples (run from the project root or the directory containing the JSON):
  python3 diagnose_civ.py "json_files/Portuguese Empire.json" --replace Portuguese
  python3 diagnose_civ.py --all gold-and-silver_config.json
"""

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from genieutils.datfile import DatFile
from civ_appender import (
    apply_civ,
    _KM_UU_TECHS,
    BUILDING_CASTLE,
    EC_SET, EC_RESOURCE, EC_ENABLE, EC_UPGRADE, EC_ADD, EC_MULTIPLY,
    EC_TECH_COST, EC_TECH_TIME,
)
from bonus_catalog import civ_bonus_techs, civ_bonus_ec_list
from build_all import _UNIQUE_CASTLE_STRINGS, _UNIQUE_IMP_STRINGS

DEFAULT_DAT = Path(__file__).parent / "dat-file-6-2-26/empires2_x2_p1.dat"
MAX_EFFECT_COMMANDS = 189   # engine crash threshold

# ── Human-readable lookup tables ──────────────────────────────────────────────

ATTR_NAMES = {
    0: "HP", 1: "LOS", 2: "garrison", 3: "radius", 4: "speed",
    5: "rot_speed", 8: "armor", 9: "min_range", 10: "HP", 11: "LOS",
    12: "max_range", 13: "work_rate", 14: "carry_cap", 19: "accuracy",
    21: "attack_delay", 100: "attack", 101: "reload_time",
    102: "accuracy_pct", 103: "frame_delay", 109: "resource_gen",
}
RESOURCE_NAMES = {0: "food", 1: "wood", 2: "stone", 3: "gold"}
BUILDING_NAMES = {
    45: "Dock", 82: "Castle", 12: "Barracks", 101: "Stable",
    103: "Archery Range", 49: "Siege Workshop", 209: "University",
    84: "Market", 63: "Town Center", 251: "Krepost", 1251: "Krepost",
    104: "Monastery", 68: "Mill",
}

_BONUS_NAMES: dict[str, str] = {}
_bn_path = Path(__file__).parent / "bonus_names.json"
if _bn_path.exists():
    _BONUS_NAMES = json.loads(_bn_path.read_text(encoding="utf-8"))

_TEAM_BONUS_NAMES: dict[str, str] = {}
_tbn_path = Path(__file__).parent / "team_bonus_names.json"
if _tbn_path.exists():
    _TEAM_BONUS_NAMES = json.loads(_tbn_path.read_text(encoding="utf-8"))


# ── EC formatting ─────────────────────────────────────────────────────────────

def _attr(c: int) -> str:
    return ATTR_NAMES.get(c, f"attr{c}")

def _res(a: int) -> str:
    return RESOURCE_NAMES.get(a, f"res{a}")

def _bldg(loc: int) -> str:
    return BUILDING_NAMES.get(loc, f"unit{loc}")

def describe_ec(ec) -> str:
    t = ec.type
    a, b, c, d = int(ec.a), int(ec.b), int(ec.c), ec.d

    if t == EC_SET:
        return f"SET  unit {a}  {_attr(c)} = {d}"
    if t == EC_RESOURCE:
        mode = {0: "set", 1: "add", -1: "trickle"}.get(b, f"mode{b}")
        return f"RESOURCE  {_res(a)} {mode} {d}"
    if t == EC_ENABLE:
        return f"ENABLE  unit {a}  {'show' if b == 1 else 'hide'}"
    if t == EC_UPGRADE:
        return f"UPGRADE  unit {a} → unit {b}"
    if t == EC_ADD:
        if c == 8:  # packed: d = (armor_class_id << 8) | amount
            di = int(d)
            cls, amt = di >> 8, di & 0xFF
            tgt = f"class {b}" if a == -1 else f"unit {a}"
            return f"ADD  armor class {cls}  +{amt}  to {tgt}"
        unit = "all" if a == -1 else f"unit {a}"
        filt = f" [class {b}]" if a == -1 and b != -1 else ""
        return f"ADD  {unit}{filt}  {_attr(c)} +{d}"
    if t == EC_MULTIPLY:
        unit = "all" if a == -1 else f"unit {a}"
        filt = f" [class {b}]" if a == -1 and b != -1 else ""
        return f"MULT {unit}{filt}  {_attr(c)} ×{d}"
    if t == EC_TECH_COST:
        return f"TECH_COST  tech {a}  {_res(b)} {'set' if c == 0 else 'add'} {d}"
    if t == EC_TECH_TIME:
        return f"TECH_TIME  tech {a}  = {d}s"
    if t == 7:
        return f"ENABLE_TEAM  unit {a}"
    if t == 8:
        return f"UNLOCK_TECH  (copied from vanilla)"
    if t == 12:
        return f"TEAM_TRAIN  unit {a}  at {_bldg(b)}"
    if t == 102:
        return f"DISABLE_TECH  tech {int(d)}"
    return f"type={t} a={a} b={b} c={c} d={d}"


# ── Tech inspection helpers ───────────────────────────────────────────────────

def _tech_loc_str(dat: DatFile, tech_id: int) -> str:
    if not (0 <= tech_id < len(dat.techs)):
        return "INVALID"
    t = dat.techs[tech_id]
    if not t.research_locations:
        return "no-locations"
    loc = t.research_locations[0]
    if loc.location_id < 0 and loc.research_time == 0:
        return "auto-fire"
    if loc.location_id < 0:
        return f"NO-BUTTON(time={loc.research_time}s)"
    bldg = _bldg(loc.location_id)
    btn  = f" btn{loc.button_id}" if loc.button_id > 0 else ""
    time = f" {loc.research_time}s" if loc.research_time > 0 else " instant"
    return f"{bldg}{btn}{time}"

def _req_techs(dat: DatFile, tech_id: int) -> list[int]:
    if not (0 <= tech_id < len(dat.techs)):
        return []
    return [r for r in (dat.techs[tech_id].required_techs or []) if r >= 0]

def _effect_cmds(dat: DatFile, tech_id: int) -> list:
    if not (0 <= tech_id < len(dat.techs)):
        return []
    eid = dat.techs[tech_id].effect_id
    if not (0 <= eid < len(dat.effects)):
        return []
    return list(dat.effects[eid].effect_commands)

def _is_invisible_button(dat: DatFile, tech_id: int) -> bool:
    if not (0 <= tech_id < len(dat.techs)):
        return False
    locs = dat.techs[tech_id].research_locations
    return bool(locs and locs[0].location_id == -1 and locs[0].research_time > 0)

def _bonus_label(bonus_id: int, multiplier: int = 1) -> str:
    name = _BONUS_NAMES.get(str(bonus_id), "")
    mult = f" ×{multiplier}" if multiplier != 1 else ""
    desc = f"  ({name})" if name else ""
    return f"[{bonus_id}]{mult}{desc}"

def _team_bonus_label(bonus_id: int, multiplier: int = 1) -> str:
    name = _TEAM_BONUS_NAMES.get(str(bonus_id), "")
    mult = f" ×{multiplier}" if multiplier != 1 else ""
    desc = f"  ({name})" if name else ""
    return f"[{bonus_id}]{mult}{desc}"

def _ut_label(bonus_id: int, multiplier: int, castle: bool) -> str:
    """Label for a UT entry using the UT-specific name from build_all tables."""
    table = _UNIQUE_CASTLE_STRINGS if castle else _UNIQUE_IMP_STRINGS
    ut_name = table[bonus_id] if 0 <= bonus_id < len(table) else ""
    mult = f" ×{multiplier}" if multiplier != 1 else ""
    desc = f"  ({ut_name})" if ut_name else ""
    return f"[{bonus_id}]{mult}{desc}"


# ── Report helpers ────────────────────────────────────────────────────────────

W = 70

def _section(title: str) -> None:
    print(f"\n  ── {title}")

def _warn(msg: str, warnings: list[str]) -> None:
    if msg not in warnings:
        warnings.append(msg)

def _report_tech(dat: DatFile, tech_id: int, label: str,
                 warnings: list[str], verbose: bool = False) -> None:
    if tech_id < 0:
        return
    if tech_id >= len(dat.techs):
        print(f"    {label}: tech {tech_id} → OUT OF RANGE")
        _warn(f"{label}: tech ID {tech_id} is out of range", warnings)
        return

    loc    = _tech_loc_str(dat, tech_id)
    reqs   = _req_techs(dat, tech_id)
    cmds   = _effect_cmds(dat, tech_id)
    req_s  = f"  req:{reqs}" if reqs else ""
    ok     = "✓" if cmds and not _is_invisible_button(dat, tech_id) else "⚠"
    print(f"    {ok} {label}: tech {tech_id}  {loc}{req_s}  → {len(cmds)} cmds")

    if _is_invisible_button(dat, tech_id):
        _warn(f"{label} (tech {tech_id}): location=-1 with time>0 — no research button shown", warnings)
    if len(cmds) == 0:
        _warn(f"{label} (tech {tech_id}): effect has 0 commands — fires but does nothing", warnings)
    if len(cmds) > MAX_EFFECT_COMMANDS:
        _warn(f"{label} (tech {tech_id}): {len(cmds)} commands exceeds engine limit {MAX_EFFECT_COMMANDS}"
              f" → engine crash risk", warnings)

    if verbose:
        for ec in cmds:
            print(f"        {describe_ec(ec)}")


# ── Main diagnostic ───────────────────────────────────────────────────────────

def diagnose_one(dat: DatFile, civ_def: dict,
                 replace_name: str | None,
                 vanilla_name_to_slot: dict[str, int]) -> None:
    """Apply civ_def to dat (in-place) and print the diagnostic report."""
    target_slot: int | None = None
    if replace_name:
        target_slot = vanilla_name_to_slot.get(replace_name)
        if target_slot is None:
            print(f"\n  WARNING: '{replace_name}' not found in DAT — appending instead")

    tech_before = len(dat.techs)
    eff_before  = len(dat.effects)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            result = apply_civ(dat, civ_def, target_slot=target_slot)
        except Exception as exc:
            print(f"\n  FATAL: apply_civ() raised {type(exc).__name__}: {exc}")
            return

    alias     = result["alias"]
    civ_index = result["civ_index"]
    b_res     = result.get("bonus_results") or {}
    skipped   = b_res.get("skipped", [])
    btmap     = result.get("bonus_tech_map", {})
    warnings: list[str] = list(result.get("warnings", []))

    slot_desc = f"replacing slot {target_slot} ({replace_name})" if replace_name else f"slot {civ_index}"
    print(f"\n{'━' * W}")
    print(f"  [{civ_index}] {alias}  ({slot_desc})")
    print(f"  {'━' * W}")
    print(f"  Added: {len(dat.techs) - tech_before} techs, "
          f"{len(dat.effects) - eff_before} effects")

    raw = civ_def.get("bonuses", [])

    # ── KM Unique Unit ────────────────────────────────────────────────────────
    uu_ref      = raw[1] if len(raw) > 1 and isinstance(raw[1], list) else []
    km_uu_index = uu_ref[0] if uu_ref and isinstance(uu_ref[0], int) else None
    make_id     = result.get("km_uu_make_avail_tech_id", -1)
    elite_id    = result.get("km_uu_elite_tech_id", -1)

    _section("KM UNIQUE UNIT")
    if km_uu_index is None:
        print("    (none)")
    else:
        pair = _KM_UU_TECHS.get(km_uu_index)
        src  = f"vanilla ({pair[0]}/{pair[1]})" if pair else "custom preset"
        print(f"    Index {km_uu_index}  source: {src}")
        _report_tech(dat, make_id,  "make-avail", warnings)
        _report_tech(dat, elite_id, "elite-upgrade", warnings, verbose=True)

    # ── Castle UT ─────────────────────────────────────────────────────────────
    castle_entries = raw[2] if len(raw) > 2 and isinstance(raw[2], list) else []
    c_tech  = result.get("castle_ut_tech_id")
    c_name  = result["castle_ut_sid"]
    c_desc  = result["castle_ut_desc_sid"]
    c_help  = result["castle_ut_help_sid"]

    _section("CASTLE UT")
    if not castle_entries:
        print("    (none)")
    else:
        for e in castle_entries:
            bid  = int(e[0]) if isinstance(e, (list, tuple)) and e else "?"
            mult = int(e[1]) if isinstance(e, (list, tuple)) and len(e) > 1 else 1
            print(f"    Source: {_ut_label(bid, mult, castle=True)}")
        if c_tech is None:
            _warn("Castle UT: no tech created (entries missing from UT catalog?)", warnings)
            print("    ⚠  No tech created")
        else:
            _report_tech(dat, c_tech, "Castle UT tech", warnings, verbose=True)
            print(f"    Strings: name={c_name}  desc={c_desc}  "
                  f"hover={c_name + 21000}  help={c_help}")

    # ── Imperial UT ───────────────────────────────────────────────────────────
    imp_entries = raw[3] if len(raw) > 3 and isinstance(raw[3], list) else []
    i_tech = result.get("imp_ut_tech_id")
    i_name = result["imp_ut_sid"]
    i_desc = result["imp_ut_desc_sid"]
    i_help = result["imp_ut_help_sid"]

    _section("IMPERIAL UT")
    if not imp_entries:
        print("    (none)")
    else:
        for e in imp_entries:
            bid  = int(e[0]) if isinstance(e, (list, tuple)) and e else "?"
            mult = int(e[1]) if isinstance(e, (list, tuple)) and len(e) > 1 else 1
            print(f"    Source: {_ut_label(bid, mult, castle=False)}")
        if i_tech is None:
            _warn("Imperial UT: no tech created (entries missing from UT catalog?)", warnings)
            print("    ⚠  No tech created")
        else:
            _report_tech(dat, i_tech, "Imperial UT tech", warnings, verbose=True)
            print(f"    Strings: name={i_name}  desc={i_desc}  "
                  f"hover={i_name + 21000}  help={i_help}")

    # ── Civ bonuses ───────────────────────────────────────────────────────────
    _section("CIV BONUSES  (bonuses[0])")
    civ_bonus_list = raw[0] if len(raw) > 0 and isinstance(raw[0], list) else []
    if not civ_bonus_list:
        print("    (none)")

    for entry in civ_bonus_list:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        bid  = int(entry[0])
        mult = int(entry[1]) if len(entry) > 1 else 1
        label = _bonus_label(bid, mult)

        if bid in skipped:
            print(f"    ✗  {label}  → NOT IN CATALOG")
            continue

        vanilla_tids = civ_bonus_techs(bid)
        ec_list_flag = bool(civ_bonus_ec_list(bid))

        if vanilla_tids:
            new_tids = [btmap[v] for v in vanilla_tids if v in btmap]
            if not new_tids:
                # Global tech (civ=-1) with multiplier=1: shared, no civ copy allocated
                print(f"    ✓  {label}  → global tech(s) {vanilla_tids} (shared, no civ copy)")
            else:
                for ntid in new_tids:
                    _report_tech(dat, ntid, label, warnings)
        elif ec_list_flag:
            print(f"    ✓  {label}  → EC-list handler (no single tech ID)")
        else:
            print(f"    ✓  {label}  → custom handler")

    # ── Team bonus ────────────────────────────────────────────────────────────
    _section("TEAM BONUS  (bonuses[4])")
    team_list = raw[4] if len(raw) > 4 and isinstance(raw[4], list) else []
    if not team_list:
        print("    (none)")
    else:
        for entry in team_list:
            if not isinstance(entry, (list, tuple)) or not entry:
                continue
            tid  = int(entry[0])
            mult = int(entry[1]) if len(entry) > 1 else 1
            print(f"    {_team_bonus_label(tid, mult)}")
        applied = b_res.get("team_applied", 0)
        total   = b_res.get("team_total", len(team_list))
        ok = "✓" if applied == total else "⚠"
        print(f"    {ok}  {applied}/{total} entries applied")
        if applied < total:
            _warn(f"Team bonus: only {applied}/{total} entries applied", warnings)

    # ── Warnings ─────────────────────────────────────────────────────────────
    print()
    if warnings or skipped:
        print(f"  {'━' * W}")
        print(f"  WARNINGS")
        print(f"  {'━' * W}")
        for bid in skipped:
            print(f"  ⚠  Bonus [{bid}] not in any catalog — skipped")
        for w in warnings:
            print(f"  ⚠  {w}")
    else:
        print(f"  ✓  No warnings detected")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Diagnose AoE2 civ builder JSON files without producing a mod ZIP.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("target", nargs="?",
                    help="Path to a civ .json file")
    ap.add_argument("--all", dest="all_config", metavar="CONFIG",
                    help="Process all civs in a mod config .json")
    ap.add_argument("--replace", metavar="VANILLA_CIV_NAME",
                    help="Vanilla civ name to overwrite (e.g. 'Portuguese')")
    ap.add_argument("--dat", default=str(DEFAULT_DAT),
                    help=f"Vanilla DAT path (default: {DEFAULT_DAT.name})")
    args = ap.parse_args()

    if not args.target and not args.all_config:
        ap.print_help()
        sys.exit(1)

    dat_path = Path(args.dat)
    if not dat_path.exists():
        print(f"ERROR: DAT not found: {dat_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading DAT: {dat_path}")
    dat = DatFile.parse(str(dat_path))
    vanilla_name_to_slot = {c.name: i for i, c in enumerate(dat.civs)}
    print(f"  {len(dat.civs)} civs, {len(dat.techs)} techs, {len(dat.effects)} effects\n")

    if args.all_config:
        cfg_path = Path(args.all_config)
        if not cfg_path.exists():
            print(f"ERROR: config not found: {cfg_path}", file=sys.stderr)
            sys.exit(1)
        config  = json.loads(cfg_path.read_text(encoding="utf-8"))
        entries = config.get("civs", [])
        print(f"Config: '{config.get('mod_name', '?')}' — {len(entries)} civs")
        for entry in entries:
            json_path = cfg_path.parent / entry["json"]
            if not json_path.exists():
                print(f"\n  ERROR: {json_path} not found — skipping")
                continue
            civ_def = json.loads(json_path.read_text(encoding="utf-8"))
            diagnose_one(dat, civ_def, entry.get("replace"), vanilla_name_to_slot)
    else:
        civ_path = Path(args.target)
        if not civ_path.exists():
            print(f"ERROR: {civ_path} not found", file=sys.stderr)
            sys.exit(1)
        civ_def = json.loads(civ_path.read_text(encoding="utf-8"))
        diagnose_one(dat, civ_def, args.replace, vanilla_name_to_slot)


if __name__ == "__main__":
    main()
