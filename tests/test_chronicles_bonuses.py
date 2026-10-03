#!/usr/bin/env python3
"""The Chronicles-derived cards (civ 441-446, team 87-90) reach the built DAT.

Chronicles civs can't be picked outside their own game mode, but their bonus
techs and effects live in the shared DAT, and the portable ones use only
standard units, techs and ages.  Each card here is checked where it lands, not
in the catalog.  DAT-gated.

    venv/bin/python tests/test_chronicles_bonuses.py
"""
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dat_reader import find_game_dat, load_dat     # noqa: E402
from civ_appender import apply_civ, EC_UPGRADE     # noqa: E402

failures = 0


def dispatched_handler_ids() -> set[int]:
    import re
    src = (Path(__file__).resolve().parent.parent / "civ_appender.py").read_text()
    start = src.index("def _create_bonus_handler")
    body = src[start:src.index("\ndef ", start + 10)]
    return {int(x) for m in re.finditer(r"if bonus_id (?:==|in) ([^:]+):", body)
            for x in re.findall(r"\d+", m.group(1))}


def check(label, ok, detail=""):
    global failures
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        failures += 1
        if detail:
            print(f"       {detail}")


# A handler-only bonus the picker doesn't know about is never offered: 446 was
# built and tested, and still missing from the catalog until this was added.
from civ_appender import HANDLED_BONUS_IDS          # noqa: E402
check("every bonus _create_bonus_handler dispatches is in HANDLED_BONUS_IDS",
      dispatched_handler_ids() <= HANDLED_BONUS_IDS,
      sorted(dispatched_handler_ids() - HANDLED_BONUS_IDS))

SLOT = 1
dat = load_dat(find_game_dat())
n_techs = len(dat.techs)
with contextlib.redirect_stdout(io.StringIO()):
    res = apply_civ(dat, {"alias": "ChronProbe",
                          "bonuses": [{"id": b, "multiplier": 1} for b in range(441, 447)],
                          "team_bonuses": [{"id": t, "multiplier": 1} for t in range(87, 91)]},
                    target_slot=SLOT)

mine = [(i, dat.techs[i]) for i in range(n_techs, len(dat.techs)) if dat.techs[i].civ == SLOT]
cmds = [c for _, t in mine if 0 <= t.effect_id < len(dat.effects)
        for c in dat.effects[t.effect_id].effect_commands]

check("all six civ cards apply, none skipped",
      res["bonus_results"]["applied"] >= 6 and not res["bonus_results"]["skipped"],
      (res["bonus_results"]["applied"], res["bonus_results"]["skipped"]))
check("no warnings", not res.get("warnings"), res.get("warnings"))

# 441 / 444 — civ-gated Macedonian / Thracian techs copied to this civ (quirk 9).
names = {t.name for _, t in mine}
check("441: the three cavalry-armor techs are this civ's own copies",
      sum("for Cavalry, Macedonian" in n for n in names) == 3, sorted(names))
check("444: both skirmisher-regen steps are this civ's own copies",
      sum("Skirmishers regen" in n for n in names) == 2)

# 442 / 443 / 445 — ec_list cards.
check("442: siege +1 pierce armor (class 3) on all four siege classes",
      {int(c.b) for c in cmds if c.type == 4 and int(c.c) == 8 and int(c.d) == 3 * 256 + 1} >= {13, 51, 54, 55})
check("443: seven Stable techs research 50% faster (mode 2)",
      sum(1 for c in cmds if c.type == 103 and int(c.c) == 2 and int(c.a) in
          (435, 39, 254, 428, 209, 265, 236)) == 7)
stone = [t for _, t in mine if any(c.type == 6 and int(c.a) == 512
                                   for c in dat.effects[t.effect_id].effect_commands)]
check("445: resource 512 switched on, then raised by Stone Mining and Stone Shaft Mining",
      any(c.type == 1 and int(c.a) == 512 for c in cmds)
      and sorted(t.required_techs[0] for t in stone) == [278, 279])

# 446 — every Outpost at once, researched at the Outpost.
fort = [t for _, t in mine if t.name == "Fortified Outposts"]
ups = [c for t in fort for c in dat.effects[t.effect_id].effect_commands if c.type == EC_UPGRADE]
check("446: one researchable tech at the Outpost", len(fort) == 1
      and fort[0].research_locations[0].location_id == 598, [t.name for t in fort])
check("446: upgrades EVERY Outpost (c=-1), not just the one researching (c=2)",
      [(int(c.a), int(c.b), int(c.c)) for c in ups] == [(598, 2415, -1)], ups)
check("446: costs wood only — no per-Outpost resource 508",
      fort and [(r.type, r.amount) for r in fort[0].resource_costs if r.type >= 0] == [(1, 50)])
check("446: no prerequisite (vanilla's only one is the team bonus release)",
      fort and fort[0].required_tech_count == 0)
check("446: Fortified Outpost shares the Outpost's build slot, so new ones come out fortified",
      [(t.unit_id, t.button_id) for t in dat.civs[SLOT].units[2415].creatable.train_locations][:1]
      == [(t.unit_id, t.button_id) for t in dat.civs[SLOT].units[598].creatable.train_locations][:1])

# Team bonuses — all merged into the civ's team-bonus effect.
tb = dat.effects[dat.civs[SLOT].team_bonus_id].effect_commands
check("T87: releases the global Fortified Outpost tech (1269 cost and time)",
      {(c.type, int(c.a)) for c in tb} >= {(101, 1269), (103, 1269)})
barracks = [int(c.a) for c in tb if c.type == 103 and int(c.c) == 1]
check("T88: 13 Barracks techs research faster, none of them Chronicles-only",
      len(barracks) == 13 and not {1137, 1173, 1174} & set(barracks), barracks)
check("T89: buildings +3 line of sight",
      any(c.type == 4 and int(c.b) == 3 and int(c.c) == 1 and c.d == 3 for c in tb))
check("T90: trade carts +15% speed",
      any(c.type == 5 and int(c.b) == 19 and int(c.c) == 5 for c in tb))

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
