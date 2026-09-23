"""_scale_ec_for_multiplier: what compounds, what accumulates, what must not move.

No DAT needed — this is pure arithmetic on EffectCommand values.

The mode-2 case exists because "tech costs -50%" is encoded as EC_TECH_COST with
c=2 and d=0.5, which is a MULTIPLY, not the "0=set / 1=add" the constant's old
comment claimed.  Counting the shipped DAT settles it: every one of the 173 cost
and 51 time commands using mode 2 carries a fraction (0.5, 0.75, 0.6, 0.25,
0.85, 0.67).  Seven civ bonus cards are built entirely from mode-2 commands, so
before this was handled their multiplier silently did nothing.

Getting the direction wrong matters: for d=0.5, compounding gives 0.25 (-75%,
stronger) while multiplying gives 1.0 (no discount at all — the bonus would
invert into a no-op).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from genieutils.effect import EffectCommand            # noqa: E402
from civ_appender import (_scale_ec_for_multiplier,    # noqa: E402
                          EC_MUL_RESOURCE,
                          EC_SET, EC_RESOURCE, EC_ADD, EC_MULTIPLY,
                          EC_TECH_COST, EC_TECH_TIME,
                          TECH_MODE_SET, TECH_MODE_MULTIPLY)

failures = 0


def check(label, got, want):
    global failures
    if abs(float(got) - float(want)) < 1e-6:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label} — got {got!r}, want {want!r}")


def scaled(type_, c, d, mult):
    return _scale_ec_for_multiplier(
        EffectCommand(type=type_, a=-1, b=-1, c=c, d=float(d)), mult).d


print("=== compounding (a proportion applied N times) ===")
check("EC_MULTIPLY 1.1 x2", scaled(EC_MULTIPLY, 13, 1.1, 2), 1.21)
check("tech cost -50% x2 compounds to -75%",
      scaled(EC_TECH_COST, TECH_MODE_MULTIPLY, 0.5, 2), 0.25)
check("tech cost -25% x3", scaled(EC_TECH_COST, TECH_MODE_MULTIPLY, 0.75, 3), 0.421875)
check("tech time x2", scaled(EC_TECH_TIME, TECH_MODE_MULTIPLY, 0.5, 2), 0.25)

print("\n=== accumulating (a flat amount applied N times) ===")
check("EC_ADD +5 x3", scaled(EC_ADD, 9, 5, 3), 15)
check("EC_RESOURCE +100 x2", scaled(EC_RESOURCE, -1, 100, 2), 200)

print("\n=== cMulResource compounds like EC_MULTIPLY ===")
# Type 6 scales a player RESOURCE, not a unit attribute, and it is the lever
# behind every "drop off +N%" and "resources last N% longer" bonus.  It used to
# fall through to "left alone", which was worse than a no-op: the "last longer"
# family pairs it with a compensating work-rate CUT that IS an EC_MULTIPLY, so
# at x2 the villager slowed to d**2 while productivity stayed at d — the card's
# own multiplier cost the player income.
check("cMulResource +15% x2 compounds", round(scaled(EC_MUL_RESOURCE, -1, 1.15, 2), 6), 1.3225)
check("cMulResource +15% x3 compounds", round(scaled(EC_MUL_RESOURCE, -1, 1.15, 3), 6), 1.520875)
check("cMulResource +10% x2 compounds", round(scaled(EC_MUL_RESOURCE, -1, 1.1, 2), 6), 1.21)
# and it must stay in step with the work-rate cut it is paired with
prod = scaled(EC_MUL_RESOURCE, -1, 2.0, 2)      # trees last +100%, x2
rate = scaled(EC_MULTIPLY, 13, 0.5, 2)          # its compensating lumberjack cut
check("bonus 235 at x2 keeps income flat (prod * rate == 1)", round(prod * rate, 6), 1.0)

print("\n=== packed armor keeps its class byte ===")
# d = class_id<<8 | amount; scaling the whole int would change the armor class
check("EC_ADD c=8 class3 +1 x2 stays class 3", scaled(EC_ADD, 8, (3 << 8) | 1, 2), (3 << 8) | 2)

print("\n=== must NOT move ===")
# d is a unit id, not an amount — civ bonuses 100 and 139
check("EC_SET ATTR_DEAD_UNIT keeps the unit id", scaled(EC_SET, 57, 888, 3), 888)
# set-to-absolute has no meaningful Nth application; 0.0 means "free"
check("tech cost mode=set stays put", scaled(EC_TECH_COST, TECH_MODE_SET, 0.0, 4), 0.0)
check("tech time mode=set stays put", scaled(EC_TECH_TIME, TECH_MODE_SET, 0.0, 4), 0.0)
check("EC_SET work rate is left alone", scaled(EC_SET, 13, 1.1, 2), 1.1)

print("\n=== resources whose value is an INDEX, not an amount ===")
# Some EC_RESOURCE commands carry a selector in `d`, and scaling one does not
# make the effect stronger — it points the effect somewhere else entirely.
from civ_appender import RES_SPAWN_LIMIT, RES_EFFECT_FUNCTION   # noqa: E402


def scaled_res(resource_id, d, mult):
    return _scale_ec_for_multiplier(
        EffectCommand(type=EC_RESOURCE, a=resource_id, b=0, c=-1,
                      d=float(d)), mult).d


# Resource 33 selects which routine in the game's own Effects.xs runs, so x2
# would turn Hamask's function 30 into 60 and Coiled Serpent Array's 6 into 12 —
# unrelated functions, not a stronger version of the card.
for fn, mult in ((30, 2), (31, 3), (6, 2), (51, 4), (56, 2)):
    check(f"EffectFunction {fn} is not scaled at x{mult}",
          scaled_res(RES_EFFECT_FUNCTION, fn, mult), float(fn))
# Spawn Limit counts participating buildings, a different axis from unit count.
check("Spawn Limit is not scaled at x3", scaled_res(RES_SPAWN_LIMIT, 1, 3), 1.0)
# ...while an ordinary resource amount still scales.
check("an ordinary resource amount still scales at x3",
      scaled_res(0, 100, 3), 300.0)

print("\n=== multiplier <= 1 is always identity ===")
for m in (0, 1):
    check(f"x{m} leaves EC_MULTIPLY alone", scaled(EC_MULTIPLY, 13, 1.1, m), 1.1)
    check(f"x{m} leaves mode-2 cost alone",
          scaled(EC_TECH_COST, TECH_MODE_MULTIPLY, 0.5, m), 0.5)

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
