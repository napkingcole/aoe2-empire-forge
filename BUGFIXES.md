# Bug Fix Log

Tracks confirmed bugs in the civ builder (mod generation pipeline) and when they were patched.
Add a new entry here whenever a bug is fixed. Format: date patched, what broke, root cause, fix.

---

## 2026-09-18 — every `team_ec_list` entry was under the wrong id, and one of them crashed the game

**Symptom:** a reporter's civ (`ignore/sandbox/bugfixing/maruviel`, 105 civ bonuses, 15 team
bonuses) crashed AoE2 DE at launch, before the main menu. He asked whether he had "overdone it
with bonuses". He had not — the civ bonuses were fine. Rebuilding his civ and scanning the
produced DAT found exactly one effect over the engine's ceiling: **`Ionians Team Bonus`, 246
commands**, against a ~189 limit and a vanilla maximum of 189 (`Hero Shadow Tech`).

**Root cause — a ten-week key drift.** `bonus_catalog_raw.json["team_ec_list"]` is keyed by team
bonus id and was authored **2026-06-26**. On **2026-07-03** `team_bonus_names.json` was rewritten
into KM's authoritative `card_descriptions[4]` ordering to fix a shuffle from index 11 on (entry
below). The names moved; the 30 `team_ec_list` entries did not. From that day every one of them
implemented a different bonus than its card promised.

Checked by diffing each entry against the **pre-rewrite** names file: all 30 matched their old
name exactly — `Trade units +50 HP` is four `ADD attr 0 += 50`, `Docks cost -15%` is five
`MULT attr 100 ×0.85`, and so on. There was no ambiguity and nothing unmatched, which is what
makes the re-key safe to do mechanically.

The crash came from the worst pairing. Id **54** reads *"Spearmen +3 attack vs. cavalry"* — three
commands. It carried *"Unique Units +5% HP"*: **142** `EC_MULTIPLY` commands, one per unique unit.
Team bonuses are all merged into the single effect `civ.team_bonus_id` points at, so 54 plus
fourteen ordinary picks came to 246. The reporter's civ now builds at **83**.

**The guard only ever covered half the problem.** `apply_civ` has checked the *tech tree* effect
against a 185-command soft limit since 2026-08-28, with a user-visible warning. The team bonus
effect — the one memory explicitly calls "the most dangerous", and the one that produced the
original 443-command crash — was never checked at all.

**Three `team` entries pointed at effects that are not team bonuses.** That column holds **effect
indices**; `_apply_bonuses` does `dat.effects[eff_idx]`. Tech ids and effect ids are both small
integers, so a tech id there does not fail, it silently resolves to the wrong effect:

| id | card | held | which as an effect is | should be |
|----|------|------|----------------------|-----------|
| 8  | Farms +10% food | 232 | `Make Fire Galley Avail` — gave allies a Fire Galley | **240** (`techs[232].effect_id`) |
| 30 | Military buildings +5 pop room | 721 | `Elite Leitis` — gave allies a free Elite Leitis upgrade | **758** (`techs[721].effect_id`) |
| 45 | Skirmishers/Spearmen/Scout-lines train 20% faster | 601 | `Carrack` — ships +1/+1 armour | *(none; use its ec_list)* |

8 and 30 are a regression from `beb679d` (2026-09-17), the commit immediately below — which fixed
a real mismap by writing the **tech** ids into the effect column, the exact trap its own entry
warns about. 30 had been correct (758) since 2026-07-03. 45 has been wrong since extraction.

These three are the modern DE shape: the civ's own `team_bonus_id` is an empty or trivial stub and
the real commands live in a tech's effect, using `type=10` (team-scoped) commands for 30 and 83.

**Fix:**
- Re-keyed `team_ec_list` to the current names. Ten entries then duplicated a real vanilla
  team-bonus effect — and the effect map wins in `_apply_bonuses`, so they were dead code reading
  like live implementations — and were dropped. 30 entries → 20.
- `team`: `8 → 240`, `30 → 758`, `45` removed.
- `apply_civ` now guards the **team bonus** effect on the same soft limit as the tech tree, and
  the warning names the three biggest contributors so the user knows what to drop.
- A team bonus the catalog cannot implement is now reported as a warning instead of vanishing
  inside `Team bonus: 14/15 entries applied`.
- `/api/builder/bonuses/catalog` filters team bonuses through `unsupported_team_bonuses()`, the
  way it has always filtered civ bonuses. It did not, so an unimplementable team bonus was
  pickable and then silently dropped at build time.
- `_TEAM_BONUS_COUNT` 80 → 84. It bounds the loop in `unsupported_team_bonuses()`, so while it
  said 80 the DLC ids 81-83 were offered in the picker but never checked for an implementation.

**Eleven ids lost their (wrong) implementation and now have none:** 40, 42, 46, 60, 61, 62, 66,
68, 72, 73, 75. They are KM-invented bonuses with no vanilla effect to copy, so each needs a
hand-written `ec_list`. They drop out of the picker automatically and are listed on
`/limitations`.

`tests/test_team_bonus_catalog.py` pins both halves and was verified to produce 18 failures
against the pre-fix catalog. The invariant that catches the id-namespace trap for good: **every
value in `team` must be some civ's own `team_bonus_id`, or one of three named tech-delivered
effects.** It also builds the reporter's 15-bonus pick and asserts the guard stays quiet, and a
deliberately overweight pick and asserts it fires.

**Not verified in-game.** The `type=10` commands on ids 30 and 83 are copied into
`civ.team_bonus_id`, which is itself the ally-application channel. 758 was the value for ten weeks
before `beb679d` changed it, so this restores known behaviour rather than introducing it, but
whether a team-scoped command nested inside a team effect actually lands has never been confirmed.

### Content sweep of the 20 surviving entries

Re-keying put each list under the right card. This is the second half: what each one actually
targets. **Twelve of the twenty were wrong**, in ways no key check could ever see.

**The tool that made it tractable was resolving display names.** `unit.name` is an internal
codename and routinely lies — `775` is `MONKY` (the **Missionary**), `1137` is `TIGER` (an
elephant-adjacent slot that is a **wild animal**), `1572` is `MERCHANT`, `594` is `SHEEPG`. Reading
the lists as codenames, they look plausible. `civ_appender.unit_label()` now resolves
`language_dll_name` against the shipped `vanilla/key-value/key-value-strings-utf8.txt`, and the
same helper feeds the build log, so warnings say `775 (Missionary)` instead of `775 (MONKY)`.

**Two bonuses did nothing whatsoever.** Both "built 100% faster" cards (**43**, **63**) were
`EC_SET attribute 20 = 1.0`, and **attribute 20 is Minimum Range**. A building's construction time
is its `creatable.train_time` — attribute **101** — confirmed against the in-game numbers (Mill
35s, Dock 35s, Market 60s, Monastery 40s, House 25s all match exactly). Both are now
`EC_MULTIPLY attr 101 ×0.5`.

