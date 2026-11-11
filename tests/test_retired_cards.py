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


from retired_cards import (HERO_CARDS, LOOK_CARDS, REPLACEMENT_CARDS, RETIRED,  # noqa: E402
                           TREE_VERSION, UNIT_CARDS, UPGRADE_CARDS, retire_cards)

# The audit (memory: project_unlock_cards_retirement), by group.
AUDIT_RETIRED = {
    *range(405, 416), 428, *range(447, 456), 361, 298,     # regional / Chronicles units
    43, 50, 69, 322, 61, 51,                               # KM units, Slinger, Longboats
    338, 344, 349,                                         # heroes
    53, 286, 308, 309, 310,                                # upgrades past a line's end
    457,                                                   # Palintonon
    282, 307, 416, 314, 417, 456, 362, 402,                # replacements (step 3)
}
STILL_CARDS = {103, 332, 360, 99, 283, 352, 221, 300}     # earlier-age cards: kept

print("=== the table ===")
check("every audited card is retired", AUDIT_RETIRED <= RETIRED, sorted(AUDIT_RETIRED - RETIRED))
check("nothing else is (replacements and earlier-age cards stay cards)",
      not RETIRED & STILL_CARDS and RETIRED <= AUDIT_RETIRED, sorted(RETIRED - AUDIT_RETIRED))

units, buildings, techs = json.loads((ROOT / "my_civs" / "19_Cannoneers.json").read_text(encoding="utf-8"))["tree"] \
    if (ROOT / "my_civs" / "19_Cannoneers.json").exists() else ([4, 24, 36, 330, 542, 1134, 1372, 331], [], [])
for u in (36, 330, 542, 1134, 1372, 331, 473, 567, 569, 441, 532, 39, 474):   # extended / replaced
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
    if bid in REPLACEMENT_CARDS:
        add, gone = REPLACEMENT_CARDS[bid]
        t = set(d["tree"]["units"])
        return "tree" if add <= t and not gone & t else None
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

print("\n=== replacements: the game's own unit in the line's place ===")
d = draft_with(417, 307)
retire_cards(d, dat)
t = set(d["tree"]["units"])
check("Savar in, Paladin out; KM's Legionary (307) as 416: Legionary in, Two-Handed Swordsman and Champion out",
      {1813, 1793} <= t and not {569, 473, 567} & t and not d["bonuses"])
from civ_appender import _tree_unit_ids, get_civ_bonuses  # noqa: E402
for unit, card, gone in ((1813, 417, {569}), (1793, 416, {473, 567}), (1707, 282, {441}),
                         (1302, 362, {532}), (2485, 456, {39, 474})):
    civ = {"tree": {"units": list(units) + [unit]}, "bonuses": []}
    check(f"a tree with {unit}: builds as card {card} and without {sorted(gone)}",
          card in {e[0] for e in get_civ_bonuses(civ)} and not gone & _tree_unit_ids(civ))
civ = {"tree": {"units": list(units) + [1302]}, "bonuses": [{"id": 402, "multiplier": 1}]}
check("...and a KM duplicate card on top doesn't build it twice",
      [e[0] for e in get_civ_bonuses(civ)].count(362) + [e[0] for e in get_civ_bonuses(civ)].count(402) == 1)
if dat is not None:
    import added_lines  # noqa: E402
    sug = {frm: [(r["base"], r["source"]) for r in added_lines.suggested_upgrades(dat, frm, [])]
           for frm in (283, 546, 529, 77)}
    check("the \"+\" under the unit before offers the game's own (Savar, Winged Hussar, Dragon Ship, Legionary)",
          sug == {283: [(1813, "real")], 546: [(1707, "real")], 529: [(1302, "real")], 77: [(1793, "real")]}, sug)
    reps = {r["base"]: r for r in added_lines.real_replacements(dat, [])}
    check("the tree page's table: Scythian replaces the line from its first unit, at the Archery Range",
          reps[2485]["line"] and reps[2485]["building"] == 87 and reps[1813]["replaces"] == [569], reps.get(2485))
    from build_civ import _retarget_replaced_nodes  # noqa: E402
    from dat_reader import find_civtechtrees  # noqa: E402
    src = find_civtechtrees(dat_path)
    if src is not None and (src / "BRITONS.json").exists():
        data = json.loads((src / "BRITONS.json").read_text(encoding="utf-8"))
        _retarget_replaced_nodes(data, {1813, 1793, 1707, 1302, 2485, 2486}, dat, 1, src)
        f2 = {n["Node ID"]: n for n in data["civ_techs_units"] if n.get("Use Type") == "Unit"}
        check("F2: the Paladin's node is the Savar, with the Persians' strings, under the Cavalier",
              f2.get(1813, {}).get("Name String ID") == 14703 and f2[1813].get("Link ID") == 283
              and 569 not in f2, f2.get(1813))
        check("F2: the Legionary takes the Two-Handed Swordsman's node; the Champion's is gone",
              1793 in f2 and not {473, 567} & set(f2))
        check("F2: Winged Hussar, Dragon Ship and both Scythians take their nodes",
              {1707, 1302, 2485, 2486} <= set(f2) and not {441, 532, 39, 474} & set(f2)
              and f2[2486].get("Link ID") == 2485)

