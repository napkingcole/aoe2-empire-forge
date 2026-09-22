# Viking Sagas (2026-09-22) — what the DLC changes for Empire Forge

Generated from `scripts/dat_drift.py` against the shipped DAT plus the patch
notes in `9-22-26 update/Update.md`. Read it as a worklist; nothing here is
fixed yet.

```
venv/bin/python scripts/dat_drift.py OLD.dat NEW.dat
```

## The three things that could have been catastrophic, and weren't

| Check | Result |
|---|---|
| **String pool** (`CAMPAIGN_STRING_POOL`) | **All 1813 ids still unused by the game.** This is the failure that killed KrakenMeister's builder — new content landing in the id range a builder claimed for custom units. It did not happen. |
| **Unit identity** | Every unit id the catalog names still resolves to the same unit. No renumbering. |
| **Tech count** | 1510 → 1510. **No tech ids shifted**, so every catalog mapping still points at the tech it meant. All changes are in-place. |
| **New opt-in techs** (quirk 10) | None. No fresh AI-leak risk. |

Structure: **civs 60 → 63**, effects 1409 → 1500 (+91), techs unchanged.

## New content we do not support yet

- **Saxons, Varangians, Danes** — DAT slots 60, 61, 62. Need adding to
  `build_civ.KM_TECHTREE_ORDER` or their civ-picker name strings (`10271 + index`)
  land on the wrong slot. The bundled `civilizations.json` also needs refreshing:
  the game validates its entry count against the DAT civ count, so a 60-entry
  file against a 63-civ DAT is a hard mismatch.
- **Mounted Crossbowman + Cranequins** — replaces Cavalry Archers for most
  European civs. This is a *regional unit swap*, the same shape as Eagle Warrior
  vs Fire Lancer, so it likely wants `_REGIONAL_PAIRS` / tech-tree editor work
  rather than a bonus card.
- **Varangian Guard** — new shock infantry that generates gold; Byzantines and
  Vikings gain it. Probably an unlock card.
- **Ordonnance Companies** — new Frankish Castle UT (Mounted Crossbowmen -40%
  gold). New UT preset.
- **Longboat renamed to Longship.**

## Cards whose text is now wrong

Confirmed against the patch notes, not just the command-count diff:

- **Bonus 90** — "Archery Range units and Fire Lancers +20% HP". Tech 632 went
  **14 → 1 command**; the notes say the Vietnamese bonus is now *"Foot-Archers
  and Skirmishers +20% HP"*.
- **Bonus 14** — "Barracks and Stable units +1 armor in Castle/Imperial". Techs
  334/335 went **32 → 5 commands**: the notes say Teutons changed to *"Infantry
  and Mounted Units"*, i.e. 32 explicit unit ids replaced by 5 class commands.
- **Bonus 51** — "Can recruit **Longboats** from docks". The unit is now the
  **Longship**.
- **Castle UT 36, Viking Chieftains** — 6 → 4 commands; notes say it no longer
  generates gold from Villagers, Trade Units or Monks.
- **Castle UT 38, Wagenburg Tactics** — notes say gunpowder speed 15% → 10%.
- **Imperial UT 13, Hun Atheism** — 3 → 9 commands, three separate behaviour
  changes in the notes.
- **Imperial UT 6, Byzantine Logistica** — effect changed; now covers Varangian
  Guards and drops the +6 vs Infantry.

## Two that need a decision, not just new text

**Tech 272 `Longboat (make avail)` changed `civ` from 11 (Vikings) to `-1`
(global).** That matters more than the rename: `_allocate_tech` deliberately
does *not* copy a `civ=-1` tech, because a global already fires for everyone.
Bonus 51's mechanism may therefore have changed underneath it — worth a probe
civ before assuming it still behaves.

**Tech 83 `Frankish Bearded Axe`** — the notes say the UT was *removed*, and the
audit flags its definition as changed. But its name, `civ`, `effect_id` and its
6 commands are **identical**; only prerequisites moved. Since UT presets clone
the tech for our civ, castle preset 11 probably still works. Verify rather than
assume — and decide whether to keep offering a UT vanilla no longer has.

## Large effect changes worth a look, lower confidence

`1380 Butalmapu` (122 → 3 commands — by far the biggest single change),
`594 Gold productivity` (5 → 2), `1381 Forager productivity` (3 → 2),
`349 Super Dock`, `409 TC and Dock work rate`, `506/517 Indians UT`,
`578 Berber UT`, `690 Burmese UT`, `755 Flemish Revolution`, `756 First
Crusade`, `805 Stone Miners`, `855 Docks garrison`, `1071 Lumberjacks food`,
`152-155 Military cost`, `453 Foragers generate wood`, `654 Instant Farmers`,
`806/807` (bonus 281's scaling techs).

A balance tweak our card already describes correctly looks identical here to one
that broke it, so each needs reading against the notes — the same method the
2026-09 catalog sweep used.

## Suggested order

1. **Ship the DAT-independent work first.** The `bugfix/dat-path-feedback` merge
   sitting unpushed on `main` is unrelated to the DLC and already verified.
2. **Structural support** — the three new civs, `KM_TECHTREE_ORDER`,
   `civilizations.json`, the updated `CivTechTrees/`. Without this the app is
   broken for anyone who has updated the game, which by now is everyone.
3. **Card text** for the seven confirmed-wrong bonuses above.
4. **New content** — Mounted Crossbowman swap, Varangian Guard, Ordonnance
   Companies.
5. **The lower-confidence effect changes**, worked through against the notes.
