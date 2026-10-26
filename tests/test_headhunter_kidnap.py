#!/usr/bin/env python3
"""The KM Headhunter kidnaps villagers, as in KM's builder.  DAT-gated.

The Scythian Scout's kidnap task (852, action 135, class 4 = villagers) after
the attack only attacked in game (2026-10-25), so mode "first" puts it ahead of
the attack; mode "twin" is KM's swappable kidnapper form (civbuilder.cpp:2768).
Both carry 1 (Elite 2).  Tasks must be on every civ's copy (and the shared
header for a unit that has one), so this saves the DAT and reads it back.

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
import km_custom_uu                                 # noqa: E402

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
_spec = km_custom_uu.PRESETS[HEADHUNTER]["extra"]["kidnap"]
_spec["mode"] = "twin"
t = build(SLOT + 2, HEADHUNTER)
_spec.pop("mode")
twin_ids = (t["uu_id"] + 2, t["uu_id"] + 3)   # appended right after the unit
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
    check(f"{tier}: kidnap comes before the attack, or the attack wins",
          u.bird.tasks[0].action_type == KIDNAP, [x.action_type for x in u.bird.tasks])
    check(f"{tier} keeps its attack", any(t.action_type == 7 for t in u.bird.tasks))
    check(f"{tier} carries {cap}", u.garrison_capacity == cap, u.garrison_capacity)
    # The header table is a fixed 1701 entries, so a new unit past it has none.
    check(f"{tier}: task on civ 0 (and the shared header, where the unit has one)",
          kidnaps(back.civs[0].units[uid].bird.tasks)
          and (uid >= len(back.unit_headers) or kidnaps(back.unit_headers[uid].task_list)))

print("twin mode (KM's swappable form)")
for uid, twin, cap in ((t["uu_id"], twin_ids[0], 1), (t["elite_uu_id"], twin_ids[1], 2)):
    u, f = back.civs[SLOT + 2].units[uid], back.civs[SLOT + 2].units[twin]
    check(f"unit {uid} fights and does not kidnap",
          not kidnaps(u.bird.tasks) and any(x.action_type == 7 for x in u.bird.tasks))
    check(f"form {twin} kidnaps and has no attack",
          kidnaps(f.bird.tasks) and not any(x.action_type == 7 for x in f.bird.tasks))
    check(f"form {twin} shares a fresh swap group with {uid}",
          u.bird.task_swap_group == f.bird.task_swap_group > 3, (u.bird.task_swap_group, f.bird.task_swap_group))
    check(f"form {twin} is not trainable and carries {cap}",
          all(l.unit_id == -1 for l in f.creatable.train_locations) and f.garrison_capacity == cap)
up = [(c.a, c.b) for c in back.effects[back.techs[t["km_uu_elite_tech_id"]].effect_id].effect_commands if c.type == 3]
check("the elite upgrade also upgrades the kidnapper form", (twin_ids[0], twin_ids[1]) in up, up)

print("other units")
check("another KM unit (Teulu) does not kidnap",
      not kidnaps(back.civs[SLOT + 1].units[other["uu_id"]].bird.tasks))

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
