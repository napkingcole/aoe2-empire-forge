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
up = [(c.a, c.b) for c in back.effects[back.techs[r["km_uu_elite_tech_id"]].effect_id].effect_commands
      if c.type == 3]
for uid, twin, tier, cap in ((uu, uu + 2, "Headhunter", 1), (elite, uu + 3, "Elite Headhunter", 2)):
    for ci, where in ((SLOT, "its civ"), (0, "civ 0")):
        u, f = back.civs[ci].units[uid], back.civs[ci].units[twin]
        check(f"{tier} ({where}) fights and has no kidnap task",
              not kidnaps(u.bird.tasks) and any(x.action_type == 7 for x in u.bird.tasks))
        check(f"its form {twin} ({where}) kidnaps like the Scythian Scout, with no attack",
              kidnaps(f.bird.tasks) == kidnaps(back.civs[0].units[852].bird.tasks) == [(4, 0.25, 2)]
              and not any(x.action_type == 7 for x in f.bird.tasks), [x.action_type for x in f.bird.tasks])
        check(f"{tier} and its form share a fresh swap group ({where})",
              u.bird.task_swap_group == f.bird.task_swap_group > 3,
              (u.bird.task_swap_group, f.bird.task_swap_group))
    u, f = back.civs[SLOT].units[uid], back.civs[SLOT].units[twin]
    check(f"{tier} and its form carry {cap}", u.garrison_capacity == f.garrison_capacity == cap)
    check(f"form {twin} is not trainable", all(l.unit_id == -1 for l in f.creatable.train_locations))
check("the elite upgrade also upgrades the kidnapper form", (uu + 2, uu + 3) in up, up)

print("other units")
check("another KM unit (Teulu) does not kidnap",
      not kidnaps(back.civs[SLOT + 1].units[other["uu_id"]].bird.tasks))

print("PASS" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
