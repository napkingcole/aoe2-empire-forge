#!/usr/bin/env python3
"""Pin the bonus fixes from docs/AUDIT-bonus-catalog-mismaps.md.

Each of these was a silent no-op or a mismap before 2026-09-10, so the useful
assertion is "the command actually reaches the built DAT", not "the catalog says
so".  Builds one civ carrying all seven bonuses and reads the result back.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dat_reader import find_game_dat, load_dat
from civ_appender import apply_civ

failures = 0


def check(label, ok, detail=""):
    global failures
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        failures += 1
        if detail:
            print(f"       {detail}")


BONUSES = [
    # ── round 1 (2026-09-10) ──
    [76, 1],    # Villagers +5% Dark / +10% Feudal speed  — Feudal tech was missing
    [108, 1],   # Farm upgrades +125% food                — used to unlock Flemish Militia
    [302, 1],   # Ships get blacksmith armor              — Galleon was missing
    [306, 1],   # Scorpions -50% gold                     — dropped the RESERVED tech
    [342, 1],   # Careening / Dry Dock free               — dropped two RESERVED techs
    [357, 1],   # Shepherds/Herders +10% food             — was entirely inert
    [360, 1],   # Heavy Cavalry Archer in Castle, -50%    — prereq was never re-pointed
    # ── round 2 (2026-09-13) ──
    [52, 1],    # Gunpowder -20% cost      — vanilla gave 5 units +25% HP instead
    [140, 1],   # Wonders                  — "cost no wood" was never implemented
    [191, 1],   # Explosive units 2x HP    — demo ships are class 22, needed ids
    [312, 1],   # Drop-off buildings -25%  — only the Mule Cart was discounted
]

CIV_DEF = {
    "alias": "AuditFixes",
    "bonuses": [{"id": b, "multiplier": m} for b, m in BONUSES],
    "team_bonuses": [],
}

print("=== audit fixes, end to end ===")
dat = load_dat(find_game_dat())
n_techs_before = len(dat.techs)
apply_civ(dat, CIV_DEF, target_slot=1)

civ_techs = [(i, t) for i, t in enumerate(dat.techs)
             if i >= n_techs_before or t.civ == 1]


def cmds_of(tech):
    eid = tech.effect_id
    if not (0 <= eid < len(dat.effects)):
        return []
    return dat.effects[eid].effect_commands


all_cmds = [c for _, t in civ_techs for c in cmds_of(t)]

# ── 76: both age steps present ───────────────────────────────────────────────
speed = [c.d for c in all_cmds
         if c.type == 5 and c.a == -1 and c.b == 4 and c.c == 5]
check("bonus 76 applies two villager-speed steps, not one",
      len(speed) == 2, f"found {speed}")
check("bonus 76's steps compound to ~+10%",
      abs(speed[0] * speed[1] - 1.10) < 0.01 if len(speed) == 2 else False,
      f"product = {speed[0] * speed[1] if len(speed) == 2 else '?'}")

# ── 108: no Flemish Militia ──────────────────────────────────────────────────
flemish = [c for c in all_cmds if c.type == 2 and c.a in (1663, 1697, 1699)]
check("bonus 108 no longer unlocks the Flemish Militia",
      not flemish, f"{len(flemish)} EC_ENABLE on Flemish Pikeman units")
farm_food = [c for c in all_cmds if c.type == 6 and c.a == 69]
check("bonus 108 still grants the farm food bonus", bool(farm_food))

# ── 302: Galleon gets the armor ──────────────────────────────────────────────
for uid, name in ((21, "Galley"), (442, "War Galley"), (539, "Galleon")):
    got = [c.d for c in all_cmds if c.type == 4 and c.a == uid and c.c == 8]
    check(f"bonus 302 arms the {name} ({uid})", len(got) == 2, f"found {got}")

# ── 306 / 342: the RESERVED techs are gone, the real work remains ────────────
gold = [c for c in all_cmds if c.type == 5 and c.a in (279, 542) and c.c == 105]
check("bonus 306 still halves Scorpion gold cost", len(gold) == 2, f"found {len(gold)}")
free_naval = [c for c in all_cmds if c.type in (101, 103) and c.a in (374, 375)]
check("bonus 342 still zeroes Careening / Dry Dock", len(free_naval) >= 4,
      f"found {len(free_naval)}")

# ── 357: no longer inert ─────────────────────────────────────────────────────
livestock = [c for c in all_cmds if c.type == 6 and c.a == 216]
check("bonus 357 emits a livestock-food multiplier at all", bool(livestock),
      "this bonus was a complete no-op before the fix")
check("bonus 357 multiplies livestock food by 1.1",
      any(abs(c.d - 1.1) < 1e-6 for c in livestock),
      f"found {[c.d for c in livestock]}")

# ── 360: tech 218 can now be satisfied in the Castle Age ─────────────────────
hca = dat.techs[218]
copies = [i for i, t in civ_techs
          if any(c.type == 101 and c.a == 218 for c in cmds_of(t))]
check("bonus 360 allocated a civ-owned copy of the Khitan trigger", bool(copies),
      f"required_techs = {hca.required_techs}")
repointed = [r for r in hca.required_techs if r in copies]
check("bonus 360 re-pointed tech 218 at that copy", bool(repointed),
      f"required_techs = {hca.required_techs}, copies = {copies}")
check("bonus 360 left required_tech_count alone (2 of N)",
      hca.required_tech_count == 2, f"count = {hca.required_tech_count}")
check("bonus 360 keeps Castle Age reachable (192 + trigger = 2)",
      192 in hca.required_techs and bool(repointed))

# ── 52: every gunpowder unit gets the discount, nobody gets stray HP ─────────
GUNPOWDER = (5, 36, 420, 691, 1709, 1001, 1003, 1901, 1903, 1904, 1907, 1911)
disc = {c.a for c in all_cmds if c.type == 5 and c.c == 100 and abs(c.d - 0.8) < 1e-6}
check("bonus 52 discounts every listed gunpowder unit",
      set(GUNPOWDER) <= disc, f"missing {sorted(set(GUNPOWDER) - disc)}")
stray_hp = [c.a for c in all_cmds
            if c.type == 5 and c.c == 0 and c.a in (1904, 1907, 1901, 1903, 1911)
            and abs(c.d - 1.25) < 1e-6]
check("bonus 52 no longer hands out +25% HP instead of the discount",
      not stray_hp, f"still boosting HP on {stray_hp}")

# ── 140: the wood cost is actually removed ───────────────────────────────────
WONDERS = (182, 276, 1096, 1367, 1368, 1369, 1622)
nowood = {c.a for c in all_cmds if c.type == 0 and c.c == 104 and c.d == 0.0}
check("bonus 140 zeroes the wood cost on every Wonder",
      set(WONDERS) <= nowood, f"missing {sorted(set(WONDERS) - nowood)}")
pop = {c.a for c in all_cmds if c.type == 4 and c.c == 21 and c.d == 50.0}
check("bonus 140 still grants +50 population", set(WONDERS) <= pop)

# ── 191: demolition ships are class 22, so they need explicit ids ────────────
hp2 = [(c.a, c.b) for c in all_cmds if c.type == 5 and c.c == 0 and c.d == 2.0]
check("bonus 191 still covers class 35 (Petard, Flaming Camel)",
      (-1, 35) in hp2, f"found {hp2}")
for uid, name in ((527, "Demolition Raft"), (528, "Demolition Ship"),
                  (1104, "Heavy Demolition Ship"), (1911, "Grenadier")):
    check(f"bonus 191 covers the {name} ({uid})", (uid, -1) in hp2)

# ── 312: the buildings, not just the Mule Cart ───────────────────────────────
DROPOFF = (68, 129, 130, 131, 562, 563, 564, 565, 584, 585, 586, 587,
           1734, 1711, 1720, 2556, 2558, 2560)
cheap = {c.a for c in all_cmds if c.type == 5 and c.c == 100 and abs(c.d - 0.75) < 1e-6}
check("bonus 312 discounts every drop-off building",
      set(DROPOFF) <= cheap, f"missing {sorted(set(DROPOFF) - cheap)}")
check("bonus 312 still discounts the Mule Cart (vanilla tech 958)", 1808 in cheap)
check("bonus 312 still applies the upgrade-effectiveness half",
      len([c for c in all_cmds
           if c.type == 5 and c.c == 13 and c.a in (123, 218, 579, 581, 124, 220)]) >= 8)

print(f"\n{'All checks passed.' if not failures else f'{failures} check(s) failed.'}")
sys.exit(0 if not failures else 1)
