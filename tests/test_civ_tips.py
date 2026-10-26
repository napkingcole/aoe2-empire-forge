#!/usr/bin/env python3
"""Loading-screen tips: four IDS_CIVTIPS_<slot>_<n> lines per custom civ.

The game keys the tips by civ slot (IDS_CIVTIPS_1_0 is a Britons tip).  Every
slot is filled, or the replaced civ's own tip shows.  The strings-file
sanitizer used to know only numeric ids and glued a named line onto the entry
before it.

    venv/bin/python tests/test_civ_tips.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_all import civ_tip_lines, sanitize_kv_strings   # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f"\n       {extra}"))
    failures += not cond


full = civ_tip_lines(5, ["Cavalry +20% HP", "Monks heal faster"], "Headhunter",
                     [("Wooden Castles", "Castles become Wooden Forts"), ("Ironclad", "")],
                     ["Stables work faster"])
check("four tips for the civ's own slot", [l.split(" ", 1)[0] for l in full]
      == [f"IDS_CIVTIPS_5_{i}" for i in range(4)], full)
check("bonus, unique unit, Castle UT, Imperial UT", full == [
    'IDS_CIVTIPS_5_0 "Civilization bonus: Cavalry +20% HP."',
    'IDS_CIVTIPS_5_1 "Your unique unit is the Headhunter."',
    'IDS_CIVTIPS_5_2 "Research Wooden Castles in your Castle: Castles become Wooden Forts."',
    'IDS_CIVTIPS_5_3 "Research Ironclad in your Castle in the Imperial Age."'], full)

bare = civ_tip_lines(7, [], "Teulu", [("", ""), ("", "")], ["Stables work faster"])
check("missing tips are stood in for, never left out", len(bare) == 4
      and all(l.split('"')[1] for l in bare), bare)
check("the team bonus stands in", 'Team bonus: Stables work faster.' in bare[0], bare)

q = civ_tip_lines(3, ['Say "hi"\nlater'], "X", [("A", ""), ("B", "")], [])
check("quotes escaped, newlines flattened", q[0] == r'IDS_CIVTIPS_3_0 "Civilization bonus: Say \"hi\" later."', q[0])

content = '1 "one"\n' + "\n".join(full) + '\n2 "two"\n'
out, repaired = sanitize_kv_strings(content)
check("the sanitizer keeps named lines as their own entries", out == content and not repaired, out)

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