**Two more were aimed at armour classes that cannot do what the card says:**

- **47** *"Scout-line +2 attack vs. gunpowder units"* packed armour class **31**, which the UGC
  guide lists as **Unused** — so the attack bonus landed nowhere. Gunpowder is **23**. Its target
  classes were wrong too: object class **12** (`cCavalryClass`, i.e. *every* cavalry unit) and
  **58** (`cLivestockClass` — **sheep**). The scout line straddles two object classes (448 is 47
  `cScoutCavalry`, the rest are 12), so it can only be hit by explicit id.
- **48** *"Infantry +5 attack vs. Elephant units"* packed armour class **19**, which is
  **Unique Units** — every Castle UU carries it. Elephants are **5**, verified to cover all ten
  trainable elephants.

**Wrong units, now that they could be read:** **55** *"Elephant units"* was the **Elite War Wagon**
and a **wild tiger**, and is now the ten real elephants; **39** *"Trade units"* included an
**Ostrich**; **45** had a **Sheep** for Scout Cavalry and the **Merchant** for Imperial Skirmisher;
**45** and **54** both listed the **Militia** as a spearman.

**Missing upgrade tiers — the Tier-2 shape from the civ-bonus audit, where a bonus evaporates the
moment the unit upgrades:** **56** *"Shock Infantry"* had no Elite Eagle Warrior or Elite Jaguar
Warrior; **45/48/54** had no **Pikeman** at all; **48** had no Champion; **58** covered one of four
Monasteries and **59** one of three Markets; **43** covered one of four Lumber Camps and one of
four Mining Camps. **50** had the male Hunter but not the female — vanilla pairs the genders in
all 16 effects that name either.

Spear-line entries now include the three Donjon copies (1786/1787/1788), matching vanilla: 14 of
the 31 shipped effects that name the spear line carry them, including every civ-bonus one.

**Checked and correct:** 41 (object class 18 is `cMonkClass`), 44 (all 142 entries verified to
train at Castle/Krepost/Donjon), 49, 50's mechanism, 51, 53, 57, 65 (*"when empty"* really is the
empty cart id only), 67.

**Known structural limit, not fixed:** **49** *"Explosive units +20% speed"* uses object class 35
(`cPetardClass`), which cannot reach **demolition ships** — they are class 22 (`cWarshipClass`),
shared with Galleys. Same constraint recorded for civ bonus 191 on 2026-09-13; it needs explicit
ids, which is a behaviour change rather than a fix.

**Not verified in-game:** attribute 101 on a *building* is the construction-time lever by
inference from `train_time` matching every in-game build time. That inference is strong but
untested, and it is what both "built 100% faster" cards now rest on.

---

## 2026-09-17 (b) — two team bonuses pointed at the wrong tech, and four civ bonuses were partial

From reviewing the 27 vanilla bonus techs the catalog never references. The user supplied the
game-side truth for each; several "gaps" turned out to be correct vanilla behaviour.

**Two team bonuses were mismapped — both the shape fixed once already on 2026-07-03.**

- **Team 8 "Farms +10% food" pointed at tech 402**, `C-Bonus, Hunting bonuses` (Goths): hunter
  carry capacity and hunt productivity. A team picking "Farms +10% food" got Goth hunting.
  The Chinese team bonus is tech **232**, which multiplies resource 69, *Farm Food Multiplier*.
- **Team 30 "Military buildings provide +5 population room" pointed at tech 758**, which is
  `Feudal eco tech requirement` with **effect_id = -1** — nothing. 758 is tech **721**'s *effect*
  id: a tech/effect id mix-up. 721 is the Slavic team bonus, `type=10` +5 pop on 12 military
  buildings. **Team bonus ids are their own namespace and a plausible-looking tech id in that
  column may be an effect id — check `dat.techs[x].name` before trusting it.**

**Four civ bonuses were missing techs:**

- **25 "Town Center, Dock 2x hit points"** doubled Town Centers only; tech **349** `Super Dock`
  (same civ) is the Dock half, covering all eight Dock ids including the SDOC variants.
- **345** promised a free Villager per Mill/Lumber/Mining Camp tech but the real bonus is *every
  economic upgrade*. Added Wheelbarrow, Hand Cart, Fishing Lines and Gillnets (1049/1050/1054/
  1051); Caravan and Guilds (1052/1053) stay out as Market techs. 10 techs → 14.
- **356 "Pastures"** disabled the Mill line (Farms, Horse Collar, Heavy Plow, Crop Rotation) and
  granted nothing back, so a Pasture civ had **no Mill economy upgrades at all**. The Khitan
  substitutes are Livestock Husbandry → Enclosures → Grazing Grasslands, on the same Mill button,
  all `civ=53` and therefore invisible to us until copied (quirk 9). Now allocated.
- **73 / 58 "Buildings cost -15% wood/stone"** — **not a bug.** Techs 595/519 discount the
  building classes then multiply Town Centers back up, and techs **156/158** re-apply the discount
  to Town Centers gated on tech **307 "Shadow TC Annex"** (a Town Center has been completed).
  That is precisely the documented Malian/Incan **Nomad-start carve-out**: the discount never
  reaches the first Town Center you build. Adding 156/158 reproduces vanilla exactly — the net is
  `0.85 × 1.1765 × 0.85 = 0.85` once a TC exists. Game Update 81058 lists the same carve-out for
  Bulgarians, Aztecs, Persians, Sicilians and Spanish.

**Starting resources standardised.** The offered set was a mixed bag — +50 wood *and* food, +50
gold, +150 wood, +100 stone, +50 wood *and* stone, +70 food/+30 gold. Now four cards, +50 of a
single resource each (424 food, 425 wood, 426 stone, 427 gold), so any amount is reachable with
the multiplier (x5 = +250) and any pairing by taking two cards. The six old ids are deprecated,
not deleted, so civs already carrying them still build.

**Also added:** 423, Cumans' "Archery Ranges and Stables cost -75 wood" (tech 664) — we offered
the two halves separately but never the combined card.

**Checked and left alone:** the Mayan per-age archer cost steps (53/56, covered by bonus 133's
handler); Slavs' "Monks 20% faster" tech 510 (bonus 219 does it via `ec_list`, and keeping our own
copy means a future vanilla rebalance cannot silently change the number out from under the card
text); Bohemians' 808 (covered by bonus 202). The Spanish "Builders work +30% faster" is already
bonus 127 via resource 195, *Construction Rate Modifier* — **no vanilla effect sets 195 at all**,
so that one is ours and covers Town Centers too, making vanilla's tech 159 unnecessary here.

---

## 2026-09-17 — cMulResource never scaled, so 13 cards' multipliers were half-broken

**Symptom:** found while building the "+% drop off" bonus family. `_scale_ec_for_multiplier`
handled EC_MULTIPLY, mode-2 EC_TECH_COST/TIME, EC_ADD and EC_RESOURCE — but **not type 6
`cMulResource`**, the lever behind every "drop off +N%" and "resources last N% longer" bonus.

