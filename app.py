#!/usr/bin/env python3
"""
app.py — Flask web UI for the AoE2 DE Civ Builder.

Routes:
  GET  /              Upload page (step 1)
  POST /upload        Process uploaded KM JSON files → configure page
  GET  /configure     Drag-and-drop civ ordering + vanilla slot assignment (step 2)
  POST /build         Run the build pipeline → results page
  GET  /results       Per-civ bonus report + download link (step 3)
  GET  /download      Serve the built mod zip
"""

import contextlib
import hashlib
import io
import json
import os
import re
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Any

from flask import (Flask, flash, jsonify, redirect, render_template,
                   request, send_file, send_from_directory, session, url_for)

from bonus_names import (bonus_name, skip_reason, unsupported_bonuses,
                         unsupported_unique_units, unsupported_unique_techs,
                         unsupported_team_bonuses)
from build_all import (_build_combined_data_zip, _build_combined_ui_zip,
                       _ut_name, _ut_bonus_id, _BONUS_NAMES, _TEAM_BONUS_NAMES,
                       _UNIQUE_CASTLE_STRINGS, _UNIQUE_IMP_STRINGS)
from build_civ import (
    AI_PER_STUB, LANGUAGES, KM_TECHTREE_ORDER,
    _find_civ_slot, _civ_techtree_index, _civ_file_name,
    _decode_flag, _find_civ_techtrees_folder,
    _patch_per_civ_techtree, _canonical_techtree_id,
    civ_name_sid, civ_roster,
    _resolve_uu_info, _find_adjacent_json, uu_cost_text,
)
from civ_overrides import (_apply_uu_overrides, _apply_hero_unit, _override_ut_costs,
                           _refresh_uu_tooltips)
from civ_appender import (apply_civ, assign_all_languages,
                          _str_id, STRING_BASE, STRING_BLOCK_SIZE,
                          STR_CASTLE_UT, STR_IMPERIAL_UT,
                          DLL_CREATION_OFFSET, DLL_HELP_OFFSET, DLL_TECH_TREE_OFFSET,
                          _ARCH_REP_CIVS,
                          get_civ_bonuses, get_team_bonuses, get_km_uu_index,
                          _KM_UU_NAMES)
from dat_reader import find_game_dat, find_civtechtrees, load_civ_era_exclusions, load_dat
from update_check import check_for_update
from version import __version__

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

SESSIONS_DIR = Path(tempfile.gettempdir()) / "aoe2civbuilder"
SESSIONS_DIR.mkdir(exist_ok=True)

# Shared parsed DatFile objects — keyed by path; all endpoints share this cache
# so the DAT is only parsed once regardless of which endpoint hits it first.
_DAT_OBJ_CACHE: dict[str, Any] = {}

def _get_dat(dat_path: str):
    """Return cached DatFile; parse and cache on first call (shared across endpoints)."""
    if dat_path not in _DAT_OBJ_CACHE:
        _DAT_OBJ_CACHE[dat_path] = load_dat(dat_path)
    return _DAT_OBJ_CACHE[dat_path]

# Read-only DAT cache keyed by path — used only for cost lookups, never mutated.
_DAT_COSTS_CACHE: dict[str, dict] = {}

# UU stat cache — keyed by dat_path → {km_idx: stats_dict}
_UU_STATS_CACHE: dict[str, dict] = {}

# Bump this when _UU_TRAITS changes so stale disk caches are automatically invalidated.
_UU_STATS_DISK_VERSION = 3  # bumped: fixed cost fallback + amount-mode cost parsing

_CACHE_DIR = Path(__file__).parent / ".cache"


def _uu_stats_cache_path(dat_path: str) -> Path:
    h = hashlib.md5(dat_path.encode()).hexdigest()[:10]
    return _CACHE_DIR / f"uu_stats_{h}.json"


def _uu_table_fingerprint() -> str:
    """Fingerprint of the UU table the cached stats were computed from.

    The cache keyed on DAT mtime alone, which is only half the story: the stats
    are produced by walking `_KM_UU_TECHS`, so ADDING a unit leaves a valid
    cache that simply has no entry for it.  That is exactly what happened when
    Viking Sagas added the Hearth Troop, Jarl and Jomsviking — the catalog
    offered them and every stat popup said "No stats available", with a DAT
    that could answer perfectly well sitting right there.  Fingerprinting the
    table means the next DLC invalidates the cache by itself.
    """
    import civ_appender as ca
    raw = repr(sorted((k, tuple(v)) for k, v in ca._KM_UU_TECHS.items()))
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _load_uu_stats_disk(dat_path: str) -> dict | None:
    """Return cached stats dict from disk, or None if missing/stale."""
    try:
        f = _uu_stats_cache_path(dat_path)
        if not f.exists():
            return None
        with open(f) as fh:
            data = json.load(fh)
        if data.get("_v") != _UU_STATS_DISK_VERSION:
            return None
        if data.get("_tbl") != _uu_table_fingerprint():
            return None
        if int(data.get("_mtime", 0)) != int(Path(dat_path).stat().st_mtime):
            return None
        return {int(k): v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        return None


def _save_uu_stats_disk(dat_path: str, stats: dict) -> None:
    """Write stats to disk so future app restarts skip the slow parse."""
    try:
        _CACHE_DIR.mkdir(exist_ok=True)
        payload: dict = {
            "_v":     _UU_STATS_DISK_VERSION,
            "_tbl":   _uu_table_fingerprint(),
            "_mtime": int(Path(dat_path).stat().st_mtime),
        }
        payload.update({str(k): v for k, v in stats.items()})
        with open(_uu_stats_cache_path(dat_path), "w") as fh:
            json.dump(payload, fh)
    except Exception:
        pass


# Attack/armor class IDs → player-readable names.
# Classes not listed here are internal/base classes and are not shown as bonuses.
_ATTACK_CLASS_NAMES: dict[int, str] = {
    1:  "infantry",
    2:  "turtle ships",
    5:  "elephants",
    8:  "cavalry",
    15: "archers",
    16: "ships",
    19: "unique units",
    20: "siege weapons",
    21: "buildings",
    27: "spearmen",
    28: "cavalry archers",
    29: "eagle warriors",
    30: "camels",
    34: "fishing ships",
}
# These are base armor classes present on nearly every unit — not meaningful bonuses.
_SKIP_ATTACK_CLASSES: frozenset[int] = frozenset({3, 4, 6, 7, 9, 10, 11, 12, 13, 14,
                                                   17, 18, 22, 23, 24, 25, 26, 31, 32,
                                                   33, 35, 36, 37, 38, 39})

# Hand-curated special traits that cannot be derived from numeric stats.
_UU_TRAITS: dict[int, list[str]] = {
    6:  ["Deals trample damage to nearby units"],
    11: ["Can fire while moving"],
    20: ["Extended melee reach — attacks units 2 tiles away"],
    23: ["Fires 5 projectiles per volley"],
    24: ["Extremely fast training time"],
    25: ["Retreats to a safe distance after throwing"],
    27: ["Projectile can hit multiple units in a line"],
    29: ["Low accuracy (60%) — high speed projectile"],
    31: ["Becomes a lighter dismounted unit on death (50 HP)"],
    34: ["Attack ignores all melee and pierce armor"],
    36: ["Can construct Donjon buildings"],
    38: ["Shields nearby allied units from arrow projectiles"],
    78: ["Projectile passes through multiple targets"],
    80: ["Can toggle between melee and ranged attack mode"],
    84: ["Ranged attack extends to 13 tiles when targeting buildings"],
    # Custom
    39: ["Cannot be converted by Monks"],
}

# Populated once by a background thread shortly after startup; stays None if
# the check hasn't finished yet, is offline, or no update is available.
_update_info: dict | None = None


def _run_update_check():
    global _update_info
    _update_info = check_for_update()


# Maps version string → list of change descriptions for the changelog page and
# the one-time "what's new" modal. Add the newest version at the top.
CHANGELOG: dict[str, list[str]] = {
    "2.2.1": [
        "<strong class=\"color-accent-2\">BUG FIX:</strong> <strong>Fixed the builder hanging on \"Loading\" at startup.</strong> 2.2.0 made the wizard wait for your game files to be read before it would draw anything, which took around half a minute on a cold start and looked like a freeze. The file is now read in the background, as it was before",
        "<em>If you downloaded 2.2.0, please update — that build cannot get past the first screen.</em>",
    ],
    "2.2.0": [
        "<strong class=\"color-accent-2\">NEW:</strong> <strong>Viking Sagas support.</strong> Saxons, Varangians and Danes can be replaced like any other civ, with their wonders, castles, and the new Nordic architecture and Monk",
        "<strong class=\"color-accent-2\">NEW:</strong> <strong>Mounted Crossbowman</strong> and <strong>Varangian Guard</strong> in the tech tree. Each shares a building slot with the units it replaces — Mounted Crossbowman with the Cavalry Archer and Elephant Archer, Varangian Guard with the Fire Lancer and Eagle line — so picking one removes the others, the same way the tree has always handled regional units. <strong>Cranequins</strong> comes and goes with the Mounted Crossbowman",
        "<strong class=\"color-accent-2\">NEW:</strong> Three unique units — <strong>Hearth Troop</strong>, <strong>Jarl</strong> and <strong>Jomsviking</strong> — and seven unique techs: Ordonnance Companies, Clerical Recruitment, Vendel Legacy, Hamask, Shield Wall, Gothikon and Northmen's Fury",
        "<strong class=\"color-accent-2\">NEW:</strong> 12 new civ bonus cards and 3 new team bonuses, taken from the three new civs",
        "<strong class=\"color-accent-2\">NEW:</strong> The six South American unique units finally have portraits in the picker, along with the three new ones",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> <strong>Three team bonuses stopped working when the DLC landed</strong> — Genitour, the free Llama, and the Condottiero. The game moved them onto a different mechanism and emptied the old one, so the cards quietly did nothing. Fixed, and they work whether or not you have updated the game",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Five card descriptions the DLC made wrong are corrected — the Vietnamese HP bonus, the Teuton armor bonus, Longboats (now Longships), Chieftains and Wagenburg Tactics. Atheism's description now covers what it actually does",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus multipliers no longer break script-driven unique techs. Setting one to x2 could send the game looking for a completely different effect — Coiled Serpent Array was reachable this way",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Typing a DAT path by hand now tells you whether it actually worked, instead of leaving you guessing. <em>Thanks to Maruviel on Discord, whose game is on a D: drive</em>",
        "<strong class=\"color-accent-2\">CHANGED:</strong> Empire Forge now only offers bonuses, techs and units your installed game actually has. If you have not updated yet, the new content simply is not listed — nothing in the picker is a card that cannot work",
        "<strong class=\"color-accent-2\">CHANGED:</strong> \"Can garrison Docks with Fishing Ships\" has been retired — the game removed the Gurjaras bonus it was built from. The custom unique unit formerly called Varangian Guard is now <strong>Hetaireia</strong>, since the game now ships a real one",
    ],
    "2.1.1": [
        "<strong class=\"color-accent-2\">BUG FIX:</strong> <strong>The Flemish Militia is back.</strong> It was only ever reachable as an accidental side effect of the \"Farm upgrades +125% food\" bonus. Cleaning that up in 2.1.0 removed the unit's only path — it now has its own <strong>Unlock the Flemish Militia</strong> card (Barracks, Feudal Age)",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Unique unit stats no longer disappear when you open a saved civ. Saved civs deliberately don't store your DAT path (it's specific to your PC), and the stats lookup had no fallback — so every unit's popup read \"No stats available\" while the civ still built fine",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> If your game files genuinely can't be found, the unit popup now says so and points you at Step 1, instead of blaming the units",
        "Unlock cards are now filed under the <strong>Unlock</strong> category automatically, rather than landing under Research",
        "<em>Thanks to Maruviel on Discord for all three reports.</em>",
    ],
    "2.1.0": [
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Fixed a crash on game startup for civs with many team bonuses — team bonuses are merged into one effect and could exceed the engine's limit. The builder now warns you before you hit it",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> <strong>Team bonuses were doing each other's jobs.</strong> An internal list drifted out of alignment in July, so hand-written team bonuses ran a different bonus entirely — \"Spearmen +3 attack vs. cavalry\" was secretly \"Unique Units +5% HP\". All re-aligned",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Reviewed every team bonus for what it actually targets and fixed 12 — some were buffing a war wagon, an ostrich, a sheep and a wild tiger. Two others did nothing at all",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Audited all 350 civ bonus cards against their real in-game effects and fixed everything that didn't match — including several that did nothing, one that secretly unlocked Flemish Militia, and several that stopped working when the unit upgraded",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus multipliers — several were making bonuses <em>weaker</em> at x2 and x3. \"Start with…\" and \"free Villager\" cards ignored the multiplier entirely",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Editing a saved civ no longer erases both of its unique techs. If you edited a civ before and its UTs stopped working, this was why — please check them",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> The civ-selection screen now shows what your unique techs do, and shows the correct team bonus",
        "<strong class=\"color-accent-2\">NEW:</strong> 40 new bonus cards — 35 bonuses that already worked but were unreachable, plus a new \"drop off +%\" family for food, wood, stone and fishing",
        "<strong class=\"color-accent-2\">CHANGED:</strong> 10 team bonuses and the unique unit \"Attack Ignores Armor\" option have been removed — none of them worked, and the armor option left the unit dealing 1 damage. Saved civs still load; the builder tells you what was skipped",
        "Build messages now name units instead of listing raw ID numbers",
    ],
    "2.0.1": [
        "<strong class=\"color-accent-2\">NEW:</strong> Empire Forge is now a full civilization and mod builder — design tech trees, bonuses, team bonuses, unique units, unique technologies, and hero units natively",
        "<strong class=\"color-accent-2\">NEW:</strong> 'Convert KM Civ' tool imports existing KrakenMeister civ JSON files into the new format, so existing civs carry forward",
        "<strong class=\"color-accent-2\">NEW:</strong> Live tech tree editor — click any unit, building, or technology to enable or disable it for your civ",
        "<strong class=\"color-accent-2\">NEW:</strong> Bonus catalog with search and category filters",
        "Reads your installed game's DAT file directly at build time, so new DLCs won't brick the app",
    ],
    "1.7.4": [
        "<strong class=\"color-accent-2\">NEW:</strong> Microsoft Store / Xbox App installation now auto-detected — DAT file path found automatically on first launch",
        "<strong class=\"color-accent-2\">NEW:</strong> Bonus #286 added: Can upgrade Bombard Cannons to Houfnice (properly gated behind Imperial Age even when Bonus #283 is active)",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #283 (Chemistry/HC in Castle Age) completely reworked — now truly mirrors the Bohemian mechanism (tech 800/801 cloning) so Bombard Cannons, Bombard Towers, and Cannon Galleons all work correctly alongside early Chemistry",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Anarchy / Marauders unique tech — UU now appears at the correct button slot (R key / button 4) in Barracks or Stable after the tech fires; previously overwrote the militia or cavalry line button",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #222 (Barracks techs one age earlier) no longer clones DLC/Chronicles shadow techs or techs for units not in the civ's tree, preventing unresearchable duplicate buttons",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Vanilla KM unique units now correctly appear as trainable at the Krepost when the civ has Bonus #93 (Can build Krepost)",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Custom unique unit pierce armor stat now displays correctly in the in-game unit stats panel",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Idempotency guards added for Imperial Scorpion (#308), Royal Battle Elephant (#309), and Royal Lancer (#310) — prevents data corruption when multiple civs share these bonuses in a single build",
    ],
    "1.7.3": [
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Custom flag icon now shows correctly in the civilization picker and in-game interface",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #283 (Chemistry/Hand Cannoneer in Castle Age) no longer breaks Bombard Cannons, Bombard Towers, or Cannon Galleons — now mirrors the Bohemian mechanism",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #283 (Chemistry/Hand Cannoneer in Castle Age) Chemistry now correctly unlocks in Castle Age — Castle Age trigger was cloned but not wired correctly",
    ],
    "1.7.2": [
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Fixed a bug that prevented camel riders from being trainable",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Fixed Bonus #283 - Chemistry/HC in Castle Age",
    ],
    "1.7.1": [
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Team bonus labels displayed the wrong text in-game and in the builder — team bonuses now read from the correct name list",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Team bonus #30 (Military buildings +5 population room) was silently never applied — now correctly implemented",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #35 (Infantry +20% HP) was allocating dead Castle and Imperial stubs that did nothing — trimmed to the single correct Feudal tech",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #55 (Stable units +1 pierce armor in Castle &amp; Imperial Age) only applied in Imperial Age — Castle Age pierce armor now also fires correctly",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #280 (Folwark replaces the Mill) was allocating 7 extra empty/unrelated techs — trimmed to the correct 4-tech Poles chain",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #300 (Camel Scouts available in Feudal Age) produced a 0-command tech — now uses a direct enable command that correctly unlocks unit 1755",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #26 (TC/Dock work rate per age) had a trailing blank tech — now resolves to a single tech covering all four age variants",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #105 (Economic upgrades −33% food) previously allocated 10 dead stubs — food discount now correctly applies to all 16 standard eco upgrade techs at game start",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Bonus #318 (Start with a Mule Cart) had a blank placeholder tech removed; the actual spawn tech now fires cleanly",
        "<strong class=\"color-accent-2\">BUG FIX:</strong> Specific mod fix: Elite Organ Gun/Caravel upgrade buttons missing; UT hover showing wrong civ name; Castle UT showing no effect description; Carrack ×2 giving 0 armor instead of +2",
        "Known limitation noted: Bonus #105 applies the food discount but the 'one age earlier' portion is not yet implemented",
        "Known limitation noted: Bonuses #81 (no buildings to age up), #283 (Chemistry/HC in Castle Age), and #352 (Siege Engineers in Castle Age) require further coding to accommodate.",
    ],
    "1.67": [
        "<strong class=\"color-accent-2\">VOICE LINES:</strong> Your selected civs voice lines will now be properly set in-game",
        "<strong class=\"color-accent-2\">Castle/Wonder Skins:</strong> Your selected castle and wonder skins will be properly set in-game",
        "After loading the latest version, a popup will show you the most recent changes",
        "'What's New' page added, reading the latest changelog",
        "'How it Works' and 'Why' pages added",
        "Updated Install Instructions",
    ],
    "1.6": [
        "Future-Proofing: The app now reads your games' DAT file *and* civ files, preventing future DLC from breaking it.",
        "All 30 missing team bonuses implemented — full vanilla team bonus coverage achieved (0 unsupported)",
        "New civ bonus #222: Cows trainable from Mills",
        "New civ bonus #356: Pastures replace Farms — clones the Khitan mechanic",
        "Brand New civ bonus #401: Blacksmith attack upgrades also affect building damage (+1 vs buildings per Forging/Iron Casting, +2 per Blast Furnace)",
        "Bonus #327 ('Blacksmith upgrades scale bonus damage') this would require changing multiple attack values manually for every unit in the game. Marked as 'Unlikely to implement' in Known Limitations",
        "Team bonus #60 added (Resources last 5% longer)",
        "Fix: Imperial Skirmisher team bonus (#41) implemented",
        "Fix: Empty Trade Carts 20% faster implemented",
    ],
    "1.4": [
        "Added bonus handlers for unique unit upgrades: Imperial Scorpion (#308), Royal Battle Elephant (#309), Royal Lancer (#310)",
        "Added bonus #9 (Elite Mercenaries) and #29 (First Crusade) castle/imperial UT support with correct UU substitution",
        "Added bonus #400: City Walls (researchable Fortified Wall HP upgrade)",
        "Added bonus #279: Each Monastery tech spawns a free Monk",
        "Added bonuses #277/#278: Gunpowder units and buildings gain attack/HP from University techs",
        "Version tracking and auto-update notifications introduced",
    ],
}


