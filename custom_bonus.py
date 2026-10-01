"""
custom_bonus.py — user-composed civ bonus cards.

A custom card is one target plus a list of stat effects:

    {"target":  {"type": "group", "id": "cavalry"}
                | {"type": "unit", "id": 38, "name": "Knight"},
     "effects": [{"attr": "hp",           "op": "mul", "value": 20},
                 {"attr": "pierce_armor", "op": "add", "value": 2}],
     "text":    ""}                  # optional; generated when blank

`value` is always what the player typed: a flat amount for op "add", a percent
for op "mul".  Each card becomes one civ-owned auto-fire tech (see
civ_appender._apply_custom_bonuses), so the ~189-command Effect cap applies per
card, not per civ.

Every mechanism here copies a vanilla precedent — nothing is invented:

  * Groups are the class lists vanilla bonuses target, e.g. Cavalry is exactly
    "C-Bonus, Cavalry +20% HP" / Bloodlines / Husbandry (12, 23, 36, 47).
  * Class targeting is a=-1, b=class — Forging, Bloodlines, Husbandry.
  * Armor/attack encode class*256 + amount; a reduction is the negated whole,
    as Forging writes -1025 on unit 1923.
  * Range also raises LOS (1) and search radius (23), as Fletching does;
    LOS also raises search radius, as Tracking does.
  * "N% faster" divides by (1 + N/100) — Aztecs "created 15% faster" is
    0.8696, "Cavalry Archers fire 25% faster" is 0.8.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path

from genieutils.effect import EffectCommand

_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")

EC_ADD      = 4
EC_MULTIPLY = 5

# ── Targets ───────────────────────────────────────────────────────────────────
# A group selects by exactly one of:
#   classes     a=-1, b=class — how Forging, Bloodlines and Husbandry target.
#   units       an exact vanilla list (plus alternate forms), copied from the
#               game's own bonus for that group — pinned by name in the tests.
#   buildings   representatives expanded at build time to every copy and age
#               version, the way "TC Wood cost" names 20 Town Centers.
#   trained_at  resolved at build time: what THIS civ trains at that building.
#   uu          resolved at build time: this civ's unique unit, base and elite.
# kind: "unit" or "building" — decides which attributes the wizard offers.
# tab / section: where the wizard shows the tile.  icon: static/icons/units/
# file, or a Font Awesome class.
_DROP_OFF = [109, 68, 562, 584, 45, 2556, 1711, 1808]   # TC, Mill, Lumber Camp,
                                                         # Mining Camp, Dock,
                                                         # Settlement, Folwark,
                                                         # Mule Cart
GROUPS: dict[str, dict] = {
    # ── Group tab: unit types ──
    "infantry":        {"label": "Infantry",        "kind": "unit", "tab": "group", "section": "Unit types", "icon": "infantry.png",            "classes": [6, 45, 46, 50]},
    "archers":         {"label": "Archers",         "kind": "unit", "tab": "group", "section": "Unit types", "icon": "crossbowman.png",         "classes": [0, 23, 36, 44]},
    "foot_archers":    {"label": "Foot archers",    "kind": "unit", "tab": "group", "section": "Unit types", "icon": "archer.png",              "classes": [0, 44]},
    "cavalry_archers": {"label": "Cavalry archers", "kind": "unit", "tab": "group", "section": "Unit types", "icon": "cavalry_archer.png",      "classes": [36]},
    "cavalry":         {"label": "Cavalry",         "kind": "unit", "tab": "group", "section": "Unit types", "icon": "elite_conquistador.png",  "classes": [12, 23, 36, 47]},
    "melee_cavalry":   {"label": "Melee cavalry",   "kind": "unit", "tab": "group", "section": "Unit types", "icon": "knight.png",              "classes": [12, 47]},
    "foot_soldiers":   {"label": "Foot soldiers",   "kind": "unit", "tab": "group", "section": "Unit types", "icon": "spearman.png",            "classes": [6, 45, 46, 50, 0, 44]},
    "gunpowder":       {"label": "Gunpowder units", "kind": "unit", "tab": "group", "section": "Unit types", "icon": "hand_cannoneer.png",
                        # "C-Bonus, Gunpowder +25% HP" (Turks) — the fuller of
                        # the game's two gunpowder lists.
                        "units": [5, 36, 46, 420, 557, 691, 771, 773, 831, 832, 1001, 1003,
                                  1704, 1706, 1709, 1901, 1903, 1904, 1907, 1911]},
    "camels":          {"label": "Camel units",     "kind": "unit", "tab": "group", "section": "Unit types", "icon": "camel_rider.png",
                        # "C-Bonus, Camels +25% HP"
                        "units": [207, 282, 329, 330, 556, 1007, 1009, 1263, 1755, 1923]},
    "elephants":       {"label": "Elephant units",  "kind": "unit", "tab": "group", "section": "Unit types", "icon": "battle_elephant.png",
                        # "C-Bonus, Elephant resistance"
                        "units": [239, 558, 873, 875, 1120, 1122, 1132, 1134, 1744, 1746]},
    "siege":           {"label": "Siege weapons",   "kind": "unit", "tab": "group", "section": "Unit types", "icon": "mangonel.png",       "classes": [13, 35, 51, 54, 55]},
    "monks":           {"label": "Monks",           "kind": "unit", "tab": "group", "section": "Unit types", "icon": "monk.png",           "classes": [18, 43]},
    "ships":           {"label": "Ships",           "kind": "unit", "tab": "group", "section": "Unit types", "icon": "ship.png",           "classes": [2, 20, 21, 22, 53]},
    "warships":        {"label": "Warships",        "kind": "unit", "tab": "group", "section": "Unit types", "icon": "galley.png",         "classes": [22, 53]},
    # ── Group tab: by training building ──
    "barracks_units":  {"label": "Barracks units",       "kind": "unit", "tab": "group", "section": "Trained at", "icon": "barracks.png",       "trained_at": 12},
    "archery_units":   {"label": "Archery Range units",  "kind": "unit", "tab": "group", "section": "Trained at", "icon": "archery_range.png",  "trained_at": 87},
    "stable_units":    {"label": "Stable units",         "kind": "unit", "tab": "group", "section": "Trained at", "icon": "stable.png",         "trained_at": 101},
    "siege_shop_units":{"label": "Siege Workshop units", "kind": "unit", "tab": "group", "section": "Trained at", "icon": "siege_workshop.png", "trained_at": 49},
    "dock_units":      {"label": "Dock units",           "kind": "unit", "tab": "group", "section": "Trained at", "icon": "dock.png",           "trained_at": 45},
    # ── Group tab: other ──
    "military":        {"label": "Military units",  "kind": "unit", "tab": "group", "section": "Other", "icon": "fa-shield-halved",
                        # "C-Bonus, Military cost -15%" — land military; no
                        # siege or ships, as the game defines it.
                        "classes": [0, 6, 12, 23, 35, 36, 44, 47]},
    "trade":           {"label": "Trade units",     "kind": "unit", "tab": "group", "section": "Other", "icon": "trade_cart.png",
                        "units": [128, 204, 17]},                    # Trade Cart empty/full, Trade Cog
    # ── Unit tab ──
    "unique_unit":     {"label": "Unique unit",     "kind": "unit", "tab": "unit", "section": "", "icon": "unique_unit.png", "uu": True},
    # ── Villager tab ──
    "villagers":       {"label": "Villagers",       "kind": "unit", "tab": "villager", "section": "", "icon": "villager.png", "classes": [4]},
    # ── Building tab ──
    "buildings":       {"label": "All buildings",   "kind": "building", "tab": "building", "section": "", "icon": "house.png",      "classes": [3, 27, 39, 49, 52]},
    "economic":        {"label": "Economic buildings", "kind": "building", "tab": "building", "section": "", "icon": "market.png",
                        "buildings": _DROP_OFF + [84, 1021, 1754]},  # + Market, Feitoria, Caravanserai
    "drop_off":        {"label": "Drop-off sites",  "kind": "building", "tab": "building", "section": "", "icon": "lumber_camp.png",
                        # "C-Bonus, Dropsites +35 food, +10 stone", plus the
                        # Town Center, Dock and the mobile Mule Cart.
                        "buildings": _DROP_OFF},
    "military_buildings": {"label": "Military buildings", "kind": "building", "tab": "building", "section": "", "icon": "fa-flag",
                        # "C-Bonus, Military Buildings +55f"
                        "buildings": [12, 87, 101, 49, 45]},
    "defensive":       {"label": "Defensive buildings", "kind": "building", "tab": "building", "section": "", "icon": "castle.png",
                        # "C-Bonus, Towers and Castles x2 arrows": every tower
                        # (Donjon and Bombard Tower included), Castle, Krepost.
                        "classes": [52], "buildings": [82, 1251]},
    "towers":          {"label": "Towers",          "kind": "building", "tab": "building", "section": "", "icon": "tower.png",      "classes": [52]},
    "walls":           {"label": "Walls and gates", "kind": "building", "tab": "building", "section": "", "icon": "stone_wall.png", "classes": [27, 39]},
}

# Villager jobs.  Every job is its own unit, in a male/female pair, and the
# game's own job bonuses target exactly these pairs — "Lumberjacks 15% faster"
# is 123/218, "+25% Shepherd" 590/592, Treadmill Crane 118/212.  Herders work
# Pastures only (they gather from the Pasture units), so they are not Shepherds.
# `work` names attribute 13 for this job; `icon` is a static/icons/units file,
# or a Font Awesome class where we have no art.
JOBS: dict[str, dict] = {
    "lumberjack":  {"label": "Lumberjacks",       "units": [123, 218],   "work": "gather rate",  "icon": "wood.png"},
    "farmer":      {"label": "Farmers",           "units": [214, 259],   "work": "gather rate",  "icon": "farm.png"},
    "forager":     {"label": "Foragers",          "units": [120, 354],   "work": "gather rate",  "icon": "berries.png"},
    "hunter":      {"label": "Hunters",           "units": [122, 216],   "work": "gather rate",  "icon": "boar.png"},
    "shepherd":    {"label": "Shepherds",         "units": [590, 592],   "work": "gather rate",  "icon": "sheep.png"},
    "herder":      {"label": "Herders (Pasture)", "units": [1891, 1892], "work": "gather rate",  "icon": "pasture.png"},
    "fisherman":   {"label": "Fishermen",         "units": [56, 57],     "work": "gather rate",  "icon": "fish.png"},
    "pearler":     {"label": "Pearlers",          "units": [2333, 2334], "work": "gather rate",  "icon": "fa-gem"},
    "gold_miner":  {"label": "Gold miners",       "units": [579, 581],   "work": "gather rate",  "icon": "gold_mining.png"},
    "stone_miner": {"label": "Stone miners",      "units": [124, 220],   "work": "gather rate",  "icon": "stone_mining.png"},
    "builder":     {"label": "Builders",          "units": [118, 212],   "work": "build speed",  "icon": "fa-hammer"},
    "repairer":    {"label": "Repairers",         "units": [156, 222],   "work": "repair speed", "icon": "fa-screwdriver-wrench"},
}

# ── Attributes ────────────────────────────────────────────────────────────────
# ops:    which of "add" / "mul" the attribute accepts.
# fields: attribute ids written for a plain add/mul.
# armor:  damage class for class*256 encoding (3 = pierce, 4 = melee).
# faster: "N% faster" — the multiplier is 1 / (1 + N/100).
# kinds:  target kinds the attribute makes sense for.
#
# "job" (a villager job) takes only STATELESS attributes — ones read from
# whichever unit the villager is right now, so they switch on and off cleanly
# as it changes job.  HP is stateful (current HP carries across the swap) and
# what the engine does there is untested, so it stays off until an in-game test
# says otherwise.  Cost and train time do nothing on a job: only the base
# Villager is ever trained.
_RES_COST = {"food": 103, "wood": 104, "gold": 105, "stone": 106}

ATTRS: dict[str, dict] = {
    "hp":            {"label": "HP",               "ops": ("add", "mul"), "fields": [0],         "kinds": ("unit", "building")},
    "melee_armor":   {"label": "melee armor",      "ops": ("add",),       "field": 8, "armor": 4, "kinds": ("unit", "building", "job")},
    "pierce_armor":  {"label": "pierce armor",     "ops": ("add",),       "field": 8, "armor": 3, "kinds": ("unit", "building", "job")},
    "melee_attack":  {"label": "melee attack",     "ops": ("add",),       "field": 9, "armor": 4, "kinds": ("unit", "job")},
    "pierce_attack": {"label": "pierce attack",    "ops": ("add",),       "field": 9, "armor": 3, "kinds": ("unit", "building")},
    "range":         {"label": "range",            "ops": ("add",),       "fields": [12, 1, 23], "kinds": ("unit", "building")},
    "los":           {"label": "line of sight",    "ops": ("add",),       "fields": [1, 23],     "kinds": ("unit", "building", "job")},
    "speed":         {"label": "movement speed",   "ops": ("mul",),       "fields": [5],         "kinds": ("unit", "job")},
    "attack_speed":  {"label": "attack speed",     "ops": ("mul",),       "fields": [10], "faster": True, "kinds": ("unit", "building")},
    "train_speed":   {"label": "train speed",      "ops": ("mul",),       "fields": [101], "faster": True, "kinds": ("unit",)},
    "build_speed":   {"label": "build speed",      "ops": ("mul",),       "fields": [101], "faster": True, "kinds": ("building",)},
    "cost":          {"label": "cost",             "ops": ("mul",),       "fields": [103, 104, 105, 106], "kinds": ("unit", "building")},
    "regen":         {"label": "HP regeneration per minute", "ops": ("add",), "fields": [109], "kinds": ("unit", "building")},
    "work_rate":     {"label": "work rate",        "ops": ("mul",),       "fields": [13],        "kinds": ("unit", "job")},
    "carry":         {"label": "carry capacity",   "ops": ("add",),       "fields": [14],        "kinds": ("unit", "job")},
    "garrison":      {"label": "garrison space",   "ops": ("add",),       "fields": [2],         "kinds": ("unit", "building")},
}

COST_RESOURCES = ("all", *_RES_COST)

# Alternate forms of one unit that no EC_UPGRADE connects — packing, stance
# switches and dismounting swap the unit for a different id.  A card on one form
# must reach the others, or "Trebuchet +100 HP" only holds while it's packed.
# The FIRST id is the one the picker shows (it has tree art), under `label`;
# the rest are hidden from the picker and reached through this table.
FORMS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("Trebuchet",    (331, 42)),           # packed / unpacked
    ("Ratha",        (1759, 1738)),        # ranged / melee stance
    ("Elite Ratha",  (1761, 1740)),
    ("Konnik",       (1225, 1254, 1252)),  # mounted / dismounted
    ("Elite Konnik", (1227, 1255, 1253)),
    ("War Chariot",  (1962, 1980)),        # focus fire / barrage — vanilla
                                           # "Siege +10% movement" lists both
)

# Kept out of the single-unit picker.  Villager's gathering forms (lumberjack,
# farmer, ...) are separate units no upgrade links; the Villager tab covers
# them, all at once or job by job.  Plus every non-representative form above.
PICKER_HIDDEN: frozenset[int] = frozenset(
    {83, 293} | {uid for _, ids in FORMS for uid in ids[1:]})
PICKER_NAMES: dict[int, str] = {ids[0]: label for label, ids in FORMS}

# Buildings kept out of the picker because another tile already reaches them.
# Harbor (1189) is the Malay Dock: Thalassocracy upgrades Docks into it, so the
# Dock's upgrade line covers it and a separate tile only invites confusion.
PICKER_HIDDEN_BUILDINGS: frozenset[int] = frozenset({1189})


def with_forms(unit_ids: set[int]) -> set[int]:
    """unit_ids plus every alternate form of any of them."""
    out = set(unit_ids)
    for _, ids in FORMS:
        if out.intersection(ids):
            out.update(ids)
    return out


def catalog() -> dict:
    """What the wizard needs to draw the composer — groups and attributes."""
    return {
        "groups": [{"id": k, "label": g["label"], "kind": g["kind"], "icon": g["icon"],
                    "tab": g["tab"], "section": g["section"]}
                   for k, g in GROUPS.items()],
        "jobs":   [{"id": k, "label": j["label"], "work": j["work"], "icon": j["icon"]}
                   for k, j in JOBS.items()],
        "attrs":  [{"id": k, "label": a["label"], "ops": list(a["ops"]),
                    "kinds": list(a["kinds"])} for k, a in ATTRS.items()],
        "cost_resources": list(COST_RESOURCES),
    }


# ── Normalisation ─────────────────────────────────────────────────────────────

def normalize(raw) -> list[dict]:
    """Clean a custom_bonuses list from a draft/JSON; drop what can't be built.

    Tolerant by design: a hand-edited JSON with one bad effect should lose that
    effect, not the build.  validate() reports what was dropped.
    """
    return [c for c in (_norm_card(r) for r in (raw or [])) if c is not None]


def _norm_card(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    t = raw.get("target") or {}
    ttype = t.get("type")
    if ttype == "group":
        if t.get("id") not in GROUPS:
            return None
        target = {"type": "group", "id": t["id"]}
    elif ttype == "job":
        if t.get("id") not in JOBS:
            return None
        target = {"type": "job", "id": t["id"]}
    elif ttype == "unit":
        try:
            uid = int(t.get("id"))
        except (TypeError, ValueError):
            return None
        if uid < 0:
            return None
        target = {"type": "unit", "id": uid, "name": str(t.get("name") or ""),
                  "kind": "building" if t.get("kind") == "building" else "unit"}
    else:
        return None

    # Enforced here, not just in the wizard: a hand-edited or shared file must not
    # be able to put HP on a villager job.
    kind = target_kind(target)
    effects = [e for e in (_norm_effect(x) for x in (raw.get("effects") or []))
               if e and kind in ATTRS[e["attr"]]["kinds"]]
    if not effects:
        return None
    card = {"target": target, "effects": effects, "text": str(raw.get("text") or "").strip()[:160]}
    # The library id.  A civ keeps it on its copy, which is how the wizard knows
    # which library card a civ's bonus came from.
    cid = raw.get("id")
    if isinstance(cid, str) and _ID_RE.fullmatch(cid):
        card["id"] = cid
    return card


def _norm_effect(raw) -> dict | None:
    if not isinstance(raw, dict) or raw.get("attr") not in ATTRS:
        return None
    spec = ATTRS[raw["attr"]]
    op = raw.get("op")
    if op not in spec["ops"]:
        return None
    try:
        value = float(raw.get("value"))
    except (TypeError, ValueError):
        return None
    if value == 0:
        return None
    if op == "mul" and not spec.get("faster") and value <= -100:
        return None                      # x0 or negative stat — never intended
    if spec.get("faster") and value <= -100:
        return None                      # 1/(1+N/100) blows up at -100%
    if value == int(value):
        value = int(value)
    out = {"attr": raw["attr"], "op": op, "value": value}
    if raw["attr"] == "cost":
        res = raw.get("resource", "all")
        out["resource"] = res if res in COST_RESOURCES else "all"
    return out


# ── Card text ─────────────────────────────────────────────────────────────────

def _fmt_num(v) -> str:
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


def target_kind(target: dict) -> str:
    if target["type"] == "group":
        return GROUPS[target["id"]]["kind"]
    if target["type"] == "job":
        return "job"
    return "building" if target.get("kind") == "building" else "unit"


def target_label(target: dict) -> str:
    if target["type"] == "group":
        return GROUPS[target["id"]]["label"]
    if target["type"] == "job":
        return JOBS[target["id"]]["label"]
    return target.get("name") or f"Unit {target['id']}"


def effect_text(eff: dict, target: dict | None = None) -> str:
    spec  = ATTRS[eff["attr"]]
    v     = float(eff["value"])
    sign  = "+" if v > 0 else "-"
    num   = _fmt_num(abs(v))
    if eff["attr"] == "cost":
        res = eff.get("resource", "all")
        what = "cost" if res == "all" else f"{res} cost"
        return f"{sign}{num}% {what}"
    if spec.get("faster"):
        verb = {"attack_speed": "attack", "train_speed": "train", "build_speed": "build"}[eff["attr"]]
        return f"{verb} {num}% {'faster' if v > 0 else 'slower'}"
    label = spec["label"]
    if eff["attr"] == "work_rate" and target and target["type"] == "job":
        label = JOBS[target["id"]]["work"]          # "gather rate", "build speed"
    if eff["op"] == "mul":
        return f"{sign}{num}% {label}"
    return f"{sign}{num} {label}"


def card_text(card: dict) -> str:
    """'Cavalry: +20% HP, +2 pierce armor' — or the player's own text."""
    if card.get("text"):
        return card["text"]
    subject = target_label(card["target"])
    if card["target"]["type"] == "unit" and card["target"].get("kind") != "building":
        subject += " line"
    return f"{subject}: " + ", ".join(effect_text(e, card["target"]) for e in card["effects"])


