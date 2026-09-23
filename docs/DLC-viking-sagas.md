# Viking Sagas (2026-09-22) — what the DLC changes for Empire Forge

Generated from `scripts/dat_drift.py` against the shipped DAT plus the patch
notes in `9-22-26 update/Update.md`. Read it as a worklist — sections marked
**DONE**/**FIXED** are finished (none of it in-game tested yet); the rest is open.

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

## New content — all supported as of 2026-09-22

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
- ~~**Ordonnance Companies**~~ — **DONE**, castle preset 64. Tech/effect
  **1496**, `civ=2`, researched at the Castle (82), `EC_MULTIPLY attr 105`
  (Gold Costs) `× 0.6` on units 2700/2701, so it is inert unless the civ also
  took the Mounted Crossbowman line.
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

## Cards whose text was wrong — FIXED 2026-09-22

Corrected to DE's own wording from `Update.md`, not invented:

| card | was | now |
|---|---|---|
| civ bonus 90 | Archery Range units and Fire Lancers +20% HP | Foot-Archers and Skirmishers +20% HP |
| civ bonus 14 | Barracks and Stable units +1 armor in Castle and Imperial Age (+2 total) | Infantry and Mounted Units +1/+2 melee armor in Castle/Imperial Age |
| civ bonus 51 | Can recruit Long**boats** from docks | Can recruit Long**ships** from docks |
| castle UT 36 | Chieftains (Infantry deal bonus damage to cavalry, **generate gold from kills**) | Chieftains (Infantry deal bonus damage to cavalry) |
| castle UT 38 | Wagenburg Tactics (Gunpowder units move **15%** faster) | …move **10%** faster |

Chieftains is worth a note: the gold-from-kills half was a **resource 33** command
(`EffectFunction 5`) and the DLC deleted it outright along with its resource 274
enabler, leaving only the anti-cavalry attack bonus. So the card was not merely
rebalanced — half of it stopped existing.

**Imperial UT 59, Butalmapu, went the other way and now needs a warning.** It
collapsed from **122 commands to 3**: DE replaced the per-unit list with
`resource 33 = EffectFunction 51` plus two explicit Bolas Rider commands. That is
the Coiled Serpent Array shape — the script knows the vanilla unique units by
name, so the discount cannot reach a custom civ's own UU. Added to
`_XS_UT_NOTES[51]`, and confirmed the warning reaches the user at build time.

### Checked and deliberately left alone

- **Imperial UT 6, Byzantine Logistica.** The effect now names the Varangian
  Guard (2703/2704) and drops the Cataphract +6 vs Infantry. But the preset path
  substitutes source-civ UU ids (40/553) with *our* UU, so "Unique Unit causes
  trample damage" is still accurate; the civ additionally gets trample on
  Varangian Guards if it fields them. No text change.
- **The ~20 other drifted techs.** A preset or bonus clones the effect out of
  **the player's own DAT**, so a balance tweak tracks automatically and only the
  *description* can go stale. Each was read against the notes; the five above are
  the ones whose text no longer matched.

## Hun Atheism — FIXED 2026-09-22 (text only; the commands were never stale)

Tech 21 went **3 → 9 commands**. Worth being precise about what that did and did
not require: a UT preset clones the source tech's effect commands out of **the
player's own DAT**, so a build against a Viking Sagas DAT was already emitting
all nine — verified by probe. Only the description was behind.

Now *"Atheism (+100 years to enemy and neutral Relic/Wonder victories; their
relic income -50%)"*, matching the three changes in the notes: the timer applies
to enemy **and neutral** players, it stacks on repeat research, and the relic
income cut now reaches neutrals too. The new command set is four scope-paired
commands (types 21/31 and 26/36 — enemy and neutral variants of the old 1/26)
plus `resource 33 = EffectFunction 56`, which handles the stacking. That XS half
is generic behaviour rather than a named unique unit, so unlike Coiled Serpent
Array it should carry over to a custom civ — **inferred from the shape, not
verified in game**.

## Frankish Bearded Axe — DECIDED 2026-09-22: keep as-is

Vanilla removed the UT, but tech 83's name, `civ`, `effect_id` and its 6 commands
are unchanged — only prerequisites moved, and castle preset 11 clones the
commands rather than the tech, so it still works. Keeping it offered.

## The three new civs' units and techs — DONE 2026-09-22

Added as presets, the same shape the Mesoamerican DLC set uses (civ-gated
make-avail tech auto-firing in the Castle Age, elite upgrade at the Castle):

| | KM index | techs | notes |
|---|---|---|---|
| Hearth Troop (Saxons) | UU 94 | 1461 / 1462 | units 2705 / 2706 |
| Jarl (Varangians) | UU 95 | 1471 / 1472 | units 2708 / 2709 |
| Jomsviking (Danes) | UU 96 | 1481 / 1482 | units 2711 / 2712 |
| Clerical Recruitment | castle 65 | 1491 | Monks +1 conversion range; train +33% faster |
| Vendel Legacy | castle 66 | 1473 | Knight-line deals trample damage |
| Hamask | castle 67 | 1484 | `EffectFunction 30`; infantry damage scales as they lose HP |
| Shield Wall | imperial 62 | 1464 | `EffectFunction 31`; infantry armor when massed |
| Gothikon | imperial 63 | 1474 | targets units 2703/2704 only — needs Varangian Guards |
| Northmen's Fury | imperial 64 | 1483 | 67 commands, siege and warships |

Descriptions are **DE's own**, read out of the game's `+21000` tooltip strings
(CLAUDE.md quirk 8) — the patch notes cover only changes to existing civs, not
the new ones. Cross-checked: the string for Ordonnance Companies matched the
wording already written from the notes.

Hamask and Shield Wall are `resource 33` script calls, but unlike Coiled Serpent
Array they describe **generic infantry behaviour** rather than a unique unit by
name, so no warning was added — inferred, not verified. Gothikon needs no warning
either: its own text names the Varangian Guard, so it is self-documenting.

**All twelve of these techs are empty placeholders before the DLC**, which
exposed a gap: the UT catalog already refused to offer an unimplemented preset,
but the UU catalog did not, so a player who had not updated was offered a Jarl
that could not exist. It now applies the same rule. KM-custom UUs are untouched —
they are built from a base unit, not from a DAT tech.

Fixed a cache bug found by the test that would have shipped: `_build_all_uu_stats`
caches to disk keyed on **DAT mtime alone**, so adding units left a valid cache
with no entry for them — the catalog offered all three and every stat popup said
"No stats available" with a perfectly good DAT sitting there. The cache now also
fingerprints `_KM_UU_TECHS`, so the next DLC invalidates it by itself.

**Still needed: picker icons.** The UU picker uses
`uniticons/<icon_id>_50730.png` at 256×256 (the tech-tree icons are 48×48 and
would not upscale), one per unit, base tier only — Tiger Cavalry ships `432` and
not its elite `526`. **Nine are missing**, and the six South American ones have
been missing since that DLC:

| | km | unit | file |
|---|---|---|---|
| Guecha Warrior (Muisca) | 92 | 2562 | `543_50730.png` |
| Kona (Mapuche) | 88 | 2566 | `545_50730.png` |
| Bolas Rider (Mapuche) | 89 | 2569 | `547_50730.png` |
| Blackwood Archer (Tupi) | 90 | 2579 | `549_50730.png` |
| Ibirapema Warrior (Tupi) | 91 | 2582 | `551_50730.png` |
| Temple Guard (Muisca) | 93 | 2586 | `553_50730.png` |
| Hearth Troop (Saxons) | 94 | 2705 | `904_50730.png` |
| Jarl (Varangians) | 95 | 2708 | `906_50730.png` |
| Jomsviking (Danes) | 96 | 2711 | `908_50730.png` |

**No code change is needed when they arrive.** `_ICON_MAP` was hand-listed, and
that is the only reason these nine had no picture — nobody added a line. A
vanilla UU's filename is always `<base unit's icon_id>_50730.png`, which was
checked against all 50 hand-listed vanilla entries and matches every one, so the
route now derives it and simply offers no icon while the file is absent.
Dropping a PNG into `uniticons/` is the whole job. The 36 KM-custom entries stay
hand-listed, because their cloned base unit does not carry the right icon, and
they still win as an override.

## The three new civs' bonus cards — DONE 2026-09-23

Twelve civ bonuses (ids **429-440**) and three team bonuses (**84-86**), all
worded from DE's own civ descriptions in the game strings rather than from the
internal tech names — which lie here in three places: techs named `+65%`,
`+33%` and `+10%` are described by the game as +50%, +50% and +5%. The tech is
cloned wholesale, so whatever DE's civ does our civ does, and DE's player-facing
text is therefore the accurate one.

| card | civ | techs |
|---|---|---|
| 429 Mills/Lumber/Mining Camps +35 food, +10 stone when built | Saxons | 1465 |
| 430 Foot Soldiers -5% per TC or Castle (max -20%) | Saxons | 1469 |
| 431 Towers and Castles fire +100% base arrows (Castle Age) | Saxons | 1493 |
| 432 Longships and Catapult Galleons +20% HP | Saxons | 1470 |
| 433 Shepherding, fishing and hunting also generate gold | Varangians | 1475 |
| 434 Bloodlines and Caravan effects +50% | Varangians | 1489, 1490 |
| 435 Varangian Guards attack +25% faster, generate +50% gold | Varangians | 1478, 1488 |
| 436 Longships and Catapult Galleons attack +15% faster | Varangians | 1479 |
| 437 Fishing Ships and Villagers drop off +5% food | Danes | 1494 |
| 438 Loot 25% of the resource cost of each destroyed building | Danes | 1485 |
| 439 Barracks and Siege Workshop upgrades cost -66% gold | Danes | 1492 |
| 440 Varangian Guards and Longships move +10% faster | Danes | 1486 |
| team 84 Repairers work +25% faster | Saxons | effect 1455 |
| team 85 Knight-line +1 attack vs. Infantry | Varangians | effect 1456 |
| team 86 Siege Weapons +2 line of sight | Danes | effect 1457 |

Every source tech is `civ=60/61/62`, so quirk 9 applies — verified that all 14
get a copy allocated to the custom civ's own slot, not merely referenced.

**Worth flagging for the test round:** three are `resource 33` script calls
(433 → `EffectFunction 34`, 438 → `36`, 437 → `35`), and **430** is the most
intricate thing in the set — a live counter that sets attribute 66 on Castles
and Town Centers and leans on helper techs 1497/1498 (`Castle/TC Built` and
`Destroyed`, both `civ=-1` and self-disabling) to track how many you control.
If anything here fails in game, 430 is the first place to look.

**The catalog now filters by DAT, the third place that rule lives** (after
unique techs and unique units): a bonus whose every tech is an empty slot in the
player's DAT is not offered, and neither is a team bonus whose effect that DAT
lacks. Bonuses implemented from `ec_list` carry no techs and are untouched.

### That filter immediately found a regression we had not noticed

**Civ bonus 297, "Can garrison Docks with Fishing Ships", is dead on a DLC DAT.**
Tech 855 went from `civ=42, effect_id=870, 5 commands` to `civ=0,
effect_id=-1` — DE gutted it, matching the note *"Gurjaras — Docks +5 garrison
capacity civilization bonus removed"*. The filter hides it automatically, which
is the safe default, but **whether to restore it is a product decision** of the
same shape as Bearded Axe. The five commands are trivial and recoverable from
any pre-DLC DAT (`type=4` on the Dock ids, attribute 2, `d=5.0`), so a
`civ_ec_list` entry could bring it back — note this would also need the civ path
to fall through on an empty tech, the way `_apply_bonuses` now does for team
bonuses. Not done pending that call.

## The identity page — DONE 2026-09-23

Four separate gaps, three of them fixed in code and one waiting on files.

**The civ list was frozen.** Wonder, castle and voice pickers were built from
our *bundled* `civilizations.json`, so they stuck at 53 civs and the three new
civs did not exist in the wizard at all — the same class of bug as the frozen
`KM_TECHTREE_ORDER`. `/api/builder/meta` now reads the player's roster through
`civ_roster`, which also carries `era` so Chronicles civs stay filtered out.
56 civs on a DLC DAT, 53 on an older one.

**Viking Sagas gave the Vikings their own architecture and their own Monk**, and
we offered neither. `icon_set` **13** (Nordic) and Monk partition **19519**
(civ 11, shared with Varangians and Danes) are both new in this DLC — before it
the Vikings were Central European with the European Monk, which is why the
architecture list's first entry no longer names them. Both are now offered, and
**both are filtered by what the player's DAT actually contains**, so an older
DAT does not get a "Nordic" option that would quietly copy Central European art
under a Nordic label. That is the same rule as the unique tech, unique unit and
bonus catalogs — the fourth place it now lives.

With that, every architecture set and every Monk partition in the DAT is offered
except the Chronicles Monk, which is deliberately blacklisted.

**Voices need no code at all.** The dropdown is driven by which
`voice_files/<value>/` folders exist, so dropping one in makes the civ appear —
verified by creating `voice_files/59/` and watching Saxons show up.

**Where the existing clips came from, since it was not written down anywhere:**
`voice_files/` is a **byte-identical copy of KrakenMeister's
`public/vanillaFiles/voiceFiles/`** (43 folders, 0-42; `bkm1.wem`, `mkm1.wem`
and `invms1.wem` all `cmp` clean against his). Nothing was ever extracted for
this project. That is the whole reason thirteen civs have no voice: KM's
snapshot predates them, exactly as it predates the South American scene art.
His repo has no extraction tooling either — `copyVoices.sh` only copies from
the committed set.

`scripts/voice_manifest.py` derives the needed filenames **from the DAT**, so it
stays right across patches:

```
venv/bin/python scripts/voice_manifest.py           # the 13 gaps, with filenames
venv/bin/python scripts/voice_manifest.py --check   # audit the 43 we have
```

`--check` turns up something worth knowing: **all 43 existing folders are 8
files short** of what the current DAT names — the `vpfm*`/`vpfs*` priest lines
DE added after KM's snapshot. Not breaking (the engine falls back to Wwise
routing per missing file), but it means even the shipped voices are incomplete.

The thirteen civs with no folder at all:

| value | civ | | value | civ |
|---|---|---|---|---|
| 43 | Armenians | | 52 | Khitans |
| 44 | Georgians | | 56 | Muisca |
| 48 | Shu | | 57 | Mapuche |
| 49 | Wu | | 58 | Tupi |
| 50 | Wei | | 59 | Saxons |
| 51 | Jurchens | | 60 | Varangians |
| | | | 61 | Danes |

Each folder holds the game's 58 `.wem` clips for that civ, named with its own
prefix (`bkm1.wem` for Britons, `mkm1.wem` for Vikings). `voice_files/` is
gitignored and not bundled into the exe, so these improve the dev build and mod
output but not the packaged binary — the standing "bundle voice_files" decision
is unchanged, just bigger.

### Art still wanted

None of it blocks anything: a slot with no art renders as a labelled placeholder,
confirmed on screen for both new entries.

| file | what |
|---|---|
| `static/img/scene/arch/tc_13.webp` | Nordic Town Center |
| `static/img/scene/monks/monk_11.webp` | Nordic Monk (scene) |
| `static/img/scene/monks/icons/monk_11.webp` | Nordic Monk (picker icon) |
| `static/img/scene/castles/castle_59.webp` | Saxons castle |
| `static/img/scene/castles/castle_60.webp` | Varangians castle |
| `static/img/scene/castles/castle_61.webp` | Danes castle |
| `static/img/scene/wonders/wonder_59.webp` | Saxons wonder |
| `static/img/scene/wonders/wonder_60.webp` | Varangians wonder |
| `static/img/scene/wonders/wonder_61.webp` | Danes wonder |

The castle and wonder numbers are the civ's option value (DAT slot − 1); art is
picked up off disk, so no code change when they land.

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

## Effect changes read and cleared

The ~30 techs `dat_drift.py` flagged were each read against the notes. All but
the ones fixed above were **balance tweaks our cards already describe
correctly** — a preset or bonus clones the effect out of the player's own DAT,
so the mechanics track by themselves and only the description can go stale.

Two were not just tweaks and are handled above: `1380 Butalmapu` (122 → 3
commands, now script-driven — warning added) and `463 Viking Chieftains`
(6 → 4, the gold half deleted outright — text fixed).

## What is left

1. **In-game testing.** Nothing here has been tested in the game yet. One round
   should cover: team bonuses 1/14/16, the Mounted Crossbowman and Varangian
   Guard (including Cranequins following its unit), Ordonnance Companies, the
   three new unique units and six new unique techs, the twelve new civ bonuses
   (**430 first** — it is the intricate one), and a civ built on the Nordic
   architecture and Monk.
2. ~~Nine UU picker icons~~ — **DONE 2026-09-23**, all 95 unique units now have
   art. Remaining art is the identity-page set listed above (Nordic Town Center
   and Monk, three castles, three wonders) plus voice clips for thirteen civs.
3. ~~The three new civs' civ bonuses~~ — **DONE**, see above. One open
   decision left over from it: whether to restore civ bonus 297, which the DLC
   gutted.
4. **Ship it** — `main` still carries the unpushed `bugfix/dat-path-feedback`
   merge, to be released together with this branch.