**Root cause:** type 6 fell through to "left alone". Thirteen visible bonuses contain type-6
commands: 7, 75, 94, 108, 132, 235, 236, 237, 238, 240, 281, 357, 368.

**Worse than a no-op for the "last longer" family.** 132 and 235-240 pair a productivity gain
with a *compensating work-rate cut*, and the cut is an EC_MULTIPLY, which did scale. So at x2 the
villager slowed to `d**2` while productivity stayed at `d` — **the card's own multiplier reduced
the player's income.** Bonus 235 at x2: lumberjacks at quarter speed, wood productivity still only
doubled. Same inversion as the 2026-09-09 mode-2 EC_TECH_COST bug, in a different command type.
For 108 and 357 (type-6 only) the multiplier did nothing at all.

**Fix:** `EC_MUL_RESOURCE = 6` compounds `d ** N`, exactly like EC_MULTIPLY. `bonus 235 at x2`
now keeps `productivity × rate == 1.0`, which `tests/test_multiplier_scaling.py` pins directly.

**Also in this batch, from a scan for vanilla bonus techs the catalog never references:**

- **67 "Ships +10% HP" was missing its Castle and Imperial steps.** Techs 1398 (`req 102`,
  x1.0476) and 1399 (`req 103`, x1.0454) compound with 560 to +10/+15/+20%. Identical gap to
  bonus 76's missing Feudal tech; the card is now a progression.
- **302 "Navy armor" was hand-rolled and wrong.** Vanilla tech **888** gives Galley, War Galley,
  Galleon and Dromon **+1/+1**. Our `ec_list` gave the upgraded three +2/+2 and needed the Galleon
  bolted on by hand (2026-09-10). Now mapped to 888 and the `ec_list` is gone.
- **Checked and NOT a bug:** techs 1199-1201 scale bonus 134's lumberjack food with the lumber
  upgrades and are absent from the catalog — but they are `civ=-1`, referenced by no type=8 and
  disabled by no type=102, so they fire on their own. Contrast bonus 281's scaling techs 806/807,
  which are `civ=38` and therefore *do* need allocating. **Whether a scaling tech needs claiming
  depends entirely on its `civ` field.**

**New bonuses (418-422), the "+% drop off" family.** `cMulResource` on a *Productivity* resource
plus carry capacity on the gatherers is what AoE2 DE means by "drop off +N%" — confirmed by the
UGC guide, which documents the gather-rate side effect and the Mayan compensation, and by the
upcoming Danes bonus. 418 food (resource **190**, "food from all sources" — a lever nothing in the
catalog used), 419 wood (189), 420 stone (79), 421 fishing ships (219), 422 the Danes-style
combined food card. Gold was already bonus 75.

---

## 2026-09-15 — Bonus 339 fed every building; the rest of the sweep was card text

**Symptom:** round 3 of the catalog sweep, closing Tiers 3 and 4.

**Bonus 339 was the only real defect.** The card says "Military production buildings and Docks
provide +65 food", but vanilla tech 1084 is `ADD class 3 Building attr 27 += 55` — **every**
building, Houses, Mills, Farms and Town Centers included.

**Root cause of the tricky half:** attribute 27 is `AmountThirdStorage`, i.e.
`resource_storages[2]`. On every military building and Dock that slot already ships as
`(type 0 = food, amount 0, flag 8)`, which is why adding to it yields food at all. **The Krepost
and the Harbor ship that slot empty (`type -1`)**, and an EffectCommand can change a slot's
*amount* but never its *type* — so no command could ever have fed them, and a class-wide command
silently skipped them while hitting every House.

**Fix:** bonus 339 became a handler. It opens the two empty slots directly on the civ's own unit
copies (the same unit-data write bonus 330 does for 2×2 farms), then emits `ADD attr 27 += 55` on
19 explicit ids — Dock ×4 + Harbor, Barracks ×4, Stable ×3, Archery Range ×3, Siege Workshop ×2,
Castle, Krepost. Kept the effect's +55 over the card's +65, matching the other Tier 3 rulings.

**Everything else was text.** Tier 3 cards 359, 180, 340 and 346 now state what their effects do
(+15% not +25%, +25% not +33%, 10/15/30 not 10/20/30, +20%/+30% not +15%/+30%). Tier 4: bonus 10's
heading was the literal string `"test"` and its progression card had no `ages` rows and no
`entity`; 59/267 stated a total as a delta; 208 said "attack" for attack speed; 376 leaked
"(team effect via type=10)" to players; 371 advertised a per-age training speedup without
mentioning the ×2.15 Feudal penalty that precedes it.

**Correction to the 2026-09-09 audit.** It reported ten blank visible cards. **Cards carry their
own `hidden: true` flag** (`builder.js:1655`), and the audit's visibility check only consulted
`bonus_names.json` minus `unsupported_bonuses()` minus `DEPRECATED_BONUSES`. Six of the ten — 61,
245, 297, 331, 338, 344, 349 — were already hidden and never rendered. The real set was 12, 18, 27
and 28, all now filled in. Any future "is this bonus visible?" check must consult the card flag as
well as the two Python sets.

---

## 2026-09-13 — Five more bonus cards claimed things their effects never did (sweep round 2)

**Symptom:** round 2 of the catalog sweep (`docs/AUDIT-bonus-catalog-mismaps.md`), closing out
Tier 2. Each card promised something no EffectCommand delivered.

**Root cause — and one new general lesson:**

- **52 "Gunpowder units cost -20%"** — vanilla tech 500 discounts five units, then gives Rocket
  Carts, Fire Lancers and Grenadiers **+25% hit points instead of the discount**. Vanilla-faithful
  (it is the Portuguese bonus) and wrong for a card whose whole claim is a cost cut.
- **140 "Wonders don't cost wood…"** — only the +50 population half was implemented.
- **191 "Explosive units 2x HP"** — `MULT class 35` covers Petard, Flaming Camel and the
  unbuildable Saboteur, but **demolition ships are class 22 (Warship)**, shared with Galleys, so
  they can never be swept in by class. They were silently excluded.
- **312 "…drop-off buildings cost -25%"** — only the Mule Cart was discounted.
- **368 "Foragers work 25% faster"** — the effect raises berry food and carry capacity; attribute
  13 is never touched. Implementation coherent, sentence wrong.

**New lesson — a building needs one id per age.** All four Mills share `language_dll_name` 5157
and differ only in `standing_graphic`; only the Dark Age one ships `enabled=1`. Same for Lumber
Camp (562-565), Mining Camp (584-587), Folwark (3) and Settlement (3). Discounting only the base
id leaves every later age at full price — the same class of trap as CLAUDE.md's "a unit has
several upgrade tiers" note, one level up.

**Fix:**
- 52 moved off tech 500 into an `ec_list` of twelve `MULT attr 100 ×0.8`, adding the units vanilla
  skipped. Deliberate divergence, recorded in `bonus_catalog.py`.
