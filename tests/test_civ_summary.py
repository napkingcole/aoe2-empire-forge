#!/usr/bin/env python3
"""The civ share page's summary (#57).

One summary feeds the page, the Markdown and the plain text, so they can't
disagree.  Bonus, unique-tech and team-bonus wording is the in-game wording.
The tech tree lists standard nodes a civ is missing (most civs have them) and
regional ones it has — nobody "misses" an Eagle Warrior.  The endpoint takes
an Empire Forge file, a Builder draft or a KM file.

    venv/bin/python tests/test_civ_summary.py
"""
import contextlib
import copy
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import civ_summary as cs                                    # noqa: E402
from civ_schema import FORMAT_KEY, to_draft                 # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


TECHTREE = json.loads((ROOT / "static/aoe2techtree/data/trees/FULL.json").read_text(encoding="utf-8"))
UU_CATALOG = [{"km_idx": 3, "name": "Teutonic Knight", "icon": "/resources/uniticons/045_50730.png",
               "training_cost": "85F 30G", "elite_upgrade": {"cost": {"food": 950, "gold": 500}, "time": 50},
               "stats": {"ranged": False,
                         "base": {"hp": 90, "attack": 14, "bonuses": [["buildings", 4]]},
                         "elite": {"hp": 110, "attack": 17}}}]
STANDARD = {"units": [83, 74, 75, 77, 473, 567, 93, 358, 359, 4, 24, 492, 7, 6, 448, 546, 441, 38, 283],
            "buildings": [12, 87, 101, 49, 45, 82, 104, 109, 70, 68, 562, 584, 103, 209, 84],
            "techs": [101, 102, 103]}
CIV = {"format": FORMAT_KEY, "schema_version": 2, "alias": "Testers", "tagline": "Infantry",
       "description": "A civ for tests.",
       "bonuses": [{"id": 4, "multiplier": 1}, {"id": 14, "multiplier": 2}],
       "custom_bonuses": [{"target": {"type": "civ"}, "effects": [{"attr": "pop_cap", "op": "add", "value": 10}]}],
       "team_bonuses": [{"id": 82, "multiplier": 1}],
       "unique_unit": {"km_idx": 3, "name": "Iron Knight", "overrides": {"hp_base": 100}},
       "castle_ut": {"mode": "custom", "name": "Steel Wargear", "description": "Upgrades wargear.",
                     "effects": [{"id": 1, "multiplier": 1}]},
       "imperial_ut": {"mode": "custom", "name": "Hard Steel (Infantry +2 armor)", "description": "",
                       "effects": [{"id": 1, "multiplier": 1}]},
       "hero_unit": {"base_unit_id": 1966, "name": "Palintonon", "description": "A hero."},
       "tree": STANDARD}
names = json.loads((ROOT / "bonus_names.json").read_text(encoding="utf-8"))
team = json.loads((ROOT / "team_bonus_names.json").read_text(encoding="utf-8"))

print("=== summary ===")
s = cs.summarize(copy.deepcopy(CIV), UU_CATALOG, TECHTREE)
check("name and tagline", s["name"] == "Testers" and s["tagline"] == "Infantry civilization")
check("bonus text is the in-game text, with the multiplier",
      s["civ_bonuses"][:2] == [names["4"], names["14"] + " [x2]"], f"{s['civ_bonuses'][:2]}")
check("custom bonus cards are included", "+10 population limit" in s["civ_bonuses"])
check("team bonus text", s["team_bonuses"] == [team["82"]])
u = s["unique_unit"]
check("UU: the player's name, the base unit noted", u["name"] == "Iron Knight" and u["base_name"] == "Teutonic Knight")
hp = next(r for r in u["stats"] if r["label"] == "HP")
check("an overridden stat shows the new value, marked", hp["base"] == 100 and hp["elite"] == 110 and hp["changed"])
check("elite upgrade cost from the game", u["elite_upgrade"] == "950 food, 500 gold, 50s", u["elite_upgrade"])
check("unique techs in the game's form",
      [t["text"] for t in s["unique_techs"]] == ["Steel Wargear (Upgrades wargear)", "Hard Steel (Infantry +2 armor)"],
      f"{[t['text'] for t in s['unique_techs']]}")