@app.context_processor
def _inject_globals():
    latest_version = next(iter(CHANGELOG))
    return {
        "app_version": __version__,
        "update_info": _update_info,
        "changelog": CHANGELOG,
        "latest_changes": CHANGELOG.get(latest_version, []),
    }


# ── Session helpers ───────────────────────────────────────────────────────────

def _session_dir() -> Path:
    sid = session.get("sid")
    if not sid:
        sid = str(uuid.uuid4())
        session["sid"] = sid
    d = SESSIONS_DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


# Fallback exclusion set used when civilizations.json is unavailable.
# Lists DAT internal names of civs that belong to non-standard pools
# (e.g. the Chronicles / Antiquity Empires DLC roster).  Keep in sync
# with whatever DLC ships if civilizations.json auto-detection is broken.
_EXCLUDED_VANILLA_CIVS_FALLBACK = {
    "Achaemenids", "Athenians", "Spartans", "Macedonians", "Thracians", "Puru",
}


def _get_vanilla_civs(dat_path: str) -> list[str]:
    """Load playable vanilla civ names from the DAT, excluding Gaia and any
    non-base-era civs detected via civilizations.json (falls back to a
    hardcoded set if the JSON is absent)."""
    exclusions = (load_civ_era_exclusions(dat_path)
                  or _EXCLUDED_VANILLA_CIVS_FALLBACK)
    dat = load_dat(dat_path)
    return [c.name for c in dat.civs[1:] if c.name not in exclusions]


# The DAT's internal civ.name field still uses old/pre-DE naming for a
# handful of civs. Cosmetic only — _find_civ_slot matches on the real DAT
# name, so the <option value="..."> must stay unchanged; only the label
# shown to the user in the Configure dropdown is remapped.
VANILLA_DISPLAY_NAMES: dict[str, str] = {
    "British": "Britons",
    "French":  "Franks",
}

# Index 0 = Gaia, 1 = Britons, … matches DAT civ order.
_CIV_NAMES_BY_DAT_INDEX: list[str] = []
try:
    _civ_list = json.loads(
        (Path(__file__).parent / "civilizations.json").read_text()
    ).get("civilization_list", [])
    _CIV_NAMES_BY_DAT_INDEX = [c.get("internal_name", "") for c in _civ_list]
except Exception:
    pass

def _km_civ_name(km_index: int) -> str:
    """Friendly name for a 0-based KM civ index (castle/wonder/language style)."""
    dat_idx = km_index + 1
    if 0 < dat_idx < len(_CIV_NAMES_BY_DAT_INDEX):
        return _CIV_NAMES_BY_DAT_INDEX[dat_idx]
    return str(km_index)

def _arch_name(arch_val: int) -> str:
    """Friendly name for a 1-based KM architecture value."""
    if 1 <= arch_val <= len(_ARCH_REP_CIVS):
        dat_idx = _ARCH_REP_CIVS[arch_val - 1]
        if dat_idx < len(_CIV_NAMES_BY_DAT_INDEX):
            return _CIV_NAMES_BY_DAT_INDEX[dat_idx]
    return str(arch_val)


# ── Build progress (live feed) ────────────────────────────────────────────────
# The mod build runs in a background thread so the browser can poll for
# progress instead of staring at a blank page. This is an in-memory,
# single-process store, keyed by session id — fine for a local, single-user
# desktop app (no multi-worker/multi-process deployment to worry about).

_BUILD_JOBS: dict[str, dict] = {}
_BUILD_JOBS_LOCK = threading.Lock()


def _progress_push(job_id: str, line: str) -> None:
    line = line.rstrip()
    if not line:
        return
    with _BUILD_JOBS_LOCK:
        job = _BUILD_JOBS.get(job_id)
        if job is not None:
            job["lines"].append(line)


def _progress_finish(job_id: str, **result) -> None:
    with _BUILD_JOBS_LOCK:
        job = _BUILD_JOBS.get(job_id)
        if job is not None:
            job["done"] = True
            job.update(result)


class _LiveLogWriter(io.TextIOBase):
    """Stdout sink used in place of a plain StringIO when capturing
    apply_civ()'s print() calls. Mirrors completed lines into the live
    build-progress feed as they're written, while still buffering the full
    text for the per-civ "Build log" panel on the results page."""

    def __init__(self, job_id: str):
        self._job_id = job_id
        self._buf = io.StringIO()
        self._partial = ""

    def write(self, s: str) -> int:
        self._buf.write(s)
        self._partial += s
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            _progress_push(self._job_id, line)
        return len(s)

    def getvalue(self) -> str:
        return self._buf.getvalue()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/build-mod")
def build_mod():
    dat_path = find_game_dat()
    civtechtrees_path = str(find_civtechtrees(dat_path) or "") if dat_path else ""
    return render_template("build_mod.html",
                           dat_path=str(dat_path or ""),
                           civtechtrees_path=civtechtrees_path)


@app.route("/upload", methods=["POST"])
def upload():
    dat_path = request.form.get("dat_path", "").strip()
    dat_path_obj = Path(dat_path)
    if dat_path_obj.is_dir():
        # User pointed at the folder — try to find the DAT inside it.
        candidate = dat_path_obj / "empires2_x2_p1.dat"
        if candidate.exists():
            dat_path = str(candidate)
            dat_path_obj = candidate
        else:
            flash(f"That's a folder, not a DAT file. Point to empires2_x2_p1.dat directly.", "error")
            return redirect(url_for("build_mod"))
    if not dat_path_obj.exists():
        flash(f"DAT file not found: {dat_path}", "error")
        return redirect(url_for("build_mod"))

    # CivTechTrees path — optional; fall back to auto-detection from dat location.
    civtechtrees_path = request.form.get("civtechtrees_path", "").strip()
    if not civtechtrees_path:
        detected = find_civtechtrees(dat_path)
        civtechtrees_path = str(detected) if detected else ""

    files = request.files.getlist("civ_files")
    if not files or all(f.filename == "" for f in files):
        flash("Please select at least one civ JSON file.", "error")
        return redirect(url_for("build_mod"))

    sd = _session_dir()
    session["dat_path"] = dat_path

    civs = []
    for f in files:
        if not f.filename or not f.filename.endswith(".json"):
            continue
        dest = sd / f.filename
        f.save(dest)
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
            # bonuses[0] is the KM slot; an Empire Forge file has a flat list of
            # dicts there instead, which counted its keys rather than its bonuses.
            bonus_list = get_civ_bonuses(data)
            civs.append({
                "filename": f.filename,
                "name": (data.get("alias") or data.get("name")
                         or Path(f.filename).stem),
                "bonus_count": len(bonus_list),
                "castle_name":  _km_civ_name(data["castle"])  if "castle"       in data else None,
                "wonder_name":  _km_civ_name(data["wonder"])  if "wonder"       in data else None,
                "arch_name":    _arch_name(data["architecture"]) if "architecture" in data else None,
            })
        except Exception as e:
            flash(f"Could not parse {f.filename}: {e}", "warning")

    if not civs:
        flash("No valid civ JSON files found.", "error")
        return redirect(url_for("build_mod"))

    # Load vanilla civ list here (alongside file uploads) so configure loads instantly.
    vanilla_civs = []
    try:
        vanilla_civs = _get_vanilla_civs(dat_path)
    except Exception as e:
        flash(f"Could not read DAT file — check the path. ({e})", "error")
        return redirect(url_for("build_mod"))

    session["civs"]              = civs
    session["vanilla_civs"]      = vanilla_civs
    session["civtechtrees_path"] = civtechtrees_path
    return redirect(url_for("configure"))


