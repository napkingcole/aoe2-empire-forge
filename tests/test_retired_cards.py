#!/usr/bin/env python3
"""The bonus catalog names every card an older civ may carry but the picker no
longer shows, so the wizard can offer to remove it (issue #78).

The grid is drawn from the catalog, so a withdrawn card in a saved civ was
invisible: still in the file, counted in "N selected", and impossible to
untick.  Cards leave the picker four ways — unsupported, DEPRECATED_BONUSES,
inert on this DAT, or hidden by their bonus_cards.json override — and the
`retired` block must cover all of them.

    venv/bin/python tests/test_retired_cards.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as A                                     # noqa: E402
from bonus_names import DEPRECATED_BONUSES          # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


r = A.app.test_client().get("/api/builder/bonuses/catalog").get_json()
retired = r["retired"]["civ"]
offered = {c["id"] for c in r["civ"]}
names = json.loads((ROOT / "bonus_names.json").read_text(encoding="utf-8"))
cards = json.loads((ROOT / "static/data/bonus_cards.json").read_text(encoding="utf-8"))

print("every named card the picker hides is listed")
hidden_by_card = {k for k, v in cards.items()
                  if isinstance(v, dict) and (v.get("hidden") or v.get("type") == "hidden")}
for k in names:
    if int(k) not in offered or k in hidden_by_card:
        check(f"{k} {names[k][:50]}", k in retired)
check("no card the picker shows normally is listed",
      not [k for k in retired if int(k) in offered and k not in hidden_by_card])

print("each says where the choice went")
for k, sup in DEPRECATED_BONUSES.items():
    if str(k) in retired and sup is not None:
        check(f"{k} -> {sup}", retired[str(k)]["successor"] == names[str(sup)],
              retired[str(k)]["successor"])
check("333 (withdrawn) has no successor", retired["333"]["successor"] is None)
check("280 (Folwark) moved to the tech tree", retired["280"]["successor"] == "the tech tree")
check("343 (Jian) names its Unlock card", "Jian" in (retired["343"]["successor"] or ""))

print("team bonuses")
team_offered = {c["id"] for c in r["team"]}
check("no offered team bonus is listed", not [k for k in r["retired"]["team"] if int(k) in team_offered])

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
