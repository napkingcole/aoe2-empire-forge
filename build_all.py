#!/usr/bin/env python3
"""
build_all.py — Build a multi-civ mod from a config JSON.

Usage:
    python build_all.py wololo_warlords_config.json
    python build_all.py wololo_warlords_config.json --dat /path/to/empires2_x2_p1.dat
    python build_all.py wololo_warlords_config.json --out my_mod.zip

Config format (see wololo_warlords_config.json for example):
    {
      "mod_name": "Wololo Warlords",
      "prefix":   "wololo_warlords",     // output zip prefix (optional)
      "civs": [
        { "json": "my_civs/foo.json", "replace": "celts" },
        ...
      ]
    }
"""

import argparse
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

from dat_reader import find_game_dat, load_dat, dat_info
from civ_appender import (apply_civ,
    DLL_CREATION_OFFSET, DLL_HELP_OFFSET, DLL_TECH_TREE_OFFSET)
from build_civ import (
    AI_PER_STUB, LANGUAGES, KM_TECHTREE_ORDER,
    _find_civ_slot, _civ_techtree_index, _civ_file_name,
    _decode_flag,
    _find_civ_techtrees_folder,
    _patch_per_civ_techtree,
    _canonical_techtree_id, _resolve_uu_info,
)
from civ_appender import _KM_UU_NAMES

# ── Lookup tables from KM modStrings.js ──────────────────────────────────────
_UNIQUE_CASTLE_STRINGS = [
    "Atlatl (Skirmishers +1 attack, +1 range)",
    "Kasbah (team Castles work 25% faster)",
    "Yeomen (+1 foot archer and skirmisher range, +2 tower attack)",
    "Stirrups (Cavalry attack 33% faster)",
    "Burgundian Vineyards (Farmers slowly generate gold)",
    "Manipur Cavalry (Cavalry +4 attack vs. Ranged Soldiers)",
    "Greek Fire (Fire ships +1 range, Bombard Towers and Dromons increased blast radius)",
    "Stronghold (Castles, Kreposts and Towers fire 33% faster, heal allied infantry)",
    "Great Wall (Walls and towers +30% HP)",
    "Steppe Husbandry (Light Cavalry, Steppe Lancers and Cavalry Archers trained 100% faster)",
    "Royal Heirs (Unique Unit and Camels receive -3 damage from Mounted Units)",
    "Bearded Axe (Unique Unit +1 range)",
    "Anarchy (create Unique Unit at Barracks)",
    "Marauders (create Unique Unit at Stables)",
    "Andean Sling (Skirmishers and Slingers no minimum range, Slingers +1 attack)",
    "Grand Trunk Road (All gold income 10% faster, Market trading fee 10%)",
    "Pavise (Archer-line, Condottiero, and Unique Unit +1/+1 armor)",
    "Yasama (Towers shoot extra arrows)",
    "Tusk Swords (Melee elephant units +3 attack)",
    "Eupseong (Watch Towers, Guard Towers, and Keeps +2 range)",
    "Hill Forts (Town Centers +3 range)",
    "Corvinian Army (Unique Unit gold cost converted to food/wood cost)",
    "Thalassocracy (upgrades Docks to Harbors, which fire arrows)",
    "Tigui (Town Centers fire arrows when ungarrisoned)",
    "Hul'che Javelineers (Skirmishers throw a second projectile)",
    "Nomads (lost houses do not decrease population headroom)",
    "Kamandaran (Archer-line gold cost replaced by wood cost)",
    "Carrack (Ships +1/+1 armor)",
    "Madrasah (Monks return 50 gold when killed)",
    "First Crusade (Town Centers spawn Unique Units; units resist conversion)",
    "Orthodoxy (Monk units +3/+3P armor)",
    "Inquisition (Monks and Missionaries convert faster; Missionaries +1 range)",
    "Silk Armor (Light Cavalry, Steppe Lancers and Cavalry Archers +1/+1P armor)",
    "Ironclad (Siege units extra melee armor)",
    "Sipahi (Cavalry Archers +20 HP)",
    "Chatras (Elephant units +100 HP)",
    "Chieftains (Infantry deal bonus damage to cavalry, generate gold from kills)",
    "Szlachta Privileges (Knight-line costs -60% gold)",
    "Wagenburg Tactics (Gunpowder units move 15% faster)",
    "Deconstruction (Siege units fire 33% faster)",
    "Obsidian Arrows (Archer-line +6 attack vs. buildings)",
    "Tortoise Engineers (Rams train 100% faster)",
    "Panoply (Infantry +1/+1P armor, +1 attack)",
    "Clout Archery (Archery Ranges work 50% faster)",
    "Medical Corps (Elephant units regenerate 30 HP per minute)",
    "Paiks (Unique Unit and elephant units attack 20% faster)",
    "Kshatriyas (Military units cost -25% food)",
    "Detinets (40% of Castle/Tower stone cost replaced with wood)",
    "Zealotry (Camel units +20 hit points)",
    "Ballistas (Scorpions and Ballista Elephants fire 33% faster, Galleys +2 attack)",
    "Bimaristan (Monk units automatically heal multiple nearby units)",
    "Cilician Fleet (Demolition Ships +20% blast radius; Galley-line and Dromons +1 range)",
    "Svan Towers (Defensive buildings +2 attack; towers fire piercing arrows)",
    "Replaceable Parts (Siege units +1/+1P armor, repairing siege is free)",
    "Silk Road (Trade units cost -50%)",
    "Coiled Serpent Array (Spearman-line and Unique Unit gain HP when near each other)",
]

