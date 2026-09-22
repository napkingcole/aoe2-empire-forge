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

- ~~**Saxons, Varangians, Danes** need adding to `KM_TECHTREE_ORDER`~~ — **DONE
  2026-09-22, and not by adding them.** The roster is now read from the player's
  own `civilizations.json` (`build_civ.civ_roster`), keyed by **DAT slot**,
  which carries `internal_name`, `tech_tree_name` and `name_string_id` outright
  — so the `10271 + index` arithmetic is gone and a future DLC needs no code
  change at all. Verified: Saxons 10330, Varangians 10331, Danes 10332.
  The bundled `civilizations.json` needs no refresh either, because the build
  already prefers the copy beside the player's DAT.

  Fixed a silent bug on the way: `_DAT_TO_TECHTREE_ID` mapped Mayan → `MAYA`,
  but the shipped file is **MAYANS.json**, and the per-civ tech-tree patch is
  guarded by `if per_civ_path.exists()` — so **replacing the Mayans quietly
  shipped an unpatched tech tree**. Slot-keyed lookup returns MAYANS.
All the new content follows the standard opt-in shape — globally disabled by
tech 79, released by a `type=8` in each owning civ's TT effect — so every one of
these has a vanilla template our code can copy (see bonus 51 above).

- ~~**Mounted Crossbowman + Cranequins**~~ and ~~**Varangian Guard**~~ —
  **DONE 2026-09-22**, see the section below.
- **Ordonnance Companies** — new Frankish Castle UT (Mounted Crossbowmen -40%
  gold). New UT preset. Tech/effect **1496**, `civ=2`, researched at the Castle
  (82), `EC_MULTIPLY attr 105 × 0.6` on units 2700/2701. Not done.
- **Longboat renamed to Longship**, tech **272**, now granted to all four Viking
  civs (Vikings, Saxons, Varangians, Danes).

## Mounted Crossbowman and Varangian Guard — DONE 2026-09-22

Both are regional units contesting a button an existing line already owns, so
neither is a bonus card: they belong in the tech tree, the same way the Elephant
Archer does.

| unit | ids | button | contests |
|---|---|---|---|
| Mounted Crossbowman / Heavy | 2700 / 2701 | Archery Range (87) btn 3 | Cavalry Archer (39/474), Elephant Archer (873/875) |
| Varangian Guard / Elite | 2703 / 2704 | Barracks (12) btn 4 | Fire Lancer (1901/1903), Eagle line (751/753/752) |

Verified against `data.json`: **no civ has both** a Cavalry Archer and a Mounted
Crossbowman, and the Varangian Guard never coexists with a Fire Lancer or Eagle.

**Both buttons are now three-way, which the old `_REGIONAL_PAIRS` table could
not express** — a pair evicts one rival and leaves the other sitting on the
button. It is now `_REGIONAL_GROUPS`: one building button, N lines, one of them
flagged `standard` (the side a blank civ keeps). `_REGIONAL_UNIT_IDS` is
*derived* from it rather than hand-listed, because those two drifted apart once
already.

**Cranequins (1452) is a new kind of node.** It is the first *researchable* tech
that is also in tech 79's global disable list — a scan confirms exactly one such
tech exists. Two consequences:

1. It needed its own `type=8`. Step 3b of the tree wiring only collected
   unlocks for tree *units*, so `_lock_unclaimed_optin_techs` turned round and
   disabled the tech the user had just ticked. Now any tree tech with a vanilla
   unlock template gets one, so the next regional tech needs no code change.
2. It belongs to the Mounted Crossbowman and must not outlive it. Lines carry a
   `techs` list: choosing a rival strips Cranequins along with the unit it
   upgrades, ticking Cranequins pulls the Mounted Crossbowman in (the layout
   links it to Thumb Ring, not to 2700, so the generic ancestor cascade cannot),
   and `_filterFullTree` keeps it out of a blank civ's seed — which would
   otherwise hand out a research node with nothing to research it on.

**Prerequisite work:** `static/aoe2techtree/data/` was still pre-DLC, so the new
units had no editor nodes at all. Refreshed from the upstream clone in
`ignore/aoe2techtree` (53 → 56 civs; the structure was unchanged, only content).
`FULL.json` is *ours*, not upstream's, so the five nodes were lifted from
upstream's SAXONS.json and a grid column inserted in each building — beside the
lines they contest, not appended, or the Varangian Guard renders past the
Barracks' tech column and reads as belonging to the Stable. Confirmed on screen.

**Also renamed:** KM's custom Castle UU 51 was called *Varangian Guard* and now
collides with DE's real one. It is **Hetaireia** — the Byzantine imperial guard
the Varangians actually served in, so the flavour survives. The internal
`VARANG`/`EVARANG` DAT codenames are unchanged, and saved civs key on the index
(`unique_unit.km_idx`), not the name, so existing drafts are unaffected.

