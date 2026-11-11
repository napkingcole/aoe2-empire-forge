#!/usr/bin/env python3
"""Unit cards retired into the tech tree (2026-11-11): every card the audit of
2026-11-10 retires lands in the tree, the hero panel or a Look — none is lost
(the user's rule) — on the wizard's draft and on a KM file, and a build of the
converted civ does what the card did.

    venv/bin/python tests/test_retired_cards.py
"""
import contextlib
import copy
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


from retired_cards import (HERO_CARDS, LOOK_CARDS, RETIRED, UNIT_CARDS,  # noqa: E402
                           UPGRADE_CARDS, retire_cards)

# The audit (memory: project_unlock_cards_retirement), by group.
AUDIT_RETIRED = {
    *range(405, 416), 428, *range(447, 456), 361, 298,     # regional / Chronicles units
    43, 50, 69, 322, 61, 51,                               # KM units, Slinger, Longboats
    338, 344, 349,                                         # heroes
    53, 286, 308, 309, 310,                                # upgrades past a line's end
    457,                                                   # Palintonon
}
STILL_CARDS = {282, 307, 416, 314, 417, 456, 362, 402,    # replacements: step 3
               103, 332, 360, 99, 283, 352, 221, 300}     # earlier-age cards: kept

print("=== the table ===")
check("every audited card is retired", AUDIT_RETIRED <= RETIRED, sorted(AUDIT_RETIRED - RETIRED))
check("nothing else is (replacements and earlier-age cards stay cards)",
      not RETIRED & STILL_CARDS and RETIRED <= AUDIT_RETIRED, sorted(RETIRED - AUDIT_RETIRED))

units, buildings, techs = json.loads((ROOT / "my_civs" / "19_Cannoneers.json").read_text(encoding="utf-8"))["tree"] \
    if (ROOT / "my_civs" / "19_Cannoneers.json").exists() else ([4, 24, 36, 330, 542, 1134, 1372, 331], [], [])
for u in (36, 330, 542, 1134, 1372, 331):        # the units the upgrade cards extend
    if u not in units:
        units = units + [u]


def draft_with(*cards, hero=None):
    d = {"bonuses": [{"id": b, "multiplier": 1} for b in cards],
         "tree": {"units": list(units), "buildings": list(buildings), "techs": list(techs)}}
    if hero is not None:
        d["hero_unit"] = {"base_unit_id": hero, "name": "", "description": "", "overrides": {}, "flags": {}}
    return d


try:
    from dat_reader import find_game_dat, load_dat
    dat_path = find_game_dat()
except Exception:                                            # noqa: BLE001
    dat_path = None
dat = load_dat(str(dat_path)) if dat_path else None


def home_of(bid, d):
    """Where card bid went in converted draft d, or None."""
    if bid in UNIT_CARDS:
        return "tree" if set(UNIT_CARDS[bid]) <= set(d["tree"]["units"]) else None
    if bid == 51:
        return "tree" if {250, 533} <= set(d["tree"]["units"]) else None
    if bid in HERO_CARDS:
        return "hero" if (d.get("hero_unit") or {}).get("base_unit_id") == HERO_CARDS[bid] else None
    if bid in LOOK_CARDS:
        uid, e = LOOK_CARDS[bid]
        return "look" if (d.get("unit_edits") or {}).get(str(uid), {}).get("skin") == e["skin"] else None
    if bid in UPGRADE_CARDS:
        frm = UPGRADE_CARDS[bid][1]
        return "upgrade" if any(l.get("from") == frm for l in d.get("added_lines") or []) else None
    return None


print("\n=== every card lands somewhere (wizard draft) ===")
lost = {}
for bid in sorted(AUDIT_RETIRED):
    d = draft_with(bid)
    retire_cards(d, dat)
    where = home_of(bid, d)
    if where is None or any(b["id"] == bid for b in d["bonuses"]):
        lost[bid] = (where, [b["id"] for b in d["bonuses"]])
check(f"all {len(AUDIT_RETIRED)} cards moved, none kept", not lost, lost)

print("\n=== the details ===")
d = draft_with(309, 405, 3)
retire_cards(d, dat)
check("other cards stay", [b["id"] for b in d["bonuses"]] == [3], d["bonuses"])
line = next(l for l in d["added_lines"] if l["from"] == 1134)
check("309 is the picker's Royal Battle Elephant: Stable, Imperial, the card's stats and price",
      line["building"] == 101 and line["tiers"][0]["age"] == 4 and line["tiers"][0]["name"] == "Royal Battle Elephant"
      and line["tiers"][0]["edits"]["hp"] == 330 and line["tiers"][0]["upgrade"]["cost"] == {"food": 1200, "gold": 1000},
      line)
from civ_schema import norm_added_lines  # noqa: E402
check("...and a valid added line", len(norm_added_lines(d["added_lines"])) == 1)
if dat is not None:
    d = draft_with(286, 53)
    retire_cards(d, dat)
    h = next((l for l in d["added_lines"] if l["from"] == 36), {})
    check("286 is the game's Houfnice after the Bombard Cannon, at the game's price",
          h.get("base") == 1709 and h.get("building") == 49 and h["tiers"][0].get("upgrade", {}).get("cost"), h)
    check("53 is the game's Imperial Camel Rider after the Heavy Camel",
          any(l["from"] == 330 and l["base"] == 207 for l in d["added_lines"]))
d = draft_with(286)
retire_cards(d, None)
check("without a DAT to price it, 286 stays a card (the build converts it)", [b["id"] for b in d["bonuses"]] == [286])