- 140 gained `EC_SET attr 104 = 0` on all seven Wonder ids. The card's "Maximum 1 Wonder" line is
  the engine's **default** behaviour, so it came off the card rather than being implemented — the
  only one-at-a-time mechanism in the DAT is the hero pair (attrs 126/127), used on exactly three
  units and never on a building.
- 191 gained 527/528/1104 and the Grenadier (1911) by explicit id.
- 312 gained `_apply_dropoff_discount` — `MULT attr 100 ×0.75` on 18 building ids. It could not be
  an `ec_list` entry: **the bonus dispatch is exclusive**, so a bonus with a tech list `continue`s
  before `ec_list` is read, and 312 maps eight techs. It runs as a supplement after the tech
  branch, the shape bonus 105 already uses after its ec_list.
- 368 reworded to the **Mapuche** bonus's official text, *"Foragers drop off +25% food"* — which
  is precisely what tech 1381 already did, so no mechanism changed. It is structurally identical
  to tech 594 (bonus 75, *"Villagers drop off 10% more gold"*): `cMulResource` on the resource
  pool plus carry capacity on both gender variants. **That pair is the codebase's idiom for "drop
  off N% more"** — the bush holds more and each trip delivers more; the gather rate is untouched.
  It is **not** the Franks bonus as first assumed — tech 1381 is `civ=58`. The Franks' forager
  bonus is **bonus 5** (tech 524, `civ=2`, work rate ×1.15), already at its patched 15% with only
  the card stale at 10%; that card is now fixed too.

---

## 2026-09-10 — Seven civ bonuses were inert, mismapped, or stale, found by a full catalog sweep

**Symptom:** an audit comparing every one of the 350 visible bonus cards against the effect
commands its techs actually fire (`scripts/dump_bonuses.py`, findings in
`docs/AUDIT-bonus-catalog-mismaps.md`) turned up 28 discrepancies. Seven were fixed in this pass.

**Root cause — four distinct kinds:**

1. **KM points at empty DAT slots.** Bonuses **357** (tech 1003 `RESERVED`), **306** (tech 893
   `RESERVED`) and **342** (techs 1077/1078, unnamed) map to techs with `effect_id = -1`, no
   prerequisites, and nothing in the DAT referencing them. He never populates them either, so
   these have never done anything. Bonus 357 was inert in full; 306 and 342 lost half their card.
2. **A mapping that carries someone else's unit.** Bonus **108** ("Farm upgrades +125% food")
   maps `{772, 773, 774, 815, 816, 817}`, and **773/774 are the Flemish Militia make-avail and
   its Castle-Age stat boost** — every civ taking the farm bonus silently gained a unit line.
   815-817 are `New Research` stubs pointing at the empty effect 0.
3. **A missing tech.** Bonus **76** maps only the Dark Age step (584). The Berbers' Feudal tech
   (**600**, requires 101, `×1.047619`) exists and is simply absent from KM's list.
4. **A prerequisite that was never re-pointed.** Bonus **360**'s "Heavy Cavalry Archer available
   in Castle Age" is not in any effect — it lives in tech 218's prerequisites, which want **2 of
   `[103 Imperial, 192 Cav Archer (Castle), 1004 Khitan trigger]`**. `_allocate_tech` copies the
   civ-gated 1004 to a new id while 218 keeps naming the original, so the civ never reached the
   threshold early. This is CLAUDE.md quirk 9 for the third time (after Winged Hussar and the
   Burgundian eco shims).

**Several were stale wording, not broken code.** DE has changed the game under the catalog:
Scorpions now get Ballistics on every civ (306), the naval rework dropped early Careening/Dry
Dock (342), Japanese fishing ships traded +2P armor for +100% HP (16, already implemented as
`class 21 HP ×2`), and the Goths lost their boar attack while keeping carry capacity and hunt
food (7). For these the fix was to retarget the card, not to implement the old text.

**Fix:**
- Catalog: `76 → [584, 600]`, `108 → [772]`, `306 → [892]`, `342 → [1079]`, `357 → ec_list`
  (`cMulResource` type 6 on resource 216, livestock food, `d=1.1`).
- `302` ("ships get blacksmith armor") gained the **Galleon 539** at `+2/+2`, matching War Galley
  and Dromon — without it the bonus vanished on the Imperial upgrade.
- `civ_appender._ALT_PREREQ_BONUSES` generalises the old Winged-Hussar special case into a table;
  bonus 360 joins it. The build log line changed from `Winged Hussar:` to
  `Bonus <id>: N tech(s) re-pointed`, and `tests/test_build_smoke.py` was updated to match.
- Wording: bonuses **7, 16, 241, 306, 342** retitled; `241` is now "Garrisoned units heal at a
  faster rate", which is what its `GarrisonHealRate ×2` always did. `342` and `365` flagged
  `"multiplier": false` — nothing to scale once a cost is already zero.

`tests/test_audit_fixes.py` builds one civ carrying all seven changed bonuses and asserts each
command reaches the built DAT, because "the catalog says so" is exactly the assertion that would
have passed while bonus 357 did nothing.

---

## 2026-09-09 — Civ bonus 54 "Fishermen work 10% faster" did the wrong thing entirely

**Symptom:** the bonus had no effect on fishing villagers. Its multiplier also did nothing.

**Root cause:** the catalog mapped bonus 54 to tech **469 `[SCEN] Move Tarkan`** — a
scenario-editor tech that sets attribute 42 (train location) to -1 on units 755/757. Nothing to
do with fishing, and potentially harmful to a civ that also fields Tarkans.

**Inherited, not introduced.** KM's builder has the identical mapping
(`civbuilder.cpp:196`, `civBonuses[CIV_BONUS_54_FISHERMEN_WORK_10_FASTER] = {469}`), and our
catalog was extracted from his C++, so we copied it faithfully. There was no correct upstream
implementation to fall back on. Same failure shape as the 2026-07-03 team-bonus-30 mismap below.

**Fix:** no vanilla tech implements this bonus, so it moved to `ec_list` — `EC_MULTIPLY` on the
fishing villagers **56 `VMFIS`** and **57 `VFFIS`**, attribute 13 (work rate), `d=1.1`. That is
the shape vanilla uses for every other per-task villager work-rate bonus (effects 956/958 do the
same for lumberjacks and gold miners, both gender variants, `b=-1`, death variants untouched).
Villagers carry a distinct unit id per task, so targeting the task variant is the only way to
scope a bonus to one resource. Fishing *ships* (techs 306/906) are a different thing and are not
what this bonus describes.

Because the fix is an `EC_MULTIPLY`, the card's multiplier now works for free: x2 gives 1.21,
x3 gives 1.331. `tests/test_bonus_54_fishermen.py` pins the mapping, since the catalog docstring
points future readers at KM's source and re-extracting would silently restore tech 469.

---

## 2026-09-09 — Civ with no unique unit crashed the build