@app.route("/configure")
def configure():
    civs         = session.get("civs")
    vanilla_civs = session.get("vanilla_civs", [])
    if not civs:
        return redirect(url_for("build_mod"))

    # Auto-assign: each uploaded civ gets the next available vanilla slot.
    # (Uses the DAT's own ordering — unrelated to the dropdown's display sort below.)
    defaults = {
        c["filename"]: vanilla_civs[i] if i < len(vanilla_civs) else ""
        for i, c in enumerate(civs)
    }

    # Sort the dropdown by the friendly display name (e.g. "Britons", not the
    # DAT's internal "British") so it lands in the alphabetical spot players expect.
    vanilla_civs_sorted = sorted(
        vanilla_civs, key=lambda v: VANILLA_DISPLAY_NAMES.get(v, v).lower())

    return render_template("configure.html", civs=civs,
                           vanilla_civs=vanilla_civs_sorted, defaults=defaults,
                           vanilla_display_names=VANILLA_DISPLAY_NAMES)


@app.route("/build", methods=["POST"])
def build():
    sd = _session_dir()
    job_id = session["sid"]
    dat_path = session.get("dat_path")
    civs_meta = {c["filename"]: c for c in session.get("civs", [])}

    ordered = request.form.getlist("civ_order[]")
    if not ordered:
        flash("No civs in build order — did JavaScript run?", "error")
        return redirect(url_for("configure"))

    mod_name = request.form.get("mod_name", "Custom Civs").strip() or "Custom Civs"
    replace_map = {fn: request.form.get(f"replace_{fn}", "").strip() for fn in ordered}

    # Safety net behind the client-side check in configure.html — two civs
    # pointed at the same vanilla slot would silently clobber each other.
    seen_targets: set[str] = set()
    for target in replace_map.values():
        if target and target in seen_targets:
            flash(f'Please select a unique civilization override for all civs '
                  f'— "{target}" is selected more than once.', "error")
            return redirect(url_for("configure"))
        seen_targets.add(target)

    with _BUILD_JOBS_LOCK:
        _BUILD_JOBS[job_id] = {"lines": [], "done": False, "error": None}

    threading.Thread(
        target=_run_build_job,
        args=(job_id, sd, dat_path, civs_meta, ordered, replace_map, mod_name),
        daemon=True,
    ).start()

    return render_template("building.html")


@app.route("/build/progress")
def build_progress():
    job_id = session.get("sid")
    with _BUILD_JOBS_LOCK:
        job = _BUILD_JOBS.get(job_id)
    if job is None:
        return jsonify(lines=[], total=0, done=True, error="No build in progress.")

    since = request.args.get("since", 0, type=int)
    payload = {
        "lines": job["lines"][since:],
        "total": len(job["lines"]),
        "done": job["done"],
        "error": job.get("error"),
    }

    if job["done"] and not job.get("error"):
        # Hand the finished build's location off to the real Flask session —
        # the background thread that built it has no request context (and
        # therefore no session) of its own to do this directly.
        session["results_path"] = job.get("results_path")
        session["out_file"]     = job.get("out_file")
        session["out_name"]     = job.get("out_name")

    return jsonify(payload)