Verified end to end on the DLC DAT: picking the units emits `type=8` for
1450/1451/1452/1453/1454 with none of them type=102-disabled, and *not* picking
them leaves all five disabled — so there is no AI leak (quirk 10).
**Not yet in-game tested.**

The three new civs' own content, for when their UU/UT presets are wanted:
Hearth Troop (**1461**/**1462**) + `Shield Wall` (**1464**); Jarl
(**1471**/**1472**) + `Vendel Legacy` (**1473**) and `Gothikon` (**1474**);
Jomsviking (**1481**/**1482**) + `Northmen's Fury` (**1483**, 67 commands) and
`Hamask` (**1484**); plus `Clerical Recruitment` (**1491**). Their team bonuses
are effects **1455** (Saxons), **1456** (Varangians), **1457** (Danes) and their
tech trees **1458**/**1459**/**1460**.

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

## Team bonuses 1, 14 and 16 — FIXED 2026-09-22

The DLC **emptied three team bonus effects** and left everything else in place:
names, and the civs still pointing at them. Genitour (bonus 1, effect 38, 3→0
commands), free Llama (14, effect 4, 2→0) and Condottiero (16, effect 11, 2→0)
simply stopped doing anything. The build reported `11/13 entries applied`, which
is the only reason we noticed.

The cause is a **mechanism swap**, and it is worth knowing because it is how DE
gates regional units generally:

| | pre-DLC | DLC |
|---|---|---|
| how the tech is held back | a **cost gate** — an auto-fire tech (`locs=[(-1,1)]`) carrying a 1-food cost that can never be paid, because there is no building to pay it at | **tech 79 `Disable Regionals`** type=102s it (34 → 45 entries) |
| how the team bonus released it | `type=101` cost→0 + `type=103` time→0 | a `type=8` unlock |

DE made that swap, emptied the three effects, and **never added the type=8** — so
these three are currently dead in vanilla too. Every *other* tech newly added to
tech 79 (Longship 272, Mounted Crossbowman 1450, Varangian Guard 1453, …) is
type=8-unlocked by the civs that should have it; exactly these four (601, 599,
730, 522) are unlocked by nobody.

Tech 79 is the global type=102 list that is the real machinery behind CLAUDE.md
**quirk 5** ("opt-in techs need type=8") — worth naming, because the quirk
described the symptom without ever pointing at the mechanism.

**The fix**, in three parts:

1. `_apply_bonuses` now treats an *empty* mapped effect the same as a missing
   one and falls through to `team_ec_list`. The player's DAT still wins wherever
   it has something to say, so a balance patch to a live team bonus rides along
   for free and only a hollowed-out one reaches our copy.
2. New `team_ec_list` entries for 1/14/16 emit **both** mechanisms, so one list
   is right on either side of the patch — `101`/`103` do the work pre-DLC and are
   no-ops once the cost is already zero; the `type=8` does the work post-DLC and
   is a no-op where nothing disabled the tech. Verified 3/3 applied against both
   DATs, with the pre-DLC build still emitting vanilla's commands verbatim.
3. `dat_drift.py` now diffs the **team bonus effect map**, which it never did —
   it checked techs we depend on but not the effects we copy wholesale. It would
   have caught all three before a user did.

Also new: `EMPIREFORGE_DAT` overrides DAT detection, so the suite can be run
against a DLC build that is not yet the copy on disk. Both branches pass:

```
./tests/run_all.sh
EMPIREFORGE_DAT="$PWD/9-22-26 update/empires2_x2_p1.dat" ./tests/run_all.sh
```

### Why bonus 51 survived the same change, and what that tells us

**Tech 272 `Longboat (make avail)` changed `civ` from 11 (Vikings) to `-1`** and
joined tech 79's disable list — the identical swap, hitting civ bonus 51 ("Can
recruit Longboats from docks", techs 272 + 372). `_allocate_tech` deliberately
does not copy a `civ=-1` tech, so the bonus should have broken too.

It did not. A probe civ on the DLC DAT emits type=8 for both techs, because the
civ-bonus path **searches every vanilla civ's TT effect for an existing type=8
on that tech and copies it verbatim** — "find the precedent", implemented in
code. The DLC gave Vikings, Saxons, Varangians and Danes exactly that command,
so our build found one and healed itself with no code change.

That is the whole shape of the bug in one sentence: **the self-healing path needs
a vanilla template to copy, and 601/599/730/522 are the only techs we depend on
that have none.** A scan of every tech referenced by any bonus, UU or UT preset
found only 272 and 372 newly globally-disabled, and both are covered. So this
class is closed, not merely patched — and it is a real demonstration of the
"keep working as it falls into disrepair" goal doing its job unattended.

## One that still needs a decision, not just new text

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