**Symptom:** `apply_civ` raised `UnboundLocalError: cannot access local variable 'uu_id'` for any
civ that selected no unique unit. Never reached a user — found the same day it was introduced.

**Root cause:** removing the unreachable from-scratch UU block (`51f856d`) also removed the
`uu_id, elite_uu_id = -1, -1` initialisation that lived inside it, while the UT substitution
blocks and `apply_civ`'s result dict still read both names on every path.

**Why the suite stayed green:** every saved civ in the corpus picks a unique unit, so the
round-trip harness and the build smoke test always walk the KM UU branches. The no-UU path had
no fixture anywhere. **This is the second time this exact shape has shipped** — see the
2026-09-02 `NameError` below, where a deletion also left a live reference behind a branch no test
exercised. When deleting a block, grep for every name it *assigned*, not just the names it called.

**Fix:** restore the initialisation unconditionally, plus `tests/test_no_uu_civ.py` (verified to
fail with the init removed again). That test also pins that bonus ids whose cards were hidden in
`5dc2ec7` still build, since hiding a card is a display decision and saved civs still carry them.

---

## 2026-09-02..04 — Discord issue batch #25-#35 (in-game confirmed 2026-09-04)

Worked from `github.com/napkingcole/aoe2-empire-forge/issues`. All of the below were
verified in-game on the two probe civs in `my_civs/` (`PROBES.md` has the test plan).

**Build-breaking regression (found first, blocked everything else).** `9259f40` deleted
the Dragon Ship block in `_apply_tree_wiring`, which was where `_civ_bonus_ids` was
defined, leaving a reference behind at what is now line ~1018. Short-circuiting `and`
meant it only fired when the building was absent from `tree[1]`, so every build crashed
with `NameError` unless the civ had Settlement, Folwark *and* Mule Cart ticked. Branch
only — the released v2.0.0-beta.1.4 was unaffected. Fix: `_civ_bonus_ids_early`.
**The round-trip test would have caught this but is opt-in (`ROUNDTRIP=1`)** — worth
deciding whether it should default to on when a DAT is present.

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 32/33 | Unticking Monks, Houses, Fishing Ships, mining/fishing techs did nothing | disable list built only from techs some vanilla civ disables | candidate universe is now `_editor_nodes()`; three mechanisms + a protected set — CLAUDE.md quirk 15 |
| 35 | UU cost override ignored | `resource_costs` is a fixed 3-tuple and the population slot fills the third, so a *new* resource had nowhere to go and was dropped | cost boxes are now the complete spendable cost; warns when >2 resources requested — quirk 14 |
| 29 | UU train time only applied at the Castle | `train_time` is per `TrainLocation`; only `[0]` was written | write every slot — quirk 14 |
| 27 | Winged Hussar: civ lost the Hussar and gained nothing | tech 786 wants 3 of `[115, 254, 788, 789]`; the copied trigger lands at a new id so only 115+254 were satisfiable | `_add_alt_prereq` — quirk 9 |
| 26 | Eco upgrades discounted but not an age earlier | the "one age earlier" half is nine Burgundian `civ=36` shim techs listed as alternative prerequisites — no EffectCommand can express it | `_apply_early_eco_shims` + `_add_alt_prereq` |
| 34 | Custom UU hover showed neither cost nor description | three stacked bugs: tooltip rendered inside `apply_civ` before overrides ran; `wizard_build._draft_to_civ_def` dropped the description; and both string blocks wrote the same ids twice with different text | `_refresh_uu_tooltips`, carry the description, `_owned_sids` guard in all three builders |
| 31 | Feitoria buildable on a civ replacing the Portuguese | the blank-civ seed carried it (see below); the DAT refused it but `_patch_per_civ_techtree` still lit the node | `UNSUPPORTED_UNIQUE_BUILDINGS`, filtered in `_tree_sets` |
| 25 | Eagle Warriors and Fire Lancers both selectable | both sit on Barracks button 4, so one was always unreachable | `_REGIONAL_PAIRS` entry; Fire Lancers are the default side (5 civs vs 2) |
| — | Monk skin: right skin idle, wrong skin walking, wrong icon | `_copy_monk_skin` copied 3 of the 6 per-skin fields while `_copy_architecture` had already written the walking graphic | copy all six — quirk 12 |
| — | New civ arrived with ~10 Unlock cards ticked and a phantom Feitoria | `_filterFullTree` read `_REGIONAL_UNIT_IDS`/`_REGIONAL_BUILDING_IDS`, which cover neither Unlock-card units nor civ-unique buildings | filter both; `tests/test_seed_tree.js` |
| — | UT research-button label could render the whole tooltip | `castle_ut_desc_sid` **is** `name_sid+1000`, the button label — two writers, one id | drop the second write; slot map now documented at `_append_unique_tech_stubs` |
| — | Crash on any civ with a blank UU name/description | `.get("name", "").strip()` — the default never fires when the key exists as `null`, which is how the wizard stores an untouched field | `or ""` |

**#22** (Bohemian free mining) needed no work — it shipped in `0187f9e` the same day it
was filed; this batch only confirmed it.

**#30** (2 sheep per new Town Center) was the hard one. The four copied techs were
faithful in every field, so it was isolated with two single-bonus civs —
`probe_sheep` (bonus 139) and `probe_tcfood` (bonus 100, the same per-TC engine hook
via tech 639 + attribute 57). **Both worked in isolation**, which means the mechanism
copies correctly and the original failure was interference from something else in
`probe_bonus`. Not yet root-caused.

**Still open:** Fish Trap cannot be disabled (no editor node anywhere). `build_all.py`
writes `help_sid_ut`, which nothing reads — left in place deliberately and commented.

---

## 2026-06-29 — Elite Cavalier / Paladin unlocked too early

**Symptom:** Elite Cavalier and/or Paladin became trainable or researchable before the
correct age requirement was met.

**Root cause:** Age-requirement tech IDs were shifted by an off-by-one when the tech
chain was cloned for the custom civ slot.

**Fix:** Corrected the required-tech pointer in `civ_appender.py` so the upgrade chain
fires in the proper age.

**Commit:** `1a34d69` (2026-06-29)

---

## 2026-06-29 — UT catalog / UU name override / UT string bleed / multiplier scaling

**Symptom (several issues in one commit):**
- Castle/Imperial UT buttons sometimes showed the wrong tech name or description,
  bleeding vanilla campaign strings into the mod UI.
- UU name override (alias → display name) did not apply correctly in some codepaths.
- Multiplier scaling produced wrong deltas for certain bonus types.
- UT catalog lookup mapped KM bonus IDs to wrong vanilla tech slots.

**Root cause:** Multiple independent issues in the UT stub builder and bonus multiplier
path in `civ_appender.py`.

**Fix:** Corrected UT catalog ID mapping (`_KM_CASTLE_UT_TECHS` / `_KM_IMP_UT_TECHS`),
fixed UU name propagation, guarded string bleed by using dedicated safe pool SIDs,
and corrected the `d * N` accumulation logic for multiplied bonuses.