d = draft_with(338)
retire_cards(d, dat)
check("a hero card with no hero: becomes the hero", d["hero_unit"]["base_unit_id"] == 1966)
d = draft_with(338, 344)
notes = retire_cards(d, dat)
check("two hero cards: the first is the hero, the second a standard unit at its kind's building",
      d["hero_unit"]["base_unit_id"] == 1966
      and any(l["base"] == 1978 and l["building"] == 101 and "from" not in l for l in d["added_lines"]), d)
d = draft_with(349, hero=1966)
notes = retire_cards(d, dat)
check("the chosen hero stays; the card's joins the tree, and the log says so",
      d["hero_unit"]["base_unit_id"] == 1966 and any(l["base"] == 1954 for l in d["added_lines"])
      and any("already has a hero" in n for n in notes), notes)
check("...as a valid added line", any(l["base"] == 1954 for l in norm_added_lines(d["added_lines"])))

d = draft_with(457)
d["unit_edits"] = {"331": {"hp": 200}}
retire_cards(d, dat)
check("457 is a Look on the Trebuchet, named Palintonon, keeping other edits, no attack edit",
      d["unit_edits"]["331"] == {"hp": 200, "skin": "Athenians", "name": "Palintonon"}, d["unit_edits"])

d = draft_with(51)
d["tree"]["units"] += [1104, 527, 528]
retire_cards(d, dat)
check("51 Longboats: the Longship line in, the Demolition line out",
      {250, 533} <= set(d["tree"]["units"]) and not {1104, 527, 528} & set(d["tree"]["units"]))

d = {"bonuses": [{"id": 405, "multiplier": 1}], "tree": {"units": [], "buildings": [], "techs": []}}
retire_cards(d, dat)
check("no tree (the slot's own is kept): a unit card stays a card", [b["id"] for b in d["bonuses"]] == [405])

d = draft_with(405, 338, 457, 309)
retire_cards(d, dat)
once = copy.deepcopy(d)
check("idempotent", retire_cards(d, dat) == [] and d == once)

print("\n=== a KM file ===")
km = {"alias": "KM", "bonuses": [[[405, 1], [43, 1], [338, 1], [3, 1]], [11], [], [], []],
      "tree": [list(units), list(buildings), list(techs)]}
retire_cards(km, dat)
check("KM's nested bonus list: the cards leave, the others stay", km["bonuses"][0] == [[3, 1]], km["bonuses"])
check("...units into tree[0], the hero into hero_unit",
      {2569, 2571, 775} <= set(km["tree"][0]) and km["hero_unit"]["base_unit_id"] == 1966)

print("\n=== the picker and the wizard ===")
import app as app_mod  # noqa: E402
client = app_mod.app.test_client()
cat = client.get("/api/builder/bonuses/catalog").get_json()
offered = {c["id"] for c in cat["civ"]}
check("retired cards are not offered", not offered & RETIRED, sorted(offered & RETIRED))
check("...and an older civ is told where each went",
      all(cat["retired"]["civ"].get(str(b), {}).get("successor") in ("the tech tree", "the hero panel")
          for b in (405, 43, 309, 457, 338)), {b: cat["retired"]["civ"].get(str(b)) for b in (405, 338)})
check("the replacements are still offered", {416, 417, 456} <= offered, sorted({416, 417, 456} - offered))
r = client.post("/api/builder/retire-cards", json={"draft": draft_with(405, 338)}).get_json()
check("/api/builder/retire-cards converts a draft",
      not r["draft"]["bonuses"] and r["draft"]["hero_unit"]["base_unit_id"] == 1966 and len(r["notes"]) == 2, r.get("notes"))
meta = client.get("/api/builder/meta").get_json()
check("meta names the retired cards", set(meta.get("retired_cards", [])) == RETIRED)

if dat is None:
    print("  skip  no game DAT found")
    print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
    sys.exit(1 if failures else 0)

print("\n=== a build of a civ that still carries the cards ===")
from civ_overrides import apply_civ_with_overrides  # noqa: E402
SLOT = 1
km = {"alias": "KM", "architecture": 2, "language": 0,
      "bonuses": [[[405, 1], [43, 1], [338, 1], [457, 1], [309, 1]], [11], [[3, 1]], [[12, 1]], []],
      "tree": [list(units), list(buildings), list(techs)]}
out = io.StringIO()
with contextlib.redirect_stdout(out):
    r, _ = apply_civ_with_overrides(dat, km, SLOT)
log = out.getvalue()
civ = dat.civs[SLOT]
check("the build log says where each card went", log.count("Card ") >= 5, log[:400])
owned = [t for t in dat.techs if t.civ == SLOT and 0 <= t.effect_id < len(dat.effects)]
enabled = {int(c.a) for t in owned for c in dat.effects[t.effect_id].effect_commands if c.type == 2 and int(c.b) != 0}
check("Bolas Rider and Missionary: a tech of this civ enables them, as their cards did",
      {2569, 775} <= enabled, sorted(enabled & {2569, 775}))
check("Liu Bei is the civ's hero (the hero panel's one-at-a-time tech)",
      any(dat.effects[t.effect_id].name == f"__hero_imp_enable_{SLOT}" and
          any(c.type == 2 and int(c.a) == 1966 for c in dat.effects[t.effect_id].effect_commands) for t in owned))
athen = next(i for i, c in enumerate(dat.civs) if c.name.lower().startswith("athen"))
check("the Trebuchet wears the Athenians' Palintonon",
      civ.units[42].standing_graphic == dat.civs[athen].units[42].standing_graphic != dat.civs[0].units[42].standing_graphic)
check("the Royal Battle Elephant is built as the tree's added line",
      any(rec["units"] and dat.civs[SLOT].units[rec["units"][0]].hit_points == 330 for rec in r.get("added_lines") or []),
      [(rec["units"]) for rec in r.get("added_lines") or []])

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