def _run_build_job(job_id, sd, dat_path, civs_meta, ordered, replace_map, mod_name):
    try:
        _progress_push(job_id, "Loading game data…")
        dat = load_dat(dat_path)
        dat_path_obj = Path(dat_path)

        ct_folder = _find_civ_techtrees_folder(dat_path_obj)

        ai_stubs:    dict[str, bytes] = {}
        button_pngs: dict[str, bytes] = {}
        per_civ_tt:  dict[str, bytes] = {}
        string_lines: dict[str, list[str]] = {lang: [] for lang in LANGUAGES}
        build_results = []
        # Maps DAT slot -> (name_string_id, uu_icon_id) for civilizations.json
        # patching (civ-picker name + unique-unit thumbnail). Mirrors build_all.py.
        civs_overrides: dict[int, dict] = {}

        # Fixed, non-per-civ strings for bonus 308/309/310's shared unit slots.
        # Mirrors build_all.py's identical block.
        from civ_appender import FIXED_UNIT_NAME_STRINGS
        for lang in LANGUAGES:
            for sid, text in FIXED_UNIT_NAME_STRINGS:
                string_lines[lang].append(f'{sid} "{text}"')

        # Pre-compute which techtree positions will be replaced so we can skip
        # writing vanilla names for them.  AoE2 DE key-value files are
        # first-definition-wins — writing "Britons" first then "Horsey Boys" second
        # would leave the vanilla name in place.
        replaced_name_sids: set[int] = set()
        for _fn in ordered:
            _replace = replace_map.get(_fn, "")
            if not _replace:
                continue
            _slot = _find_civ_slot(dat, _replace)
            if _slot is None:
                continue
            _sid = civ_name_sid(dat.civs[_slot].name, dat_path, slot=_slot)
            if _sid is not None:
                replaced_name_sids.add(_sid)

        # Write vanilla civ name strings upfront, skipping replaced positions.
        for entry in civ_roster(dat_path)[1:]:       # slot 0 is Gaia
            sid = entry["name_sid"]
            if sid is None or sid in replaced_name_sids:
                continue
            vanilla_name = entry["name"]
            for lang in LANGUAGES:
                string_lines[lang].append(f'{sid} "{vanilla_name}"')
                string_lines[lang].append(f'{sid + 80000} "Click to play as {vanilla_name}."')

        total = sum(1 for fn in ordered if civs_meta.get(fn) and replace_map.get(fn))
        done_count = 0

        for fn in ordered:
            replace = replace_map.get(fn, "")
            meta = civs_meta.get(fn)
            if not meta or not replace:
                continue

            done_count += 1
            civ_path = sd / fn
            if not civ_path.exists():
                build_results.append({"name": meta["name"], "replace": replace,
                                      "error": f"Uploaded file missing: {fn}"})
                _progress_push(job_id, f"[{done_count}/{total}] {meta['name']}: "
                                       f"ERROR — uploaded file missing")
                continue

            civ_def = json.loads(civ_path.read_text(encoding="utf-8"))
            slot = _find_civ_slot(dat, replace)
            if slot is None:
                build_results.append({"name": meta["name"], "replace": replace,
                                      "error": f"Vanilla civ '{replace}' not found in DAT"})
                _progress_push(job_id, f"[{done_count}/{total}] {meta['name']}: "
                                       f"ERROR — '{replace}' not found in DAT")
                continue

            # Capture the vanilla civ name BEFORE apply_civ renames the slot.
            ui_civ_name = dat.civs[slot].name

            _progress_push(job_id, f"[{done_count}/{total}] Building {meta['name']} "
                                   f"→ replaces {replace}…")
            log_buf = _LiveLogWriter(job_id)
            with contextlib.redirect_stdout(log_buf):
                result = apply_civ(dat, civ_def, target_slot=slot)
                # Resolve UU info while still in the log context so any
                # diagnostic prints go to the web build log, then apply
                # civbuilder_v1-only overrides (UU stats, UT costs, hero unit).
                uu_info_resolved = _resolve_uu_info(civ_def, dat, slot, result)
                _override_ut_costs(dat, result, civ_def)
                _apply_uu_overrides(dat, slot, uu_info_resolved, civ_def)
                _refresh_uu_tooltips(dat, slot, result)
                _apply_hero_unit(dat, slot, civ_def)
            result["replace"] = replace
            result["log"]     = log_buf.getvalue()
            build_results.append(result)

            alias = result["alias"]
            # Slot-keyed via the live roster: a civ a DLC added gets its own
            # name string instead of writing over Britons (the 10271 fallback).
            name_sid = civ_name_sid(ui_civ_name, dat_path, slot=slot) or 10271

            _bonuses_raw_normalized      = get_civ_bonuses(civ_def)
            _team_bonuses_raw_normalized = get_team_bonuses(civ_def)

            # Resolve UT names — wizard format supplies name directly; KM format
            # uses the bonus-table lookup which packs "Name (desc)" together.
            castle_ut_bid  = _ut_bonus_id(civ_def, 2)
            imp_ut_bid     = _ut_bonus_id(civ_def, 3)
            castle_ut_name = (
                (civ_def.get("castle_ut") or {}).get("name")
                or _ut_name(castle_ut_bid, castle=True)
            )
            imp_ut_name = (
                (civ_def.get("imperial_ut") or {}).get("name")
                or _ut_name(imp_ut_bid, castle=False)
            )
            # Strip any parenthesized description suffix so button labels stay short.
            castle_ut_name_short = castle_ut_name.partition(" (")[0]
            imp_ut_name_short    = imp_ut_name.partition(" (")[0]
            # Enrich result with UT names for CivTechTrees node label updates.
            result["castle_ut_name"] = castle_ut_name
            result["imp_ut_name"]    = imp_ut_name

            # Real existing-id pool slots (civ_appender.CAMPAIGN_STRING_POOL) —
            # NOT the old high-range _str_id fallback, which never worked in-game.
            castle_ut_sid = result.get("castle_ut_sid") or _str_id(slot, STR_CASTLE_UT)
            imp_ut_sid    = result.get("imp_ut_sid")    or _str_id(slot, STR_IMPERIAL_UT)
            castle_ut_desc_sid = result.get("castle_ut_desc_sid") or castle_ut_sid
            imp_ut_desc_sid    = result.get("imp_ut_desc_sid")    or imp_ut_sid
            castle_ut_help_sid = result.get("castle_ut_help_sid")
            imp_ut_help_sid    = result.get("imp_ut_help_sid")
            castle_ut_desc_text = ((civ_def.get("castle_ut") or {}).get("description") or "").strip()
            imp_ut_desc_text    = ((civ_def.get("imperial_ut") or {}).get("description") or "").strip()

            # uu_info was already resolved inside the log context above.
            uu_info = uu_info_resolved
            uu_override_name = ((civ_def.get("unique_unit") or {}).get("name") or "").strip()
            uu_override_desc = ((civ_def.get("unique_unit") or {}).get("description") or "").strip()
            # See build_all.py's identical block for why civilizations.json's own
            # UU metadata block (unique_unit_id/elite_unique_unit_id/
            # unique_unit_string_ids/unique_unit_upgrade_id) needs explicit
            # retargeting — it's a separate block from the per-unit DAT strings
            # and is otherwise left pointing at the overwritten civ's original UU.
            civs_overrides[slot] = {
                "name_sid": name_sid,
                "icon_id": uu_info["icon_id"] if uu_info else None,
                "uu_unit_id":    uu_info["unit_id"]  if uu_info else None,
                "uu_elite_id":   uu_info["elite_id"] if uu_info else None,
                "uu_upgrade_tech_id": result.get("km_uu_elite_tech_id"),
                "uu_name_sid":   uu_info["dll_name"] if uu_info else None,
                "uu_desc_sid":   uu_info["dll_help"] if uu_info else None,
            }
            # Also look up the elite unit's dll_name for string writes.
            uu_elite_dll: int | None = None
            uu_elite_name: str | None = None
            if uu_info:
                elite_uid = uu_info.get("elite_id")
                if elite_uid is not None and elite_uid != uu_info["unit_id"]:
                    try:
                        eu = dat.civs[slot].units[elite_uid]
                        uu_elite_dll  = eu.language_dll_name
                        uu_elite_name = f"Elite {uu_override_name or uu_info['name']}"
                    except (IndexError, AttributeError):
                        pass

            # Hero unit string IDs — read after _apply_hero_unit has set language_dll_name.
            _hero_raw  = (civ_def.get("hero_unit") or {})
            _hero_bid  = _hero_raw.get("base_unit_id")
            _hero_name = (_hero_raw.get("name") or "").strip()
            _hero_desc = (_hero_raw.get("description") or "").strip()
            _hero_dll  = -1
            _hero_cost_str = ""
            if _hero_bid is not None and _hero_name:
                try:
                    _hero_dll = dat.civs[slot].units[_hero_bid].language_dll_name or -1
                except (IndexError, TypeError, AttributeError):
                    pass
                # Read after _apply_hero_unit, so the tooltip quotes the cost the
                # player will actually pay.
                _hero_cost_str = uu_cost_text(dat, slot, _hero_bid)

            # Build civ selection screen description with bonuses + UT names.
            # The wizard writes the blurb to `tagline` and nothing writes
            # `description`, so a schema file's own description is always "" and
            # this door used to fall back to "<Alias> civilization" while the
            # wizard door showed the real tagline. KM imports are the reverse,
            # which is why both keys are read. One key, in normalize().
            description   = civ_def.get("tagline") or civ_def.get("description", "")
            civ_bonuses        = _bonuses_raw_normalized
            team_bonus_entries = _team_bonuses_raw_normalized
            desc_parts = [f'{description} civilization' if description else f'{alias} civilization']
            desc_parts.append(" \\n\\n")
            for entry in civ_bonuses:
                if not isinstance(entry, list):
                    continue
                bid  = str(entry[0])
                mult = entry[1] if len(entry) > 1 else 1
                txt  = _BONUS_NAMES.get(bid, "")
                if not txt:
                    continue
                suffix = f" [x{mult}]" if mult > 1 else ""
                desc_parts.append(f"• {txt}{suffix} \\n")
            desc_parts.append("\\n<b>Unique Unit:<b> \\n")
            uu_display = uu_override_name or (uu_info["name"] if uu_info else "Unique Unit")
            desc_parts.append(f"{uu_display} \\n")
            desc_parts.append("\\n<b>Unique Techs:<b> \\n")
            desc_parts.append(f"• {castle_ut_name} \\n")
            desc_parts.append(f"• {imp_ut_name} \\n")
            if team_bonus_entries:
                desc_parts.append("\\n<b>Team Bonus:<b> \\n")
                for entry in team_bonus_entries:
                    if not isinstance(entry, list):
                        continue
                    bid = str(entry[0])
                    txt = _TEAM_BONUS_NAMES.get(bid, "")
                    if txt:
                        desc_parts.append(f"• {txt} \\n")
            full_desc = "".join(desc_parts)

            for lang in LANGUAGES:
                string_lines[lang].append(f'{name_sid} "{alias}"')
                string_lines[lang].append(
                    f'{name_sid + 80000} "Click to play as {alias}."')
                string_lines[lang].append(
                    f'{name_sid + 109879} "{full_desc}"')

                # Hero unit name + Castle train-button tooltip.
                if _hero_dll > 0 and _hero_name:
                    _hero_hover = f"Create <b>{_hero_name}<b>"
                    if _hero_desc:
                        _hero_hover += f"\\n{_hero_desc}"
                    if _hero_cost_str:
                        _hero_hover += f"\\n{_hero_cost_str}"
                    string_lines[lang].append(f'{_hero_dll} "{_hero_name}"')
                    string_lines[lang].append(f'{_hero_dll + DLL_CREATION_OFFSET} "{_hero_hover}"')
                    string_lines[lang].append(f'{_hero_dll + 21000} "{_hero_hover}"')
                    string_lines[lang].append(f'{_hero_dll + DLL_HELP_OFFSET} "{_hero_hover}"')

                # Castle UT: language_dll_help (60xxx pool SID) drives the research-button
                # hover tooltip — NOT name+21000, which is the unit-train-button slot.
                string_lines[lang].append(f'{castle_ut_sid} "{castle_ut_name_short}"')
                string_lines[lang].append(
                    f'{castle_ut_sid + DLL_CREATION_OFFSET} "Research {castle_ut_name_short}"')
                _castle_ut_help = f"Research <b>{castle_ut_name_short}<b> (<cost>)"
                if castle_ut_desc_text:
                    _castle_ut_help += f"\\n{castle_ut_desc_text}"
                # language_dll_help = name_sid+21000 (same slot KM uses; 60xxx pool range
                # is overwritten by campaign string files loaded after the mod).
                string_lines[lang].append(f'{castle_ut_sid + 21000} "{_castle_ut_help}"')
                # NOTE: no write to castle_ut_desc_sid — it IS castle_ut_sid+1000,
                # the short research-button label set just above.  See the matching
                # note in wizard_build.py.
                string_lines[lang].append(
                    f'{castle_ut_sid + DLL_TECH_TREE_OFFSET} "{castle_ut_name_short}"')

                # Imperial UT
                string_lines[lang].append(f'{imp_ut_sid} "{imp_ut_name_short}"')
                string_lines[lang].append(
                    f'{imp_ut_sid + DLL_CREATION_OFFSET} "Research {imp_ut_name_short}"')
                _imp_ut_help = f"Research <b>{imp_ut_name_short}<b> (<cost>)"
                if imp_ut_desc_text:
                    _imp_ut_help += f"\\n{imp_ut_desc_text}"
                string_lines[lang].append(f'{imp_ut_sid + 21000} "{_imp_ut_help}"')
                # NOTE: same as the Castle UT above — imp_ut_desc_sid is the
                # button label slot, not a separate description slot.
                # Short name, like the Castle UT six lines up and like both UTs
                # on the wizard door: the bonus-table lookup packs "Name (desc)"
                # into one string and the F2 tech-tree node wants only the name.
                string_lines[lang].append(
                    f'{imp_ut_sid + DLL_TECH_TREE_OFFSET} "{imp_ut_name_short}"')
                # Bonus-specific research buttons (Imperial Scorpion, Royal Battle
                # Elephant, Royal Lancer — bonuses 308/309/310). Mirrors
                # build_all.py's identical block — this was previously missing
                # here entirely, leaving these buttons blank when built via the
                # web app.
                for ext in result["bonus_results"].get("extra_tech_strings", []):
                    sid, name = ext["sid"], ext["name"]
                    string_lines[lang].append(f'{sid} "{name}"')
                    string_lines[lang].append(f'{sid + DLL_CREATION_OFFSET} "Research {name}"')
                    _ext_help = f"Research <b>{name}<b> (<cost>)"
                    string_lines[lang].append(f'{sid + DLL_HELP_OFFSET} "{_ext_help}"')
                    string_lines[lang].append(f'{sid + 150000} "{name}"')
                    # language_dll_help = name+21000 (same slot used for UTs; 60xxx
                    # pool range is overwritten by campaign files loaded after the mod).
                    string_lines[lang].append(f'{sid + 21000} "{_ext_help}"')
                _owned_sids: set[int] = set()
                # KM-custom UU units' OWN name/help strings — see build_all.py's
                # identical block for why this is separate from the dll_name+10000
                # tech-tree-viewer block right below.
                for ext in result["bonus_results"].get("extra_unit_strings", []):
                    # sid+DLL_CREATION_OFFSET (name+1000) is what the engine
                    # actually reads for the Castle "create unit" button/elite
                    # tech description — must be written explicitly, same
                    # reasoning as the Castle/Imperial UT block above. desc_sid
                    # (=sid+DLL_HELP_OFFSET, computed by civ_appender) is the
                    # full tooltip.
                    # extra_unit_strings holds the richest text for these ids —
                    # real stats, real cost, the user's description.  Record the
                    # ids so the generic block below cannot overwrite them with a
                    # bare name, which is what left a custom UU's hover tooltip
                    # showing neither cost nor description (issue #34).
                    sid, name = ext["sid"], ext["name"]
                    string_lines[lang].append(f'{sid} "{name}"')
                    string_lines[lang].append(
                        f'{sid + DLL_CREATION_OFFSET} "Create {name}"')
                    help_text = ext.get("help_text", name)
                    desc_sid = ext.get("desc_sid", sid)
                    string_lines[lang].append(f'{desc_sid} "{help_text}"')
                    _owned_sids |= {sid, sid + DLL_CREATION_OFFSET, desc_sid}
                    # The Castle "create unit" button's EXTENDED hover tooltip
                    # for a UNIT is read from name+21000, NOT name+100000 — see
                    # build_all.py's identical block / civ_appender.
                    # _extended_tooltip_sid's docstring for how this was found.
                    if "ext_sid" in ext:
                        string_lines[lang].append(
                            f'{ext["ext_sid"]} "{ext.get("ext_text", name)}"')
                        _owned_sids.add(ext["ext_sid"])

                def _put(sid_: int, text: str) -> None:
                    """Write unless extra_unit_strings already owns that id."""
                    if sid_ not in _owned_sids:
                        string_lines[lang].append(f'{sid_} "{text}"')

                # UU name strings for civ selection tech tree display and Castle button.
                if uu_info:
                    uu_dll = uu_info["dll_name"]
                    _ext_sid_taken = (uu_dll + 21000) in _owned_sids
                    is_renamed = bool(uu_override_name) or (
                        uu_display != _KM_UU_NAMES.get(get_km_uu_index(civ_def), uu_display))
                    if is_renamed:
                        _put(uu_dll, uu_display)
                        _put(uu_dll + DLL_CREATION_OFFSET, f"Create {uu_display}")
                    _put(uu_dll + 10000, uu_display)
                    # Quote the training cost the player is actually charged.
                    # This block previously wrote no cost at all, so a UU built
                    # through this route never showed one (issue #34).
                    _uu_hover = f"Create <b>{uu_display}<b>"
                    if uu_override_desc:
                        _uu_hover += f"\\n{uu_override_desc}"
                    _cost = uu_cost_text(dat, slot, uu_info.get("unit_id"))
                    if _cost:
                        _uu_hover += f"\\n{_cost}"
                    _put(uu_dll + DLL_HELP_OFFSET, _uu_hover)
                    if not _ext_sid_taken:
                        _put(uu_dll + 21000, _uu_hover)
                if uu_elite_dll and uu_elite_name:
                    _elite_hover = f"Create <b>{uu_elite_name}<b>"
                    if uu_override_desc:
                        _elite_hover += f"\\n{uu_override_desc}"
                    _ecost = uu_cost_text(dat, slot,
                                           uu_info.get("elite_id") if uu_info else None)
                    if _ecost:
                        _elite_hover += f"\\n{_ecost}"
                    _put(uu_elite_dll, uu_elite_name)
                    _put(uu_elite_dll + DLL_CREATION_OFFSET, f"Create {uu_elite_name}")
                    _put(uu_elite_dll + 10000, uu_elite_name)
                    _put(uu_elite_dll + DLL_HELP_OFFSET, _elite_hover)
                    _put(uu_elite_dll + 21000, _elite_hover)

            flag_png = _decode_flag(civ_def)
            if flag_png:
                # Use canonical civTechTrees name (e.g. "britons") not DAT internal
                # name (e.g. "british") — game loads icons by canonical name.
                fn_img = _canonical_techtree_id(ui_civ_name, dat_path, slot=slot).lower()
                for variant in ("", "_hover", "_pressed"):
                    button_pngs[f"menu_techtree_{fn_img}{variant}.png"] = flag_png

            ai_name = f"{alias} AI (pre-alpha)"
            ai_stubs[f"resources/_common/ai/{ai_name}.ai"]  = b""
            ai_stubs[f"resources/_common/ai/{ai_name}.per"] = AI_PER_STUB

            if ct_folder:
                vanilla_tt_name = _canonical_techtree_id(ui_civ_name, dat_path, slot=slot)
                per_civ_path = ct_folder / f"{vanilla_tt_name}.json"
                if per_civ_path.exists():
                    patched = _patch_per_civ_techtree(per_civ_path, civ_def, dat, slot,
                                                        civ_result=result)
                    if patched is not None:
                        per_civ_tt[f"{vanilla_tt_name}.json"] = patched

        # Fill in vanilla per-civ CivTechTrees JSONs for every unmodified civ.
        # AoE2 DE (post 2026-06-02 patch) uses per-civ files exclusively — if any are
        # missing, the game falls back to the vanilla global and ignores all our patches.
        if ct_folder:
            for json_file in sorted(ct_folder.glob("*.json")):
                if json_file.name not in per_civ_tt:
                    per_civ_tt[json_file.name] = json_file.read_bytes()

        # Tie-break MUST be insertion order, not the line's own text — see
        # build_all.py's identical sort (which has this fix already; app.py was
        # missing it). Sorting ties alphabetically silently breaks "first-
        # definition-wins" whenever two different call sites write different
        # text to the SAME id (e.g. a bare unit name from the tech-tree-viewer
        # block + a richer formatted tooltip from extra_unit_strings) — confirmed
        # via a live build that this exact collision can shadow Gendarme's help
        # text. In the current code the richer line happens to be appended
        # first, so this is currently a latent-risk fix rather than the active
        # cause of any reported symptom, but matching build_all.py's safety net
        # costs nothing and removes the dependency on append-order staying lucky.
        def _sort_key(indexed_line: tuple[int, str]) -> tuple[int, int]:
            idx, line = indexed_line
            try:
                return (int(line.split(" ", 1)[0]), idx)
            except ValueError:
                return (10**9, idx)

        combined_strings = {
            lang: "\n".join(line for _, line in sorted(enumerate(lines), key=_sort_key)) + "\n"
            for lang, lines in string_lines.items()
            if lines
        }

        # Generate civilizations.json with updated names + UU icon paths for
        # replaced civs. Required since the 2026-06-06 patch — AoE2 DE now
        # validates this file's entry count against the DAT civ count and
        # silently drops modded-strings civ-picker overrides without it.
        civs_json_bytes: bytes | None = None
        base_civs_json = _find_adjacent_json(dat_path_obj, "civilizations.json")
        if base_civs_json is None or not base_civs_json.exists():
            base_civs_json = Path(__file__).parent / "civilizations.json"
        if base_civs_json.exists() and civs_overrides:
            try:
                with open(base_civs_json, encoding="utf-8") as f:
                    civ_list = json.load(f).get("civilization_list", [])
                for slot_idx, ov in civs_overrides.items():
                    if slot_idx >= len(civ_list):
                        continue
                    entry = civ_list[slot_idx]
                    entry["name_string_id"] = ov["name_sid"]
                    icon_id = ov.get("icon_id")
                    if icon_id is not None:
                        entry["unique_unit_image_paths"] = [
                            f"/resources/uniticons/{icon_id:03d}_50730.png"
                        ]
                    uu_unit_id = ov.get("uu_unit_id")
                    if uu_unit_id is not None:
                        entry["unique_unit_id"] = uu_unit_id
                        if ov.get("uu_elite_id") is not None:
                            entry["elite_unique_unit_id"] = ov["uu_elite_id"]
                        if ov.get("uu_upgrade_tech_id") is not None:
                            entry["unique_unit_upgrade_id"] = ov["uu_upgrade_tech_id"]
                        if ov.get("uu_name_sid") is not None:
                            name_sid_uu = ov["uu_name_sid"]
                            # See build_all.py's identical block — prefer the
                            # explicit desc sid (real id for both vanilla and
                            # KM-custom UUs); the +DLL_HELP_OFFSET fallback only
                            # reliably works for the vanilla path.
                            desc_sid_uu = ov.get("uu_desc_sid") or (name_sid_uu + DLL_HELP_OFFSET)
                            entry["unique_unit_string_ids"] = [
                                {"name": name_sid_uu, "description": desc_sid_uu}
                            ]
                civs_json_bytes = json.dumps(
                    {"civilization_list": civ_list}, separators=(",", ":")
                ).encode("utf-8")
            except Exception as e:
                print(f"WARNING: Could not generate civilizations.json: {e}")

        # Batch language/voice assignment using KM's 3-phase algorithm.
        lang_assignments = [(r["civ_index"], r["lang_val"]) for r in build_results]
        log_buf = _LiveLogWriter(job_id)
        with contextlib.redirect_stdout(log_buf):
            assign_all_languages(dat, lang_assignments)

        _progress_push(job_id, "Packaging mod files…")
        prefix   = mod_name.lower().replace(" ", "_")
        unique_lang_values = {lang_val for _, lang_val in lang_assignments}
        # Packaging runs under the same redirect as the language pass so its
        # output — notably the "no voice files found" warning — reaches the
        # build log the user actually sees, not bare stdout (which a windowed
        # exe discards).
        with contextlib.redirect_stdout(log_buf):
            data_zip = _build_combined_data_zip(dat, button_pngs, per_civ_tt, mod_name=mod_name,
                                                civs_json_bytes=civs_json_bytes)
            ui_zip   = _build_combined_ui_zip(ai_stubs, button_pngs, combined_strings,
                                              mod_name=mod_name,
                                              lang_values=unique_lang_values)

        out_path = sd / f"{prefix}.zip"
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as outer:
            outer.writestr(f"{prefix}-data.zip", data_zip)
            outer.writestr(f"{prefix}-ui.zip",   ui_zip)

        # Store results in a file — logs make them too large for a cookie session.
        results_path = sd / "results.json"
        results_path.write_text(json.dumps(build_results), encoding="utf-8")

        out_name = f"{prefix}.zip"
        _progress_push(job_id, f"Done — {out_name} ready to download.")
        _progress_finish(job_id, results_path=str(results_path),
                         out_file=str(out_path), out_name=out_name)
    except Exception as e:
        import traceback
        traceback.print_exc()  # still goes to the real console for debugging
        _progress_push(job_id, f"ERROR: {e}")
        _progress_finish(job_id, error=str(e))