check("hero", s["hero"] == {"name": "Palintonon", "description": "A hero."})

print("\n=== tech tree ===")
tt = {b["building"]: b for b in s["tech_tree"]["buildings"]}
barracks_missing = tt.get("Barracks", {}).get("missing", [])
check("regional units aren't 'missing' (no Eagle Warrior, no Fire Lancer)",
      not ({"Eagle Scout", "Fire Lancer", "Champi Scout"} & set(barracks_missing)), f"{barracks_missing}")
check("a standard tech the civ lacks is missing (Gambesons)", "Gambesons" in barracks_missing, f"{barracks_missing}")
regional = cs.summarize(dict(copy.deepcopy(CIV), tree={**STANDARD, "units": STANDARD["units"] + [1132, 1134]}),
                        UU_CATALOG, TECHTREE)
stable = {b["building"]: b for b in regional["tech_tree"]["buildings"]}.get("Stable", {})
check("a regional unit the civ has is an extra (Battle Elephant)", "Battle Elephant" in stable.get("extras", []),
      f"{stable}")
mule = cs.summarize(dict(copy.deepcopy(CIV), tree={**STANDARD, "buildings": [b for b in STANDARD["buildings"]
                                                                            if b not in (562, 584)] + [1808]}),
                    UU_CATALOG, TECHTREE)
check("camps a Mule Cart replaces aren't listed as missing",
      not ({"Lumber Camp", "Mining Camp"} & set(mule["tech_tree"]["missing_buildings"])),
      f"{mule['tech_tree']['missing_buildings']}")

print("\n=== copy formats ===")
md, txt = cs.to_markdown(s), cs.to_text(s)
check("Markdown has the title and sections",
      md.startswith("# Testers") and "## Civilization bonuses" and "## Unique unit" in md and "## Tech tree" in md)
check("Markdown marks changed stats", "HP 100/110*" in md, md[md.find("Stats"):md.find("Stats") + 80])
check("plain text has no Markdown markup", "#" not in txt.split("\n")[0] and "**" not in txt)
check("both say the same bonuses", all(b in md and b in txt for b in s["civ_bonuses"]))

print("\n=== endpoint: three shapes in, one summary out ===")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
c = A.app.test_client()
A._uu_catalog_entries = lambda: UU_CATALOG            # keep the test DAT-free
for label, body in (("Empire Forge file", copy.deepcopy(CIV)),
                    ("Builder draft", to_draft(copy.deepcopy(CIV)))):
    r = c.post("/api/civ/summary", json={"civ": body})
    d = r.get_json()
    check(f"{label}: 200 with summary, markdown and text",
          r.status_code == 200 and d["summary"]["name"] == "Testers" and d["markdown"] and d["text"],
          f"{r.status_code} {d.get('error')}")
km_files = [f for f in sorted((ROOT / "my_civs").glob("*.json"))
            if "format" not in json.loads(f.read_text(encoding="utf-8"))]
if km_files:
    km = json.loads(km_files[0].read_text(encoding="utf-8"))
    r = c.post("/api/civ/summary", json={"civ": km})
    d = r.get_json()
    check(f"KM file ({km_files[0].name}): 200 with bonuses",
          r.status_code == 200 and d["summary"]["civ_bonuses"], f"{r.status_code} {d.get('error')}")
else:
    print("  skip  no KM-format civ in my_civs/")
r = c.post("/api/civ/summary", json={"civ": "nonsense"})
check("not a civ: 400 with a message, not a 500", r.status_code == 400 and r.get_json().get("error"))
r = c.get("/civ/view")
check("the page renders", r.status_code == 200 and b"View a Civilization" in r.data)

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