# ── Effect commands ───────────────────────────────────────────────────────────

def _selectors(card: dict, line_of, resolve=None) -> list[tuple[int, int]]:
    """(a, b) pairs the commands address — classes and/or individual units.

    `line_of(uid)` expands a unit or building to its line and copies;
    `resolve(kind, arg)` answers the build-time questions ("trained_at",
    building id) and ("uu", None) for this civ.  Without `resolve` those parts
    resolve to nothing, which is what a pure test wants.
    """
    t = card["target"]
    if t["type"] == "job":
        # The exact pair, never an upgrade line — jobs don't upgrade.
        return [(uid, -1) for uid in JOBS[t["id"]]["units"]]
    if t["type"] != "group":
        return [(uid, -1) for uid in sorted(line_of(t["id"]))]

    g = GROUPS[t["id"]]
    pairs = [(-1, cls) for cls in g.get("classes", ())]
    ids: set[int] = set()
    if "units" in g:
        ids |= resolve("units", g["units"]) if resolve else with_forms(set(g["units"]))
    for b in g.get("buildings", ()):
        ids |= line_of(b)
    if "trained_at" in g and resolve:
        ids |= resolve("trained_at", g["trained_at"])
    if g.get("uu") and resolve:
        ids |= resolve("uu", None)
    return pairs + [(uid, -1) for uid in sorted(ids)]


