#!/usr/bin/env python3
"""A replaced civ leaves nothing of itself behind (#66).

Two surfaces outside the DAT still described the ORIGINAL civ:

  civilizations.json  unique_tech_id_1/2 and unique_unit_line kept the
                      replaced civ's values (Ionians-over-Gurjaras still named
                      Frontier Guards / Kshatriyas and the Chakram line)
  CivTechTrees        another civ's unique unit ticked in the tree kept its node
                      lit — Ionians-over-Goths showed the Goths' Huskarl in F2,
                      though the build never lets the civ train it

The first part is pure; the second needs the game DAT and skips without it.

    venv/bin/python tests/test_replaced_civ_leftovers.py
"""
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from civ_appender import patch_civilizations_list   # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f" — {extra}" if extra else ""))


print("=== civilizations.json names the new civ's UTs and UU line ===")
base = json.loads((ROOT / "civilizations.json").read_text(encoding="utf-8"))["civilization_list"]
names = [e["internal_name"] for e in base]
GURJ, TEUT, BRIT = names.index("Gurjaras"), names.index("Teutons"), names.index("Britons")
civ_list = json.loads(json.dumps(base))
patch_civilizations_list(civ_list, {
    # A second civ in the same mod over the Teutons, with a KM-custom UU —
    # listed first, so its entry is rewritten before Gurjaras reads the line
    TEUT: {"name_sid": 10271, "icon_id": 60, "uu_unit_id": 1700, "uu_elite_id": 1701,
           "castle_ut_tech_id": 1520, "imp_ut_tech_id": 1521},
    # Ionians over Gurjaras: Teutonic Knight, UT stubs 1510 (Castle) / 1511 (Imperial)
    GURJ: {"name_sid": 10312, "icon_id": 45, "uu_unit_id": 25, "uu_elite_id": 554,
           "uu_upgrade_tech_id": 1514, "uu_name_sid": 5112, "uu_desc_sid": 26112,
           "castle_ut_tech_id": 1510, "imp_ut_tech_id": 1511},
})
g = civ_list[GURJ]
check("Imperial UT -> unique_tech_id_1, Castle UT -> _2",
      (g["unique_tech_id_1"], g["unique_tech_id_2"]) == (1511, 1510),
      f"{g['unique_tech_id_1']}, {g['unique_tech_id_2']}")
check("a vanilla UU takes its home civ's line (Teutonic Knight -> -272)",
      g["unique_unit_line"] == base[TEUT]["unique_unit_line"] == -272, f"{g['unique_unit_line']}")
check("...even when that home civ's slot was rewritten first in the same mod",
      civ_list[TEUT]["unique_unit_id"] == 1700 and g["unique_unit_line"] == -272)
check("the UU fields still follow the new UU",
      (g["unique_unit_id"], g["elite_unique_unit_id"], g["unique_unit_upgrade_id"]) == (25, 554, 1514))
check("an untouched civ is untouched", civ_list[BRIT] == base[BRIT])

try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                    # noqa: BLE001
    dat_path = None
if dat_path is None:
    print("  skip  no game DAT found — F2 tree checks need it")
else:
    from civ_appender import apply_civ
    from build_civ import _patch_per_civ_techtree
    from civ_schema import FORMAT_KEY
    dat = load_dat(str(dat_path))
    slot_of = {c.name: i for i, c in enumerate(dat.civs)}

    def f2_units(civ_def, civ_name, tree_file):
        slot = slot_of[civ_name]
        with contextlib.redirect_stdout(io.StringIO()):
            result = apply_civ(dat, civ_def, target_slot=slot)
            data = json.loads(_patch_per_civ_techtree(
                ROOT / "CivTechTrees" / tree_file, civ_def, dat, slot, result))
        return {n.get("Node ID"): n.get("Node Status") for n in data["civ_techs_units"]
                if n.get("Node Type") == "UniqueUnit"}

    print("\n=== F2: another civ's unique unit in the tree stays dark ===")
    BASE_TREE = [83, 13, 74, 75, 77, 4, 24, 38, 283, 539, 21, 442]
    goths_over = {"format": FORMAT_KEY, "alias": "Leftovers", "architecture": 2, "language": 0,
                  "bonuses": [], "unique_unit": {"km_idx": 3},
                  "tree": {"units": BASE_TREE + [41, 759, 761, 8, 46],
                           "buildings": [12, 87, 101, 45, 82, 109, 70], "techs": [101, 102, 103]}}
    st = f2_units(goths_over, "Goths", "GOTHS.json")
    check("the Goths' Huskarl is not shown", st.get(759) == st.get(761) == "NotAvailable", f"{st}")
    check("the civ's own Teutonic Knight is", st.get(25) == "ResearchedCompleted", f"{st}")

    print("\n=== F2: unique units a card grants still show ===")
    for card, civ_name, tree_file, uid, what in (
            (69, "Portuguese", "PORTUGUESE.json", 1004, "Caravel (card 69)"),
            (282, "Lithuanians", "LITHUANIANS.json", 1707, "Winged Hussar (card 282)")):
        civ_def = {**goths_over, "bonuses": [{"id": card, "multiplier": 1}],
                   "tree": {**goths_over["tree"], "units": BASE_TREE + [uid]}}
        st = f2_units(civ_def, civ_name, tree_file)
        check(f"{what} shows over the {civ_name}", st.get(uid) == "ResearchedCompleted", f"{st}")

print()
print("FAIL" if failures else "PASS", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
