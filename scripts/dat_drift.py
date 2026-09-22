#!/usr/bin/env python3
"""What moved between two versions of the game DAT, and what of ours it breaks.

    venv/bin/python scripts/dat_drift.py OLD.dat NEW.dat [--verbose]

Every DLC is the same story: the game grows, our hardcoded ids stop meaning what
they meant, and nothing errors — the mod just quietly does the wrong thing.
That is what killed KrakenMeister's builder (new unit ids landed in the slot
range it used for custom unique units, so civs started spawning Gaia units
instead of berries), and it is what the 2026-09 catalog sweep kept finding in
smaller doses: *"DE changed the game under the catalog."*

A plain diff of two DATs is useless — thousands of values move every patch. This
reports only what **we** point at:

  1. Structure — civs, techs, effects added or removed.
  2. **Techs whose effect changed, cross-referenced to the bonus cards that use
     them.** A card whose tech now does something else is the exact failure the
     catalog sweep chased by hand for a month.
  3. New `civ=-1` opt-in techs — CLAUDE.md quirk 10. A make-avail tech that is
     referenced by a type=8 and disabled by nobody leaks its unit to the AI, so
     each new one needs to reach `_lock_unclaimed_optin_techs`.
  4. String-pool safety — `CAMPAIGN_STRING_POOL` assumes those ids are empty in
     vanilla. If a DLC starts using one, custom unit and tech names collide with
     real game text (CLAUDE.md quirk 8).
  5. Unit ids the catalog names that changed identity, or vanished.

Read it as a worklist, not a verdict: a changed effect might be a balance tweak
our card already describes correctly, and only the game can settle that.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import load_dat                                   # noqa: E402
import civ_appender as ca                                         # noqa: E402


def _cmd_tuple(c):
    return (c.type, int(c.a), int(c.b), int(c.c), round(float(c.d), 4))


def _effect_fingerprint(dat, eff_id):
    if not (0 <= eff_id < len(dat.effects)):
        return None
    return tuple(_cmd_tuple(c) for c in dat.effects[eff_id].effect_commands)


def _tech_fingerprint(dat, tid):
    t = dat.techs[tid]
    return (t.civ, t.effect_id, tuple(t.required_techs), t.required_tech_count)


def _catalog_tech_users() -> dict[int, list[str]]:
    """tech id -> the things of ours that depend on it."""
    users: dict[int, list[str]] = defaultdict(list)
    cat = json.loads((ROOT / "bonus_catalog_raw.json").read_text())
    names = json.loads((ROOT / "bonus_names.json").read_text())
    for bid, tids in cat.get("civ", {}).items():
        for t in (tids or []):
            users[int(t)].append(f"civ bonus {bid} ({names.get(bid, '?')[:44]})")
    for km_idx, pair in ca._KM_UU_TECHS.items():
        for t in pair:
            users[int(t)].append(f"unique unit {km_idx} ({ca._KM_UU_NAMES.get(km_idx, '?')})")
    for km_idx, t in ca._KM_CASTLE_UT_TECHS.items():
        users[int(t)].append(f"castle UT preset {km_idx}")
    for km_idx, t in ca._KM_IMP_UT_TECHS.items():
        users[int(t)].append(f"imperial UT preset {km_idx}")
    for bid, spec in ca._UNLOCK_UNIT_BONUSES.items():
        for t in spec["techs"]:
            users[int(t)].append(f"unlock card {bid} ({spec['name']})")
    return users


def _catalog_unit_ids() -> dict[int, list[str]]:
    units: dict[int, list[str]] = defaultdict(list)
    cat = json.loads((ROOT / "bonus_catalog_raw.json").read_text())
    tnames = json.loads((ROOT / "team_bonus_names.json").read_text())
    for bid, entries in cat.get("team_ec_list", {}).items():
        for e in entries:
            if int(e.get("A", -1)) >= 0:
                units[int(e["A"])].append(f"team bonus {bid} ({tnames.get(bid, '?')[:40]})")
    for bid, spec in ca._UNLOCK_UNIT_BONUSES.items():
        for u in spec["units"]:
            units[int(u)].append(f"unlock card {bid} ({spec['name']})")
    return units


def _unit_name(dat, uid):
    for c in dat.civs:
        try:
            u = c.units[uid]
        except (IndexError, TypeError):
            continue
        if u is not None and getattr(u, "name", None):
            return u.name
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old"); ap.add_argument("new")
    ap.add_argument("--verbose", action="store_true",
                    help="list every changed tech, not just ones we depend on")
    args = ap.parse_args()

    print(f"old: {args.old}\nnew: {args.new}\n")
    old, new = load_dat(args.old), load_dat(args.new)

    # ── 1. Structure ─────────────────────────────────────────────────────────
    print("═══ Structure ═══")
    for label, o, n in (("civs", old.civs, new.civs),
                        ("techs", old.techs, new.techs),
                        ("effects", old.effects, new.effects)):
        delta = len(n) - len(o)
        print(f"  {label:<9} {len(o):>5} → {len(n):<5} {f'({delta:+d})' if delta else ''}")
    added_civs = [c.name for c in new.civs[len(old.civs):]]
    if added_civs:
        print(f"\n  new civs: {added_civs}")
        print("  → add these to build_civ.KM_TECHTREE_ORDER, or their civ-picker")
        print("    name strings (10271 + index) land on the wrong slot.")
        print("  → refresh the bundled civilizations.json: the game validates its")
        print("    entry count against the DAT civ count.")

    # ── 2. Techs we depend on whose effect changed ──────────────────────────
    print("\n═══ Techs we depend on ═══")
    users = _catalog_tech_users()
    shared = min(len(old.techs), len(new.techs))
    hits = []
    for tid in sorted(users):
        if tid >= shared:
            hits.append((tid, "no longer exists in the new DAT", users[tid]))
            continue
        if _tech_fingerprint(old, tid) != _tech_fingerprint(new, tid):
            hits.append((tid, "tech definition changed (civ / effect_id / prereqs)", users[tid]))
            continue
        eo, en = _effect_fingerprint(old, old.techs[tid].effect_id), \
                 _effect_fingerprint(new, new.techs[tid].effect_id)
        if eo != en:
            n_o = len(eo) if eo else 0
            n_n = len(en) if en else 0
            what = (f"effect commands {n_o} → {n_n}" if n_o != n_n
                    else f"effect values changed ({n_n} commands)")
            hits.append((tid, what, users[tid]))
    if not hits:
        print("  nothing we reference moved.")
    for tid, what, who in hits:
        print(f"\n  tech {tid} — {what}")
        print(f"    name: {new.techs[tid].name!r}" if tid < shared else "")
        for w in who[:6]:
            print(f"      used by {w}")
        if len(who) > 6:
            print(f"      …and {len(who)-6} more")

    # ── 3. New opt-in techs (quirk 10) ──────────────────────────────────────
    print("\n═══ New opt-in techs (AI leak risk — quirk 10) ═══")
    ec8 = set()
    for civ in new.civs:
        tt = getattr(civ, "tech_tree_id", None)
        if tt is not None and 0 <= tt < len(new.effects):
            for c in new.effects[tt].effect_commands:
                if c.type == 8:
                    ec8.add(int(c.a))
    new_optin = [t for t in range(shared, len(new.techs))
                 if t in ec8 and new.techs[t].civ == -1]
    if not new_optin:
        print("  none.")
    for t in new_optin:
        print(f"  tech {t} {new.techs[t].name!r} — civ=-1 and type=8 unlocked by some civ.")
    if new_optin:
        print("  → _lock_unclaimed_optin_techs keys on these properties, so it should")
        print("    pick them up automatically; confirm with a build log line count.")

    # ── 4. String pool safety (quirk 8) ─────────────────────────────────────
    print("\n═══ String pool ═══")
    pool = set(ca.CAMPAIGN_STRING_POOL)
    used = set()
    for c in new.civs:
        for u in (c.units or []):
            if u is None:
                continue
            for attr in ("language_dll_name", "language_dll_creation", "language_dll_help"):
                v = getattr(u, attr, None)
                if v in pool:
                    used.add(v)
    for t in new.techs:
        for attr in ("language_dll_name", "language_dll_description", "language_dll_help"):
            v = getattr(t, attr, None)
            if v in pool:
                used.add(v)
    if used:
        print(f"  ⚠ {len(used)} pool ids are now used by the game: {sorted(used)[:12]}")
        print("  → these must be removed from CAMPAIGN_STRING_POOL or custom names")
        print("    will collide with real game text (this is what broke KM's builder).")
    else:
        print(f"  all {len(pool)} pool ids still unused by the game.")

    # ── 5. Units the catalog names ──────────────────────────────────────────
    print("\n═══ Units the catalog names ═══")
    unit_users = _catalog_unit_ids()
    moved = []
    for uid in sorted(unit_users):
        o_name, n_name = _unit_name(old, uid), _unit_name(new, uid)
        if o_name != n_name:
            moved.append((uid, o_name, n_name, unit_users[uid]))
    if not moved:
        print("  every unit we name still resolves to the same unit.")
    for uid, o_name, n_name, who in moved:
        print(f"  unit {uid}: {o_name!r} → {n_name!r}")
        for w in who[:4]:
            print(f"      used by {w}")

    print("\nDone. Treat changed effects as a worklist — a balance tweak our card")
    print("already describes correctly looks identical here to one that broke it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