**Commit:** `e22bfc0` (2026-06-29)

---

## 2026-07-01 — Elite Organ Gun / Elite Caravel research buttons missing

**Symptom:** After building a Portuguese Empire custom civ, the Elite Organ Gun and
Elite Caravel upgrade buttons did not appear in the Castle / Dock.

**Root cause:** Step-0 nullification (which wipes `research_locations[0].location_id`
on existing civ-specific techs to prevent ghost buttons) ran *before*
`_allocate_tech` deep-copied the template techs 563 and 597. The clones inherited
`location_id = -1` with `research_time > 0`, making the button invisible.

**Fix:** Added `_restore_elite_upgrade_location()` in `civ_appender.py`. After each
elite-upgrade tech is cloned, it reads the base unit's own `train_locations[0].unit_id`
to recover the correct building (Castle = 82, Dock = 45) and restores the location.

**Commit:** `4943c6a` (2026-07-01)

---

## 2026-07-01 — Imperial UT hover shows "Click to play as the Burmese"

**Symptom:** The Imperial Unique Technology research button tooltip in the Castle showed
"Click to play as the Burmese" instead of the intended UT description.

**Root cause:** UT name SIDs were allocated from the 70000-range pool
(`UT_POOL_OFFSET = 126`). The Castle button hover reads from `language_dll_name + 21000`;
for the Portuguese Empire slot this produced SID 91300, which AoE2 DE's language DLL
hard-codes as the Burmese civ-picker string. Mod key-value files cannot override
language DLL strings.

**Fix:** Moved `UT_POOL_OFFSET` to 335 (first index in the 44000-range block of
`CAMPAIGN_STRING_POOL`). Hover SIDs now land at 65000–65434, which are empty vanilla
slots that mod overrides can safely fill.

**Commit:** `4943c6a` (2026-07-01)

---

## 2026-07-01 — Castle UT button shows no effect description

**Symptom:** The Castle Unique Technology research button displayed only the tech name
and cost (e.g. "Carrack (Cost: 300f, 300g)") with no effect description.

**Root cause:** `lang_desc` in the UT tech was set to `name_sid` (the tech name SID),
same as `lang_name`, so the description field carried no additional information.

**Fix:** Changed `lang_desc = name_sid + DLL_CREATION_OFFSET` (i.e. `name_sid + 1000`).
`build_all.py` now writes `"TechName (effect)"` (e.g. `"Carrack (Ships +1/+1 armor)"`)
to that SID, giving the Castle button a proper effect description line. Safe because the
44000-range name SIDs put `+1000` at 45000-range — empty in vanilla.

**Commit:** `4943c6a` (2026-07-01)

---

## 2026-07-01 — Carrack ×2 gave Elite Caravel 0 melee armor

**Symptom:** A Portuguese Empire civ with Carrack configured as a ×2 Castle UT gave
the Elite Caravel 0 melee armor instead of +2/+2.

**Root cause:** EC_ADD with `c = 8` (armor attribute) uses packed `d` values where
`d = (armor_class_id << 8) | amount`. The multiplier scaling in
`_scale_ec_for_multiplier` and `_multiply_effect` treated `d` as a plain float and
multiplied the whole value (e.g. `769 × 2 = 1538`). This corrupted the armor class
ID (class 3 → class 6), targeting an armor class that ships do not have, so the
add had no effect.

**Fix:** For `EC_ADD` with `c == 8`, both functions now unpack the class ID and amount,
scale only the amount byte, and repack: `d = (class_id << 8) | (amount × multiplier)`.
Result: `769 × 2 → 770` (class 3, +2 melee) and `1025 × 2 → 1026` (class 4, +2 pierce).

**Commit:** `4943c6a` (2026-07-01)

---

## 2026-07-03 — Team bonus label shows wrong text in diagnostic and in-game description

**Symptom:** A civ with team bonus 33 (conversion resistance) showed "Scout Cavalry,
Light Cavalry, Hussar +1 pierce armor" in both the `diagnose_civ.py` output and the
in-game civilization picker description. The actual mod effect (conversion resistance)
was applied correctly; only the display text was wrong.

**Root cause:** Two separate issues:
1. `team_bonus_names.json` had entries shuffled from index 11 onward vs. KM's
   authoritative `card_descriptions[4]` ordering in `common.js`. Index 33 was
   "Trade units yield 10% food" instead of "Units resist conversion."
2. `diagnose_civ.py`, `build_all.py`, and `app.py` all looked up team bonus labels
   from `bonus_names.json` (the *civ* bonus catalog) instead of `team_bonus_names.json`.
   `bonus_names.json["33"]` = the Scout Cavalry pierce armor string.

**Fix:** Rewrote `team_bonus_names.json` with the correct KM ordering for indices 0–79.
Added `_TEAM_BONUS_NAMES` dict and `_team_bonus_label()` in `diagnose_civ.py`.
Added `_TEAM_BONUS_NAMES` dict in `build_all.py` (exported) and imported + used it in
`app.py` for team bonus description generation.

**Commit:** (2026-07-03)

---

## 2026-07-07 — Custom flag icon missing from in-game civ picker and in-game interface

**Symptom:** A civ with a custom flag showed the default AoE2 flag icon in both the
civilization picker menu and the in-game interface, even though the widgetui folder
was present.

**Root cause:** `_build_ui_zip` in `build_civ.py` wrote the flag PNG to
`widgetui/textures/ingame/icons/civ_techtree_buttons/` (tech-tree button) but not to
`widgetui/textures/menu/civs/` (the civ picker / in-game flag slot).

**Fix:** Added the missing `widgetui/textures/menu/civs/{fn}.png` write after the
per-variant icon loop in `_build_ui_zip`. Also added warning logs to `_decode_flag`
for silent Pillow/JPEG failures.

**Commit:** (2026-07-07)

---

## 2026-07-07 — Bonus #283 broke Bombard Cannons, Bombard Towers, and Cannon Galleons

**Symptom:** A civ with bonus #283 (Chemistry and Hand Cannoneer available in Castle
Age) could not train Bombard Cannons even in Imperial Age. Houfnice upgrade was also
missing because it depends on Bombard Cannon being researchable first.

**Root cause:** The original bonus #283 handler cloned Chemistry (tech 47) as a
civ-specific Castle-Age version, then disabled the original tech 47 via a `type=102`
command in the TT effect. Techs 188 (Bombard Cannon), 64 (Bombard Tower), and 37
(Cannon Galleon) all have tech 47 in their `required_techs` — with 47 disabled, their
prerequisite was never satisfied and they never fired.

**Fix:** Replaced the handler entirely. The correct mechanism mirrors how Bohemians
actually work in the DAT: Chemistry (47) already has `required_techs=[103, 800],
count=1` (OR-logic). Tech 800 is a Bohemian-owned auto-fire that triggers at Castle
Age, satisfying Chemistry's OR-prereq without disabling 47. We clone techs 800 and
801 for the custom civ and add the 800-clone ID to Chemistry's free OR-prereq slot so
Chemistry unlocks at Castle Age for that civ only. Chemistry 47 is never disabled.