print("\n=== the old full tree's Winged Hussar and Dragon Ship ===")
d = draft_with()
d["tree"]["units"] += [1707, 1302]
notes = retire_cards(d, dat)
check("a civ from before, holding them without their cards: they leave (it never built them)",
      not {1707, 1302} & set(d["tree"]["units"]) and d["tree_version"] == TREE_VERSION
      and sum("left the tree" in n for n in notes) == 2, notes)
d = draft_with()
d["tree"]["units"] += [775, 1004, 1010, 882]
retire_cards(d, dat)
check("...and so do the KM catalog's units and the team-bonus units",
      not {775, 1004, 1010, 882} & set(d["tree"]["units"]))
d = draft_with(282)
d["tree"]["units"] += [1707, 1302]
retire_cards(d, dat)
check("...the one whose card it held stays", 1707 in d["tree"]["units"] and 1302 not in d["tree"]["units"])
d = draft_with()
d["tree"]["units"] += [1707]
d["tree_version"] = TREE_VERSION
check("a civ past the cleanup keeps what its tree picked", retire_cards(d, dat) == [] and 1707 in d["tree"]["units"])
from civ_schema import from_draft, to_draft  # noqa: E402
from wizard_build import _draft_to_civ_def  # noqa: E402
check("the stamp survives saving, loading and the build's conversion",
      to_draft(from_draft(d)).get("tree_version") == TREE_VERSION
      and _draft_to_civ_def(d).get("tree_version") == TREE_VERSION)

print("\n=== the Dock's siege ship: from the picker into the tree (version 3) ===")
CG, ECG, CATG, DROMON, LOU = 420, 691, 2633, 1795, 1948
SIEGE = {CG, ECG, CATG, DROMON, LOU}


def ships_after(version, **picker):
    d = draft_with()
    d["tree"]["units"] = [u for u in d["tree"]["units"] if u not in SIEGE] + [CG, CATG]   # the old tree's noise
    d["tree_version"] = version
    d.update(picker)
    notes = retire_cards(d, dat)
    return d, {u for u in d["tree"]["units"] if u in SIEGE}, notes


d, got, notes = ships_after(2, long_range_ship="dromon")
check("a Dromon picked: the tree holds the Dromon alone, and the picker's fields go",
      got == {DROMON} and "long_range_ship" not in d and "long_range_ship_elite" not in d
      and d["tree_version"] == TREE_VERSION and any("siege ship" in n for n in notes), (got, notes))
check("...no pick was the Cannon Galleon and its Elite", ships_after(2)[1] == {CG, ECG})
check("...the Elite unticked: the Cannon Galleon alone",
      ships_after(2, long_range_ship_elite=False)[1] == {CG})
check("...None: no siege ship", ships_after(2, long_range_ship="none")[1] == set())
check("...the Lou Chuan and the Catapult Galleon",
      ships_after(1, long_range_ship="lou_chuan")[1] == {LOU}
      and ships_after(1, long_range_ship="catapult_galleon")[1] == {CATG})
check("a civ already on version 3: its tree is its own", ships_after(TREE_VERSION, long_range_ship="dromon")[1] == {CG, CATG})
km_ships = {"alias": "KM", "bonuses": [[], [11], [], [], []], "tree": [[4, 74, DROMON, CG], [], []]}
retire_cards(km_ships, dat)
check("a KM file (no picker in KM): the Cannon Galleon and Elite, as the picker's default gave",
      {u for u in km_ships["tree"][0] if u in SIEGE} == {CG, ECG}, km_ships["tree"][0])
bare = {"bonuses": [], "long_range_ship": "dromon"}
retire_cards(bare, dat)
check("no tree (the slot's own): nothing written, the fields still go",
      "tree" not in bare and "long_range_ship" not in bare)
check("a variant in the tree beside the Cannon Galleon wins (as the picker had it)",
      _tree_unit_ids({"tree": {"units": [CG, ECG, DROMON]}}) & SIEGE == {DROMON})
