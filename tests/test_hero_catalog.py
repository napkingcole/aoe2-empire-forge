#!/usr/bin/env python3
"""The Heroes tab's catalog comes from the player's DAT.  DAT-gated.

Until 2026-10-22 the tab was a hand-typed list of 30.  heroes.hero_catalog now
offers every hero the game can place (~215), with stats from the DAT, and keeps
only what the DAT can't say in static/data/hero_notes.json.  Pinned here:

  - every hero the notes list is still offered (Saladin is hidden from the
    editor, the Warwolf Trebuchet is type 80 — both were offered before);
  - no animal and no ship (a ship would train at the Castle, on land);
  - names are the game's own: unit 1269 is Girgen Khan, not the "Genghis Khan"
    the old list called it, and the real Genghis Khan (731) is offered too;
  - stats are the DAT's (the old hand-typed blocks matched it exactly);
  - every hero has a train slot for civ_appender._place_hero to move.

    venv/bin/python tests/test_hero_catalog.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dat_reader import find_game_dat, load_dat, find_unit_icon   # noqa: E402

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

import app                                                        # noqa: E402
import heroes                                                     # noqa: E402
from civ_appender import _string_table                            # noqa: E402

dat = load_dat(str(dat_path))
units = dat.civs[0].units
cat = heroes.hero_catalog(dat, app._unit_stats_block,
                          lambda u: _string_table().get(u.language_dll_name))
by_id = {h["id"]: h for h in cat}
notes = {int(k): v for k, v in json.loads(
    (ROOT / "static/data/hero_notes.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}

print("=== the catalog ===")
check("about two hundred heroes", len(cat) >= 200, f"{len(cat)}")
check("every hero in the notes is offered", set(notes) <= set(by_id), sorted(set(notes) - set(by_id)))
check("the three multiplayer heroes come first",
      [h["category"] for h in cat[:3]] == ["multiplayer"] * 3, [h["name"] for h in cat[:3]])
check("no two heroes share a name", len({h["name"] for h in cat}) == len(cat))
check("no animals", not [h for h in cat if units[h["id"]].class_ == 10])
check("no ships", not [h for h in cat if units[h["id"]].class_ == 22])
check("every hero has a train slot to move to the Castle",
      all(units[h["id"]].creatable and units[h["id"]].creatable.train_locations for h in cat))

print("\n=== names are the game's ===")
check("1269 is Girgen Khan", by_id.get(1269, {}).get("name") == "Girgen Khan", by_id.get(1269))
check("the real Genghis Khan (731) is offered", by_id.get(731, {}).get("name") == "Genghis Khan", by_id.get(731))
check("a codename never shows as a name",
      not [h for h in cat if h["name"] == units[h["id"]].name and h["name"].isupper()],
      [h["name"] for h in cat if h["name"] == units[h["id"]].name][:5])

print("\n=== stats are the DAT's ===")
for uid, hp, attack in ((432, 400, 20), (1954, 475, 14)):      # William Wallace, Cao Cao
    s = by_id[uid]["stats"]
    check(f"{by_id[uid]['name']}: {hp} HP, {attack} attack", (s["hp"], s["attack"]) == (hp, attack), s)
check("notes' abilities ride along", by_id[1954]["stats"]["specials"] == notes[1954]["specials"])
check("new heroes get no invented abilities",
      all(not h["stats"]["specials"] for h in cat if h["id"] not in notes))

print("\n=== icons come from the game ===")
missing = [h["name"] for h in cat if find_unit_icon(dat_path, units[h["id"]].icon_id) is None]
if find_unit_icon(dat_path, units[432].icon_id) is None:
    print("  skip  this DAT is not inside a game install (no widgetui icons)")
else:
    check("every hero's icon is in the game", not missing, missing[:8])

print("\nPASS" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