def effect_commands(eff: dict, selectors: list[tuple[int, int]]) -> list[EffectCommand]:
    spec = ATTRS[eff["attr"]]
    v    = float(eff["value"])
    out: list[EffectCommand] = []

    if "armor" in spec:
        d = float(spec["armor"] * 256 + abs(v))
        d = d if v > 0 else -d
        for a, b in selectors:
            out.append(EffectCommand(type=EC_ADD, a=a, b=b, c=spec["field"], d=d))
        return out

    fields = spec["fields"]
    if eff["attr"] == "cost" and eff.get("resource", "all") != "all":
        fields = [_RES_COST[eff["resource"]]]

    if eff["op"] == "add":
        cmd_type, d = EC_ADD, v
    elif spec.get("faster"):
        cmd_type, d = EC_MULTIPLY, 1.0 / (1.0 + v / 100.0)
    else:
        cmd_type, d = EC_MULTIPLY, 1.0 + v / 100.0

    for a, b in selectors:
        for c in fields:
            out.append(EffectCommand(type=cmd_type, a=a, b=b, c=c, d=d))
    return out


def card_commands(card: dict, line_of, resolve=None) -> list[EffectCommand]:
    """Every command one card writes, in card order.  See _selectors."""
    sel = _selectors(card, line_of, resolve)
    cmds: list[EffectCommand] = []
    for eff in card["effects"]:
        cmds.extend(effect_commands(eff, sel))
    return cmds