check("a tree Caravel or Turtle Ship drops the demolition line (Dock button 8), card or no card",
      not _tree_unit_ids({"tree": {"units": [1004, 1104, 527, 528, 13]}}) & {1104, 527, 528}
      and not _tree_unit_ids({"tree": {"units": [831, 1104]}}) & {1104}
      and {1104, 527, 528} <= _tree_unit_ids({"tree": {"units": [1104, 527, 528]}}))
check("a new civ's seed never holds a variant (a deliberate pick)",
      {CATG, DROMON, LOU} <= __import__("retired_cards").SEED_EXCLUDED_UNITS)

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
r = client.post("/api/builder/retire-cards", json={"draft": draft_with(405, 338)}).get_json()
check("/api/builder/retire-cards converts a draft",
      not r["draft"]["bonuses"] and r["draft"]["hero_unit"]["base_unit_id"] == 1966
      and sum(n.startswith("Card ") for n in r["notes"]) == 2, r.get("notes"))
meta = client.get("/api/builder/meta").get_json()
check("meta names the retired cards", set(meta.get("retired_cards", [])) == RETIRED)
check("meta keeps the replacement, KM and team-bonus units out of a new civ's seed",
      {1707, 1302, 1813, 1793, 2485, 2486, 775, 831, 1004, 1263, 1010, 882}
      <= set(meta.get("seed_excluded_units", [])))

if dat is None:
    print("  skip  no game DAT found")
    print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
    sys.exit(1 if failures else 0)

print("\n=== a build of a civ that still carries the cards ===")
from civ_overrides import apply_civ_with_overrides  # noqa: E402
SLOT = 1
km = {"alias": "KM", "architecture": 2, "language": 0,
      "bonuses": [[[405, 1], [43, 1], [338, 1], [457, 1], [309, 1], [417, 1], [282, 1], [362, 1]],
                  [11], [[3, 1]], [[12, 1]], []],
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

own_up = {int(c.b) for t in owned for c in dat.effects[t.effect_id].effect_commands if c.type == 3}
check("Savar and Dragon Ship: this civ's own copy of the game's upgrade", {1813, 1302} <= own_up,
      sorted(own_up & {1813, 1302}))
wh = dat.techs[786]
check("Winged Hussar: the game's upgrade, re-pointed at this civ's copy of its trigger (card 282)",
      any(r >= 0 and r not in (115, 254, 788, 789) for r in wh.required_techs), wh.required_techs)
tt = dat.effects[civ.tech_tree_id].effect_commands
off = {int(c.d) for c in tt if c.type == 102}
check("the Paladin, Hussar and Fast Fire Ship upgrades are off", {265, 428, 246} <= off, sorted({265, 428, 246} - off))

print("\n=== a build with the Dromon in its tree ===")
from wizard_build import _draft_to_civ_def  # noqa: E402,F811


def makes(uid):
    return {tid for tid, t in enumerate(dat.techs) if 0 <= t.effect_id < len(dat.effects) and t.civ == -1
            and any(c.type == 2 and int(c.a) == uid and int(c.b) != 0 for c in dat.effects[t.effect_id].effect_commands)}


def ship_build(ship_units):
    draft = {"tree_version": TREE_VERSION, "alias": "Ships", "architecture": 2, "language": 0,
             "bonuses": [], "team_bonuses": [], "unique_unit": {"km_idx": 11},
             "castle_ut": {"mode": "vanilla", "effects": [{"id": 3, "multiplier": 1}]},
             "imperial_ut": {"mode": "vanilla", "effects": [{"id": 12, "multiplier": 1}]},
             "tree": {"units": [u for u in units if u not in SIEGE] + ship_units,
                      "buildings": list(buildings), "techs": list(techs)}}
    with contextlib.redirect_stdout(io.StringIO()):
        apply_civ_with_overrides(dat, _draft_to_civ_def(draft), SLOT, draft)
    tt = dat.effects[dat.civs[SLOT].tech_tree_id].effect_commands
    return {int(c.a) for c in tt if c.type == 8}, {int(c.d) for c in tt if c.type == 102}


on, off = ship_build([DROMON])
check("the Dromon is unlocked, the Cannon Galleon switched off",
      makes(DROMON) & on and not makes(DROMON) & off and makes(CG) <= off,
      (sorted(makes(DROMON)), sorted(on & makes(DROMON)), sorted(makes(CG) - off)))
on, off = ship_build([CG, ECG])
check("the Cannon Galleon line ticked: it stays on, no Dromon",
      not makes(CG) & off and not makes(DROMON) & on, (sorted(makes(CG) & off), sorted(makes(DROMON) & on)))

print("\nPASS" if not failures else "\nFAIL", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
