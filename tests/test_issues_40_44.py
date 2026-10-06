#!/usr/bin/env python3
"""Pin the 2026-09-29 Discord batch (issues #38, #40, #41, #44).

Each was a silent failure the build reported as success, so every assertion
reads the built DAT (or the produced bytes), not the catalog.

  #40/#41  Folwark missing — the unticked-entity sweep forced the Mill off, and
           the Folwark only exists as an EC_UPGRADE of the Mill's button.
  #40      Huns bonus kept the House — the pop cap came across, the TT type=2
           that hides the House did not.
  #41      Free relic — the chain continues through helper unit 1118, whose
           building.tech_id still named the Armenian-gated original.
  (sweep)  Sibling disables (bonuses 38, 346, 223) named the originals, so
           both halves of an either/or pair could fire.
  #38      A newline in a UT description split the civ-selection string.
  #44      JPEG/WebP flags — WebP's data-URI prefix was never stripped.
"""
import base64
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures = 0


def check(label, ok, detail=""):
    global failures
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        failures += 1
        if detail:
            print(f"       {detail}")


# ── Pure checks first: no DAT needed ─────────────────────────────────────────
from wizard_build import _kv_text                                  # noqa: E402

check("#38 a newline becomes the literal \\n the game renders",
      _kv_text("one\ntwo\r\nthree") == "one\\ntwo\\nthree")
check("#38 a bare double quote is escaped the way vanilla files do",
      _kv_text('the "best" tech') == 'the \\"best\\" tech')
check("#38 a hand-typed \\n and an already-escaped quote survive untouched",
      _kv_text('a\\nb \\"c\\"') == 'a\\nb \\"c\\"')

try:
    from PIL import Image
    from build_civ import _decode_flag
    for fmt, mime in (("JPEG", "jpeg"), ("WEBP", "webp"), ("PNG", "png")):
        buf = io.BytesIO()
        Image.new("RGB", (300, 200), (200, 30, 30)).save(buf, fmt)
        uri = f"data:image/{mime};base64," + base64.b64encode(buf.getvalue()).decode()
        out = _decode_flag({"customFlagData": uri})
        ok = bool(out) and out.startswith(b"\x89PNG") \
            and Image.open(io.BytesIO(out)).size == (104, 104)
        check(f"#44 a {fmt} flag becomes a 104x104 PNG", ok)
except ImportError:
    check("#44 Pillow is installed (requirements.txt)", False,
          "without it only PNG flags survive, unresized")

cards = json.loads((ROOT / "static/data/bonus_cards.json").read_text(encoding="utf-8"))
check("#41 bonus 324 (villager aura) is withdrawn from the picker",
      cards["324"].get("type") == "hidden")

# ── One build carrying every DAT-side fix ────────────────────────────────────
from dat_reader import find_game_dat, load_dat                    # noqa: E402
from civ_appender import apply_civ, EC_ENABLE                     # noqa: E402

dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found — DAT checks not run")
    sys.exit(1 if failures else 0)

poles = json.loads((ROOT / "static/aoe2techtree/data/trees/POLES.json").read_text(encoding="utf-8"))
live = [n for n in poles["buildings"] + poles["units_techs"]
        if n.get("node_status") != "NotAvailable"]
tree = [
    sorted({n["node_id"] for n in poles["units_techs"] if n in live and n["use_type"] == "Unit"}),
    sorted({n["node_id"] for n in poles["buildings"] if n in live}),
    sorted({n["node_id"] for n in poles["units_techs"] if n in live and n["use_type"] == "Tech"}),
]
check("the Poles template has a Folwark and no Mill (the reporter's input)",
      1734 in tree[1] and 68 not in tree[1])

CIV = {
    "alias": "Issues40to44", "architecture": 1, "language": 0,
    "bonuses": [[[131, 1], [313, 1], [38, 1], [346, 1], [223, 1]], [], [], [], []],
    "tree": tree,
}

import contextlib                                                  # noqa: E402
dat = load_dat(dat_path)
with contextlib.redirect_stdout(io.StringIO()):
    ci = apply_civ(dat, CIV, target_slot=1)["civ_index"]
civ = dat.civs[ci]
ours = {i for i, t in enumerate(dat.techs) if t.civ == ci}

# #40/#41 Folwark: vanilla Poles ship Mill enabled / Folwark disabled; the
# Folwark tech converts the Mill's button, so the Mill must stay on.
check("#40 the Mill stays enabled so the Folwark upgrade has a button to take",
      civ.units[68].enabled == 1, f"Mill enabled = {civ.units[68].enabled}")
folwark = [i for i in ours if dat.techs[i].name == "C-Bonus, Enable Folwark"]
check("#40 the Folwark tech was copied to this civ", len(folwark) == 1)

# #40 Huns: the House button is hidden exactly as vanilla Huns do it.
tt = dat.effects[civ.tech_tree_id].effect_commands
check("#40 bonus 131 hides the House (type=2 a=70 b=0 in the TT effect)",
      any(c.type == EC_ENABLE and c.a == 70 and int(c.b) == 0 for c in tt))
check("#40 bonus 131 still lifts the pop cap",
      any(c.type == 1 and c.a == 4 and c.d == 2000.0 for c in tt))

# #41 relic: helper unit 1118 must research OUR copy of 957.
tid_1118 = civ.units[1118].building.tech_id
check("#41 the relic helper unit researches this civ's copy of 'Free Relic2'",
      tid_1118 in ours and dat.techs[tid_1118].name == "C-Bonus, Free Relic2",
      f"1118 -> {tid_1118} ({dat.techs[tid_1118].name}, civ {dat.techs[tid_1118].civ})")
check("#41 other civs' relic helper is untouched",
      dat.civs[2].units[1118].building.tech_id == 957)

# Sweep: every type=102 inside one of our bonus copies must name one of ours.
stray = []
for i in ours:
    eid = dat.techs[i].effect_id
    for c in dat.effects[eid].effect_commands if 0 <= eid < len(dat.effects) else []:
        if c.type == 102 and int(c.d) not in ours and dat.techs[int(c.d)].civ != -1:
            stray.append(f"{dat.techs[i].name} disables {int(c.d)} {dat.techs[int(c.d)].name}")
check("bonuses 38/346/223 disable their own copies, not the originals",
      not stray, "; ".join(stray))

# Free relic x3: three relics, but still ONE trigger helper.  Both techs are
# repeatable, so scaling the helper too would multiply twice (nine relics).
def _spawns(civ_i, name):
    return [(int(c.a), int(c.c)) for i, t in enumerate(dat.techs)
            if t.civ == civ_i and t.name == name
            for c in dat.effects[t.effect_id].effect_commands if c.type == 7]


x3 = {"alias": "RelicX3", "architecture": 1, "language": 0,
      "bonuses": [[[313, 3]], [], [], [], []], "tree": [[], [], []]}
with contextlib.redirect_stdout(io.StringIO()):
    ci3 = apply_civ(dat, x3, target_slot=3)["civ_index"]
check("bonus 313 x3 spawns three relics", _spawns(ci3, "C-Bonus, Free Relic2") == [(285, 3)],
      str(_spawns(ci3, "C-Bonus, Free Relic2")))
check("bonus 313 x3 leaves the trigger helper at one",
      _spawns(ci3, "C-Bonus, Free Relic") == [(1118, 1)], str(_spawns(ci3, "C-Bonus, Free Relic")))
check("bonus 313 offers a multiplier", "multiplier" not in cards["313"])

print()
print("PASS" if not failures else f"{failures} FAILURE(S)")
sys.exit(1 if failures else 0)