# ── Library ───────────────────────────────────────────────────────────────────
# The player's own cards live in one JSON file outside any civ, so a card is made
# once and picked by many civs.  A civ stores a COPY of each card it uses (tagged
# with the card's id), never a reference: a shared civ file has to build on a
# machine that has never seen the author's library.
#
# The share format is the same file shape, so exporting a selection and the
# library file itself are interchangeable.

PACK_FORMAT = "empireforge_bonuses_v1"
LIBRARY_FILE = "custom_bonuses.json"


def data_dir() -> Path:
    """Per-user directory for Empire Forge's own files.

    `EMPIREFORGE_DATA_DIR` overrides it — the tests point it at a scratch dir.
    """
    override = os.environ.get("EMPIREFORGE_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "EmpireForge"


def library_path() -> Path:
    return data_dir() / LIBRARY_FILE


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def pack(cards: list[dict]) -> dict:
    return {"format": PACK_FORMAT, "custom_bonuses": cards}


def unpack(data) -> list:
    """Raw card list from a pack, a bare list, or a single card."""
    if isinstance(data, dict) and isinstance(data.get("custom_bonuses"), list):
        return data["custom_bonuses"]
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "target" in data:
        return [data]
    return []


def load_library() -> list[dict]:
    try:
        raw = json.loads(library_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    cards = normalize(unpack(raw))
    # Every library card has an id — a hand-edited file may have dropped some.
    for c in cards:
        c.setdefault("id", new_id())
    return cards


def save_library(cards: list[dict]) -> None:
    path = library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pack(cards), indent=2), encoding="utf-8")
    tmp.replace(path)            # atomic: a crash mid-write never eats the library


