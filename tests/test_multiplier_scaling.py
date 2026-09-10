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

print("\n=== multiplier <= 1 is always identity ===")
for m in (0, 1):
    check(f"x{m} leaves EC_MULTIPLY alone", scaled(EC_MULTIPLY, 13, 1.1, m), 1.1)
    check(f"x{m} leaves mode-2 cost alone",
          scaled(EC_TECH_COST, TECH_MODE_MULTIPLY, 0.5, m), 0.5)

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