_UNIQUE_IMP_STRINGS = [
    "Garland Wars (Infantry +4 attack)",
    "Maghrebi Camels (Camel units regenerate)",
    "Warwolf (Trebuchet units do blast damage)",
    "Bagains (Militia-line gains +5 armor)",
    "Flemish Revolution (Upgrades all existing Villagers to Flemish Militia)",
    "Howdah (Elephant units +1/+1P armor)",
    "Logistica (Unique Unit causes trample damage)",
    "Furor Celtica (Siege Workshop units +40% HP)",
    "Rocketry (Scorpions, Rocket Carts and Lou Chuans +25% attack)",
    "Elite Mercenaries (team receives 5 free Elite Unique Units per castle)",
    "Torsion Engines (increases blast radius of Siege Workshop units)",
    "Chivalry (Stables work 40% faster)",
    "Perfusion (Barracks work 100% faster)",
    "Atheism (+100 years for Relic, Wonder victories; enemy relics -50% resources)",
    "Fabric Shields (Shock Infantry, Slingers, Unique Unit +1/+2 armor)",
    "Shatagni (Hand Cannoneers +2 range)",
    "Pirotechnia (Hand Cannoneers deal +15% pass through damage and are more accurate)",
    "Kataparuto (Trebuchet units fire and pack faster)",
    "Double Crossbow (Scorpion and Ballista units fire two projectiles)",
    "Shinkichon (Rocket Carts and Turtle Ships +1 range, fire additional rockets)",
    "Tower Shields (Spearmen and Skirmishers +2P armor)",
    "Recurve Bow (Cavalry Archers +1 range, +1 attack)",
    "Forced Levy (Militia-line gold cost replaced by food cost)",
    "Farimba (Cavalry +5 attack)",
    "El Dorado (Shock Infantry have +40 hit points)",
    "Drill (Siege Workshop units move 50% faster)",
    "Citadels (Castles and Kreposts fire Bullets, receive -25% bonus damage)",
    "Arquebus (Gunpowder units more accurate)",
    "Counterweights (Trebuchet units and Mangonel-line +15% attack)",
    "Hauberk (Knights +1/+2P armor)",
    "Druzhina (Infantry damage adjacent units)",
    "Supremacy (Villagers stronger in combat)",
    "Timurid Siegecraft (Trebuchet units +2 range, enables Flaming Camels)",
    "Crenellations (+3 range Castles garrisoned infantry fire arrows)",
    "Artillery (+2 range Bombard Towers, Bombard Cannons, Cannon Galleons)",
    "Paper Money (Lumberjacks slowly generate gold in addition to wood)",
    "Bogsveigar (Foot Archers and Unique ships +1 attack)",
    "Lechitic Legacy (Light Cavalry deals trample damage)",
    "Hussite Reforms (Monks and Monastery upgrades gold replaced by food)",
    "Brigandine Armor (Camels and Cavalry Archers +2/+1P armor)",
    "Field Repairmen (Rams regain HP)",
    "Golden Age (All buildings work 10% faster)",
    "Villager's Revenge (Dead villagers become Halberdiers)",
    "Gate Crashing (Ram gold cost replaced by wood cost)",
    "Wootz Steel (Infantry and cavalry attacks ignore armor)",
    "Mahayana (Villagers and monk units take 10% less population space)",
    "Frontier Guards (Camel units and Elephant Archers +4 melee armor)",
    "Comitatenses (Militia-line, Knight-line, and Unique Unit train 50% faster with charge attack)",
    "Fereters (Infantry except Spearmen +30 HP, Warrior Priests +100% heal speed)",
    "Aznauri Cavalry (Cavalry units take 15% less population space)",
    "Pila (Skirmisher attacks strip armour)",
    "Enlistment (Infantry take 15% less population space)",
    "Marshalled Hunters (Foot archers and skirmishers take 15% less population space)",
    "Shigeto Yumi (Unique Unit, Mounted Archers, and Towers attack 15% faster)",
    "Bolt Magazine (Archer-line, Lou Chuans, and War Chariots fire additional projectiles)",
    "Sitting Tiger (Trebuchet units fire additional projectiles)",
    "Ming Guang Armor (Mounted units +4 melee armor)",
    "Thunderclap Bombs (Rocket Carts, Grenadiers detonate when defeated)",
    "Ordo Cavalry (Cavalry regenerates HP in combat)",
]

_BONUS_NAMES: dict[str, str] = json.loads(
    (Path(__file__).parent / "bonus_names.json").read_text(encoding="utf-8"))


