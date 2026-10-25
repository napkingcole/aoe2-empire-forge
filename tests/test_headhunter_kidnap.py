#!/usr/bin/env python3
"""The KM Headhunter kidnaps villagers, as in KM's builder.  DAT-gated.

KM (civbuilder.cpp:2768) gave the Headhunter a swappable kidnapper form; ours
puts the Scythian Scout's kidnap task (852, action 135, class 4 = villagers)
beside its attack, and room to carry 1 (Elite 2).  The task must be on every
civ's copy (and the shared header for a unit that has one), so this saves the DAT and reads it back.

    venv/bin/python tests/test_headhunter_kidnap.py
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat      # noqa: E402
from dat_lazy import save_bytes                     # noqa: E402
from civ_appender import apply_civ                  # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found")
    sys.exit(0)

HEADHUNTER, TEULU, KIDNAP, SLOT = 63, 64, 135, 5
dat = load_dat(str(dat_path))


def build(slot, km_idx):
    civ_def = {"alias": f"Kidnap Probe {slot}", "description": "", "architecture": 2,
               "language": 0, "wonder": -1, "castle": -1,
               "bonuses": [[], [km_idx], [], [], []], "tree": [[], [], []]}
    with contextlib.redirect_stdout(io.StringIO()):
        return apply_civ(dat, civ_def, target_slot=slot)


r = build(SLOT, HEADHUNTER)
other = build(SLOT + 1, TEULU)
uu, elite = r["uu_id"], r["elite_uu_id"]

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "empires2_x2_p1.dat"
    out.write_bytes(save_bytes(dat))
    back = load_dat(str(out))


def kidnaps(tasks):
    return [(t.class_id, round(t.work_range, 2), t.target_diplomacy)
            for t in tasks or () if t.action_type == KIDNAP]


print("Headhunter (read back from the saved DAT)")
for uid, tier, cap in ((uu, "Headhunter", 1), (elite, "Elite Headhunter", 2)):
    u = back.civs[SLOT].units[uid]
    check(f"{tier} kidnaps villagers, like the Scythian Scout",
          kidnaps(u.bird.tasks) == kidnaps(back.civs[0].units[852].bird.tasks) == [(4, 0.25, 2)],
          kidnaps(u.bird.tasks))
    check(f"{tier} keeps its attack", any(t.action_type == 7 for t in u.bird.tasks))
    check(f"{tier} carries {cap}", u.garrison_capacity == cap, u.garrison_capacity)
    # The header table is a fixed 1701 entries, so a new unit past it has none.
    check(f"{tier}: task on civ 0 (and the shared header, where the unit has one)",
          kidnaps(back.civs[0].units[uid].bird.tasks)
          and (uid >= len(back.unit_headers) or kidnaps(back.unit_headers[uid].task_list)))

print("other units")
check("another KM unit (Teulu) does not kidnap",
      not kidnaps(back.civs[SLOT + 1].units[other["uu_id"]].bird.tasks))

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
