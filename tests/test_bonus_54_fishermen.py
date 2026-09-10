"""Civ bonus 54 must target the fishing VILLAGERS, not tech 469.

No DAT needed — this is a catalog assertion.

KM's builder maps bonus 54 ("Fishermen work 10% faster") to tech 469, and our
catalog was extracted from his C++, so we inherited it verbatim.  Tech 469 is
`[SCEN] Move Tarkan`: it sets attribute 42 (train location) to -1 on units
755/757, which has nothing to do with fishing and may break Tarkan training.

The bonus is fishing VILLAGERS, not fishing ships, so neither tech 306
(C-Bonus, Better Fishing Ships) nor 906 (Fishing Lines) is the right target
either.  No vanilla tech implements it, which is why it lives in ec_list.

This test exists because the catalog's own docstring points future readers at
KM's source as the origin, and re-extracting from it would silently restore the
broken mapping.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bonus_catalog import civ_bonus_techs, civ_bonus_ec_list   # noqa: E402

VMFIS, VFFIS = 56, 57
EC_MULTIPLY, ATTR_WORK_RATE = 5, 13
TARKAN_SCEN_TECH = 469

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


print("=== civ bonus 54 — Fishermen work 10% faster ===")

techs = civ_bonus_techs(54)
check("no longer maps to the [SCEN] Move Tarkan tech",
      TARKAN_SCEN_TECH not in techs, f"techs={techs}")
check("has no vanilla tech mapping at all", techs == [], f"techs={techs}")

entries = civ_bonus_ec_list(54)
check("has an ec_list entry", len(entries) == 1, f"got {len(entries)} entries")

if entries:
    ecs = entries[0].get("ecs", [])
    targets = {ec["A"] for ec in ecs}
    check("targets both fishing villagers (VMFIS 56, VFFIS 57)",
          targets == {VMFIS, VFFIS}, f"targets={sorted(targets)}")
    check("every command is EC_MULTIPLY on work rate",
          all(ec["type"] == EC_MULTIPLY and ec["C"] == ATTR_WORK_RATE for ec in ecs),
          str([(ec["type"], ec["C"]) for ec in ecs]))
    check("the rate is +10%",
          all(abs(ec["D"] - 1.1) < 1e-6 for ec in ecs),
          str([ec["D"] for ec in ecs]))
    # Death variants (VMFIS_D 58 / VFFIS_D 60) are never touched by vanilla's
    # equivalent bonuses, and a fishing SHIP id here would mean the wrong fix.
    check("does not touch death variants or ships",
          not (targets & {58, 60, 13, 545, 691}), f"targets={sorted(targets)}")
    # EC_MULTIPLY is what _scale_ec_for_multiplier compounds, so the card's
    # multiplier works for free — x2 must mean 1.21, not 2.2.
    check("uses the type the multiplier can scale (EC_MULTIPLY)",
          all(ec["type"] == EC_MULTIPLY for ec in ecs))

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
