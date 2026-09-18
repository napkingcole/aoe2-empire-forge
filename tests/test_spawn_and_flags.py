#!/usr/bin/env python3
"""Findings from the 2026-09-18 in-game test round.  DAT-gated.

Three bugs, each invisible to every existing test because each one produced a
well-formed DAT that simply did the wrong thing.

**1. EC_SPAWN's count is in `c`, and the multiplier only ever scaled `d`.**
Civ bonus 345 ("a free Villager for each economic upgrade") offered a multiplier
that did nothing: at x3 it still spawned one Villager. All 17 vanilla spawn
commands carry the count in `c` and `d = 0.0`, so the generic "scale d" rule
could never move it. Two halves had to change — `_scale_ec_for_multiplier` to
scale `c`, and `_multiply_effect`, which copied back **only `d`** on the
reasonable assumption that every scalable command keeps its magnitude there. The
delegation between them existed specifically to stop this kind of divergence and
did not, because it discarded the field it did not expect to change.

Resource 234 ("Spawn Limit") must NOT be scaled: it is how many spawning
*buildings* may participate, not how many units each produces. Scaling it turned
one card into "one Villager from each of up to N Town Centers", which is why the
bonus looked inert on a single Town Center.

**2. Bonuses 345 and 356 could not see each other.** Pastures replace Horse
Collar / Heavy Plow / Crop Rotation with three civ=53 Khitan techs, which 356
copies to fresh ids — so 345's free-Villager techs, which name the vanilla Mill
upgrades, paid nothing for three of the player's economic upgrades. The wiring
has to happen after the whole bonus loop, because bonus order in a civ_def is
whatever the user clicked.

**3. The `ignore_armor` flag reduced the unit to 1 damage.** It replaced the
unit's real attacks with one against armour class 50, which **no unit in the
game has**; a missing armour class resolves to the base armour value ("almost
always 1000"), so the attack line contributed 0 and the engine's minimum damage
of 1 applied. Confirmed in-game on a 25-attack Elite Janissary hitting for 1.

    venv/bin/python tests/test_spawn_and_flags.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat          # noqa: E402
import civ_appender as ca                                # noqa: E402
from civ_appender import apply_civ                       # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

dat = load_dat(str(dat_path))

# ── 1. The spawn count scales; the spawn limit does not ──────────────────────
from genieutils.effect import EffectCommand                # noqa: E402

spawn = EffectCommand(type=ca.EC_SPAWN, a=83, b=109, c=1, d=0.0)
scaled = ca._scale_ec_for_multiplier(spawn, 3)
check("EC_SPAWN x3 scales the count in `c`", int(scaled.c) == 3, f"c={scaled.c}")
check("EC_SPAWN x3 leaves `d` alone", scaled.d == 0.0, f"d={scaled.d}")

limit = EffectCommand(type=ca.EC_RESOURCE, a=ca.RES_SPAWN_LIMIT, b=0, c=-1, d=1.0)
check("the Spawn Limit resource is never scaled",
      ca._scale_ec_for_multiplier(limit, 3).d == 1.0)
other = EffectCommand(type=ca.EC_RESOURCE, a=4, b=0, c=-1, d=100.0)
check("an ordinary EC_RESOURCE still scales",
      ca._scale_ec_for_multiplier(other, 3).d == 300.0)

# _multiply_effect is the path the catalog tech branch actually uses, and it is
# where the fix was initially missed — it copied back only `d`.
dat.effects.append(type(dat.effects[0])(name="spawn probe", effect_commands=[
    EffectCommand(type=ca.EC_SPAWN, a=83, b=109, c=1, d=0.0),
    EffectCommand(type=ca.EC_RESOURCE, a=ca.RES_SPAWN_LIMIT, b=0, c=-1, d=1.0),
]))
probe_id = len(dat.effects) - 1
ca._multiply_effect(dat, probe_id, 3)
cmds = dat.effects[probe_id].effect_commands
check("_multiply_effect copies back `c`, not just `d`", int(cmds[0].c) == 3,
      f"spawn count stayed at {cmds[0].c} — the scaler ran but its `c` was discarded")
check("_multiply_effect leaves the spawn limit at 1", cmds[1].d == 1.0,
      f"d={cmds[1].d}")


# ── 2 & 3. A civ carrying the reported combination ───────────────────────────
def civ_def(bonuses, flags):
    return {
        "format": "empireforge_v2", "schema_version": 2,
        "alias": "Spawn Probe", "tagline": "", "description": "",
        "architecture": 1, "language": 0, "wonder_model": -1, "castle_model": -1,
        "emblem": "", "monk_skin": None, "hero_unit": None, "second_uu": None,
        "unique_unit": {"km_idx": 9, "vanilla_id": None, "name": None,
                        "description": None, "overrides": {"attack_elite": 25},
                        "advanced_flags": flags},
        "bonuses": bonuses, "team_bonuses": [],
        "castle_ut": {"mode": "custom", "vanilla_id": None, "name": "", "description": "",
                      "cost": {"food": 0, "wood": 0, "stone": 0, "gold": 0},
                      "time": 0, "effects": []},
        "imperial_ut": {"mode": "custom", "vanilla_id": None, "name": "", "description": "",
                        "cost": {"food": 0, "wood": 0, "stone": 0, "gold": 0},
                        "time": 0, "effects": []},
        "tree": {"units": [], "buildings": [], "techs": []},
        "unit_overrides": [], "button_moves": [], "free_techs": [],
    }


# 356 is listed FIRST here and 345 second on purpose in the second civ below:
# the fix must not depend on the order the user clicked the cards.
for slot, order in ((5, [{"id": 345, "multiplier": 3}, {"id": 356, "multiplier": 1}]),
                    (6, [{"id": 356, "multiplier": 1}, {"id": 345, "multiplier": 3}])):
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ(dat, civ_def(order, {}), target_slot=slot)

    spawn_techs = []
    for tid, t in enumerate(dat.techs):
        if t.civ != slot or not (0 <= t.effect_id < len(dat.effects)):
            continue
        for c in dat.effects[t.effect_id].effect_commands:
            if c.type == ca.EC_SPAWN and int(c.a) == 83:
                spawn_techs.append((tid, int(c.c), [r for r in t.required_techs if r >= 0]))

    first = order[0]["id"]
    check(f"[{first} first] 345 + 356 yields 17 free-Villager techs (14 + 3 Pasture)",
          len(spawn_techs) == 17, f"got {len(spawn_techs)}")
    check(f"[{first} first] every spawn is scaled to 3 by the x3 multiplier",
          all(n == 3 for _, n, _ in spawn_techs),
          f"counts: {sorted({n for _, n, _ in spawn_techs})}")
    # The Pasture techs must name 356's COPIES, not the civ=53 originals, or they
    # can never fire — the whole reason this runs after the loop.
    named = {r for _, _, reqs in spawn_techs for r in reqs}
    check(f"[{first} first] no Pasture tech names a civ=53 original",
          not (named & set(ca._PASTURE_MILL_TECHS)),
          f"still naming originals: {sorted(named & set(ca._PASTURE_MILL_TECHS))}")
    pasture_clones = {tid for tid, t in enumerate(dat.techs)
                      if t.civ == slot and t.name in
                      ("Grazing Grasslands", "Enclosures", "Livestock Husbandry")}
    check(f"[{first} first] three spawn techs are gated on the Pasture copies",
          len({tid for tid, _, reqs in spawn_techs
               if set(reqs) & pasture_clones}) == 3,
          f"pasture clones={sorted(pasture_clones)}")

# ── 3. ignore_armor must not strip the unit's real attack ────────────────────
from civ_overrides import _apply_uu_overrides              # noqa: E402

ARMOUR_CLASSES = {a.class_
                  for c in dat.civs for u in (c.units or []) if u is not None
                  and getattr(u, "type_50", None)
                  for a in (u.type_50.armours or [])}
check("armour class 50 does not exist anywhere in the game", 50 not in ARMOUR_CLASSES,
      "if a future patch adds it, the old ignore_armor implementation could be revisited")

draft = civ_def([], {"ignore_armor": True})
uu_info = {"unit_id": 46, "elite_id": 557}
with contextlib.redirect_stdout(io.StringIO()) as buf:
    _apply_uu_overrides(dat, 7, uu_info, draft)
out = buf.getvalue()
for uid, label in ((46, "Janissary"), (557, "Elite Janissary")):
    attacks = dat.civs[7].units[uid].type_50.attacks
    classes = {a.class_ for a in attacks}
    real = [a for a in attacks if a.class_ in (3, 4) and a.amount > 0]
    check(f"ignore_armor leaves {label} a real Base Melee/Pierce attack", bool(real),
          f"attack classes present: {sorted(classes)}")
    check(f"ignore_armor adds no class-50 attack to {label}", 50 not in classes)
check("ignore_armor says plainly that it was ignored", "not supported" in out,
      f"output was: {out!r}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