@app.route("/results")
def results():
    results_path = session.get("results_path")
    build_results = []
    if results_path and Path(results_path).exists():
        build_results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    has_download  = bool(session.get("out_file") and
                         Path(session["out_file"]).exists())
    out_name      = session.get("out_name", "mod.zip")
    return render_template("results.html", results=build_results,
                           has_download=has_download, out_name=out_name,
                           bonus_name=bonus_name, skip_reason=skip_reason)


_BONUS_NEVER_WORKED = {211, 218}
_BONUS_UNLIKELY     = {327}
_BONUS_UPCOMING     = {222, 229, 270, 323, 356}


@app.route("/limitations")
def limitations():
    all_unsupported = unsupported_bonuses()
    never_worked = [b for b in all_unsupported if b["id"] in _BONUS_NEVER_WORKED]
    unlikely     = [b for b in all_unsupported if b["id"] in _BONUS_UNLIKELY]
    upcoming     = [b for b in all_unsupported if b["id"] in _BONUS_UPCOMING]
    return render_template(
        "limitations.html",
        never_worked_bonuses=never_worked,
        unlikely_bonuses=unlikely,
        upcoming_bonuses=upcoming,
        unsupported_units=unsupported_unique_units(),
        unsupported_castle_uts=unsupported_unique_techs(castle=True),
        unsupported_imp_uts=unsupported_unique_techs(castle=False),
        unsupported_team=unsupported_team_bonuses(),
    )


@app.route("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")

@app.route("/why")
def why():
    return render_template("why.html")

@app.route("/changelog")
def changelog():
    return render_template("changelog.html", changelog=CHANGELOG)


@app.route("/download")
def download():
    out_file = session.get("out_file")
    out_name = session.get("out_name", "mod.zip")
    if not out_file or not Path(out_file).exists():
        flash("No output file available — please build first.", "error")
        return redirect(url_for("results"))
    return send_file(out_file, as_attachment=True, download_name=out_name)


@app.route("/reset")
def reset():
    session.clear()
    return redirect(url_for("index"))


# ── Civ Builder ───────────────────────────────────────────────────────────────

_ARCH_OPTIONS = [
    {"value": 1,  "label": "Central European",       "example": "Goths, Teutons, Huns"},
    {"value": 2,  "label": "Western European",        "example": "Britons, Franks, Celts"},
    {"value": 3,  "label": "East Asian",              "example": "Japanese, Chinese, Koreans"},
    {"value": 4,  "label": "Middle Eastern",          "example": "Persians, Saracens, Turks"},
    {"value": 5,  "label": "Mesoamerican",            "example": "Aztecs, Mayans"},
    {"value": 6,  "label": "Mediterranean",           "example": "Byzantines, Italians, Spanish"},
    {"value": 7,  "label": "South Asian",             "example": "Hindustanis, Dravidians"},
    {"value": 8,  "label": "Eastern European",        "example": "Magyars, Slavs, Bulgarians"},
    {"value": 9,  "label": "African",                 "example": "Ethiopians, Malians"},
    {"value": 10, "label": "Southeast Asian",         "example": "Khmer, Malay, Burmese"},
    {"value": 11, "label": "Central Asian / Nomadic", "example": "Tatars, Cumans, Mongols"},
    {"value": 12, "label": "South American",           "example": "Inca, Mapuche, Muisca, Tupi"},
    # icon_set 13, NEW in Viking Sagas: the Vikings were Central European until
    # that DLC gave them their own set, which is why the value-1 example above
    # no longer names them.  Offered only when the player's DAT actually has
    # icon_set 13 — on an older one it would copy Central European under a
    # Nordic label.
    {"value": 13, "label": "Nordic",                   "example": "Vikings, Varangians, Danes"},
]

# Unit the civ starts the game with, written to civ.resources[263].
# Mirrors civ_appender.STARTING_SCOUT_UNITS; the unit need not be trainable.
_SCOUT_OPTIONS = [
    {"value": 448,  "label": "Scout Cavalry",  "example": "Default — most civilizations"},
    {"value": 751,  "label": "Eagle Scout",    "example": "Aztecs, Mayans"},
    {"value": 1755, "label": "Camel Scout",    "example": "Gurjaras"},
    {"value": 2550, "label": "Champi Runner",  "example": "Inca, Mapuche, Muisca, Tupi"},
]


@app.route("/resources/uniticons/<path:filename>")
def serve_unit_icon(filename):
    return send_from_directory(Path(__file__).parent / "uniticons", filename)


@app.route("/builder")
def builder_landing():
    return render_template("builder_landing.html")


@app.route("/builder/new")
def builder_new():
    return render_template("builder_wizard.html")


@app.route("/api/builder/detect-dat")
def api_builder_detect_dat():
    """Return auto-detected DAT and CivTechTrees paths (may be empty strings if not found)."""
    dat = find_game_dat()
    dat_path = str(dat) if dat else ""
    ct_path  = str(find_civtechtrees(dat) or "") if dat else ""
    return jsonify({"dat_path": dat_path, "civtechtrees_path": ct_path, "found": bool(dat_path)})


@app.route("/api/builder/validate-dat")
def api_builder_validate_dat():
    """Is this path usable as the game DAT?  Cheap enough to run as you type.

    Auto-detection only knows the default install locations, so anyone with
    Steam on a second drive (`D:\\SteamLibrary\\...`) has to type the path by
    hand — and until now the wizard gave them **no** signal either way.  The
    path was saved to the draft, prewarm was fired and its answer thrown away,
    and the status line kept showing "Not auto-detected" forever.  A user on a
    D: drive reported "I entered it manually and it doesn't work"; his path was
    in fact correct, and nothing told him so (2026-09-22).

    Deliberately does not parse the DAT: that is ~16s, far too slow for typing
    feedback, and prewarm already does it in the background.  This answers the
    questions that actually go wrong — wrong drive, folder instead of file,
    typo in the filename — and reports whether CivTechTrees was found alongside,
    which is the other half of a usable install.
    """
    raw = (request.args.get("dat_path") or "").strip().strip('"')
    if not raw:
        return jsonify({"ok": False, "reason": "Enter the path to empires2_x2_p1.dat."})

    p = Path(raw)
    if p.is_dir():
        # Same helpfulness the /upload route already has: people paste the folder.
        candidate = p / "empires2_x2_p1.dat"
        if candidate.exists():
            p = candidate
        else:
            return jsonify({"ok": False,
                            "reason": "That's a folder, not the DAT file. "
                                      "Point to empires2_x2_p1.dat itself."})
    if not p.exists():
        hint = ""
        # A drive letter that isn't there at all is worth calling out — it is the
        # single most common cause on a machine with more than one drive.
        if len(raw) > 1 and raw[1] == ":" and not Path(raw[:3]).exists():
            hint = f" Drive {raw[0].upper()}: isn't reachable from here."
        return jsonify({"ok": False, "reason": f"No file at that path.{hint}"})
    if not p.is_file():
        return jsonify({"ok": False, "reason": "That path isn't a file."})
    if p.name.lower() != "empires2_x2_p1.dat":
        return jsonify({"ok": False,
                        "reason": f"Expected empires2_x2_p1.dat, got {p.name}."})
    try:
        size_mb = p.stat().st_size / (1024 * 1024)
    except OSError as e:                                          # noqa: BLE001
        return jsonify({"ok": False, "reason": f"Cannot read that file: {e}"})
    if size_mb < 1:
        return jsonify({"ok": False,
                        "reason": f"That file is only {size_mb:.1f} MB — too small "
                                  f"to be the game DAT."})

    ct = find_civtechtrees(p)
    return jsonify({"ok": True, "dat_path": str(p), "size_mb": round(size_mb, 1),
                    "civtechtrees_path": str(ct) if ct else "",
                    "reason": "" if ct else
                              "Found the DAT, but no CivTechTrees folder beside it — "
                              "set that below if your build looks wrong."})


@app.route("/api/builder/meta")
def api_builder_meta():
    # value = dat_index - 1 (KM 0-based convention; 0 = Britons).
    # Antiquity / Chronicles civs are excluded: their wonder and castle models
    # are not available to base-game civs.
    # Read the PLAYER's civilizations.json, not our bundled copy, for the same
    # reason the build does: a DLC adds civs, and a frozen list silently offers
    # the wrong roster.  Before this, the wonder, castle and voice pickers were
    # stuck at 53 civs and the three Viking Sagas civs simply did not exist in
    # the wizard.  Falls back to the bundled copy on its own.
    from build_civ import civ_roster
    from civ_appender import _UNLOCK_UNIT_BONUSES, MONK_SKIN_OPTIONS, _ARCH_REP_CIVS
    dat_path = _resolve_dat_path(request.args.get("dat_path"))
    roster = civ_roster(dat_path) or []
    if not roster:
        roster = [{"name": c.get("internal_name", ""), "era": c.get("era", "base")}
                  for c in _civ_list]
    civ_options = sorted([
        {"value": i - 1, "label": c.get("name", "")}
        for i, c in enumerate(roster)
        if i > 0 and c.get("era", "base") != "antiquity" and c.get("name")
    ], key=lambda x: x["label"])

    # Architecture and Monk sets are partitions of the DAT, so offer only the
    # ones the player's DAT actually contains.  Viking Sagas added both a
    # thirteenth architecture and an eleventh Monk; on an older DAT neither
    # exists, and the option would quietly copy its representative civ's OLD
    # art under the new label.
    arch_options = _ARCH_OPTIONS
    monk_options = MONK_SKIN_OPTIONS
    # Use the DAT only if it is ALREADY parsed.  This route is awaited by the
    # wizard's init() before anything renders, so it must never be the thing
    # that triggers a parse: doing so made a cold start sit on "Loading..." for
    # 34 seconds (measured 2026-09-24, shipped in 2.2.0 — my regression).
    # `/api/builder/prewarm` exists to fill this cache on a background thread,
    # which is the whole reason meta was fast before.  Cold, we fall back to the
    # unfiltered lists, which is exactly the pre-2.2.0 behaviour.
    if dat_path and dat_path in _DAT_OBJ_CACHE:
        try:
            _pd = _DAT_OBJ_CACHE[dat_path]
            _sets = {c.icon_set for c in _pd.civs[1:]}
            arch_options = [a for a in _ARCH_OPTIONS if a["value"] in _sets]

            def _monk_of(idx):
                u = (_pd.civs[idx].units[125]
                     if _pd.civs[idx].units and len(_pd.civs[idx].units) > 125 else None)
                return u.standing_graphic if u else None

            _seen: dict = {}
            for _i in range(1, len(_pd.civs)):
                _g = _monk_of(_i)
                if _g is not None:
                    _seen.setdefault(_g, []).append(_i)
            # A Monk option is real here only if its representative civ heads a
            # partition no earlier option already covers.
            _claimed: set = set()
            monk_options = []
            for _o in MONK_SKIN_OPTIONS:
                _g = _monk_of(_o["value"])
                if _g is None or _g in _claimed:
                    continue
                _claimed.add(_g)
                monk_options.append(_o)
        except Exception:                                        # noqa: BLE001
            arch_options, monk_options = _ARCH_OPTIONS, MONK_SKIN_OPTIONS
    # Driven by which voice_files/<value>/ folders actually exist, not a fixed
    # count.  build_all bundles those .wem files into the mod, so offering a
    # voice we have no folder for would silently ship a civ with no audio.
    # Drop a new folder in and the option appears.
    voice_options = sorted([
        {"value": i - 1, "label": c.get("name", "")}
        for i, c in enumerate(roster)
        if i > 0 and (i - 1) in _available_voice_values() and c.get("name")
    ], key=lambda x: x["label"])
    # bonus_id → unit_ids, so the wizard can derive the "Unlock ..." bonuses
    # from the tech tree without keeping its own copy of the table.
    unlock_bonuses = {
        str(bid): list(spec["units"]) for bid, spec in _UNLOCK_UNIT_BONUSES.items()
    }
    return jsonify({
        "architectures": arch_options,
        "civs": civ_options,
        "voices": voice_options,
        "starting_scouts": _SCOUT_OPTIONS,
        "monk_skins": monk_options,
        "unlock_bonuses": unlock_bonuses,
        # Display names for the identity scene ("Hagia Sophia" rather than
        # "Byzantines").  Written by scripts/import_km_art.py; absent until that
        # has been run, so the wizard falls back to civ names.
        "scene_names": _scene_names(),
        # civ option value -> KM art index (they diverge past 44; see above)
        "scene_art_index": _scene_art_index(civ_options),
        # architecture value -> the civ option value whose art it borrows, so the
        # scene can draw a concrete wonder/castle for "— Architecture Default —".
        # Mirrors _ARCH_REP_CIVS (DAT indices) shifted into the KM 0-based
        # convention the wonder/castle selects use.
        "arch_rep_civs": {
            str(i + 1): dat_idx - 1 for i, dat_idx in enumerate(_ARCH_REP_CIVS)
        },
    })


