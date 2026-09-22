#!/usr/bin/env python3
"""Every "Unlock <unit>" card must actually make its unit reachable.  DAT-gated.

These cards exist because of CLAUDE.md quirk 9: the units are `civ`-gated in the
DAT, so they look enabled in the tech tree and cannot be trained until their
make-avail tech is copied for our civ.  The card *is* the only path.

Which makes a missing card silent in a very specific way — the unit does not
error, it just never appears, and nobody notices until a player goes looking.
That is exactly what happened to the **Flemish Militia**: bonus 108 ("Farm
upgrades +125% food") used to map techs 773/774 alongside its own 772, so every
civ taking a farm bonus silently gained the unit.  Trimming 108 to {772} on
2026-09-10 was correct — 773/774 had no business in a farm bonus — but it
removed the only way to reach the unit, and unit 1699 is not a node in
`FULL.json` either.  Reported by a user 2026-09-20; card 428 added.

So this checks the whole class rather than that one card: build one civ carrying
every unlock bonus and assert each one allocated a civ-owned tech that enables
its units.  One build, not fourteen — `load_dat` is ~16s.

    venv/bin/python tests/test_unlock_unit_bonuses.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat                  # noqa: E402
from civ_appender import apply_civ, _UNLOCK_UNIT_BONUSES        # noqa: E402
import bonus_names                                              # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


# ── Every unlock bonus is offered in the picker ──────────────────────────────
# An implemented bonus with no name is unreachable: the catalog API builds its
# list from bonus_names.json.  That is how 35 working bonuses sat invisible
# until 2026-09-17.
import json                                                     # noqa: E402

names = json.loads((ROOT / "bonus_names.json").read_text())
cards = json.loads((ROOT / "static/data/bonus_cards.json").read_text())
unsupported = {b["id"] for b in bonus_names.unsupported_bonuses()}

for bid, spec in sorted(_UNLOCK_UNIT_BONUSES.items()):
    label = f"bonus {bid} ({spec['name']})"
    check(f"{label} has a name in bonus_names.json", str(bid) in names)
    check(f"{label} has a card in bonus_cards.json", str(bid) in cards)
    check(f"{label} is not reported unsupported", bid not in unsupported)

# ── Every unlock bonus actually enables its units ────────────────────────────
dat_path = find_game_dat()
if dat_path is None:
    print("\n  skip  build checks — no game DAT found")
    print()
    print("FAIL" if failures else "PASS", f"({failures} failure(s))")
    sys.exit(1 if failures else 0)

SLOT = 5
dat = load_dat(str(dat_path))
civ_def = {
    "alias": "Unlock Probe", "description": "", "architecture": 2, "language": 0,
    "wonder": -1, "castle": -1,
    "bonuses": [[[bid, 1] for bid in sorted(_UNLOCK_UNIT_BONUSES)], [], [], [], []],
    "tree": [[], [], []],
}
with contextlib.redirect_stdout(io.StringIO()) as buf:
    apply_civ(dat, civ_def, target_slot=SLOT)
log = buf.getvalue()

# Which unit ids does a tech owned by THIS civ switch on?
enabled_by_our_civ: set[int] = set()
for tech in dat.techs:
    if tech.civ != SLOT or not (0 <= tech.effect_id < len(dat.effects)):
        continue
    for cmd in dat.effects[tech.effect_id].effect_commands:
        if cmd.type == 2 and int(cmd.b) == 1:          # EC_ENABLE, show
            enabled_by_our_civ.add(int(cmd.a))
        elif cmd.type == 3:                            # EC_UPGRADE (Legionary, Savar)
            enabled_by_our_civ.add(int(cmd.b))

print()
for bid, spec in sorted(_UNLOCK_UNIT_BONUSES.items()):
    missing = [u for u in spec["units"] if u not in enabled_by_our_civ]
    check(f"bonus {bid} ({spec['name']}) reaches its unit(s) {spec['units']}",
          not missing,
          f"no civ-owned tech enables {missing} — the card is the only path to "
          f"these units, so this one is unreachable in-game")

check("no unlock bonus was skipped as uncatalogued",
      "0 bonus IDs skipped" in log,
      [l for l in log.splitlines() if "skipped" in l])

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
