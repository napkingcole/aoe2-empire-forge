#!/usr/bin/env python3
"""Cards for content the player's game doesn't have yet are left out, said so,
and never read whatever an earlier civ appended in their place.

A player built a 20-civ mod from a game that predated Viking Sagas (reported
2026-11-15: "no Varangian Guard bonuses", a civ name showing "ERROR ...
LocString", an AI script failure).  On that DAT the Varangian Guard card's techs
(1478, 1488) are unnamed placeholders, so the card built and did nothing while
the civ text still listed it.  Team bonuses 84-86 were worse: they read effects
1455-1457 by index, which a pre-Sagas DAT (1409 effects) only has once an
earlier civ in the same build has appended that many — and then the card copies
that civ's effect.

Needs the pre-Sagas DAT kept at ignore/6-6-26/ (skipped without it).

    venv/bin/python tests/test_old_game_cards.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat           # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


# Languages first: no DAT needed.
from build_civ import LANGUAGES                          # noqa: E402
check("Polish and Russian get string files", {"pl", "ru"} <= set(LANGUAGES))

OLD = ROOT / "ignore" / "6-6-26" / "empires2_x2_p1.dat"
if not OLD.exists():
    print("  skip  no pre-Viking-Sagas DAT at ignore/6-6-26/")
    sys.exit(1 if failures else 0)

import civ_appender as ca                                # noqa: E402
from build_all import drop_unavailable                   # noqa: E402
from genieutils.effect import Effect, EffectCommand      # noqa: E402

SAGAS_CARDS = list(range(429, 441))   # the twelve Viking Sagas civ bonus cards
VG_CARD = 435                         # Varangian Guards attack faster, +gold
TEAM_SAGAS = 84                       # effect 1455 — the Saxons' team bonus
MARK = 9999                           # resource id no real effect uses


def civ(alias, bonuses=(), team=()):
    return {"alias": alias, "tagline": "", "architecture": 2, "language": 0,
            "castle": -1, "wonder": -1, "monk_skin": -1,
            "bonuses": [list(bonuses), [], [], [], list(team)], "tree": [[], [], []]}


old = load_dat(str(OLD))
check("the old DAT is from before Viking Sagas", len(old.effects) < 1455,
      f"{len(old.effects)} effects")
check("catalog_cards_missing names exactly the twelve Viking Sagas cards",
      ca.catalog_cards_missing(old) == SAGAS_CARDS, ca.catalog_cards_missing(old))

with contextlib.redirect_stdout(io.StringIO()):
    first = ca.apply_civ(old, civ("First", [[1, 1]]), target_slot=1)
    # Stand in for more earlier civs: fill the effect table past 1455 with
    # effects a leak would carry along.
    while len(old.effects) <= 1460:
        old.effects.append(Effect(name="earlier civ", effect_commands=[
            EffectCommand(type=1, a=MARK, b=1, c=-1, d=1.0)]))
    second = ca.apply_civ(old, civ("Second", [[1, 1], [VG_CARD, 1]], [[TEAM_SAGAS, 1], [2, 1]]),
                          target_slot=2)

check("the first civ warns that the game is older than the catalog",
      any("older than" in w for w in first["warnings"]), first["warnings"])
check("...once per build, not again for the second civ",
      not any("older than" in w for w in second["warnings"]), second["warnings"])

br = second["bonus_results"]
check("the Varangian Guard card is reported unavailable", br.get("unavailable") == [VG_CARD],
      br.get("unavailable"))
check("the Saxons' team bonus is reported unavailable, not 'no implementation'",
      br.get("team_unavailable") == [TEAM_SAGAS] and TEAM_SAGAS not in br.get("team_skipped", []),
      (br.get("team_unavailable"), br.get("team_skipped")))
check("the player is told what was left out",
      any("Left out" in w and "Varangian" in w for w in second["warnings"]), second["warnings"])

tb = old.effects[old.civs[2].team_bonus_id].effect_commands
check("the team bonus copied nothing an earlier civ appended",
      not any(c.type == 1 and int(c.a) == MARK for c in tb))
check("the other team bonus still applied", br.get("team_applied") == 1, br.get("team_applied"))

check("drop_unavailable leaves the card out of the civ text",
      [e[0] for e in drop_unavailable([[1, 1], [VG_CARD, 1]], second)] == [1])
check("...and the team bonus out of the Team Bonus line",
      [e[0] for e in drop_unavailable([[TEAM_SAGAS, 1], [2, 1]], second, team=True)] == [2])

# The current game has every card: nothing missing, nothing warned.
cur = find_game_dat()
if cur:
    check("the current game has every catalog card", ca.catalog_cards_missing(load_dat(str(cur))) == [])

if failures:
    print(f"\n{failures} failed")
    sys.exit(1)
print("\nall passed")