_SCENE_NAMES_PATH = Path(__file__).parent / "static" / "data" / "scene_names.json"
_scene_names_cache: dict | None = None

# KM's art arrays are indexed by HIS civ order, which matches ours only up to
# index 44.  His snapshot predates the current DAT ordering of the Three
# Kingdoms / Dynasties of China civs: he has Shu/Wu/Wei at 45-47 and
# Jurchens/Khitans at 48-49, where the live DAT has Shu=48 … Khitans=52.
# Without this remap, choosing Shu would silently render a Jurchen castle.
_VOICE_FILES_DIR = Path(__file__).parent / "voice_files"


# The 43 languages KM extracted (values 0-42).  Used as a floor when the
# voice_files/ tree isn't present at all.
_VOICE_FALLBACK_VALUES = frozenset(range(43))


def _available_voice_values() -> set[int]:
    """Voice values with a voice_files/<value>/ folder holding at least one .wem.

    The spec bundles voice_files/, so the scan works in the packaged exe too.
    The historical 0-42 fallback only covers a checkout without the (gitignored)
    folder, where scanning alone would render the Voice dropdown empty.
    """
    out: set[int] = set()
    try:
        for d in _VOICE_FILES_DIR.iterdir():
            if d.is_dir() and d.name.isdigit() and any(d.glob("*.wem")):
                out.add(int(d.name))
    except OSError:
        pass
    return out or set(_VOICE_FALLBACK_VALUES)


_SCENE_ART_OVERRIDES = {48: 45, 49: 46, 50: 47, 51: 48, 52: 49}

# Which art indices actually exist is read off disk rather than hardcoded to
# KM's 0-49, so hand-gathered additions (the South American civs, which postdate
# his snapshot) light up without touching this file.  A civ is mapped if EITHER
# a castle or a wonder exists for it; the other slot 404s to a placeholder.
_SCENE_ART_DIRS = (("castles", "castle"), ("wonders", "wonder"))
_SCENE_ART_RE = re.compile(r"^(?:castle|wonder)_(\d+)\.webp$")


def _scene_names() -> dict:
    """KM's wonder/castle/language display-name arrays, indexed by ART index."""
    global _scene_names_cache
    if _scene_names_cache is None:
        try:
            with open(_SCENE_NAMES_PATH, encoding="utf-8") as f:
                _scene_names_cache = json.load(f)
        except (OSError, json.JSONDecodeError):
            _scene_names_cache = {}
    return _scene_names_cache


def _scene_art_index(civ_options: list[dict]) -> dict[str, int]:
    """civ option value -> KM art index, omitting civs KM has no art for.

    Civs newer than KM's snapshot (Muisca, Mapuche, Tupi) are simply absent; the
    wizard renders a labelled placeholder for those rather than a broken image.
    """
    available: set[int] = set()
    base = Path(__file__).parent / "static" / "img" / "scene"
    for sub, _stem in _SCENE_ART_DIRS:
        try:
            for f in (base / sub).iterdir():
                m = _SCENE_ART_RE.match(f.name)
                if m:
                    available.add(int(m.group(1)))
        except OSError:
            pass

    out: dict[str, int] = {}
    for opt in civ_options:
        v = opt["value"]
        art = _SCENE_ART_OVERRIDES.get(v, v)
        if art in available:
            out[str(v)] = art
    return out


_TECHTREE_DATA_PATH = Path(__file__).parent / "static" / "aoe2techtree" / "data" / "data.json"
_techtree_data: dict | None = None

def _load_techtree_data() -> dict:
    global _techtree_data
    if _techtree_data is None:
        with open(_TECHTREE_DATA_PATH, encoding="utf-8") as f:
            _techtree_data = json.load(f)
    return _techtree_data


@app.route("/api/builder/techtree")
def api_builder_techtree():
    """Return a localtree array ([[unitIds], [buildingIds], [techIds]]) for a
    given civ, or the full master tree if civ=full (or omitted).

    data.json now uses SE format: top-level key 'civs' (not 'techtrees'),
    with per-civ dicts having 'Unit', 'Building', 'Tech' integer arrays.
    """
    civ = request.args.get("civ", "full")
    td  = _load_techtree_data()

    if civ == "full":
        # Return all IDs known across all civs combined
        all_units = set()
        all_bldgs = set()
        all_techs = set()
        for cv in td.get("civs", {}).values():
            all_units.update(cv.get("Unit", []))
            all_bldgs.update(cv.get("Building", []))
            all_techs.update(cv.get("Tech", []))
        return jsonify({
            "units":     sorted(all_units),
            "buildings": sorted(all_bldgs),
            "techs":     sorted(all_techs),
        })

    civs = td.get("civs", {})
    if civ not in civs:
        return jsonify({"error": f"Unknown civ: {civ}"}), 404

    cv = civs[civ]
    return jsonify({
        "units":     cv.get("Unit",     []),
        "buildings": cv.get("Building", []),
        "techs":     cv.get("Tech",     []),
    })


@app.route("/api/builder/techtree/civs")
def api_builder_techtree_civs():
    td = _load_techtree_data()
    return jsonify(sorted(td.get("civs", {}).keys()))


@app.route("/api/builder/bonuses/catalog")
def api_builder_bonuses_catalog():
    from bonus_names import (unsupported_bonuses, unsupported_team_bonuses,
                             DEPRECATED_BONUSES)
    with open(Path(__file__).parent / "bonus_names.json", encoding="utf-8") as f:
        names = json.load(f)
    with open(Path(__file__).parent / "team_bonus_names.json", encoding="utf-8") as f:
        team_names = json.load(f)
    unsupported_ids = {b["id"] for b in unsupported_bonuses()}
    # Deprecated bonuses still build for civs that reference them; they are just
    # not offered for new picks. See bonus_names.DEPRECATED_BONUSES.
    hidden_ids = unsupported_ids | set(DEPRECATED_BONUSES)

    # ...and, as for unique techs and unique units, a bonus the PLAYER's OWN DAT
    # cannot implement.  A card is built by cloning its techs' effect commands,
    # so the twelve Viking Sagas bonuses are inert for anyone still on the
    # previous patch, where those tech slots are nameless and empty.  Only
    # bonuses that HAVE techs are judged this way: plenty are implemented from
    # `ec_list` instead and carry none, and hiding those would empty the picker.
    dat_path = _resolve_dat_path(request.args.get("dat_path"))
    if dat_path:
        try:
            _d = _get_dat(dat_path)
            from bonus_catalog import civ_bonus_techs, team_bonus_tech

            def _live(tech_id: int) -> bool:
                if tech_id >= len(_d.techs):
                    return False
                eid = _d.techs[tech_id].effect_id
                return 0 <= eid < len(_d.effects) and bool(_d.effects[eid].effect_commands)

            for k in names:
                techs = civ_bonus_techs(int(k)) or []
                if techs and not any(_live(int(x)) for x in techs):
                    hidden_ids.add(int(k))
        except Exception:                                        # noqa: BLE001
            pass
    civ_bonuses = [
        {"id": int(k), "label": v}
        for k, v in sorted(names.items(), key=lambda x: int(x[0]))
        if int(k) not in hidden_ids
    ]
    # Team bonuses get the same treatment as civ bonuses: an id the catalog
    # cannot implement is not offered.  This list used to be unfiltered, so a
    # team bonus with no catalog entry was pickable and then silently dropped at
    # build time.
    unsupported_team_ids = {b["id"] for b in unsupported_team_bonuses()}
    # Same for team bonuses, which copy a vanilla effect wholesale: an effect
    # this DAT ships empty leaves the card doing nothing, unless a team_ec_list
    # entry stands in for it (which is exactly how the three bonuses Viking
    # Sagas hollowed out keep working).
    if dat_path:
        try:
            from bonus_catalog import team_bonus_ec_list
            for k in team_names:
                ei = team_bonus_tech(int(k))
                if ei is None:
                    continue                      # no mapping; ec_list decides
                # Out of range counts as empty, not as "cannot tell": the three
                # new civs' effects (1455-1457) simply do not exist in a DAT
                # from before the DLC, which is precisely when the card must
                # not be offered.
                live = (0 <= ei < len(_d.effects)
                        and bool(_d.effects[ei].effect_commands))
                if not live and not team_bonus_ec_list(int(k)):
                    unsupported_team_ids.add(int(k))
        except Exception:                                        # noqa: BLE001
            pass
    team_bonuses = [
        {"id": int(k), "label": v}
        for k, v in sorted(team_names.items(), key=lambda x: int(x[0]))
        if int(k) not in unsupported_team_ids
    ]
    return jsonify({"civ": civ_bonuses, "team": team_bonuses})


def _unit_stats_block(u) -> dict:
    """Extract display stats from a genieutils unit object."""
    t50 = u.type_50
    bonuses = []
    for a in t50.attacks:
        if a.class_ in _SKIP_ATTACK_CLASSES or a.amount <= 0:
            continue
        name = _ATTACK_CLASS_NAMES.get(a.class_)
        if name:
            bonuses.append([name, a.amount])
    bonuses.sort(key=lambda x: -x[1])
    try:
        train_time = int(u.creatable.train_time)
    except (AttributeError, TypeError):
        train_time = None
    return {
        "hp":          u.hit_points,
        "attack":      t50.displayed_attack,
        "melee_armor": t50.displayed_melee_armour,
        "pierce_armor": u.creatable.displayed_pierce_armour,
        "range":       t50.max_range if t50.max_range > 0 else None,
        "min_range":   t50.min_range if t50.min_range > 0 else None,
        "reload_time": round(t50.reload_time, 2),
        "speed":       round(u.speed, 2),
        "train_time":  train_time,
        "bonuses":     bonuses,
    }