**Commit:** (2026-07-07)

---

## 2026-07-07 — Bonus #283 Chemistry still locked behind Imperial Age after handler rewrite

**Symptom:** After the handler rewrite above, Chemistry was still only researchable in
Imperial Age.

**Root cause:** The new handler called `_allocate_tech(dat, 800, ...)` to clone tech
800 but discarded the return value. The clone's new ID was never written into Chemistry
(47)'s `required_techs` list. The engine checks prereqs by exact tech ID — tech 800
was in Chemistry's list, but our clone (e.g. ID 1200) was not, so the clone's firing
never satisfied Chemistry's prereq for non-Bohemian civs.

**Fix:** Captured `new_800_id` from `_allocate_tech` and slotted it into the first
free `−1` entry in Chemistry's `required_techs` list. `required_tech_count` stays 1
(OR-logic already set); any of `[103, 800, new_800_id]` now satisfies it. Other civs
are unaffected because `new_800_id` is civ-specific and never fires for them.

**Commit:** (2026-07-07)

---

## 2026-07-03 — Bonus 35 (Infantry +20% HP) fires empty Castle/Imperial techs

**Symptom:** `diagnose_civ.py` reported bonus 35 allocating three techs (Feudal,
Castle, Imperial) but the Castle and Imperial copies had 0 commands and did nothing.

**Root cause:** `bonus_catalog_raw.json["civ"]["35"]` listed three Burmese tech IDs
`[416, 415, 391]`. Techs 415 and 391 are dead stubs in the Burmese tech tree with
`effect_id = -1` — they produce no effect when cloned. Only tech 416 (Feudal Age) has
a valid effect (effect 428: multiply infantry class HP by ×1.2).

**Fix:** Trimmed the catalog entry to `[416]`. The bonus is a flat one-time Feudal buff
("Infantry +20% HP starting in the Feudal Age"), not a per-age cumulative stack, so
the Castle and Imperial stubs were never supposed to do anything.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 280 (Folwark) allocates 7 extra empty/wrong techs

**Symptom:** `diagnose_civ.py` reported bonus 280 allocating 11 techs total; the first
4 worked correctly (techs 1532–1535, matching the Poles' Folwark chain) but 6 additional
copies (1536–1541) had 0 commands. A 7th extra slot matched tech 797 (Flemish Militia
Age4, Burgundians global tech) which was silently skipped as global.

**Root cause:** `bonus_catalog_raw.json["civ"]["280"]` listed
`[793, 794, 795, 796, 797, 798, 799, 818, 819, 820, 821]`. The first four (793–796) are
the correct Poles Folwark techs (Enable Folwark + 3 age upgrades). The remaining seven
were a mix of a Burgundians global tech (797) and blank "New Research" slots (798–821)
— likely effect IDs that were confused for tech IDs when the catalog was originally built.

**Fix:** Trimmed the catalog entry to `[793, 794, 795, 796]`. The Folwark chain
(Dark Age enable → Feudal/Castle/Imperial upgrades) is fully described by these four
Poles techs; no additional entries are needed.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Team bonus 30 (Military buildings +5 pop room) never applied

**Symptom:** Any civ with team bonus 30 ("Military buildings provide +5 population room")
reported N-1/N entries applied in `diagnose_civ.py`. The bonus was silently skipped.

**Root cause:** `bonus_catalog_raw.json["team"]["30"]` pointed to effect index 9
("Slavs Team Bonus"), which has 0 commands in the current DE DAT. This was the old
Slavs team bonus slot — it was emptied when AoE2 DE changed the Slavs team bonus to
"Farmers work 15% faster." Because the effect has no commands, `civ_appender.py`
skips it (`if not safe_cmds: continue`), so the bonus is never written to the mod.

**Fix:** Changed the catalog entry from `9` to `758` (effect "Slavic team bonus"),
which is the current live implementation: type=10 / C=21 / D=5.0 commands applied to
all age variants of Barracks, Archery Range, Stable, and Siege Workshop.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 300 (Camel Scouts in Feudal Age) produced 0-command tech

**Symptom:** Any civ with bonus 300 ("Can recruit Camel Scouts in Feudal Age") showed
a `→ 0 cmds` warning in `diagnose_civ.py`. Camel Scouts were not trainable.

**Root cause:** `bonus_catalog_raw.json["civ"]["300"]` listed `[235, 860, 858]`, derived
from the Gurjaras' implementation. Tech 235 ('Make Camels Available') is civ=-1 (global,
never cloned), tech 860 ('Upgrade Camel Scouts to Riders') is also global, and tech 858
('Camel Scout make avail', Gurjaras civ=42) has `effect_id=-1` — a dead stub that only
serves as a gate for tech 235 in the Gurjaras chain. None of these actually enable the
unit for a non-Gurjaras custom civ. Tech 235 is also globally disabled via "Disable
Regionals" (effect 79, type=102) and would need a type=8 opt-in in the TT anyway.

**Fix:** Removed the `civ` catalog entries and added bonus 300 to `ec_list` with a
single EC_ENABLE command (`type=2 A=1755 B=1 C=-1 D=0`) at `requires=[101]` (Feudal
Age). This creates a civ-specific auto-fire tech that directly enables unit 1755 (Camel
Scout) in Feudal Age. The global tech 860 (which upgrades Camel Scouts → Camel Riders
at Castle Age) continues to fire for all civs as a no-op for civs without Camel Scouts.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 55 (Stable units +1P armor Castle/Imperial) half-fired with 0 cmds

**Symptom:** `diagnose_civ.py` reported one of the two techs for bonus 55 as
`unit0 instant req:[0,0,0,0,0,0] → 0 cmds` and the other (Imperial Age) as
`auto-fire req:[103] → 1 cmds`. Castle Age armor was silently missing.

**Root cause:** `bonus_catalog_raw.json["civ"]["55"]` listed `[338, 552]`. Tech 338 is
a blank "New Research" placeholder (civ=0, eff=0, blank requirements) that cloned into
a useless 0-command tech. Tech 552 is the Persians' "Caravanserai (make avail)" tech
(EC_ENABLE unit 1754 at Imperial Age) — entirely unrelated to cavalry pierce armor.
Neither tech was correct; there is no single vanilla tech that adds pierce armor only
to stable units at Castle/Imperial age.

**Fix:** Cleared the `civ` catalog entry and added bonus 55 to `ec_list` with two
entries — `requires:[102]` and `requires:[103]` — each applying
`EC_ADD A=-1 B=12 C=8 D=1025.0` (cavalry class +1 pierce) and
`EC_ADD A=-1 B=47 C=8 D=1025.0` (light cavalry class +1 pierce). Unit classes 12
and 47 cover the full stable roster (knights, camels, scouts, elephants, steppe lancers).

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 26 (TC/Dock work rate) allocated empty trailing tech

