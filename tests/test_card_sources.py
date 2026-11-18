#!/usr/bin/env python3
"""Where a card comes from (#95): app._card_sources and the emblem lookup.

A vanilla bonus, team bonus or unique tech wears the emblem of the civ it was
taken from, read from the game: the civ-gated techs a bonus copies, the civ
whose team bonus effect a team card copies, a unique tech's vanilla tech.
A card from no civ, or from more than one, wears none.  DAT-gated.

    venv/bin/python tests/test_card_sources.py
"""
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


try:
    from dat_reader import find_game_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

with contextlib.redirect_stdout(io.StringIO()):
    import app                                               # noqa: E402
src = app._card_sources(str(dat_path))
name = lambda table, k: src["civs"].get(str(src[table].get(str(k))), {}).get("name")   # noqa: E731
civ_names = json.loads((ROOT / "bonus_names.json").read_text(encoding="utf-8"))
team_names = json.loads((ROOT / "team_bonus_names.json").read_text(encoding="utf-8"))

check("Foragers work 15% faster (5) is the Franks'", name("civ", 5) == "Franks", civ_names.get("5"))
check("Archer armor upgrades free (49) is the Koreans'", name("civ", 49) == "Koreans", civ_names.get("49"))
check("Archery Ranges work 10% faster (team 2) is the Britons'", name("team", 2) == "Britons", team_names.get("2"))
check("a bonus whose techs belong to two civs (281: the Poles' and Gaia's) wears none",
      "281" not in src["civ"], name("civ", 281))
check("every unique tech preset has a source", len(src["castle"]) >= 60 and len(src["imperial"]) >= 55,
      (len(src["castle"]), len(src["imperial"])))
check("DAT names that differ read as the civ's: British -> Britons, French -> Franks",
      {"Britons", "Franks", "Byzantines", "Mayans", "Hindustanis"} <= {c["name"] for c in src["civs"].values()})
missing = [c["emblem"] for c in src["civs"].values() if app._civ_emblem_path(str(dat_path), c["emblem"]) is None]
check("every civ offered has an emblem (the game's, else the copy on disk)", not missing, missing)
check("the copy on disk serves without a game (the Hindustanis' is hindustanis.png there, indians.png in it)",
      app._civ_emblem_path(None, "hindustanis") is not None)

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