def _build_all_uu_stats(dat_path: str) -> dict[int, dict]:
    """
    Compute full stats for every UU from the DAT file.
    Returns km_idx → {base, elite, ranged, traits, cost}.
    Cached in _UU_STATS_CACHE keyed by dat_path.
    """
    import civ_appender as ca
    import km_custom_uu as kcu

    if dat_path in _UU_STATS_CACHE:
        return _UU_STATS_CACHE[dat_path]

    # Try the disk cache — survives app restarts, keyed by DAT mtime.
    cached = _load_uu_stats_disk(dat_path)
    if cached is not None:
        _UU_STATS_CACHE[dat_path] = cached
        return cached

    dat  = _get_dat(dat_path)
    out: dict[int, dict] = {}
    vanilla_keys = set(ca._KM_UU_TECHS.keys())
    presets      = getattr(kcu, "PRESETS", {})
    RES          = {0: "F", 1: "W", 2: "S", 3: "G"}

    # ── Vanilla units ────────────────────────────────────────────────────────
    for km_idx in vanilla_keys:
        try:
            t1, t2 = ca._KM_UU_TECHS[km_idx]
            eff1   = dat.effects[dat.techs[t1].effect_id]
            eff2   = dat.effects[dat.techs[t2].effect_id]

            base_uid: int | None = None
            for cmd in eff1.effect_commands:
                if cmd.type == 2:          # EC_ENABLE
                    base_uid = int(cmd.a); break

            if base_uid is None:
                continue

            # Match EC_UPGRADE in elite tech where a == base_uid
            elite_uid: int | None = None
            for cmd in eff2.effect_commands:
                if cmd.type == 3 and int(cmd.a) == base_uid:
                    elite_uid = int(cmd.b); break

            bu = dat.civs[0].units[base_uid]
            eu = dat.civs[0].units[elite_uid] if elite_uid is not None else None

            cost_parts: list[str] = []
            for civ_i in range(min(2, len(dat.civs))):
                parts = [
                    f"{int(rc.amount)}{RES[rc.type]}"
                    for rc in dat.civs[civ_i].units[base_uid].creatable.resource_costs
                    if rc.type in RES and rc.amount > 0
                ]
                if parts:
                    cost_parts = parts
                    break

            out[km_idx] = {
                "base":   _unit_stats_block(bu),
                "elite":  _unit_stats_block(eu) if eu else None,
                "ranged": bu.type_50.max_range > 0,
                "traits": _UU_TRAITS.get(km_idx, []),
                "cost":   " ".join(cost_parts),
            }
        except Exception:
            pass

    # ── Custom units (PRESETS) ───────────────────────────────────────────────
    for km_idx, p in presets.items():
        try:
            base_uid = p.get("base_unit_id")
            bu = dat.civs[0].units[base_uid] if base_uid is not None else None

            hp      = p.get("hp",     (None, None)) or (None, None)
            speed_p = p.get("speed",  (None, None)) or (None, None)
            da      = p.get("displayed_attack",    (None, None)) or (None, None)
            dma     = p.get("displayed_melee_armor",  (None, None)) or (None, None)
            dpa     = p.get("displayed_pierce_armor", (None, None)) or (None, None)

            mode    = p.get("mode", "replace")
            attacks = p.get("attacks") or ([], [])

            # Derive displayed_attack from class 4 (melee) when not set explicitly
            def _class4_atk(atk_list):
                if not atk_list:
                    return None
                for item in atk_list:
                    if len(item) == 2 and isinstance(item[0], int) and item[0] == 4:
                        return item[1]
                return None

            def _r(pair, fallback):
                b = pair[0] if pair[0] is not None else (fallback() if callable(fallback) else fallback)
                e = pair[1] if pair[1] is not None else b
                return b, e

            # For attack: prefer explicit da, then class-4 amount, then base_unit field
            c4_base  = _class4_atk(attacks[0] if attacks else [])
            c4_elite = _class4_atk(attacks[1] if len(attacks) > 1 else [])
            base_da  = da[0] if da[0] is not None else (c4_base if c4_base is not None else
                        (bu.type_50.displayed_attack if bu else None))
            elite_da = da[1] if da[1] is not None else (c4_elite if c4_elite is not None else base_da)

            base_ma, elite_ma = _r(dma, lambda: bu.type_50.displayed_melee_armour    if bu else None)
            base_pa, elite_pa = _r(dpa, lambda: bu.creatable.displayed_pierce_armour if bu else None)

            base_range  = bu.type_50.max_range   if bu else None
            base_reload = bu.type_50.reload_time if bu else None
            base_speed  = round(bu.speed, 2)     if bu else None

            spd_b = speed_p[0] or base_speed
            spd_e = (speed_p[1] if len(speed_p) > 1 else None) or spd_b

            # Attack bonuses — only works cleanly in 'replace' mode; skip class 4 (main attack)
            def _parse_attacks(lst):
                result = []
                if mode != "replace":
                    return result
                for item in (lst or []):
                    if len(item) == 2 and isinstance(item[0], int):
                        cls, amt = item[0], item[1]
                        # class 4 = melee base attack, already shown as Attack field
                        if cls == 4 or cls in _SKIP_ATTACK_CLASSES or amt <= 0:
                            continue
                        nm = _ATTACK_CLASS_NAMES.get(cls)
                        if nm:
                            result.append([nm, amt])
                return sorted(result, key=lambda x: -x[1])

            base_bon  = _parse_attacks(attacks[0] if attacks else [])
            elite_bon = _parse_attacks(attacks[1] if len(attacks) > 1 else [])

            # Training cost — unit_cost may be None
            uc       = p.get("unit_cost") or {}
            uu_tup   = uc.get("uu") if uc else None
            cost_mode = uc.get("mode", "full")
            if cost_mode == "full" and isinstance(uu_tup, (tuple, list)) and len(uu_tup) == 4:
                cost_str = " ".join(f"{int(v)}{['F','W','S','G'][i]}"
                                    for i, v in enumerate(uu_tup) if v)
            elif cost_mode == "amount" and isinstance(uu_tup, list) and bu is not None:
                # [(slot_idx, amount), ...] — slot index into base unit's ResourceCosts array,
                # keeps the inherited resource type, only amount is overridden.
                slot_amts = {int(si): int(amt) for si, amt in uu_tup}
                parts = []
                for si, rc in enumerate(bu.creatable.resource_costs):
                    amt = slot_amts.get(si, int(rc.amount))
                    if rc.type in RES and amt > 0:
                        parts.append(f"{amt}{RES[rc.type]}")
                cost_str = " ".join(parts) if parts else None
            else:
                cost_str = None

            hp_b = hp[0]
            hp_e = hp[1] if len(hp) > 1 and hp[1] is not None else hp_b

            def _tier(hp_v, da_v, ma_v, pa_v, spd_v, bons):
                return {
                    "hp":          hp_v,
                    "attack":      da_v,
                    "melee_armor": ma_v,
                    "pierce_armor":pa_v,
                    "range":       base_range if base_range and base_range > 0 else None,
                    "min_range":   None,
                    "reload_time": round(base_reload, 2) if base_reload else None,
                    "speed":       spd_v,
                    "bonuses":     bons,
                }

            out[km_idx] = {
                "base":   _tier(hp_b, base_da,  base_ma,  base_pa,  spd_b, base_bon),
                "elite":  _tier(hp_e, elite_da, elite_ma, elite_pa, spd_e, elite_bon),
                "ranged": bool(base_range and base_range > 0),
                "traits": _UU_TRAITS.get(km_idx, []),
                "cost":   cost_str,
            }
        except Exception:
            pass

    _UU_STATS_CACHE[dat_path] = out
    _save_uu_stats_disk(dat_path, out)   # persist so future restarts skip the parse
    return out


def _resolve_dat_path(arg: str | None = None) -> str:
    """The DAT to read, from the request, then the session, then detection.

    The wizard sends `draft.dat_path`, but **`civ_schema` strips `dat_path`
    when a civ is saved** — correctly, since it is machine-specific and has no
    business in a shared `.civbuilder.json`.  So every draft loaded from a saved
    civ arrives without one.

    `/builder/build` has always fallen back to the session, so builds kept
    working; these read-only helper routes did not, so they silently returned
    nothing.  The visible result was that **loading a saved civ made every
    unique unit's stat popup read "No stats available"** while the civ still
    built fine — reported by a user 2026-09-21, and impossible to connect to
    "you opened a saved civ" from the outside.

    Each candidate has to exist on disk before it wins, so a path that has gone
    stale — a moved install, a civ file edited by hand, a drive that is not
    mounted — falls through to the next one instead of being honoured into a
    blank screen.
    """
    for candidate in ((arg or "").strip(),
                      (session.get("dat_path") or "").strip(),
                      str(find_game_dat() or "")):
        if candidate and Path(candidate).exists():
            return candidate
    return ""


@app.route("/api/builder/prewarm")
def api_builder_prewarm():
    """Start DAT parsing + UU stat computation in a background thread.

    Called by the JS as soon as dat_path is known (step 1 page load), so the
    cache is warm long before the user reaches the UU picker step.
    """
    dat_path = _resolve_dat_path(request.args.get("dat_path"))
    if not dat_path:
        return jsonify({"status": "skipped", "reason": "no dat_path"})
    if dat_path in _UU_STATS_CACHE:
        return jsonify({"status": "already_cached"})

    def _warm():
        try:
            _build_all_uu_stats(dat_path)
        except Exception as exc:
            print(f"[prewarm] {exc}")

    threading.Thread(target=_warm, daemon=True).start()
    return jsonify({"status": "warming"})


@app.route("/api/builder/uu/catalog")
def api_builder_uu_catalog():
    import civ_appender as ca
    import km_custom_uu as kcu

    # km_idx → icon filename (only confirmed-present entries)
    _ICON_MAP: dict[int, str] = {
        0:  "041_50730.png",   # Longbowman
        1:  "046_50730.png",   # Throwing Axeman
        2:  "050_50730.png",   # Huskarl
        4:  "044_50730.png",   # Samurai
        5:  "036_50730.png",   # Chu Ko Nu
        6:  "035_50730.png",   # Cataphract
        7:  "037_50730.png",   # Mameluke
        8:  "043_50730.png",   # War Elephant
        11: "042_50730.png",   # Mangudai
        12: "047_50730.png",   # Woad Raider
        13: "106_50730.png",   # Conquistador
        14: "110_50730.png",   # Jaguar Warrior
        16: "105_50730.png",   # Tarkan
        17: "117_50730.png",   # War Wagon
        18: "133_50730.png",   # Genoese Crossbowman
        21: "099_50730.png",   # Magyar Huszar
        22: "114_50730.png",   # Boyar
        23: "190_50730.png",   # Organ Gun
        24: "195_50730.png",   # Shotel Warrior
        26: "191_50730.png",   # Camel Archer
        27: "231_50730.png",   # Ballista Elephant
        29: "230_50730.png",   # Arambai
        30: "232_50730.png",   # Rattan Archer
        32: "251_50730.png",   # Keshik
        33: "252_50730.png",   # Kipchak
        34: "253_50730.png",   # Leitis
        35: "355_50730.png",   # Coustillier
        36: "356_50730.png",   # Serjeant
        37: "369_50730.png",   # Obuch
        38: "370_50730.png",   # Hussite Wagon
        45: "405_50730.png",   # Centurion
        82: "408_50730.png",   # Monaspa
        84: "436_50730.png",   # Fire Archer
        86: "461_50730.png",   # Iron Pagoda
        87: "463_50730.png",   # Liao Dao
        3:  "045_50730.png",   # Teutonic Knight
        9:  "039_50730.png",   # Janissary
        10: "038_50730.png",   # Berserk
        15: "108_50730.png",   # Plumed Archer
        19: "385_50730.png",   # Ghulam
        20: "097_50730.png",   # Kamayuk
        25: "197_50730.png",   # Gbeto
        28: "233_50730.png",   # Karambit Warrior
        31: "249_50730.png",   # Konnik
        78: "390_50730.png",   # Chakram Thrower
        79: "386_50730.png",   # Urumi Swordsman
        80: "389_50730.png",   # Ratha
        81: "407_50730.png",   # Composite Bowman
        83: "434_50730.png",   # White Feather Guard
        85: "432_50730.png",   # Tiger Cavalry
        # Custom units
        39: "377_50730.png",   # Crusader Knight
        40: "351_50730.png",   # Xolotl Warrior
        41: "058_50730.png",   # Saboteur
        42: "299_50730.png",   # Ninja
        43: "144_50730.png",   # Flamethrower
        44: "300_50730.png",   # Photonman
        46: "319_50730.png",   # Apukispay
        48: "166_50730.png",   # Amazon Warrior
        49: "165_50730.png",   # Amazon Archer
        50: "297_50730.png",   # Iroquois Warrior
        51: "357_50730.png",   # Hetaireia
        52: "260_50730.png",   # Gendarme
        54: "379_50730.png",   # Ritterbruder
        55: "256_50730.png",   # Kazak
        56: "376_50730.png",   # Szlachcic
        58: "236_50730.png",   # Rajput
        60: "207_50730.png",   # Numidian Javelinman
        61: "350_50730.png",   # Sosso Guard
        62: "136_50730.png",   # Swiss Pikeman
        63: "359_50730.png",   # Headhunter
        64: "368_50730.png",   # Teulu
        65: "366_50730.png",   # Maillotins
        66: "206_50730.png",   # Hashashin
        67: "163_50730.png",   # Highlander
        68: "361_50730.png",   # Stradiot
        69: "216_50730.png",   # Ahosi
        70: "162_50730.png",   # Landsknecht
        71: "181_50730.png",   # Clibinarii
        72: "259_50730.png",   # Silahtar
        73: "119_50730.png",   # Jaridah
        74: "081_50730.png",   # Wolf Warrior
        76: "375_50730.png",   # Castellan
        53: "317_50730.png",   # Cuahchiqueh
        57: "244_50730.png",   # Cuirassier
        59: "180_50730.png",   # Seljuk Archer
        77: "306_50730.png",   # Wind Warrior
    }

    unsupported = {47, 75}
    vanilla_keys = set(ca._KM_UU_TECHS.keys())
    catalog = []

    # Load full stats from DAT if a path is available
    dat_path = _resolve_dat_path(request.args.get("dat_path"))
    stats_map: dict[int, dict] = {}
    if dat_path:
        try:
            stats_map = _build_all_uu_stats(dat_path)
        except Exception as e:                                   # noqa: BLE001
            # Was a bare `pass`.  A DAT that will not parse then looked exactly
            # like a unit that has no stats, and the popup said "No stats
            # available" with nothing anywhere explaining why.
            print(f"  WARNING: could not read unit stats from {dat_path!r}: {e}",
                  flush=True)

    # A vanilla UU is built by cloning its make-avail and elite techs, so one
    # whose techs are empty placeholders in THIS DAT cannot be built at all —
    # the three Viking Sagas units are empty slots for anyone who has not
    # updated.  Same rule the UT catalog uses.  KM-custom UUs are unaffected:
    # they are built from a base unit, not from a DAT tech.
    missing_in_dat: set[int] = set()
    derived_icons: dict[int, str] = {}
    if dat_path:
        try:
            _d = _get_dat(dat_path)

            def _tech_live(tech_id: int) -> bool:
                if tech_id >= len(_d.techs):
                    return False
                eid = _d.techs[tech_id].effect_id
                return 0 <= eid < len(_d.effects) and bool(_d.effects[eid].effect_commands)

            missing_in_dat = {i for i, pair in ca._KM_UU_TECHS.items()
                              if not all(_tech_live(t) for t in pair)}

            # A vanilla UU's icon file is always "<base unit's icon_id>_50730.png"
            # — checked against all 50 hand-listed vanilla entries, and every
            # one matches.  So derive it rather than hand-listing the next one:
            # the six South American units and the three Viking Sagas units were
            # all missing purely because nobody had added a map entry.  The
            # 36 KM-custom entries stay hand-listed (their cloned base unit does
            # not carry the right icon) and still win as an override.
            def _base_unit(tech_id: int) -> int | None:
                if not _tech_live(tech_id):
                    return None
                for c in _d.effects[_d.techs[tech_id].effect_id].effect_commands:
                    if c.type in (2, 3):
                        return int(c.a)
                return None

            for i, pair in ca._KM_UU_TECHS.items():
                if i in _ICON_MAP or i in missing_in_dat:
                    continue
                uid = _base_unit(pair[0])
                if uid is None:
                    continue
                u = next((cv.units[uid] for cv in _d.civs
                          if cv.units and len(cv.units) > uid and cv.units[uid]), None)
                icon_id = getattr(u, "icon_id", -1) if u else -1
                if isinstance(icon_id, int) and icon_id >= 0:
                    derived_icons[i] = f"{icon_id:03d}_50730.png"
        except Exception:                                        # noqa: BLE001
            missing_in_dat = set()
            derived_icons = {}

    # Only offer an icon whose file is actually there.  A map entry pointing at
    # a missing PNG renders as a broken image; `None` renders as no image, which
    # is what an un-illustrated unit should look like.  The upshot is that
    # dropping a new file into uniticons/ is the whole job — no code change.
    _icon_dir = Path(__file__).parent / "uniticons"

    for km_idx, name in ca._KM_UU_NAMES.items():
        if km_idx in unsupported or km_idx in missing_in_dat:
            continue
        icon_file = _ICON_MAP.get(km_idx) or derived_icons.get(km_idx)
        if icon_file and not (_icon_dir / icon_file).exists():
            icon_file = None
        is_vanilla = km_idx in vanilla_keys
        entry_stats = stats_map.get(km_idx)

        catalog.append({
            "km_idx":        km_idx,
            "name":          name,
            "vanilla":       is_vanilla,
            "icon":          f"/resources/uniticons/{icon_file}" if icon_file else None,
            "stats":         entry_stats,
            "training_cost": entry_stats["cost"] if entry_stats else None,
        })
    catalog.sort(key=lambda x: x["name"])
    return jsonify(catalog)