**Symptom:** `diagnose_civ.py` reported one of the two bonus 26 techs as `unit0 instant req:[0,0,0,0,0,0] → 0 cmds`.

**Root cause:** `bonus_catalog_raw.json["civ"]["26"]` listed `[409, 412]`. Tech 409 is the correct Persian "C-Bonus, TC and Dock work rate" tech (civ=8, 8 commands covering TC×4 age variants and Dock×4 age variants in one Dark Age auto-fire tech). Tech 412 is a blank "New Research" placeholder (civ=0, eff=0) that clones into a 0-command instant tech.

**Fix:** Trimmed the catalog entry to `[409]`. The single Persian tech covers the full per-age progression for both building types.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 105 (Eco upgrades -33% food) produced 10 empty techs

**Symptom:** `diagnose_civ.py` reported all 10 bonus 105 techs as `auto-fire → 0 cmds`.

**Root cause:** `bonus_catalog_raw.json["civ"]["105"]` listed `[758–767]` — all ten Burgundian "requirement" gate techs (e.g., 'Feudal eco tech requirement', 'Heavy Plow requirement'). These are internal prerequisite stubs with `effect_id=-1`; they never produce any commands when cloned. The actual Burgundians food discount logic lives in their TT effect (effect 782) as direct `EC_TECH_COST type=101 C=2 D=0.6` commands — not in any auto-fire tech.

**Fix:** Cleared the `civ` catalog entry to `[]` and added bonus 105 to `ec_list` with `requires=[]` (fires at game start) applying `EC_TECH_COST type=101 B=0 C=2 D=0.667` (×0.667 ≈ −33% food) to all 16 standard eco upgrade tech IDs: Horse Collar(12), Heavy Plow(13), Crop Rotation(14 — wait, corrected below), Guilds(15), Caravan(48), Gold Mining(55), Gillnets(65), Gold Shaft Mining(182), Double-Bit Axe(202), Bow Saw(203), Wheelbarrow(213), Two-Man Saw(221), Hand Cart(249), Stone Mining(278), Stone Shaft Mining(279), Fishing Lines(906). This matches the Burgundians' own TT discount list.

**Limitation:** The "available one age earlier" portion of this bonus is not implemented. That mechanic requires modifying global tech `required_techs` arrays (e.g., removing the Castle Age prerequisite from Heavy Plow for this civ), which cannot be done via EC commands and would need a dedicated handler in `civ_appender.py`.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonus 318 (Start with Mule Cart) allocated one empty tech

**Symptom:** `diagnose_civ.py` reported one of the two bonus 318 techs as `unit0 instant req:[0,0,0,0,0,0] → 0 cmds`.

**Root cause:** `bonus_catalog_raw.json["civ"]["318"]` listed `[229, 925]`. Tech 229 is a blank "New Research" placeholder (civ=0, eff=0) — produces a 0-command instant tech. Tech 925 (civ=45/Georgians, eff=937, 2 cmds: EC_RESOURCE + type=7 spawn unit) was already working correctly.

**Fix:** Trimmed entry to `[925]`. The Mule Cart spawn tech fires at game start (auto-satisfies global prereqs 639 and 307). Whether the type=7 "spawn unit" command successfully creates a Mule Cart in-game requires in-game verification.

**Commit:** (2026-07-03)

---

## 2026-07-03 — Bonuses 81/283/352 unsupported gate-stub mechanism; catalog cleared

**Symptom:** `diagnose_civ.py` reported dead-stub techs (0 cmds) for:
- **81** (No buildings required to age up) — tech 638, Khmer, eff=-1
- **283** (Chemistry + Hand Cannoneer in Castle Age) — techs 800 and 801, Bohemians, eff=-1
- **352** (Siege Engineers in Castle Age) — tech 978, Jurchens, eff=-1

**Root cause:** These bonuses use AoE2's "gate-stub" mechanism: the civ's gate tech has `eff=-1` (no commands) and fires automatically, satisfying one slot in a global tech's `required_techs` array (`required_tech_count=1`). For example, global Siege Engineers (tech 377) has `required_techs=[103, 978]` with `required_tech_count=1` — normally needs Imperial Age (103), but fires in Castle Age for Jurchens because their gate tech 978 satisfies the count early. When cloned, the gate tech gets a **new ID** the global tech doesn't reference, so it never satisfies the requirement.

**Fix:** Cleared all three catalog entries to `[]`. These bonuses are now silently skipped ("not in any catalog"). They require a custom handler in `civ_appender.py` to implement: either modifying global tech `required_techs` at build time or creating civ-specific clones of the gated global techs with different age requirements.

**Commit:** (2026-07-03)

---

## 2026-07-03 — [282] Winged Hussar: diagnostic false positive NO-BUTTON(time=1s)

**Symptom:** `diagnose_civ.py` flags bonus 282 tech 1774 with `⚠ NO-BUTTON(time=1s) → 3 cmds`.

**Root cause:** Source tech 791 (Poles, civ=38) has `research_locations[0] = (-1, 1)` — location=-1 (auto-fire, no button) but research_time=1. This is intentional vanilla Poles behavior: after entering Imperial Age, a 1-second delay fires the tech that sets Winged Hussar upgrade costs to 0. The diagnostic warns about any `location=-1 with time>0` as a potential misconfiguration, but this pattern is deliberate.

**Not a bug.** Both bonus 282 techs fire correctly — tech 1773 (2 cmds: disable Hussar, unlock Winged Hussar) and tech 1774 (3 cmds: set WH food/gold/time to 0) apply as expected.

---

<!-- 
  Template for new entries:

## 2026-07-03 — Vanilla UU Castle train-button hover shows wrong unit name

**Symptom:** A civ using a vanilla UU (e.g. Teutonic Knight) replacing a civ slot whose original UU had a different name (e.g. Ethiopians / Shotel Warrior) showed the replaced civ's unit name and description in the Castle train-button hover tooltip.

**Root cause:** `build_all.py` writes the UU display name to `dll_name + 10000` (tech tree) and `dll_name + DLL_HELP_OFFSET` (+100000) for vanilla UUs, but not to `dll_name + 21000` — the slot the Castle train-button hover reads from. KM-custom UUs had this covered via `ext_sid` in the `extra_unit_strings` path. For vanilla UUs the `+21000` slot was left unwritten, so the game fell back to whatever vanilla campaign/scenario string existed at that SID, which for the Ethiopians slot happened to be "Shotel Warrior (fragile infantry, high attack)".

**Fix:** Added `dll_name + 21000` write for both the normal and elite vanilla UU in the string block in `build_all.py`.

**Commit:** (2026-07-03)

---

<!-- 
## YYYY-MM-DD — Short description

**Symptom:** What the user saw / what broke in-game.

**Root cause:** What the code was actually doing wrong.

**Fix:** What was changed and why it works now.

**Commit:** `<hash>` (YYYY-MM-DD)

-->
