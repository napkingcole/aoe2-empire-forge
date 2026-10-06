#!/usr/bin/env python3
"""Custom bonus composer — cards built from a target plus a list of effects.

Three layers:

1. **Pure** — normalisation drops what can't be built, card text reads like a
   civ bonus, and every command uses the encoding vanilla does (class*256 +
   amount for armor/attack, the negated whole for a reduction, 1/(1+N%) for
   "N% faster").
2. **Precedent** — every group's class list is pinned to the vanilla effect it
   mirrors.  If a DLC widens "Cavalry +20% HP", this fails rather than our
   Cavalry quietly meaning something the game's doesn't.  DAT-gated.
3. **Build** — apply_civ turns each card into one civ-owned auto-fire tech, and
   a unit target reaches its whole upgrade line.  DAT-gated.

    venv/bin/python tests/test_custom_bonus.py
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import custom_bonus as cb                                # noqa: E402

failures = 0


def check(label, cond, extra=""):
    global failures
    if cond:
        print(f"  ok   {label}")
    else:
        failures += 1
        print(f"  FAIL {label}" + (f"\n       {extra}" if extra else ""))


# ── 1. Pure ───────────────────────────────────────────────────────────────────
cav = {"target": {"type": "group", "id": "cavalry"},
       "effects": [{"attr": "hp", "op": "mul", "value": 20},
                   {"attr": "pierce_armor", "op": "add", "value": 2}]}
norm = cb.normalize([cav])
check("a valid two-effect card survives normalize", len(norm) == 1 and len(norm[0]["effects"]) == 2)
check("card text reads like a civ bonus",
      cb.card_text(norm[0]) == "Cavalry: +20% HP, +2 pierce armor", cb.card_text(norm[0]))
check("player-written text wins",
      cb.card_text({**norm[0], "text": "Horses eat well"}) == "Horses eat well")

bad = cb.normalize([
    {"target": {"type": "group", "id": "dragons"}, "effects": [{"attr": "hp", "op": "add", "value": 5}]},
    {"target": {"type": "group", "id": "infantry"}, "effects": [{"attr": "melee_armor", "op": "mul", "value": 5}]},
    {"target": {"type": "group", "id": "infantry"}, "effects": [{"attr": "hp", "op": "add", "value": 0}]},
    {"target": {"type": "group", "id": "infantry"}, "effects": [{"attr": "hp", "op": "mul", "value": -100}]},
    "garbage",
])
check("unknown group / op an attribute can't take / zero / x0 are all dropped", bad == [], bad)

mixed = cb.normalize([{"target": {"type": "group", "id": "infantry"},
                       "effects": [{"attr": "hp", "op": "add", "value": 10},
                                   {"attr": "nonsense", "op": "add", "value": 1}]}])
check("one bad effect costs only that effect, not the card",
      len(mixed) == 1 and len(mixed[0]["effects"]) == 1)

no_line = lambda uid: {uid}                       # noqa: E731
cmds = cb.card_commands(norm[0], no_line)
cav_classes = cb.GROUPS["cavalry"]["classes"]
hp   = [c for c in cmds if c.c == 0]
arm  = [c for c in cmds if c.c == 8]
check("HP +20% is EC_MULTIPLY x1.2 on every cavalry class",
      {(c.type, c.a, c.b, round(c.d, 4)) for c in hp}
      == {(cb.EC_MULTIPLY, -1, k, 1.2) for k in cav_classes})
check("+2 pierce armor is EC_ADD 3*256+2 = 770, as Plate Barding writes",
      {(c.type, c.d) for c in arm} == {(cb.EC_ADD, 770.0)} and len(arm) == len(cav_classes))

minus = cb.effect_commands({"attr": "melee_attack", "op": "add", "value": -1}, [(74, -1)])
check("-1 melee attack is the negated whole, -1025 (Forging on unit 1923)",
      [(c.a, c.b, c.c, c.d) for c in minus] == [(74, -1, 9, -1025.0)])

rng = cb.effect_commands({"attr": "range", "op": "add", "value": 1}, [(-1, 0)])
check("+1 range also raises LOS and search radius, as Fletching does",
      sorted(c.c for c in rng) == [1, 12, 23])

fast = cb.effect_commands({"attr": "attack_speed", "op": "mul", "value": 25}, [(-1, 36)])
check("'attack 25% faster' is reload x0.8, as the vanilla cav-archer bonus",
      round(fast[0].d, 4) == 0.8 and fast[0].c == 10)
check("its text says faster", cb.effect_text({"attr": "attack_speed", "op": "mul", "value": 25})
      == "attack 25% faster")

cost = cb.effect_commands({"attr": "cost", "op": "mul", "value": -15, "resource": "gold"}, [(-1, 6)])
check("-15% gold cost touches only attribute 105", [(c.c, round(c.d, 4)) for c in cost] == [(105, 0.85)])
allc = cb.effect_commands({"attr": "cost", "op": "mul", "value": -10}, [(-1, 6)])
check("-10% cost touches all four resources", sorted(c.c for c in allc) == [103, 104, 105, 106])

unit_card = cb.normalize([{"target": {"type": "unit", "id": 38, "name": "Knight"},
                           "effects": [{"attr": "hp", "op": "add", "value": 20}]}])[0]
line_cmds = cb.card_commands(unit_card, lambda uid: {38, 283, 569})
check("a unit target writes one command per unit in its line",
      sorted(c.a for c in line_cmds) == [38, 283, 569] and all(c.b == -1 for c in line_cmds))
check("unit card text names the line", cb.card_text(unit_card) == "Knight line: +20 HP")

# Schema round-trip keeps the cards.
from civ_schema import to_draft, from_draft             # noqa: E402
rt = to_draft(from_draft({"custom_bonuses": [cav], "tree": {}}))
check("custom_bonuses survive a save/load round trip",
      rt.get("custom_bonuses") == norm, rt.get("custom_bonuses"))


check("the library id survives normalize; a junk id does not",
      cb.normalize([{**cav, "id": "abc123"}])[0].get("id") == "abc123"
      and "id" not in cb.normalize([{**cav, "id": "../../etc"}])[0])

# Villager jobs.
job = cb.normalize([{"target": {"type": "job", "id": "builder"},
                     "effects": [{"attr": "melee_armor", "op": "add", "value": 5},
                                 {"attr": "pierce_armor", "op": "add", "value": 5},
                                 {"attr": "hp", "op": "add", "value": 100},
                                 {"attr": "work_rate", "op": "mul", "value": 30}]}])
check("a job card keeps stateless effects and drops HP — enforced server-side",
      len(job) == 1 and [e["attr"] for e in job[0]["effects"]] == ["melee_armor", "pierce_armor", "work_rate"],
      job)
check("job card text names the job and its work rate",
      cb.card_text(job[0]) == "Builders: +5 melee armor, +5 pierce armor, +30% build speed",
      cb.card_text(job[0]))
jcmds = cb.card_commands(job[0], lambda uid: {uid, 9999})
check("a job writes exactly its male/female pair, never an upgrade line",
      {int(c.a) for c in jcmds} == {118, 212} and all(c.b == -1 for c in jcmds))
check("+5 melee armor while building matches KM #266's encoding shape (class*256+n)",
      {c.d for c in jcmds if c.c == 8} == {4 * 256 + 5.0, 3 * 256 + 5.0})
check("an unknown job is dropped", cb.normalize([{"target": {"type": "job", "id": "wizard"},
                                                  "effects": [{"attr": "carry", "op": "add", "value": 5}]}]) == [])

check("a packed Trebuchet card reaches the unpacked one", cb.with_forms({331}) == {42, 331})
check("a War Chariot card reaches both stances", cb.with_forms({1962}) == {1962, 1980})
check("a Konnik card reaches the dismounted Konnik", 1252 in cb.with_forms({1225}))
check("an unrelated unit gains no forms", cb.with_forms({38}) == {38})


# ── Techs (pure) ─────────────────────────────────────────────────────────────
T = lambda gid, *effs: cb.normalize([{"target": {"type": "group", "id": gid}, "effects": list(effs)}])  # noqa: E731
gold = T("set_gold", {"attr": "free", "op": "set"})[0]
import civ_appender as _ca                                # noqa: E402
check("'free' on a tech writes exactly what _free_tech_cmds writes (free AND instant)",
      [(c.type, c.a, c.b, c.c, c.d) for c in cb.card_commands(gold, None)]
      == [(c.type, c.a, c.b, c.c, c.d) for c in _ca._free_tech_cmds([55, 182])])
pct = cb.card_commands(T("age_all", {"attr": "tech_cost", "op": "mul", "value": -15})[0], None)
check("-15% cost on all resources is one b=-1 multiply per tech (the Italians' age discount)",
      [(c.type, c.a, c.b, c.c, round(c.d, 4)) for c in pct]
      == [(cb.EC_TECH_COST, t, -1, cb.TECH_MUL, 0.85) for t in (101, 102, 103)])
fast = cb.card_commands(T("age_all", {"attr": "research_speed", "op": "mul", "value": 66})[0], None)
check("'research 66% faster' is EC_TECH_TIME x0.6024 (Malay 'Age up faster')",
      {round(c.d, 4) for c in fast} == {0.6024} and {c.type for c in fast} == {cb.EC_TECH_TIME})
flat = T("age_feudal", {"attr": "tech_cost", "op": "add", "value": -100})[0]
costs = lambda tid: {0: 500}                               # noqa: E731  Feudal: 500 food only
check("flat '-100 cost' touches only the resource the tech charges",
      [(c.b, c.c, c.d) for c in cb.card_commands(flat, None, lambda k, a: {101} if k == "techs" else costs(a))]
      == [(0, cb.TECH_ADD, -100.0)])
gone = T("age_feudal", {"attr": "tech_cost", "op": "add", "value": -900, "resource": "food"})[0]
check("a flat cut past zero sets the cost to 0 rather than paying the player",
      [(c.b, c.c, c.d) for c in cb.card_commands(gone, None, lambda k, a: {101} if k == "techs" else costs(a))]
      == [(0, cb.TECH_SET, 0.0)])
nogold = T("age_feudal", {"attr": "tech_cost", "op": "add", "value": 50, "resource": "gold"})[0]
check("a flat change to a resource the tech doesn't charge writes nothing (no 4th cost slot)",
      cb.card_commands(nogold, None, lambda k, a: {101} if k == "techs" else costs(a)) == [])
check("unit attributes are refused on a tech target",
      T("set_gold", {"attr": "hp", "op": "add", "value": 5}) == [])
check("tech card text", cb.card_text(T("techs_blacksmith", {"attr": "tech_cost", "op": "mul", "value": -50},
                                       {"attr": "research_speed", "op": "mul", "value": 100})[0])
      == "Blacksmith techs: -50% cost, research 100% faster")


# ── Library: storage, import, export ──────────────────────────────────────────
import os                                                 # noqa: E402
import tempfile                                           # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    os.environ["EMPIREFORGE_DATA_DIR"] = tmp
    check("an empty library loads as []", cb.load_library() == [])

    saved = cb.upsert(cav)
    check("upsert assigns an id", bool(saved and saved.get("id")))
    check("the library file is a shareable pack",
          __import__("json").loads(cb.library_path().read_text(encoding="utf-8"))["format"] == cb.PACK_FORMAT)

    edited = cb.upsert({**cav, "id": saved["id"], "text": "Edited"})
    lib = cb.load_library()
    check("upsert with an existing id edits in place", len(lib) == 1 and lib[0]["text"] == "Edited")
    check("upsert refuses a card with no valid effect", cb.upsert({"target": cav["target"], "effects": []}) is None)

    shared = cb.pack([
        {**cav, "id": saved["id"], "text": "Someone else's card, same id"},   # collides, differs
        {**cav, "id": "zzz", "text": "Edited"},                              # same content as ours
        {"target": {"type": "group", "id": "monks"},
         "effects": [{"attr": "speed", "op": "mul", "value": 10}]},           # new, no id
        {"target": {"type": "group", "id": "dragons"}, "effects": []},         # unreadable
    ])
    res = cb.import_cards(shared)
    lib = cb.load_library()
    check("import: 2 added, 1 duplicate skipped, 1 unreadable",
          res == {"added": 2, "skipped": 1, "invalid": 1}, res)
    check("an id collision never overwrites the player's own card",
          next(c for c in lib if c["id"] == saved["id"])["text"] == "Edited")
    check("every library card ends up with a unique id",
          len({c["id"] for c in lib}) == len(lib) == 3)
    check("a bare single card imports too",
          cb.import_cards({"target": {"type": "group", "id": "towers"},
                           "effects": [{"attr": "hp", "op": "mul", "value": 10}]})["added"] == 1)

    check("delete removes by id", cb.delete(saved["id"]) and len(cb.load_library()) == 3)
    check("delete of an unknown id reports it", cb.delete("nope") is False)

    # HTTP layer — the same calls the library page makes.
    import app as webapp                                  # noqa: E402
    client = webapp.app.test_client()
    r = client.post("/api/custom-bonuses", json=cav)
    check("POST /api/custom-bonuses saves", r.status_code == 200 and r.get_json().get("id"))
    r = client.get(f"/api/custom-bonuses/export?ids={r.get_json()['id']}")
    exported = r.get_json() if r.is_json else __import__("json").loads(r.data)
    check("export of one id is a one-card pack",
          r.status_code == 200 and exported["format"] == cb.PACK_FORMAT and len(exported["custom_bonuses"]) == 1)
    check("export downloads as a file", "attachment" in r.headers.get("Content-Disposition", ""))
    r = client.post("/api/custom-bonuses/import", data=b"not json", content_type="application/json")
    check("import of a non-JSON body is a 400, not a 500", r.status_code == 400, r.status_code)
    cat = client.get("/api/builder/custom-bonus/catalog").get_json()
    check("the picker hides Villager and every secondary form",
          not any(u["id"] in cb.PICKER_HIDDEN for u in cat["units"]))
    names = {u["name"]: u for u in cat["units"]}
    check("each form group shows once, under its own name, with art",
          all(lbl in names and names[lbl]["id"] == ids[0] and names[lbl]["icon"] for lbl, ids in cb.FORMS),
          [lbl for lbl, ids in cb.FORMS if lbl not in names])
    check("every unit and building tile has art",
          all(x["icon"] for x in cat["units"] + cat["buildings"]),
          [x["name"] for x in cat["units"] + cat["buildings"] if not x["icon"]])
    check("every group and job tile has art",
          all(x["icon"] for x in cat["groups"] + cat["jobs"]))
    check("Harbor has no tile of its own — the Dock tile reaches it",
          not any(b["id"] in cb.PICKER_HIDDEN_BUILDINGS for b in cat["buildings"])
          and any(b["id"] == 45 for b in cat["buildings"]))
    check("units carry a picker category",
          {u["category"] for u in cat["units"]} <= {c["id"] for c in cat["unit_categories"]})
    check("the library page renders", client.get("/builder/custom-bonuses").status_code == 200)
    del os.environ["EMPIREFORGE_DATA_DIR"]


# ── 2 & 3. DAT-gated ──────────────────────────────────────────────────────────
from dat_reader import find_game_dat, load_dat          # noqa: E402

dat_path = find_game_dat()
if dat_path is None:
    print("  skip  no game DAT found — precedent and build checks skipped")
    sys.exit(1 if failures else 0)

import civ_appender as ca                                # noqa: E402

dat = load_dat(str(dat_path))

# Each group mirrors the classes of one vanilla effect.  Keyed by effect NAME,
# not id, so a DLC renumbering doesn't turn this into a false pass.
PRECEDENT = {
    "cavalry":       ("C-Bonus, Cavalry +20% HP", 0),
    "archers":       ("Padded Archer Armor", 8),
    "melee_cavalry": ("Plate Barding Armor", 8),
    "siege":         ("C-Bonus, Siege +10% movement", 5),
    "monks":         ("C-Bonus, Monks 20% faster", 5),
    "ships":         ("C-Bonus, Ships +10% faster", 0),
    "buildings":     ("C-Bonus, Building HP x1.5", 0),
    "infantry":      ("Forging", 9),
}
for gid, (ename, attr) in PRECEDENT.items():
    eff = next((e for e in dat.effects if e.name == ename), None)
    if eff is None:
        check(f"vanilla effect {ename!r} exists", False)
        continue
    classes = {int(c.b) for c in eff.effect_commands if c.a == -1 and c.b >= 0 and c.c == attr}
    ours = set(cb.GROUPS[gid]["classes"])
    if gid == "infantry":
        # Forging is infantry AND cavalry; the infantry half is ours.
        ok = ours <= classes and not ours & set(cb.GROUPS["cavalry"]["classes"])
    else:
        ok = ours == classes
    check(f"group {gid!r} matches {ename!r}", ok, f"ours={sorted(ours)} vanilla={sorted(classes)}")


# Each job's pair is pinned to the vanilla bonus that targets it, by effect name.
# Herders and Pearlers have no job bonus of their own, so they are pinned as the
# remainder of the vanilla effect that lists them beside another job.
JOB_PRECEDENT = {
    "lumberjack":  ("C-Bonus, Lumberjacks 15% faster", set()),
    "gold_miner":  ("C-Bonus, +% Gold up", set()),
    "stone_miner": ("C-Bonus, +% Stone up", set()),
    "shepherd":    ("C-Bonus, +25% Shepherd", set()),
    "forager":     ("C-Bonus, 15% faster foragers", set()),
    "hunter":      ("C-Bonus, Hunters 40% faster", set()),
    "farmer":      ("C-Bonus, Instant Farmers", set()),
    "builder":     ("Treadmill Crane", set()),
    # Saxons arrived with Viking Sagas.  On older DATs, Flemish Revolution —
    # which converts every villager job — names the same pair (as an upgrade).
    "repairer":    ("Saxons Team Bonus|Flemish Revolution", set()),
    "herder":      ("C-Bonus, Sheep +50% food", {590, 592}),
    "pearler":     ("C-Bonus, Fish carry", {56, 57}),
    "fisherman":   ("C-Bonus, Fish carry", {2333, 2334}),
}
vil_ids = {i for i, u in enumerate(dat.civs[1].units) if u is not None and u.class_ == 4}
for jid, (enames, minus) in JOB_PRECEDENT.items():
    ename, eff = next(((n, e) for n in enames.split("|") for e in dat.effects if e.name == n),
                      (enames, None))
    if eff is None:
        check(f"vanilla effect {ename!r} exists", False)
        continue
    # Work rate (13) or carry (14) only — "Sheep +50% food" also touches Hunter
    # 216 on another attribute, which is not a statement about who herds.
    attrs = (13, 14) if ename != "Flemish Revolution" else (1,)   # its EC_UPGRADE c
    ids = {int(c.a) for c in eff.effect_commands
           if int(c.a) in vil_ids and int(c.c) in attrs} - minus
    if ename == "Flemish Revolution":
        ids &= set(cb.JOBS[jid]["units"]) | {156, 222}            # repairer half only
    check(f"job {jid!r} is the pair {ename!r} targets", ids == set(cb.JOBS[jid]["units"]),
          f"ours={cb.JOBS[jid]['units']} vanilla={sorted(ids)}")


def civ_def(cards):
    return {
        "alias": "Custom Probe", "tagline": "", "architecture": 1, "language": 0,
        "wonder": -1, "castle": -1,
        "bonuses": [[], [], [], [], []],
        "tree": [[], [], []],
        "custom_bonuses": cards,
    }


cards = [cav, {"target": {"type": "unit", "id": 38, "name": "Knight"},
               "effects": [{"attr": "hp", "op": "add", "value": 20}]},
         {"target": {"type": "unit", "id": 331, "name": "Trebuchet"},
          "effects": [{"attr": "hp", "op": "add", "value": 50}]}]
slot = 5
with contextlib.redirect_stdout(io.StringIO()):
    res = ca.apply_civ(dat, civ_def(cards), target_slot=slot)

ours = [t for t in dat.techs if t.civ == slot and t.name == "C-Bonus, Custom"]
check("one civ-owned tech per card", len(ours) == 3, f"got {len(ours)}")
check("each is auto-fire with a research location (quirk 6)",
      all(len(t.research_locations) == 1 and t.research_locations[0].location_id == -1 for t in ours))
check("apply_civ reports them", res["bonus_results"].get("custom_applied") == 3,
      res["bonus_results"].get("custom_applied"))

if len(ours) == 3:
    targeted = {int(c.a) for c in dat.effects[ours[1].effect_id].effect_commands}
    check("the Knight card reaches Cavalier and Paladin through the upgrade line",
          {38, 283, 569} <= targeted, sorted(targeted))
    targeted = {int(c.a) for c in dat.effects[ours[2].effect_id].effect_commands}
    check("the Trebuchet card reaches both the packed and unpacked unit",
          {42, 331} <= targeted, sorted(targeted))

# A building card must reach every same-named copy, not just its upgrade line.
# The upgrade walk alone found 7 of the 20 Town Centers the game's own TC
# bonuses name.  Pinned to those vanilla lists, by effect name.
bcards = [{"target": {"type": "unit", "id": 109, "name": "Town Center", "kind": "building"},
           "effects": [{"attr": "hp", "op": "mul", "value": 10}]},
          {"target": {"type": "unit", "id": 45, "name": "Dock", "kind": "building"},
           "effects": [{"attr": "hp", "op": "mul", "value": 10}]}]
with contextlib.redirect_stdout(io.StringIO()):
    ca.apply_civ(dat, civ_def(bcards), target_slot=6)
btechs = [t for t in dat.techs if t.civ == 6 and t.name == "C-Bonus, Custom"]
for t, (label, ename) in zip(btechs, (("Town Center", "C-Bonus, TC Wood cost"),
                                     ("Dock", "C-Bonus, Super Dock"))):
    got = {int(c.a) for c in dat.effects[t.effect_id].effect_commands}
    eff = next((e for e in dat.effects if e.name == ename), None)
    want = {int(c.a) for c in eff.effect_commands if c.a >= 0} if eff else set()
    check(f"a {label} card reaches every copy {ename!r} names",
          eff is not None and want <= got, f"missing {sorted(want - got)}")

# ── New groups (2026-10-01) ──────────────────────────────────────────────────
# Exact-list groups equal the vanilla effect they copy, on the ids this DAT has.
have = {i for i, u in enumerate(dat.civs[1].units) if u is not None}
LIST_PRECEDENT = {
    "gunpowder": "C-Bonus, Gunpowder +25% HP",
    "camels":    "C-Bonus, Camels +25% HP",
    "elephants": "C-Bonus, Elephant resistance",
}
for gid, ename in LIST_PRECEDENT.items():
    eff = next((e for e in dat.effects if e.name == ename), None)
    want = {int(c.a) for c in eff.effect_commands if c.a >= 0} if eff else None
    check(f"group {gid!r} is exactly {ename!r}",
          want is not None and set(cb.GROUPS[gid]["units"]) & have == want,
          f"ours-only={sorted(set(cb.GROUPS[gid]['units']) & have - (want or set()))} "
          f"vanilla-only={sorted((want or set()) - set(cb.GROUPS[gid]['units']))}")
eff = next(e for e in dat.effects if e.name == "C-Bonus, Military cost -15%")
check("group 'military' is exactly the classes 'Military cost -15%' discounts",
      set(cb.GROUPS["military"]["classes"]) == {int(c.b) for c in eff.effect_commands if c.a == -1})


def built_ids(cards, slot, extra=None):
    """apply_civ the cards; return [(set of unit ids, set of classes)] per tech."""
    cd = civ_def(cards)
    cd.update(extra or {})
    with contextlib.redirect_stdout(io.StringIO()) as log:
        ca.apply_civ(dat, cd, target_slot=slot)
    out = []
    for t in dat.techs:
        if t.civ == slot and t.name == "C-Bonus, Custom":
            cs = dat.effects[t.effect_id].effect_commands
            out.append(({int(c.a) for c in cs if c.a >= 0}, {int(c.b) for c in cs if c.a == -1}))
    return out, log.getvalue()


g = lambda gid: {"target": {"type": "group", "id": gid},             # noqa: E731
                 "effects": [{"attr": "hp", "op": "mul", "value": 10}]}

# Building groups reach every copy their vanilla precedent names.
res, _ = built_ids([g("military_buildings"), g("drop_off"), g("defensive")], 7)
for (ids, classes), (label, ename) in zip(res, (("military buildings", "C-Bonus, Military Buildings +55f"),
                                                ("drop-off sites", "C-Bonus, Dropsites +35 food, +10 stone"),
                                                ("defensive buildings", "C-Bonus, Towers and Castles x2 arrows"))):
    eff = next((e for e in dat.effects if e.name == ename), None)
    if eff is None:
        # Both precedents are newer than the pre-DLC DAT; nothing to pin there.
        print(f"  skip {label}: {ename!r} is not in this DAT")
        continue
    want = {int(c.a) for c in eff.effect_commands if c.a >= 0}
    check(f"{label} reach every building {ename!r} names", want <= ids,
          f"missing {sorted(want - ids)}")
check("defensive buildings also take every tower by class", res[2][1] == {52} if len(res) > 2 else False)

# "Trained at" is what THIS civ trains there — not every civ's Barracks unit.
barracks_tree = [74, 75, 77, 473, 567, 93, 358, 359]
res, _ = built_ids([g("barracks_units")], 8, {"tree": [barracks_tree, [12], []]})
ids = res[0][0] if res else set()
check("Barracks units cover the civ's own Barracks lines", set(barracks_tree) <= ids, sorted(ids))
check("...and not another civ's Barracks unique unit (Condottiero 882)", 882 not in ids)
check("...and nothing trained elsewhere (Knight 38)", 38 not in ids)

# The Unique unit group resolves to this civ's UU at build time.
km = {"bonuses": [[], [0], [], [], []]}          # KM index 0
res, log = built_ids([g("unique_unit")], 9, km)
uu = next((t for t in dat.techs if t.civ == 9), None)
check("the Unique unit card builds", len(res) == 1, log[-400:])
res_none, log_none = built_ids([g("unique_unit")], 10)
check("a civ with no UU skips the card with a warning, rather than writing nothing silently",
      res_none == [] and "has none" in log_none)

# A card past the Effect cap is split, not refused, and keeps its order.
big = {"target": {"type": "group", "id": "barracks_units"},
       "effects": [{"attr": a, "op": "add", "value": 1}
                   for a in ("range", "los", "melee_armor", "pierce_armor", "melee_attack")]
                  + [{"attr": "hp", "op": "add", "value": 5}, {"attr": "hp", "op": "mul", "value": 10}]}
res, log = built_ids([big], 11)       # bare tree: every unit trained at the Barracks
big_techs = [t for t in dat.techs if t.civ == 11 and t.name == "C-Bonus, Custom"]
sizes = [len(dat.effects[t.effect_id].effect_commands) for t in big_techs]
check("a card over the cap is split across several techs, each under it",
      len(sizes) > 1 and max(sizes) <= 185, sizes)
flat = [c for t in big_techs for c in dat.effects[t.effect_id].effect_commands]
hp = [c.type for c in flat if c.c == 0]
check("the split keeps card order — every HP add precedes every HP multiply",
      hp and hp.index(cb.EC_MULTIPLY) > max(i for i, t in enumerate(hp) if t == cb.EC_ADD))

# ── Effect-cap guard for every civ-owned effect ─────────────────────────────
# Only the tech-tree and team-bonus effects used to be measured.  A Custom
# Imperial UT merges its picks into one effect: these four are 85+67+56+50.
# It used to be reported; it is now split like a card (issue #49), into hidden
# techs that require the UT — the Imperial Nomads shape.
cd = civ_def([])
cd["bonuses"] = [[], [], [], [[60, 1], [64, 1], [8, 1], [47, 1]], []]
with contextlib.redirect_stdout(io.StringIO()):
    res = ca.apply_civ(dat, cd, target_slot=12)
over = [w for w in res.get("warnings", []) if "effect commands" in w and "soft limit" in w]
check("an oversized custom UT is split, so nothing is over the cap", not over, over)
ut_tid = res.get("imp_ut_tech_id")
cont = [t for t in dat.techs if t.civ == 12 and t.name.endswith("(cont.)")]
sizes = [len(dat.effects[t.effect_id].effect_commands) for t in [dat.techs[ut_tid]] + cont]
check("...into the UT plus hidden techs that fire once the UT is researched",
      cont and all(t.required_techs[0] == ut_tid and t.required_tech_count == 1
                   and t.research_locations[0].location_id == -1 for t in cont), sizes)
check("...each under the cap", max(sizes) <= 185 and sum(sizes) > 185, sizes)
with contextlib.redirect_stdout(io.StringIO()):
    res = ca.apply_civ(dat, civ_def(cards), target_slot=13)
check("a normal civ raises no effect-size warning",
      not any("effect commands" in w for w in res.get("warnings", [])), res.get("warnings"))

# ── Techs (DAT) ──────────────────────────────────────────────────────────────
S = ca._string_table()
tname = lambda i: S.get(dat.techs[i].language_dll_name) or dat.techs[i].name   # noqa: E731
SET_NAMES = {
    "set_lumber": {"Double-Bit Axe", "Bow Saw", "Two-Man Saw"},
    "set_gold": {"Gold Mining", "Gold Shaft Mining"},
    "set_stone": {"Stone Mining", "Stone Shaft Mining"},
    "set_carts": {"Wheelbarrow", "Hand Cart"},
    "set_melee_attack": {"Forging", "Iron Casting", "Blast Furnace"},
    "set_archer_attack": {"Fletching", "Bodkin Arrow", "Bracer"},
    "set_inf_armor": {"Scale Mail Armor", "Chain Mail Armor", "Plate Mail Armor"},
    "set_archer_armor": {"Padded Archer Armor", "Leather Archer Armor", "Ring Archer Armor"},
    "set_cav_armor": {"Scale Barding Armor", "Chain Barding Armor", "Plate Barding Armor"},
    "set_building_armor": {"Masonry", "Architecture"},
    "set_ships": {"Careening", "Dry Dock", "Shipwright"},
    "age_all": {"Feudal Age", "Castle Age", "Imperial Age"},
}
for gid, names in SET_NAMES.items():
    got = {tname(t) for t in cb.GROUPS[gid]["techs"]}
    check(f"tech set {gid!r} is {sorted(names)}", got == names, sorted(got))
check("Farm upgrades are the Mill trio plus the Pasture trio",
      {tname(t) for t in cb.GROUPS["set_farm"]["techs"]}
      == {"Horse Collar", "Heavy Plow", "Crop Rotation", "Domestication", "Pastoralism", "Transhumance"})
it = next((e for e in dat.effects if e.name == "Italians Tech Tree"), None)
check("vanilla writes 'all resources' as EC_TECH_COST b=-1 (Italians)", it is not None and any(
    c.type == cb.EC_TECH_COST and c.b == -1 and c.c == cb.TECH_MUL for c in it.effect_commands))


def tech_card_ids(cards, slot, extra=None):
    cd = civ_def(cards)
    cd.update(extra or {})
    with contextlib.redirect_stdout(io.StringIO()):
        res = ca.apply_civ(dat, cd, target_slot=slot)
    out = [{int(c.a) for c in dat.effects[t.effect_id].effect_commands}
           for t in dat.techs if t.civ == res["civ_index"] and t.name == "C-Bonus, Custom"]
    return out, res


TC = lambda gid: {"target": {"type": "group", "id": gid},             # noqa: E731
                  "effects": [{"attr": "tech_cost", "op": "mul", "value": -50}]}
(bs,), _ = tech_card_ids([TC("techs_blacksmith")], 14)
check("Blacksmith techs are exactly the 15 Blacksmith upgrades",
      {tname(t) for t in bs} == SET_NAMES["set_melee_attack"] | SET_NAMES["set_archer_attack"]
      | SET_NAMES["set_inf_armor"] | SET_NAMES["set_archer_armor"] | SET_NAMES["set_cav_armor"],
      sorted(tname(t) for t in bs))
(tc,), _ = tech_card_ids([TC("techs_tc")], 14)
check("Town Center techs leave the age advances to their own tiles", not tc & set(cb.TECH_AGES), sorted(tc))

# A Pasture civ researches COPIES of the Khitan Mill techs; the card must reach them.
(farm,), res = tech_card_ids([TC("set_farm")], 15, {"bonuses": [[[356, 1]], [], [], [], []]})
ci = res["civ_index"]
copies = {t for t in farm if dat.techs[t].civ == ci}
check("on a Pasture civ, Farm upgrades reach the civ's own copies of the Pasture techs",
      {tname(t) for t in copies} == {"Domestication", "Pastoralism", "Transhumance"},
      sorted((t, tname(t), dat.techs[t].civ) for t in farm))

(ut,), res = tech_card_ids([TC("unique_techs")], 16, {"bonuses": [[], [0], [[1, 1]], [[1, 1]], []]})
check("Unique techs resolve to this civ's Castle and Imperial UTs",
      ut == {res["castle_ut_tech_id"], res["imp_ut_tech_id"]}, (sorted(ut), res["castle_ut_tech_id"], res["imp_ut_tech_id"]))

print()
if failures:
    print(f"{failures} check(s) FAILED")
    sys.exit(1)
print("All checks passed.")
