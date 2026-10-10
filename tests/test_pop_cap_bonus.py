#!/usr/bin/env python3
"""Civilization cards: population limit and one-time resources (#65 + follow-up).

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

# ── Resources (start / on reaching an age) ───────────────────────────────────
# Built in vanilla's own shapes: "C-Bonus, +50g" (Starting Gold once a TC
# exists, 639 + 307) -> "Post-TC +50g" (stockpile); the Chinese "-200f -50w"
# (Starting Food/Wood on 639); "+200w in age2" (stockpile on the age).
R = lambda r, v: {"attr": "resources", "op": "add", "value": v, "resource": r}   # noqa: E731


def civ_card(age, *effs):
    got = cb.normalize([{"target": {"type": "civ", **({"age": age} if age else {})}, "effects": list(effs)}])
    return got[0] if got else None


print("\n=== resource cards ===")
check("start text", cb.card_text(civ_card(None, R("stone", 100))) == "+100 stone at the start")
check("age text", cb.card_text(civ_card(102, R("wood", 200))) == "+200 wood on reaching the Castle Age")
check("each text", cb.card_text(civ_card(None, R("each", 25))) == "+25 of each resource at the start")
check("a start penalty is allowed (the Chinese -200 food)",
      cb.card_text(civ_card(None, R("food", -200))) == "-200 food at the start")
check("a negative age grant is refused", civ_card(103, R("gold", -50)) is None)
steps = cb.civ_steps(civ_card(None, R("stone", 100)))
check("start +100 stone: Starting Stone (93) once a TC exists, then the stockpile after it",
      [(s["reqs"], s["after"], [(c.a, c.d) for c in s["cmds"]]) for s in steps]
      == [([639, 307], None, [(93, 100.0)]), ([], 0, [(2, 100.0)])], f"{steps}")

if dat_path is not None:
    # The vanilla shapes this copies, checked against the DAT itself.
    def shape(tid):
        t = dat.techs[tid]
        return ([r for r in t.required_techs if r >= 0],
                [(c.type, c.a, c.b) for c in dat.effects[t.effect_id].effect_commands])
    check("vanilla +100s (228) is Starting Stone after 639 + 307", shape(228) == ([639, 307], [(1, 93, 1)]),
          f"{shape(228)}")
    check("vanilla Post-TC +100s (261) is the stockpile after 228", shape(261) == ([228], [(1, 2, 1)]),
          f"{shape(261)}")
    check("vanilla +200w in age2 (851) is the stockpile on Feudal", shape(851) == ([101], [(1, 1, 1)]),
          f"{shape(851)}")

    print("\n=== built ===")
    def built(slot, c):
        civ = {"format": FORMAT_KEY, "alias": f"Res {slot}", "architecture": 2, "language": 0,
               "bonuses": [], "custom_bonuses": [c],
               "tree": {"units": [83], "buildings": [109, 70], "techs": [101, 102, 103]}}
        n = len(dat.techs)
        with contextlib.redirect_stdout(io.StringIO()):
            apply_civ(dat, civ, target_slot=slot)
        return [(i, [r for r in t.required_techs if r >= 0],
                 [(c.type, c.a, c.b, c.d) for c in dat.effects[t.effect_id].effect_commands])
                for i, t in enumerate(dat.techs) if i >= n and t.civ == slot and t.name == "C-Bonus, Custom"]
    got = built(7, civ_card(None, R("stone", 100)))
    check("start +100 stone builds two chained techs",
          len(got) == 2 and got[0][1] == [639, 307] and got[0][2] == [(1, 93, 1, 100.0)]
          and got[1][1] == [got[0][0]] and got[1][2] == [(1, 2, 1, 100.0)], f"{got}")
    got = built(8, civ_card(102, R("wood", 200)))
    check("+200 wood on Castle: one tech on 102 adding to the wood stockpile",
          got == [(got[0][0], [102], [(1, 1, 1, 200.0)])] if got else False, f"{got}")
    got = built(9, civ_card(None, R("food", -200)))
    check("-200 food at the start: Starting Food on 639 only",
          got == [(got[0][0], [639], [(1, 91, 1, -200.0)])] if got else False, f"{got}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
