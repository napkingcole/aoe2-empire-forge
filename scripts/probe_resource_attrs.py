"""
probe_resource_attrs.py — Inventory the player-resource attribute surface.

EC_RESOURCE (type 1) and its multiplicative twin (type 6) address ~284 named
player attributes, but our bonus catalog only ever touches ten of them.  The
rest are how vanilla civs implement most of their signature mechanics
(Feitoria trickles, gather productivity, relic rates, kill rewards, auras).

Before building bonuses on any of them we need to know two things per id:

  1. Does the engine actually read it?  An id defined in the constant table but
     referenced by no vanilla effect is dead weight — the name exists, the
     behaviour may not.  Every id used by a shipping vanilla tech is attested.

  2. Does it need `repeatable = 1`?  Rate/trickle writes (b = -1) only sustain
     if the parent tech is repeatable.  This is the bug that made Vineyards
     look civ-locked for months (see llm/resource_ids.md) — it was never an
     engine restriction, just a missing flag.

Civ-slot portability is NOT statically decidable: `tech.civ` tells you which
civ vanilla ships the effect on, not whether the attribute refuses to fire
elsewhere.  Testing settled that question for 236/266 (they travel).  This
report ranks the remaining candidates so an in-game probe can start with the
attributes most likely to pay off.

Usage:
    venv/bin/python scripts/probe_resource_attrs.py            # summary
    venv/bin/python scripts/probe_resource_attrs.py --all      # every id
    venv/bin/python scripts/probe_resource_attrs.py --json out.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dat_reader import find_game_dat, load_dat  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent

# EC_RESOURCE (1) and EC_RESOURCE_MULTIPLY (6), plus their scoped variants.
# Scoped forms add +10 TEAM / +20 ENEMY / +30 NEUTRAL / +40 GAIA.
RESOURCE_EC_TYPES = frozenset(
    {base + off for base in (1, 6) for off in (0, 10, 20, 30, 40)}
)

# b parameter on EC_RESOURCE.
MODE_NAMES = {0: "set", 1: "add", -1: "trickle"}

# Resource ids our own hand-authored bonus ECs already write to.
# Anything outside this set is reachable today only by copying a vanilla
# civ's tech wholesale, which drags along whatever else that tech does.
def _catalog_used_ids() -> set[int]:
    raw = json.loads((_ROOT / "bonus_catalog_raw.json").read_text())
    used: set[int] = set()
    for groups in raw["ec_list"].values():
        for group in groups:
            for ec in group["ecs"]:
                if ec["type"] in RESOURCE_EC_TYPES:
                    used.add(ec["A"])
    for ecs in raw.get("team_ec_list", {}).values():
        for ec in ecs:
            if ec["type"] in RESOURCE_EC_TYPES:
                used.add(ec["A"])
    return used


def _attr_names() -> dict[int, str]:
    p = _ROOT / "llm" / "resource_attrs.json"
    if not p.exists():
        return {}
    return {int(k): v for k, v in json.loads(p.read_text()).items()}


# Ids whose cross-civ portability has been settled by in-game testing, so the
# static verdict below should not send anyone back to re-test them.
# See llm/resource_ids.md for the Vineyards/Paper Money write-up.
VERIFIED_PORTABLE = {236, 266}


class Usage:
    """Everything we learned about one resource attribute id."""

    __slots__ = ("rid", "name", "refs", "effects", "modes", "civs",
                 "repeatable", "in_catalog")

    def __init__(self, rid: int, name: str):
        self.rid = rid
        self.name = name
        self.refs: list[tuple[int, str]] = []   # (tech_id, tech_name)
        self.effects: set[int] = set()          # effect ids that write this id
        self.modes: set[str] = set()
        self.civs: set[int] = set()
        self.repeatable: set[int] = set()
        self.in_catalog = False

    @property
    def written_by_vanilla(self) -> bool:
        """Some shipping effect writes this id, tech-owned or not."""
        return bool(self.effects)

    @property
    def tech_owned(self) -> bool:
        """A researchable/auto-fire tech owns an effect that writes this id.

        Effects with no owning tech are still live — civ tech-tree effects and
        unique-tech stubs reach them by other routes — but we cannot read a
        civ gate off them, so they get their own bucket.
        """
        return bool(self.refs)

    @property
    def needs_repeatable(self) -> bool:
        return "trickle" in self.modes

    @property
    def civ_locked_in_vanilla(self) -> bool:
        """Vanilla only ever writes it from civ-gated techs.

        Not proof it refuses to travel — 236/266 look exactly like this and
        work fine for any civ.  It only means we have no vanilla example of
        the attribute firing for an arbitrary civ, so it needs a live test.
        """
        return bool(self.civs) and -1 not in self.civs

    def verdict(self) -> str:
        if self.in_catalog:
            return "IN USE"
        if self.rid in VERIFIED_PORTABLE:
            return "READY"
        if not self.written_by_vanilla:
            return "UNREFERENCED"
        if not self.tech_owned:
            return "ORPHAN"
        if self.civ_locked_in_vanilla:
            return "PROBE"
        return "READY"


def collect(dat) -> dict[int, Usage]:
    names = _attr_names()
    in_catalog = _catalog_used_ids()
    out: dict[int, Usage] = {}

    def get(rid: int) -> Usage:
        if rid not in out:
            out[rid] = Usage(rid, names.get(rid, f"<unnamed {rid}>"))
            out[rid].in_catalog = rid in in_catalog
        return out[rid]

    # Effects are shared; walk techs so we can attribute civ + repeatable.
    effect_to_techs: dict[int, list] = collections.defaultdict(list)
    for tid, tech in enumerate(dat.techs):
        if tech.effect_id is not None and tech.effect_id >= 0:
            effect_to_techs[tech.effect_id].append((tid, tech))

    for eid, effect in enumerate(dat.effects):
        cmds = [c for c in effect.effect_commands if c.type in RESOURCE_EC_TYPES]
        if not cmds:
            continue
        owners = effect_to_techs.get(eid, [])
        for c in cmds:
            u = get(c.a)
            u.effects.add(eid)
            u.modes.add(MODE_NAMES.get(c.b, f"b={c.b}"))
            for tid, tech in owners:
                u.refs.append((tid, tech.name))
                u.civs.add(tech.civ)
                u.repeatable.add(getattr(tech, "repeatable", 0))

    # Ids we use that vanilla never touches still deserve a row.
    for rid in in_catalog:
        get(rid)
    return out


# Attributes whose names promise a mechanic we have no bonus for yet.
_INTEREST = (
    "Productivity", "Trickle", "Generation", "Reward", "Conversion", "Relic",
    "Repair", "Elevation", "SpeedUp", "Speed Up", "Trade", "Farming", "Hunting",
    "Foraging", "Chopping", "Livestock", "Spawn", "Feudal", "Fishing",
    "Folwark", "Heal", "Herding", "Shepherding", "Monument", "Feitoria",
    "Workshop", "Militia",
)


def _interesting(u: Usage) -> bool:
    return any(w in u.name for w in _INTEREST)


def report(usages: dict[int, Usage], show_all: bool) -> None:
    rows = sorted(usages.values(), key=lambda u: u.rid)
    buckets: dict[str, list[Usage]] = collections.defaultdict(list)
    for u in rows:
        buckets[u.verdict()].append(u)

    print(f"{len(rows)} resource attribute ids referenced or catalogued\n")
    order = ["READY", "PROBE", "ORPHAN", "IN USE", "UNREFERENCED"]
    blurb = {
        "READY":        "vanilla writes these from a civ-agnostic tech — safe to build on now",
        "PROBE":        "vanilla only writes these from a civ-gated tech — needs one in-game test each",
        "ORPHAN":       "written by an effect no tech owns — live, but no civ gate to read; test before use",
        "IN USE":       "our catalog already writes these",
        "UNREFERENCED": "named in the constant table but nothing in the DAT writes them — assume inert",
    }
    for verdict in order:
        group = buckets.get(verdict, [])
        if not group:
            continue
        shown = group if show_all else [u for u in group if _interesting(u) or u.in_catalog]
        print(f"── {verdict}  ({len(group)} ids) — {blurb[verdict]}")
        if not shown:
            print("     (none matching the interest filter; pass --all to see them)\n")
            continue
        for u in shown:
            flags = []
            if u.rid in VERIFIED_PORTABLE:
                flags.append("portability confirmed in-game")
            if u.in_catalog and not u.written_by_vanilla:
                flags.append("WE WRITE THIS BUT VANILLA NEVER DOES — verify it fires")
            if u.needs_repeatable:
                flags.append("needs repeatable=1")
            if u.civs and u.civs != {-1}:
                civ_list = sorted(c for c in u.civs if c != -1)
                flags.append("vanilla civ " + ",".join(map(str, civ_list)))
            modes = "/".join(sorted(u.modes)) or "—"
            tail = ("  [" + "; ".join(flags) + "]") if flags else ""
            print(f"   {u.rid:4d}  {u.name:<38} {modes:<16}{tail}")
            if u.refs:
                tid, tname = u.refs[0]
                extra = f" (+{len(u.refs) - 1} more)" if len(u.refs) > 1 else ""
                print(f"         e.g. tech {tid} {tname!r}{extra}")
        if not show_all and len(shown) < len(group):
            print(f"     … {len(group) - len(shown)} more (--all)")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dat", help="path to empires2_x2_p1.dat (default: auto-detect)")
    ap.add_argument("--all", action="store_true", help="show every id, not just gameplay-interesting ones")
    ap.add_argument("--json", metavar="PATH", help="also write the raw findings as JSON")
    args = ap.parse_args()

    path = Path(args.dat) if args.dat else find_game_dat()
    if not path:
        print("Could not locate the game DAT. Pass --dat.", file=sys.stderr)
        return 1
    print(f"DAT: {path}\n")
    usages = collect(load_dat(path))
    report(usages, args.all)

    if args.json:
        payload = {
            str(u.rid): {
                "name": u.name,
                "verdict": u.verdict(),
                "modes": sorted(u.modes),
                "needs_repeatable": u.needs_repeatable,
                "vanilla_civs": sorted(u.civs),
                "in_catalog": u.in_catalog,
                "refs": u.refs[:20],
            }
            for u in sorted(usages.values(), key=lambda u: u.rid)
        }
        Path(args.json).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