def _load_vanilla_civ_descriptions() -> dict[int, str]:
    """Extract vanilla civ descriptions (sids 120150-120194) from the bundled
    aoe2techtree locale JSON, converting <br> → literal \\n for the modded-strings
    format that AoE2 DE expects.

    Why this exists: the engine silently ignores 120150+i overrides unless ALL
    45 vanilla civ description IDs are present in the modded-strings file (the
    KM/NKC pattern). Writing only the modified slots was not enough; we have to
    re-emit vanilla content for the unchanged slots too.
    """
    src = Path(__file__).parent / "vanilla" / "aoe2techtree_strings" / "en_strings.json"
    if not src.exists():
        src = Path(__file__).parent / "AoE2-Civbuilder-main" / "public" / \
              "aoe2techtree" / "data" / "locales" / "en" / "strings.json"
    if not src.exists():
        return {}
    raw = json.loads(src.read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    for sid in range(120150, 120195):
        text = raw.get(str(sid))
        if text is None:
            continue
        # Normalise to AoE2 DE modded-strings markup:
        #   <br>      → \n     (DE uses \n for line breaks in this file)
        #   </b>      → <b>    (DE uses <b>...<b> toggle, not HTML-style close)
        #   real LF   → strip  (the source JSON has both <br> and a following LF;
        #                       we only want the literal \n that replaced <br>)
        #   "         → '      (avoid breaking the surrounding "..." quotes)
        # Leaving </b> in place crashes the picker once the engine actually
        # reads the description (e.g., once entries become contiguous).
        text = text.replace("<br>", "\\n")
        text = text.replace("</b>", "<b>")
        text = text.replace("\n", "")
        text = text.replace('"', "'")
        out[sid] = text
    return out


_VANILLA_CIV_DESCRIPTIONS: dict[int, str] = _load_vanilla_civ_descriptions()


def _ut_name(bonus_id: int | None, castle: bool) -> str:
    """Resolve a UT name from its KM bonus ID."""
    if bonus_id is None:
        return "Castle Unique Technology" if castle else "Imperial Unique Technology"
    table = _UNIQUE_CASTLE_STRINGS if castle else _UNIQUE_IMP_STRINGS
    if 0 <= bonus_id < len(table):
        return table[bonus_id]
    return "Castle Unique Technology" if castle else "Imperial Unique Technology"


def _ut_bonus_id(civ_def: dict, group: int) -> int | None:
    """Extract bonus ID from bonuses[group][0][0], or None if absent."""
    bonuses = civ_def.get("bonuses", [])
    if len(bonuses) <= group:
        return None
    grp = bonuses[group]
    if not grp or not isinstance(grp[0], list):
        return None
    return int(grp[0][0])


def _build_combined_data_zip(dat,
                              button_pngs: dict[str, bytes],
                              per_civ_tt: dict[str, bytes],
                              mod_name: str = "Custom Civs",
                              civs_json_bytes: bytes | None = None) -> bytes:
    """Serialize the modified DAT + all supporting data-side assets.

    Ships the game's default 60-entry civilizations.json so the civ picker
    honours modded-strings overrides for descriptions and UU display. After
    the June 6 2026 patch, AoE2 DE validates civilizations.json entry count
    against DAT civ count and silently ignores modded-strings 120150+i for
    the picker UI unless this file is present in the mod.
    """
    with tempfile.NamedTemporaryFile(suffix=".dat", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        dat.save(tmp_path)
        dat_bytes = Path(tmp_path).read_bytes()
    finally:
        os.unlink(tmp_path)

    info_json = json.dumps(
        {"Title": mod_name, "CacheStatus": 0, "Description": "", "Author": ""},
        separators=(",", ":"),
    ).encode("utf-8")

    futura_path = Path(__file__).parent / "futuravailableunits.json"
    futura_bytes = (futura_path.read_bytes() if futura_path.exists() else None)

    # NKC's stored zips have a top-level wrapper folder, but those wrappers
    # appear to be NKC's local-backup convention — installing our build with
    # wrappers inside the zip triggers "Failed to load dataset / .gpv" errors
    # and the mod browser flags the mod with an exclamation mark. Files at
    # the zip root is what AoE2 DE actually expects.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("info.json", info_json)
        zf.writestr("resources/_common/dat/empires2_x2_p1.dat", dat_bytes)
        if civs_json_bytes is not None:
            zf.writestr("resources/_common/dat/civilizations.json", civs_json_bytes)
        if futura_bytes is not None:
            zf.writestr("resources/_common/dat/futuravailableunits.json",
                        futura_bytes)
        for name, data in per_civ_tt.items():
            zf.writestr(f"resources/_common/dat/CivTechTrees/{name}", data)
        for fname, png in button_pngs.items():
            zf.writestr(
                f"resources/_common/wpfg/resources/civ_techtree/{fname}", png)
    return buf.getvalue()


def _build_combined_ui_zip(ai_stubs: dict[str, bytes],
                            button_pngs: dict[str, bytes],
                            combined_strings: dict[str, str],
                            mod_name: str = "Custom Civs") -> bytes:
    """Package all UI assets for every civ into one ui zip."""
    info_json = json.dumps(
        {"Title": f"{mod_name} (UI)", "CacheStatus": 0, "Description": "", "Author": ""},
        separators=(",", ":"),
    ).encode("utf-8")

    # Reverted wrapper folders (see data-zip comment).
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("info.json", info_json)
        for path, data in ai_stubs.items():
            zf.writestr(path, data)
        aiconfig_path = Path(__file__).parent / "aiconfig.json"
        if aiconfig_path.exists():
            zf.writestr("resources/_common/ai/aiconfig.json",
                        aiconfig_path.read_bytes())
        ai_stubs_folder = Path(__file__).parent / "ai_stubs"
        if ai_stubs_folder.exists():
            written_paths = set(ai_stubs.keys())
            for stub_file in sorted(ai_stubs_folder.iterdir()):
                if stub_file.suffix not in (".ai", ".per"):
                    continue
                dest = f"resources/_common/ai/{stub_file.name}"
                if dest in written_paths:
                    continue
                zf.writestr(dest, stub_file.read_bytes())
        for fname, png in button_pngs.items():
            zf.writestr(
                f"resources/_common/wpfg/resources/civ_techtree/{fname}", png)
            zf.writestr(
                f"widgetui/textures/ingame/icons/civ_techtree_buttons/{fname}",
                png)
            if "_hover" not in fname and "_pressed" not in fname:
                civ_fn = fname.removeprefix("menu_techtree_")
                zf.writestr(f"widgetui/textures/menu/civs/{civ_fn}", png)
        uniticons_folder = Path(__file__).parent / "uniticons"
        if uniticons_folder.exists():
            for icon_file in sorted(uniticons_folder.glob("*.png")):
                if not re.match(r"^\d+_\d+\.png$", icon_file.name):
                    continue
                zf.writestr(
                    f"resources/_common/wpfg/resources/uniticons/{icon_file.name}",
                    icon_file.read_bytes(),
                )
        for lang, content in combined_strings.items():
            zf.writestr(
                f"resources/{lang}/strings/key-value/"
                f"key-value-modded-strings-utf8.txt",
                content.encode("utf-8"),
            )
    return buf.getvalue()



def build_mod(config_path: Path, dat_path: Path, out_path: Path) -> None:
    config    = json.loads(config_path.read_text(encoding="utf-8"))
    mod_name  = config.get("mod_name", "Custom Mod")
    civ_defs  = config.get("civs", [])

    print(f"Mod: {mod_name!r}  ({len(civ_defs)} civs)")
    print(f"Loading DAT: {dat_path}")
    dat  = load_dat(dat_path)
    info = dat_info(dat)
    print(f"  {info['num_civs']} civs, {info['num_units_per_civ']} units/civ, "
          f"{info['num_techs']} techs, {info['num_effects']} effects")

    ct_folder = _find_civ_techtrees_folder(dat_path)

    # Locate base civilizations.json next to the DAT (or fall back to project root).
    from build_civ import _find_adjacent_json
    base_civs_json = _find_adjacent_json(dat_path, "civilizations.json")
    if base_civs_json is None or not base_civs_json.exists():
        base_civs_json = Path(__file__).parent / "civilizations.json"

    # Accumulated UI assets across all civs.
    ai_stubs:   dict[str, bytes] = {}
    button_pngs: dict[str, bytes] = {}
    per_civ_tt: dict[str, bytes] = {}
    string_lines: dict[str, list[str]] = {lang: [] for lang in LANGUAGES}
    # Maps DAT slot → (name_string_id, uu_icon_id) for civilizations.json patching.
    civs_overrides: dict[int, dict] = {}

    # Fixed, non-per-civ strings for bonus 308/309/310's shared unit slots.
    # Written once, unconditionally — harmless if this build has no civ
    # using those bonuses.
    from civ_appender import FIXED_UNIT_NAME_STRINGS
    for lang in LANGUAGES:
        for sid, text in FIXED_UNIT_NAME_STRINGS:
            string_lines[lang].append(f'{sid} "{text}"')

    # Pre-compute which techtree positions will be replaced by custom civs so
    # we can skip writing vanilla names for those positions.  AoE2 DE key-value
    # string files are first-definition-wins, so writing "Britons" first then
    # "Horsey Boys" second would leave the vanilla name in place.
    replaced_tt_positions: set[int] = set()
    for entry in civ_defs:
        _jp = Path(entry["json"])
        if not _jp.exists():
            continue
        _slot = _find_civ_slot(dat, entry["replace"])
        if _slot is None:
            continue
        _tti = _civ_techtree_index(dat.civs[_slot].name)
        if _tti is not None:
            replaced_tt_positions.add(_tti)

    # NOTE: Custom civ strings are written FIRST (in the loop below), and
    # vanilla civ name fallbacks are written LAST (after the loop). This
    # mirrors NapKingCole's Unhinged Empires structure, which is known to
    # render civ-picker descriptions correctly in-game. Our earlier output
    # (vanilla-first, custom-last) did not — even with no duplicate IDs.

    for entry in civ_defs:
        json_path    = Path(entry["json"])
        replace_name = entry["replace"]

        if not json_path.exists():
            print(f"  ERROR: {json_path} not found — skipping")
            continue

        civ_def = json.loads(json_path.read_text(encoding="utf-8"))
        alias   = civ_def.get("alias", json_path.stem)

        slot = _find_civ_slot(dat, replace_name)
        if slot is None:
            print(f"  ERROR: No civ named {replace_name!r} in DAT — skipping {alias!r}")
            continue

        ui_civ_name = dat.civs[slot].name
        tt_idx      = _civ_techtree_index(ui_civ_name)
        name_sid    = 10271 + tt_idx if tt_idx is not None else 10271

        print(f"\n  [{slot}] {replace_name!r} → {alias!r}  (string ID {name_sid})")

        # Apply civ to DAT (modifies dat in place).
        civ_result = apply_civ(dat, civ_def, target_slot=slot)

        # Resolve UT names from bonus IDs.
        castle_ut_bid = _ut_bonus_id(civ_def, 2)
        imp_ut_bid    = _ut_bonus_id(civ_def, 3)
        castle_ut_name = _ut_name(castle_ut_bid, castle=True)
        imp_ut_name    = _ut_name(imp_ut_bid, castle=False)
        # Enrich civ_result with UT names so _patch_per_civ_techtree can update node labels.
        civ_result["castle_ut_name"] = castle_ut_name
        civ_result["imp_ut_name"]    = imp_ut_name

        # UT string IDs: real existing vanilla ids from
        # civ_appender.CAMPAIGN_STRING_POOL (see that module's docstring —
        # brand-new high-range ids never worked in-game). The DAT tech's
        # language_dll_name now points here, so the in-game Castle UT button
        # label resolves to our custom name instead of falling back to the
        # vanilla tech text.
        castle_ut_sid = civ_result["castle_ut_sid"]
        imp_ut_sid    = civ_result["imp_ut_sid"]
        castle_ut_desc_sid = civ_result["castle_ut_desc_sid"]
        imp_ut_desc_sid    = civ_result["imp_ut_desc_sid"]

        # Resolve the custom UU info for description + string writes + techtree.
        uu_info = _resolve_uu_info(civ_def, dat, slot, civ_result)
        civs_overrides[slot] = {
            "name_sid": name_sid,
            "icon_id": uu_info["icon_id"] if uu_info else None,
            # civilizations.json carries its OWN separate UU metadata block
            # (unique_unit_id/elite_unique_unit_id/unique_unit_string_ids/
            # unique_unit_upgrade_id) — confirmed via a live build that this
            # is NEVER touched otherwise, so an overwritten civ keeps
            # pointing at the ORIGINAL vanilla civ's UU here (e.g. Britons
            # stayed on Longbowman/unit 8/string 5107 even after a custom
            # Gendarme UU was correctly wired into the DAT itself). Whatever
            # in-game UI surface reads this block (separate from the per-unit
            # language_dll_help tooltip, which IS correctly written) would
            # keep showing stale/unrelated content. KM's own civbuilder
            # (createCivilizationsJson.js) sidesteps this by never setting
            # these fields at all when generating a FRESH file; since we
            # instead PRESERVE the vanilla civ's original block by carrying
            # the whole entry forward, we must explicitly overwrite it here.
            "uu_unit_id":    uu_info["unit_id"]  if uu_info else None,
            "uu_elite_id":   uu_info["elite_id"] if uu_info else None,
            "uu_upgrade_tech_id": civ_result.get("km_uu_elite_tech_id"),
            "uu_name_sid":   uu_info["dll_name"] if uu_info else None,
            "uu_desc_sid":   uu_info["dll_help"] if uu_info else None,
        }
        # Display name: prefer the resolved UU (vanilla or KM-custom, both
        # handled by _resolve_uu_info above); fall back to the KM UU name
        # table only for the two still-unimplemented custom indices (Monkey
        # Boy 47, Warrior Monk 75).
        _uu_refs = civ_def.get("bonuses", [None]*2)
        _km_uu_idx = (_uu_refs[1][0]
                      if len(_uu_refs) > 1 and isinstance(_uu_refs[1], list) and _uu_refs[1]
                      else None)
        uu_display = (uu_info["name"] if uu_info
                      else _KM_UU_NAMES.get(_km_uu_idx, "Unique Unit"))
        # Also look up the elite unit's dll_name for string writes.
        uu_elite_dll: int | None = None
        uu_elite_name: str | None = None
        if uu_info:
            elite_uid = uu_info.get("elite_id")
            if elite_uid is not None and elite_uid != uu_info["unit_id"]:
                try:
                    eu2 = dat.civs[slot].units[elite_uid]
                    uu_elite_dll  = eu2.language_dll_name
                    uu_elite_name = f"Elite {uu_display}"
                except (IndexError, AttributeError):
                    pass

        # Build civ selection screen description.
        description = civ_def.get("description", "")
        bonuses_raw  = civ_def.get("bonuses", [])
        civ_bonuses  = bonuses_raw[0] if bonuses_raw and isinstance(bonuses_raw[0], list) else []
        team_bonus_entries = (bonuses_raw[4]
                              if len(bonuses_raw) > 4 and isinstance(bonuses_raw[4], list)
                              else [])

        # Strict vanilla format (verified against game's key-value-strings-utf8.txt
        # 2026-06-12): spaces appear ONLY after `<b>Section:<b>` tags before \n.
        # No trailing space before any other \n. No trailing \n before closing ".
        # Example: `civilization\n\n• Bonus 1\n• Bonus 2\n\n<b>Unique Unit:<b> \nUU
        # name\n\n<b>Unique Techs:<b> \n• UT 1\n• UT 2\n\n<b>Team Bonus:<b> \nTB"`.
        desc_parts = [f'{description} civilization' if description else f'{alias} civilization']
        desc_parts.append("\\n\\n")
        bullet_lines = []
        for entry in civ_bonuses:
            if not isinstance(entry, list):
                continue
            bid  = str(entry[0])
            mult = entry[1] if len(entry) > 1 else 1
            txt  = _BONUS_NAMES.get(bid, "")
            if not txt:
                continue
            suffix = f" [x{mult}]" if mult > 1 else ""
            bullet_lines.append(f"• {txt}{suffix}")
        desc_parts.append("\\n".join(bullet_lines))
        # Section break + UU
        desc_parts.append(f"\\n\\n<b>Unique Unit:<b> \\n{uu_display}")
        # Section break + UTs
        desc_parts.append(
            "\\n\\n<b>Unique Techs:<b> \\n"
            f"• {castle_ut_name}\\n• {imp_ut_name}"
        )
        if team_bonus_entries:
            tb_lines = []
            for entry in team_bonus_entries:
                if not isinstance(entry, list):
                    continue
                bid = str(entry[0])
                txt = _BONUS_NAMES.get(bid, "")
                if txt:
                    tb_lines.append(txt)
            if tb_lines:
                # Vanilla format: no bullets in Team Bonus; multiple bonuses
                # are joined by "; " into one line of plain text.
                desc_parts.append("\\n\\n<b>Team Bonus:<b> \\n")
                desc_parts.append("; ".join(tb_lines))
        full_desc = "".join(desc_parts)
        # Strip trailing escape sequences and whitespace before the closing
        # quote. AoE2 DE's modded-strings parser rejects entries ending in a
        # dangling \n (literal backslash-n), silently falling back to the base
        # game string — confirmed via Discord community report 2026-06-12.
        # NKC's working strings end cleanly with the last bullet's content;
        # ours used to end with ` \n"` which broke the override for the
        # picker description specifically.
        while full_desc.endswith("\\n") or full_desc.endswith(" "):
            if full_desc.endswith("\\n"):
                full_desc = full_desc[:-2]
            else:
                full_desc = full_desc.rstrip()

        # Strings: one line per civ per language (all langs get same English text).
        # Description string ID follows KM's offset: 120150 - 10271 = 109879 above name_sid.
        for lang in LANGUAGES:
            string_lines[lang].append(f'{name_sid} "{alias}"')
            string_lines[lang].append(
                f'{name_sid + 80000} "Click to play as {alias}."')
            string_lines[lang].append(
                f'{name_sid + 109879} "{full_desc}"')
            # name_sid/desc_sid are two SEPARATE real existing-id pool slots
            # (civ_appender.CAMPAIGN_STRING_POOL) — NOT arithmetic offsets of
            # one base id, which never worked in-game. name_sid covers BOTH
            # the button label (language_dll_name) AND the hover
            # (language_dll_description) — both point at the same id on the
            # DAT tech, so the hover shows the same short text as the
            # button rather than a distinct "Research X — description"
            # line; that's an accepted simplification (matches the
            # convention already used for km_custom_uu.py and bonus
            # 308/309/310). desc_sid covers both the full tooltip and the
            # F1 tech-tree text. The KM catalog packs "Name (description)"
            # into one string; split so the button label matches vanilla
            # style (just the name) and the tooltip shows the description
            # after the cost token.
            for name_sid_ut, desc_sid_ut, full in (
                (castle_ut_sid, castle_ut_desc_sid, castle_ut_name),
                (imp_ut_sid, imp_ut_desc_sid, imp_ut_name),
            ):
                short, _, paren = full.partition(" (")
                desc = paren.rstrip(")") if paren else ""
                string_lines[lang].append(f'{name_sid_ut} "{short}"')
                # The tech's language_dll_description/tech_tree fields point
                # at name_sid_ut+1000/+150000 (vanilla offset convention —
                # see civ_appender._creation_sid/_tech_tree_sid). Without a
                # written override at THOSE exact ids too, the engine falls
                # back to whatever vanilla content already lives there
                # instead of leaving it blank — confirmed live (a Castle UT
                # button showed an unrelated campaign dialogue line at
                # name+1000 until this was added).
                string_lines[lang].append(
                    f'{name_sid_ut + DLL_CREATION_OFFSET} "Research {short}"')
                # Full <cost> tooltip — vanilla pattern: name+cost on first line,
                # description on second. Avoids duplicating the name as we did before.
                help_body = f"Research <b>{short}<b> (<cost>)"
                if desc:
                    help_body += f"\\n{desc}"
                string_lines[lang].append(f'{desc_sid_ut} "{help_body}"')
                string_lines[lang].append(
                    f'{name_sid_ut + DLL_TECH_TREE_OFFSET} "{short}"')
            # Bonus-specific research buttons (e.g. Imperial Scorpion, Royal
            # Battle Elephant, Royal Lancer — bonuses 308/309/310). civ_appender
            # surfaces these via bonus_results["extra_tech_strings"] since they
            # aren't part of the castle_ut/imp_ut slots.
            for ext in civ_result["bonus_results"].get("extra_tech_strings", []):
                sid, name = ext["sid"], ext["name"]
                string_lines[lang].append(f'{sid} "{name}"')
                string_lines[lang].append(f'{sid + DLL_CREATION_OFFSET} "Research {name}"')
                string_lines[lang].append(
                    f'{sid + DLL_HELP_OFFSET} "Research <b>{name}<b> (<cost>)"')
                string_lines[lang].append(f'{sid + 150000} "{name}"')
            # KM-custom UU units' OWN name/help strings (the actual in-game
            # selection-panel/training-queue text, distinct from the
            # dll_name+10000/+100000 tech-tree-viewer block below). Without
            # this, a custom UU keeps showing its cloned base unit's
            # original name (e.g. a campaign hero's name for Gendarme).
            for ext in civ_result["bonus_results"].get("extra_unit_strings", []):
                # sid+DLL_CREATION_OFFSET (name+1000) is what the engine
                # actually reads for the Castle "create unit" button/elite
                # tech description (km_custom_uu.py and the bonus 308/309/310
                # upgrade tech both set their creation/description field to
                # exactly this id) — must be written explicitly, same
                # reasoning as the Castle/Imperial UT block above.
                # desc_sid (=sid+DLL_HELP_OFFSET, computed by civ_appender)
                # is the full tooltip.
                sid, name = ext["sid"], ext["name"]
                string_lines[lang].append(f'{sid} "{name}"')
                string_lines[lang].append(
                    f'{sid + DLL_CREATION_OFFSET} "Create {name}"')
                help_text = ext.get("help_text", name)
                desc_sid = ext.get("desc_sid", sid)
                string_lines[lang].append(f'{desc_sid} "{help_text}"')
                # The Castle "create unit" button's EXTENDED hover tooltip
                # for a UNIT (as opposed to a tech's research-button
                # tooltip) is read from name+21000, NOT name+100000 — a
                # separate string slot the engine derives from
                # language_dll_creation+20000 with no corresponding DAT
                # field of its own. Confirmed live: the user saw exactly
                # this text in-game for Elite Budget Knight while the
                # name+100000 entry never showed. See
                # civ_appender._extended_tooltip_sid's docstring.
                if "ext_sid" in ext:
                    string_lines[lang].append(
                        f'{ext["ext_sid"]} "{ext.get("ext_text", name)}"')
            # UU name strings for civ selection tech tree display. For
            # KM-custom UUs, uu_dll == the extra_unit_strings sid above (both
            # ultimately read the unit's own language_dll_name) — the
            # `+DLL_HELP_OFFSET` line here is then a harmless duplicate
            # (same id, weaker bare-name text) that the now-fixed insertion-
            # order tie-break correctly lets the richer one win. Left as-is
            # rather than cross-wiring the two independently-evolved paths.
            if uu_info:
                uu_dll = uu_info["dll_name"]
                string_lines[lang].append(f'{uu_dll + 10000} "{uu_display}"')
                string_lines[lang].append(f'{uu_dll + DLL_HELP_OFFSET} "{uu_display}"')
            if uu_elite_dll and uu_elite_name:
                string_lines[lang].append(f'{uu_elite_dll + 10000} "{uu_elite_name}"')
                string_lines[lang].append(f'{uu_elite_dll + DLL_HELP_OFFSET} "{uu_elite_name}"')

        # Button PNGs (104×104 civ picker emblem).
        # Use the canonical civTechTrees name (e.g. "britons"), not the DAT
        # internal name (e.g. "british") — the game loads icons by canonical name.
        flag_png = _decode_flag(civ_def)
        if flag_png:
            fn = _canonical_techtree_id(ui_civ_name).lower()
            for variant in ("", "_hover", "_pressed"):
                button_pngs[f"menu_techtree_{fn}{variant}.png"] = flag_png

        # AI stubs.
        ai_name = f"{alias} AI (pre-alpha)"
        ai_stubs[f"resources/_common/ai/{ai_name}.ai"]  = b""
        ai_stubs[f"resources/_common/ai/{ai_name}.per"] = AI_PER_STUB

        # Per-civ CivTechTrees JSON.
        if ct_folder:
            vanilla_tt_name = _canonical_techtree_id(ui_civ_name)
            per_civ_path = ct_folder / f"{vanilla_tt_name}.json"
            if per_civ_path.exists():
                patched = _patch_per_civ_techtree(per_civ_path, civ_def, dat, slot,
                                                    civ_result=civ_result)
                if patched is not None:
                    per_civ_tt[f"{vanilla_tt_name}.json"] = patched

    # Fill in vanilla (unpatched) per-civ CivTechTrees JSONs for every civ not
    # already overridden.
    if ct_folder:
        for json_file in sorted(ct_folder.glob("*.json")):
            if json_file.name not in per_civ_tt:
                per_civ_tt[json_file.name] = json_file.read_bytes()

    # Vanilla civ-name fallbacks: AFTER all custom civ entries, fill in the
    # remaining slots so the picker still shows correct names for unmodified
    # civs. First-definition-wins keeps custom entries above untouched.
    for i, vanilla_name in enumerate(KM_TECHTREE_ORDER):
        if i in replaced_tt_positions:
            continue
        sid = 10271 + i
        for lang in LANGUAGES:
            string_lines[lang].append(f'{sid} "{vanilla_name}"')
            string_lines[lang].append(f'{sid + 80000} "Click to play as {vanilla_name}."')

    # Vanilla civ-description fallbacks: re-emit 120150+i for positions 0-44
    # so the full block is present (KM/NKC ship this — see project memory).
    # (Previously suspected of crashing the lobby; turned out to be a corrupted
    # Steam game-file install masquerading as a mod bug. See feedback memory.)
    for i in range(min(len(KM_TECHTREE_ORDER), 45)):
        if i in replaced_tt_positions:
            continue
        sid = 120150 + i
        text = _VANILLA_CIV_DESCRIPTIONS.get(sid)
        if text is None:
            continue
        for lang in LANGUAGES:
            string_lines[lang].append(f'{sid} "{text}"')

    # Combine string lines per language, sorted by numeric ID into contiguous
    # blocks (matches NKC's known-good mod's structure). Insertion order also
    # works in-game but leaves the picker description ignored by the engine;
    # NKC's contiguous-block layout is the only known pattern where 120150+i
    # overrides actually render in the picker UI.
    #
    # Tie-break MUST be insertion order, not the line's own text — sorting
    # ties alphabetically silently breaks "first-definition-wins" whenever
    # two DIFFERENT call sites legitimately write different text to the SAME
    # id (e.g. a bare unit name from one block + a richer formatted tooltip
    # from another — alphabetical comparison picked the bare text every
    # time, purely because its first letter sorted earlier, discarding the
    # richer one regardless of which was actually written first). Confirmed
    # via a live build: Gendarme's help text was silently shadowed this way.
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

    # Generate civilizations.json with updated UU icon paths for replaced civs.
    civs_json_bytes: bytes | None = None
    if base_civs_json and base_civs_json.exists() and civs_overrides:
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
                # Retarget the civ-level UU metadata block (see civs_overrides
                # assignment above for why this is necessary) so any in-game
                # UI surface keyed off civilizations.json's own UU fields
                # — not just the per-unit DAT strings — shows the custom UU.
                uu_unit_id = ov.get("uu_unit_id")
                if uu_unit_id is not None:
                    entry["unique_unit_id"] = uu_unit_id
                    if ov.get("uu_elite_id") is not None:
                        entry["elite_unique_unit_id"] = ov["uu_elite_id"]
                    if ov.get("uu_upgrade_tech_id") is not None:
                        entry["unique_unit_upgrade_id"] = ov["uu_upgrade_tech_id"]
                    if ov.get("uu_name_sid") is not None:
                        name_sid_uu = ov["uu_name_sid"]
                        # Prefer the EXPLICIT desc sid (always a real id —
                        # for KM-custom UUs it's a CAMPAIGN_STRING_POOL id,
                        # nothing to do with name_sid+offset). Fall back to
                        # the +DLL_HELP_OFFSET computation only when desc_sid
                        # is unavailable — true for vanilla UUs, where it
                        # coincidentally still lands on a real vanilla id
                        # (vanilla's own language_dll_help convention also
                        # happens to be name+100000).
                        desc_sid_uu = ov.get("uu_desc_sid") or (name_sid_uu + DLL_HELP_OFFSET)
                        entry["unique_unit_string_ids"] = [
                            {"name": name_sid_uu, "description": desc_sid_uu}
                        ]
            civs_json_bytes = json.dumps(
                {"civilization_list": civ_list}, separators=(",", ":")
            ).encode("utf-8")
        except Exception as e:
            print(f"  WARNING: Could not generate civilizations.json: {e}")

    print(f"\nBuilding combined mod zip → {out_path}")
    prefix = config.get("prefix", mod_name.lower().replace(" ", "_"))
    data_zip = _build_combined_data_zip(dat, button_pngs, per_civ_tt, mod_name=mod_name,
                                         civs_json_bytes=civs_json_bytes)
    ui_zip   = _build_combined_ui_zip(ai_stubs, button_pngs, combined_strings, mod_name=mod_name)

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as outer:
        outer.writestr(f"{prefix}-data.zip", data_zip)
        outer.writestr(f"{prefix}-ui.zip",   ui_zip)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"  → {out_path}  ({size_mb:.1f} MB)")
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a multi-civ AoE2 DE mod from a config JSON."
    )
    parser.add_argument("config", help="Path to mod config JSON")
    parser.add_argument("--dat",  help="Path to empires2_x2_p1.dat (auto-detected if omitted)")
    parser.add_argument("--out",  help="Output zip filename")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}")
        sys.exit(1)

    dat_path = Path(args.dat) if args.dat else find_game_dat()
    if not dat_path:
        print("ERROR: Could not auto-detect game DAT. Use --dat /path/to/dat")
        sys.exit(1)

    config   = json.loads(config_path.read_text(encoding="utf-8"))
    prefix   = config.get("prefix", config.get("mod_name", "mod").lower().replace(" ", "_"))
    out_path = Path(args.out) if args.out else Path(f"{prefix}.zip")

    build_mod(config_path, dat_path, out_path)


if __name__ == "__main__":
    main()