def _split_ut_label(label: str) -> tuple[str, str]:
    """'Garland Wars (Infantry +4 attack)' → ('Garland Wars', 'Infantry +4 attack')"""
    m = re.match(r'^(.+?)\s*\((.+)\)\s*$', label)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return label, ""


@app.route("/api/builder/ut/catalog")
def api_builder_ut_catalog():
    from civ_appender import _KM_CASTLE_UT_TECHS, _KM_IMP_UT_TECHS

    # A preset is only offered if the PLAYER's OWN DAT implements its source
    # tech, because the preset works by cloning that tech's effect commands.
    # Ordonnance Companies (castle 64) is tech 1496, which is a nameless empty
    # placeholder until Viking Sagas fills it in — offering it to someone who
    # has not updated would ship a unique tech that researches and does
    # nothing.  Exactly one preset is affected today, but keying on "does this
    # tech have an effect here" rather than a version check means the next DLC
    # preset is safe the day it is added.
    #
    # If no DAT can be read we offer everything, which is the old behaviour:
    # the catalog is also used for browsing, and hiding the whole list because
    # we could not find a DAT would be worse than listing one dud.
    has_effect = None
    dat_path = _resolve_dat_path(request.args.get("dat_path"))
    if dat_path and Path(dat_path).exists():
        try:
            dat = _get_dat(dat_path)

            def has_effect(tech_id: int) -> bool:       # noqa: F811
                if tech_id >= len(dat.techs):
                    return False
                eid = dat.techs[tech_id].effect_id
                return (0 <= eid < len(dat.effects)
                        and bool(dat.effects[eid].effect_commands))
        except Exception:
            has_effect = None

    def _entries(strings, table):
        out = []
        for i, label in enumerate(strings):
            tech_id = table.get(i)
            if tech_id is None:
                continue
            if has_effect is not None and not has_effect(tech_id):
                continue
            name, desc = _split_ut_label(label)
            out.append({"id": i, "label": label, "name": name, "desc": desc})
        return out

    return jsonify({"castle":   _entries(_UNIQUE_CASTLE_STRINGS, _KM_CASTLE_UT_TECHS),
                    "imperial": _entries(_UNIQUE_IMP_STRINGS, _KM_IMP_UT_TECHS)})


@app.route("/api/builder/ut/costs")
def api_builder_ut_costs():
    """Return vanilla tech research costs (from DAT) for all UT catalog entries."""
    from civ_appender import _KM_CASTLE_UT_TECHS, _KM_IMP_UT_TECHS
    dat_path = _resolve_dat_path(request.args.get("dat_path"))
    if not dat_path or not Path(dat_path).exists():
        return jsonify({"castle": {}, "imperial": {}})

    if dat_path not in _DAT_COSTS_CACHE:
        try:
            dat = _get_dat(dat_path)
            RES_MAP = {0: "food", 1: "wood", 2: "stone", 3: "gold"}

            def _tech_cost(tech_id: int) -> dict | None:
                if tech_id >= len(dat.techs):
                    return None
                t = dat.techs[tech_id]
                cost = {"food": 0, "wood": 0, "stone": 0, "gold": 0}
                for rc in t.resource_costs:
                    if rc.type in RES_MAP and rc.amount > 0:
                        cost[RES_MAP[rc.type]] = int(rc.amount)
                time_s = (t.research_locations[0].research_time
                          if t.research_locations else 60)
                return {"cost": cost, "time": int(time_s)}

            castle   = {str(k): v for k, tid in _KM_CASTLE_UT_TECHS.items()
                        if (v := _tech_cost(tid)) is not None}
            imperial = {str(k): v for k, tid in _KM_IMP_UT_TECHS.items()
                        if (v := _tech_cost(tid)) is not None}
            _DAT_COSTS_CACHE[dat_path] = {"castle": castle, "imperial": imperial}
        except Exception:
            return jsonify({"castle": {}, "imperial": {}})

    return jsonify(_DAT_COSTS_CACHE[dat_path])


@app.route("/builder/build", methods=["POST"])
def builder_build():
    import re
    from wizard_build import build_wizard_mod

    data        = request.get_json(silent=True) or {}
    draft       = data.get("draft", {})
    replace_civ = data.get("replace_civ", "Goths")

    if not draft.get("alias"):
        return jsonify({"error": "Draft is missing a civilization name."}), 400
    if not draft.get("architecture"):
        return jsonify({"error": "Draft is missing an architecture selection."}), 400

    # Accept dat_path from POST body (wizard self-contained), fall back to session
    dat_path = data.get("dat_path") or session.get("dat_path")
    if not dat_path or not Path(dat_path).exists():
        return jsonify({
            "error": (
                "No game DAT file found. "
                "Please enter the path to your empires2_x2_p1.dat file in Step 1."
            )
        }), 400

    try:
        zip_bytes = build_wizard_mod(draft, dat_path, replace_civ)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Build failed: {e}"}), 500

    sd       = _session_dir()
    alias    = draft.get("alias", "custom_civ")
    prefix   = re.sub(r"[^A-Za-z0-9_-]", "_", alias).lower() or "custom_civ"
    out_name = f"{prefix}_wizard_mod.zip"
    out_path = sd / out_name
    out_path.write_bytes(zip_bytes)
    session["wizard_out_file"] = str(out_path)
    session["wizard_out_name"] = out_name

    return jsonify({"url": url_for("builder_download"), "filename": out_name})


@app.route("/builder/download")
def builder_download():
    out_file = session.get("wizard_out_file")
    out_name = session.get("wizard_out_name", "wizard_mod.zip")
    if not out_file or not Path(out_file).exists():
        return "No wizard mod file available — please build first.", 404
    return send_file(out_file, as_attachment=True, download_name=out_name)


@app.route("/api/builder/export", methods=["POST"])
def builder_export():
    import io
    import re
    from civ_schema import from_draft

    data  = request.get_json(silent=True) or {}
    draft = data.get("draft", {})

    if not draft.get("alias"):
        return jsonify({"error": "Draft is missing a civilization name."}), 400

    try:
        schema = from_draft(draft)
    except Exception as e:
        return jsonify({"error": f"Export failed: {e}"}), 500

    alias    = draft.get("alias", "custom_civ")
    filename = re.sub(r"[^A-Za-z0-9_-]", "_", alias).lower() or "custom_civ"
    filename = f"{filename}.civbuilder.json"

    json_bytes = json.dumps(schema, indent=2, ensure_ascii=False).encode("utf-8")
    return send_file(
        io.BytesIO(json_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/json",
    )


@app.route("/builder/convert-km")
def builder_convert_km():
    return render_template("convert_km.html")


@app.route("/api/builder/convert-km", methods=["POST"])
def api_convert_km():
    """Convert a KrakenMeister civ JSON into a wizard draft."""
    import re
    from civ_schema import is_km_format, is_empireforge, _DRAFT_VER

    data   = request.get_json(silent=True) or {}
    km_raw = data.get("km", {})

    if not km_raw:
        return jsonify({"error": "No JSON body provided."}), 400
    if is_empireforge(km_raw):
        return jsonify({"error": "This file is already in Empire Forge format — use Edit Civ instead."}), 400
    if not is_km_format(km_raw):
        return jsonify({"error": "File does not look like a KrakenMeister civ JSON."}), 400

    try:
        draft = _km_to_draft(km_raw)
    except Exception as e:
        return jsonify({"error": f"Conversion failed: {e}"}), 500

    return jsonify({"draft": draft})


def _km_to_draft(km: dict) -> dict:
    """Convert a KrakenMeister civ JSON dict to a wizard draft dict."""
    from civ_schema import _DRAFT_VER

    raw_b = km.get("bonuses", [])
    civ_bons  = raw_b[0] if len(raw_b) > 0 and isinstance(raw_b[0], list) else []
    uu_part   = raw_b[1] if len(raw_b) > 1 else []
    castle_fx = raw_b[2] if len(raw_b) > 2 and isinstance(raw_b[2], list) else []
    imp_fx    = raw_b[3] if len(raw_b) > 3 and isinstance(raw_b[3], list) else []
    team_bons = raw_b[4] if len(raw_b) > 4 and isinstance(raw_b[4], list) else []

    km_uu_idx = uu_part[0] if uu_part and isinstance(uu_part[0], int) else None

    def _norm(lst):
        out = []
        for e in lst:
            if isinstance(e, (list, tuple)) and len(e) >= 1:
                out.append({"id": int(e[0]), "multiplier": int(e[1]) if len(e) > 1 else 1})
            elif isinstance(e, int):
                out.append({"id": e, "multiplier": 1})
        return out

    def _ut(fx_list):
        # No `time` key: absence is the honest way to say "the KM file did not
        # carry one", and _override_ut_costs then leaves the vanilla tech's own.
        # The all-zero `cost` stays because the wizard's cost inputs assign into
        # it, and _override_ut_costs now reads zero as unset too.
        return {
            "mode": "vanilla", "vanilla_km_idx": None,
            "name": "", "description": "",
            "cost": {"food": 0, "wood": 0, "stone": 0, "gold": 0},
            "effects": _norm(fx_list),
        }

    raw_tree = km.get("tree", [[], [], []])
    if isinstance(raw_tree, list) and len(raw_tree) >= 3:
        tree = {
            "units":     [int(x) for x in (raw_tree[0] or [])],
            "buildings": [int(x) for x in (raw_tree[1] or [])],
            "techs":     [int(x) for x in (raw_tree[2] or [])],
        }
    else:
        tree = {"units": [], "buildings": [], "techs": []}

    return {
        "_draftVer":    _DRAFT_VER,
        "alias":        km.get("alias", km.get("civName", "Converted Civ")),
        "tagline":      "",
        "description":  km.get("description", ""),
        "architecture": km.get("architecture", 2),
        "language":     km.get("language", 0),
        "castle":       km.get("castle", -1),
        "wonder":       km.get("wonder", -1),
        "emblem":       km.get("customFlagData", "") if km.get("customFlag") else "",
        "hero_unit":    None,
        "unique_unit":  {
            "km_idx": km_uu_idx, "name": "", "description": "",
            "overrides": {}, "advanced_flags": {},
        },
        "bonuses":      _norm(civ_bons),
        "team_bonuses": _norm(team_bons),
        "castle_ut":    _ut(castle_fx),
        "imperial_ut":  _ut(imp_fx),
        "tree":         tree,
    }


# ── Startup prewarm ───────────────────────────────────────────────────────────

def _startup_prewarm() -> None:
    """Auto-detect the DAT at boot and begin stat computation in the background.

    By the time the user opens the browser and navigates to the UU step, the
    slow first-run parse is usually already done (or served from disk cache).
    """
    try:
        raw = find_game_dat()
        if not raw:
            return
        dat_path = str(raw)
        if dat_path in _UU_STATS_CACHE:
            return
        threading.Thread(
            target=lambda: _build_all_uu_stats(dat_path),
            daemon=True,
            name="uu-startup-prewarm",
        ).start()
    except Exception:
        pass


_startup_prewarm()


# ── Dev server entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser

    import werkzeug.serving

    # This is a packaged single-user desktop app, not a hosted deployment —
    # Werkzeug's red "do not use in production" banner just scares users who
    # are double-clicking an exe, not running a real server. Patch out only
    # that line; keep the "Running on http://..." line, which is genuinely
    # useful if the auto-opened browser tab gets closed.
    def _quiet_log_startup(self):
        scheme = "http" if self.ssl_context is None else "https"
        werkzeug.serving._log(
            "info", f" * Running on {scheme}://{self.host}:{self.port}. \n\n Starting up Empire Forge - just a moment.")

    werkzeug.serving.BaseWSGIServer.log_startup = _quiet_log_startup

    def _open_browser():
        webbrowser.open("http://127.0.0.1:8080")

    threading.Timer(1.0, _open_browser).start()
    threading.Thread(target=_run_update_check, daemon=True).start()
    app.run(debug=False, port=8080, threaded=True)
