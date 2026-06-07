# AoE2 Civ Builder — Project Plan

## Vision

A local desktop app that lets anyone in the AoE2 community design a custom civilization and generate a working mod zip — no server, no dependencies, no prior modding knowledge required.

Users double-click the app, configure their civ in a browser UI, and download a ready-to-install mod.

---

## Architecture

```
[User's game DAT]  +  [Civ JSON]
         ↓
   Python backend (local server, localhost only)
         ↓
   Modified DAT + language files + AI config
         ↓
   Mod zip (data + ui inner zips, ageofempires.com format)
```

**Distribution:** PyInstaller bundles Python + genieutils + Flask into a single executable (.exe / .app). No Python installation required. App launches a local web server, opens the browser automatically.

**No hosted server.** Can never go down. Works offline. Old copies keep working indefinitely.

---

## Key Decisions

| Decision | Choice | Reason |
|---|---|---|
| Build input | User's own game DAT | DLC-safe; no copyright issues bundling files |
| Civ slots | 45 total (vanilla + custom) | Hard limit prevents known crash; matches KM behavior |
| Bonus system | Preset catalog + multiplier scaling | Accessible to casual players; covers 90% of cases |
| Tech tree UI | Siege Engineers aoe2techtree component | Community already knows it; same ID-whitelist format |
| Mod scope | Standalone only (no layering on other mods) | Massive simplification; additive is a v2 problem |
| JSON format | KM-compatible import; richer internal format | Users can port existing KM civs |
| Unique units | Pick from existing unit pool, rename + modify stats | Practical for v1; full custom graphics is out of scope |
| Languages | English strings; stub other 14 | Reasonable v1 scope |
| Slot allocation | Always append at `len(existing_units)` | Forward-compatible with future DLC content additions |

---

## What Gets Modified

For each custom civ, the tool modifies:

- **DAT file** (`empires2_x2_p1.dat`)
  - Appends a new civ slot (copied from a vanilla template)
  - Appends unit slots: base UU + elite UU
  - Appends tech slots: castle UT, imperial UT, N civ bonus auto-fire techs
  - Appends effect slots: one per tech
  - Wires tech tree connections (buildings, units, techs)
  - Sets architecture set, wonder graphic, castle graphic
  - Sets language DLL IDs for all new strings

- **Language files** (one per supported language)
  - Civ name
  - UU name + description
  - Castle UT name + description
  - Imperial UT name + description
  - Civ bonus descriptions

- **AI config** (`aiconfig.json`)
  - Stub entry so the game doesn't complain

---

## JSON Civ Schema (v1 draft)

```json
{
  "alias": "My Civ",
  "description": "Short civ blurb shown in-game",
  "architecture": 10,
  "language": 29,
  "wonder": 45,
  "castle": 48,
  "flag_palette": [3, 4, 5, 6, 7, 3, 3, 3],
  "customFlagData": "data:image/png;base64,...",

  "tree": {
    "units":     [13, 17, 21, ...],
    "buildings": [12, 45, 82, ...],
    "techs":     [22, 101, 102, ...]
  },

  "bonuses": [
    { "id": 100, "multiplier": 2 },
    { "id": 291, "multiplier": 1 }
  ],
  "team_bonus": { "id": 8, "multiplier": 1 },

  "castle_ut": {
    "name": "My Castle Tech",
    "description": "Does something cool",
    "cost": { "food": 300, "gold": 300 },
    "research_time": 60,
    "effects": [{ "id": 33, "multiplier": 1 }]
  },
  "imperial_ut": {
    "name": "My Imperial Tech",
    "description": "Does something cooler",
    "cost": { "food": 400, "gold": 400 },
    "research_time": 90,
    "effects": [{ "id": 33, "multiplier": 1 }]
  },

  "unique_unit": {
    "name": "My Unit",
    "description": "A fearsome warrior",
    "base_unit_id": 291,
    "stats": {
      "hp": 120,
      "attack": 12,
      "melee_armor": 2,
      "pierce_armor": 3,
      "speed": 1.0,
      "range": 0,
      "cost": { "food": 80, "gold": 40 },
      "train_time": 16
    }
  }
}
```

**KM import compatibility:** The KM format maps cleanly. `tree` arrays are identical. `bonuses` is `[[id, multiplier], ...]` in KM vs `[{"id": id, "multiplier": m}]` here — trivially converted. KM doesn't capture UU stats or UT descriptions; these get filled with sensible defaults on import.

---

## Bonus Catalog

Each entry maps a preset bonus ID to one or more EffectCommands. The multiplier scales the `d` value of each command.

Sourced from KM's catalog + our own build.py patterns. To be defined in `bonus_catalog.py`.

Example:
```python
{
  100: {
    "label": "Archers +15% movement speed",
    "effects": [
      { "type": EC_MULTIPLY, "a": -1, "b": CLASS_FOOT_ARCHER, "c": ATTR_SPEED, "d": 1.15 }
    ]
  }
}
```

Multiplier applies to the delta from 1.0: `1.0 + (d - 1.0) * multiplier` for multiplicative bonuses, `d * multiplier` for additive ones.

---

## Development Phases

### Phase 1 — Backend core (start here)
- [ ] Project setup: Python venv, Flask, genieutils, requirements.txt
- [ ] `dat_reader.py`: load user's vanilla DAT, inspect civ/unit counts
- [ ] `civ_appender.py`: given a civ JSON, append a new civ to the DAT
- [ ] `bonus_catalog.py`: define preset bonuses as EffectCommand templates
- [ ] `string_writer.py`: generate language key-value files
- [ ] `mod_packager.py`: zip output into ageofempires.com format
- [ ] CLI test: `python build_civ.py my_civ.json --dat /path/to/dat` → outputs mod zip

### Phase 2 — Local server
- [ ] Flask server with REST endpoints:
  - `GET /api/civs` — list vanilla civs + their slots
  - `POST /api/build` — accept civ JSON, return mod zip
  - `GET /api/dat-info` — unit/tech counts from loaded DAT
- [ ] Auto-detect Steam game DAT path (Windows + Mac)
- [ ] Browser auto-launch on server start

### Phase 3 — UI (owner's domain)
- [ ] Integrate Siege Engineers aoe2techtree component for tech selection
- [ ] Bonus picker with +/- multiplier controls
- [ ] UU stat editor
- [ ] UT name/effect editor
- [ ] Architecture/wonder/castle picker (visual)
- [ ] Emblem designer or upload
- [ ] KM JSON import
- [ ] Generate + download button

### Phase 4 — Distribution
- [ ] PyInstaller build script (Windows + Mac)
- [ ] Single-click launcher that starts server + opens browser
- [ ] Test on clean machines (no Python installed)

---

## Open Questions

- Should a user be able to define multiple custom civs in one session, or one at a time?
- UT effects: expose full preset catalog, or a subset matched to UT power level?
- Should we support a "random civ" generator for inspiration?
- Elite UU upgrade: auto-generated with stat boosts, or user-configurable?
- What happens when a new AoE2 DLC updates the DAT format? (ship genieutils update, users re-download app)

---

## Reference Links

- Siege Engineers tech tree: https://github.com/SiegeEngineers/aoe2techtree
- KM server reference: https://github.com/Krakenmeister/AoE2-Civbuilder/blob/main/server.js
- Fritz fork: https://github.com/fritz-net/AoE2-Civbuilder
- genieutils Python: (bundled in aoe2 project venv)
