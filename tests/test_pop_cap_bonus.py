#!/usr/bin/env python3
"""A custom bonus can raise the population limit, from a chosen age (#65).

A Civilization card with the "population limit" effect adds to resource 32
(Bonus Population Cap) — exactly vanilla's "+10 population in Imperial Age"
(tech 406, effect 418).  Flat and positive only: the lobby limit is a game
setting no resource exposes, so a percentage would be a guess, and nothing in
vanilla lowers resource 32.  The pure part runs anywhere; the build needs the
game DAT.

    venv/bin/python tests/test_pop_cap_bonus.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import custom_bonus as cb                                   # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


def card(value, age=None, target=None):
    t = target or {"type": "civ", **({"age": age} if age else {})}
    got = cb.normalize([{"target": t, "effects": [{"attr": "pop_cap", "op": "add", "value": value}]}])
    return got[0] if got else None


print("=== cards ===")
imp = card(25, 103)
check("an Imperial card keeps its age", imp and imp["target"] == {"type": "civ", "id": "civ", "age": 103})
check("text in the game's wording", cb.card_text(imp) == "+25 population limit in the Imperial Age",
      cb.card_text(imp))
check("no age = from the start", cb.card_text(card(10)) == "+10 population limit")
check("a bogus age is dropped", "age" not in card(10, 999)["target"])
check("a negative amount is refused", card(-10) is None)
check("a fraction rounds to whole population", card(12.6)["effects"][0]["value"] == 13)
check("capped at 1000", card(5000)["effects"][0]["value"] == 1000)
check("population limit can't go on a unit group", card(10, target={"type": "group", "id": "cavalry"}) is None)
cmds = [(c.type, c.a, c.b, c.d) for c in cb.card_commands(imp, lambda u: {u})]
check("writes EC_RESOURCE 32 +25, as vanilla's +10 pop does", cmds == [(1, 32, 1, 25.0)], f"{cmds}")

try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
if dat_path is None:
    print("  skip  no game DAT found — build check needs it")
else:
    from civ_appender import apply_civ
    from civ_schema import FORMAT_KEY
    dat = load_dat(str(dat_path))
    v406 = [(c.type, c.a, c.b) for c in dat.effects[dat.techs[406].effect_id].effect_commands]
    check("vanilla +10 pop (tech 406) is the same command shape", v406 == [(1, 32, 1)], f"{v406}")
    print("\n=== built ===")
    for slot, age, want_req in ((5, 103, 103), (6, None, None)):
        civ = {"format": FORMAT_KEY, "alias": f"Pop {slot}", "architecture": 2, "language": 0,
               "bonuses": [], "custom_bonuses": [card(25, age)],
               "tree": {"units": [83], "buildings": [109, 70], "techs": [101, 102, 103]}}
        n = len(dat.techs)
        with contextlib.redirect_stdout(io.StringIO()):
            apply_civ(dat, civ, target_slot=slot)
        techs = [t for t in dat.techs[n:] if t.civ == slot and 0 <= t.effect_id < len(dat.effects)
                 and any(c.type == 1 and c.a == 32 for c in dat.effects[t.effect_id].effect_commands)]
        reqs = [r for t in techs for r in t.required_techs if r >= 0]
        label = f"{'Imperial' if age else 'start'} card"
        check(f"{label}: one civ tech adds 25 to resource 32",
              len(techs) == 1 and [c.d for c in dat.effects[techs[0].effect_id].effect_commands] == [25.0],
              f"{len(techs)} techs")
        check(f"{label}: gated on {want_req or 'nothing'}",
              reqs == ([want_req] if want_req else []), f"reqs={reqs}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