def upsert(card_raw) -> dict | None:
    """Add or replace one card by id.  Returns the stored card, or None if invalid."""
    cards = normalize([card_raw])
    if not cards:
        return None
    card = cards[0]
    card.setdefault("id", new_id())
    lib = load_library()
    for i, c in enumerate(lib):
        if c["id"] == card["id"]:
            lib[i] = card
            break
    else:
        lib.append(card)
    save_library(lib)
    return card


def delete(card_id: str) -> bool:
    lib = load_library()
    kept = [c for c in lib if c["id"] != card_id]
    if len(kept) == len(lib):
        return False
    save_library(kept)
    return True


def _same(a: dict, b: dict) -> bool:
    strip = lambda c: {k: v for k, v in c.items() if k != "id"}   # noqa: E731
    return strip(a) == strip(b)


def import_cards(data) -> dict:
    """Merge a shared file into the library.

    A card already in the library — same id, or identical content under another
    id — is skipped.  A card whose id collides with a DIFFERENT card is kept
    under a fresh id rather than overwriting the player's own.
    """
    raw = unpack(data)
    incoming = normalize(raw)
    lib = load_library()
    ids = {c["id"] for c in lib}
    added = skipped = 0
    for card in incoming:
        if any(_same(card, c) for c in lib):
            skipped += 1
            continue
        if card.get("id") in ids or "id" not in card:
            card["id"] = new_id()
        lib.append(card)
        ids.add(card["id"])
        added += 1
    if added:
        save_library(lib)
    return {"added": added, "skipped": skipped, "invalid": len(raw) - len(incoming)}
