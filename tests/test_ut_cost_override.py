"""_override_ut_costs must read zero as "unset", not as "free and instant".

No saved civ in the corpus exercises this: all 14 Empire Forge UT slots carry a
real cost, and the 24 KM slots have no castle_ut/imperial_ut dict at all, so the
round-trip harness skips the path entirely.  It is reachable in production
through KM import, which emits an all-zero cost, and through any save round-trip
— from_draft and to_draft both write `int(x or 0)`, so "unset" becomes 0 on
disk.  Applying those zeros stripped the real cost and research time off a
copied vanilla tech and shipped a free, instant unique tech.

Dependency-free apart from genieutils' ResearchResourceCost: the DAT and tech
are stand-ins, because the rule under test is about reading the draft, not about
the DAT.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from genieutils.tech import ResearchResourceCost   # noqa: E402
from civ_overrides import _override_ut_costs       # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


VANILLA_COST = (
    ResearchResourceCost(type=0, amount=300, flag=1),   # 300 food
    ResearchResourceCost(type=3, amount=200, flag=1),   # 200 gold
    ResearchResourceCost(type=-1, amount=0, flag=0),
)
VANILLA_TIME = 45


class FakeTech:
    def __init__(self):
        self.research_time = VANILLA_TIME
        self.resource_costs = VANILLA_COST


class FakeDat:
    def __init__(self):
        self.techs = [FakeTech()]


def run(ut_dict):
    """Apply one castle_ut draft against a fresh vanilla-costed tech."""
    dat = FakeDat()
    _override_ut_costs(dat, {"castle_ut_tech_id": 0}, {"castle_ut": ut_dict})
    return dat.techs[0]


def spend(tech):
    """(resource type, amount) for the spendable slots, in order."""
    return [(rc.type, rc.amount) for rc in tech.resource_costs if rc.amount > 0]


print("=== _override_ut_costs: zero means unset ===")

# The bug: KM import emits exactly this, and so does any saved civ whose UT
# cost/time were never set, because from_draft writes `int(x or 0)`.
t = run({"mode": "vanilla", "cost": {"food": 0, "wood": 0, "stone": 0, "gold": 0},
         "time": 0, "effects": [{"id": 13, "multiplier": 1}]})
check("all-zero cost leaves the vanilla cost alone", spend(t) == [(0, 300), (3, 200)],
      f"got {spend(t)}")
check("time 0 leaves the vanilla research time alone", t.research_time == VANILLA_TIME,
      f"got {t.research_time}")

t = run({"mode": "vanilla", "effects": [{"id": 13, "multiplier": 1}]})
check("absent cost/time leave both alone",
      spend(t) == [(0, 300), (3, 200)] and t.research_time == VANILLA_TIME,
      f"got {spend(t)}, time {t.research_time}")

# A real override must still win, or the fix would have broken the feature.
t = run({"cost": {"food": 0, "wood": 65, "stone": 0, "gold": 30}, "time": 90})
check("a real cost overrides", spend(t) == [(1, 65), (3, 30)], f"got {spend(t)}")
check("a real time overrides", t.research_time == 90, f"got {t.research_time}")
check("unused slots are cleared, not left vanilla", len(t.resource_costs) == 3,
      f"got {len(t.resource_costs)} slots")

t = run({"cost": {"gold": 500}, "time": 1})
check("a single-resource cost overrides", spend(t) == [(3, 500)], f"got {spend(t)}")
check("a 1-second time is a real value, not unset", t.research_time == 1,
      f"got {t.research_time}")

# from_draft/to_draft coerce with `or 0`, but a hand-written file can carry null.
t = run({"cost": {"food": None, "gold": None}, "time": None})
check("null cost/time are treated as unset, not crashed on",
      spend(t) == [(0, 300), (3, 200)] and t.research_time == VANILLA_TIME,
      f"got {spend(t)}, time {t.research_time}")

t = run({})
check("an empty UT dict is a no-op", spend(t) == [(0, 300), (3, 200)], f"got {spend(t)}")

print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
