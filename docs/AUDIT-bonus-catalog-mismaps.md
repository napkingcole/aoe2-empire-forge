# Bonus catalog mismap sweep — 2026-09-09

Audit of all **350 visible civ bonuses**: for each one, the card text was compared against the
actual EffectCommands its catalog techs / `ec_list` entries fire in the shipped DAT.

Method: `dump_bonuses.py` resolved every mapped tech to its effect, decoded each command with
real unit / attribute / class / resource names, and printed it next to the card. Attribute and
class ids came from `~/Sites/aoe2/AoE2DE_UGC_Guide-main` (object-class constants are offset by
900). Suspicious cases were then confirmed against the DAT directly and against KM's
`civbuilder.cpp`.

## Status

**Round 1 landed 2026-09-10** — all six Tier 1 items and five Tier 2 items.
**Round 2 landed 2026-09-13** — the remaining five Tier 2 items, closing Tiers 1 and 2 entirely.

Both rounds were triaged by the user against current DE behaviour, and that mattered: a large
share turned out to be bonuses the game itself has since changed, where the right fix was to
retarget the card rather than implement the old wording. Items are marked **FIXED** below with
what was actually done. `tests/test_audit_fixes.py` builds one civ carrying all eleven changed
bonuses and asserts each command reaches the built DAT — "the catalog says so" is exactly the
assertion that would have passed while bonus 357 did nothing.

Everything not marked FIXED is still a proposal awaiting triage; see **Still open** at the end.

---

## Tier 1 — the bonus does nothing, or does something it shouldn't

The bonus-54 class: silent no-ops and mismaps.

### 1. Bonus 357 — "Shepherds and Herders generate +10% additional food" is completely inert — **FIXED**
Maps to tech **1003 `RESERVED`**: `civ=-1`, `effect_id=-1`, no required techs, and no tech in the
DAT references it. KM's line is `civBonuses[CIV_BONUS_357_...] = {TECH_RESERVED_20}` and he never
populates that slot either. This bonus has never done anything.

**Fix:** DE removed this Khitan bonus, so there is no vanilla tech left to copy. Implemented as an
`ec_list` `cMulResource` (type 6) on resource **216 (livestock food), d=1.1** — each animal yields
10% more food. That is the same lever bonus 94 uses to make livestock last longer, minus 94's
compensating work-rate cut. Deliberately *not* a carry-capacity bump: that would be a gathering-
speed buff the card does not claim.

### 2. Bonus 306 — the Ballistics half is inert, and the gold discount is -50% not -60% — **FIXED**
Card: "Scorpions cost -60% gold and benefit from Ballistics research."
- Tech 892 does `GoldCost ×0.5` on SCBAL 279 / HWBAL 542 → **-50%**, not -60%.
- Tech **893 `RESERVED`** (`effect_id=-1`) was meant to carry the Ballistics half. Nothing.

Compare bonus 227, which implements "benefit from Ballistics" properly by setting
`EnableSmartProjectile=1` on the projectile unit.

**Fix:** DE gave Ballistics to every civ's Scorpions, so that half of the card is now redundant
rather than missing. Dropped tech 893 and retitled the bonus to what tech 892 actually does:
**"Scorpions cost -50% gold"**.

### 3. Bonus 108 — the farm bonus also unlocks the Flemish Militia — **FIXED**
Card: "+125% Farm Upgrade Food Bonus." Mapping is `[772, 773, 774, 815, 816, 817]`:
- 772 — correct (`TYPE6 a=69 d=2.25`, farm food).
- **773 `Flemish Militia (make avail)`** — `ENABLE 1699 show`, gated on tech 101 (Feudal). Any civ
  taking the farm bonus silently gets Flemish Militia from the Feudal Age.
- **774 `Flemish Militia Age3`** — +15 HP / +3 attack to the three Flemish Pikeman units.
- 815/816/817 — `New Research`, `civ=0`, `effect_id=0` which holds **zero commands**. Harmless
  filler, but they get deepcopied into every civ that takes this bonus.

Only bonus 108 references any of these. KM's line is identical (`civbuilder.cpp:250`), so this is
inherited, not ours.

**Fix:** trimmed the mapping to `[772]`. That alone is the whole current Sicilian bonus, so the
card needed no change.

### 4. Bonus 342 — "available one age earlier" is unimplemented; the discount is 100% not 75% — **FIXED**
Techs **1077 and 1078** (KM's `TECH_CAREENING_REQUIREMENT` / `TECH_DRY_DOCK_REQUIREMENT`) are
unnamed, `civ=-1`, `effect_id=-1`, no prerequisites, referenced by nothing. Tech 1079 sets
Careening and Dry Dock cost **and** time to `0.0` (`mode=set`), i.e. free and instant — the card
says "-75%".

**Fix:** the naval rework removed the early-availability half. Dropped 1077/1078 and retitled to
**"Careening and Dry Dock are free"**, which is what tech 1079 does. Also flagged
`"multiplier": false` — there is nothing left to scale once a cost is already zero (bonus 365 has
the same shape and got the same flag).

### 5. Bonus 76 — the Feudal row of the card never fires — **FIXED**
Card is a progression with two rows (`dark +5%`, `feudal +10%`), but the mapping has exactly one
tech (584, villagers `MovementSpeed ×1.05`). There is no Feudal tech.

**Fix:** there is — KM's list just omits it. Tech **600 `C-Bonus, Villagers 10% faster`** (civ 27,
requires 101 Feudal, `×1.047619`) exists in the DAT and compounds with 584 to exactly +10%.
Mapping is now `[584, 600]`.

### 6. Bonus 360 — "available in Castle Age" is unimplemented — **FIXED**
Tech 1004 is named `C-Bonus, Early + Cheaper HCA` but its **effect** is named `C-Bonus, Cheaper
HCA` and contains only two `EC_TECH_COST … MULT 0.5` commands. Nothing changes when Heavy Cavalry
Archer becomes available.

**Fix:** the age change is not in the effect because it is in the *prerequisites*. Tech 218 wants
**2 of `[103 Imperial, 192 Cav Archer (Castle), 1004 Khitan trigger]`** — so a civ holding 1004
reaches the threshold with 192 alone, in the Castle Age. This is CLAUDE.md quirk 9 again:
`_allocate_tech` copies the civ-gated 1004 to a new id and tech 218 still names the original.
Added bonus 360 to `_ALT_PREREQ_BONUSES` (generalised from the Winged Hussar special case) so the
copy is written into a spare `required_techs` slot. No catalog change.

---

## Tier 2 — the card claims more than the effect delivers

### 7. Bonus 16 — fishing ships never get the "+2P armor" — **FIXED**
The four mapped techs (306, 422, 423, 424) contain only HP and work-rate commands. Confirmed two
ways: no effect in the DAT adds class-21 armor except Careening / Dry Dock / Carrack / Hypozomata,
and `civs[5].units[13]` (Japanese fishing ship) has armor identical to Britons.

**Fix:** DE replaced the armor with +100% HP — which tech 306 already grants (`class 21 HP ×2`).
So the implementation was right and the wording was stale. Dropped "+2P armor" from the name and
gave the card real text (it was one of the ten blank cards).

### 8. Bonus 7 — "Villagers +5 attack vs. wild boar" is unimplemented — **FIXED**
Tech 402 has carry capacity, hunt food, and a compensating work-rate command — no attack command.
No per-civ unit-data difference either (`civs[3]` villager and hunter attacks == `civs[1]`), and
the only villager attack effect in the DAT is 528 "+2 vs Animals" (bonus 62's wolf bonus).

**Fix:** DE removed the boar attack from the Goths; the carry capacity and hunt food persist.
Dropped the clause from the name and card, and re-pointed the card at "Hunters".

### 9. Bonus 140 — only 1 of 3 claims is implemented — **FIXED**
Card lines: "Wonders cost no wood" / "+50 population capacity" / "Maximum 1 Wonder".
`ec_list` contains only the `+50 AmountFirstStorage` on the seven WNDR units.

**Fix:** added `EC_SET attr 104 = 0` on all seven Wonder ids (they cost 1000W/1000G/1000S, all
three slots spendable). "Maximum 1 Wonder" turns out to be the engine's **default** behaviour, so
it needed no command — the line came off the card instead, since as written it reads like a
restriction the bonus imposes. Worth knowing for anything similar: the only one-at-a-time
mechanism in the DAT is the hero pair (attrs 126/127), and it is used on exactly three units —
Cao Cao, Liu Bei, Sun Jian — and never on a building.

### 10. Bonus 312 — "economic drop-off buildings cost -25%" is just the Mule Cart — **FIXED**
Tech 958 discounts unit **1808 MULECART** alone. Mills, Lumber Camps and Mining Camps are
untouched. (The "wood and mining upgrades 40% more effective" half is fully implemented, techs
960-966.)

**Fix:** `_apply_dropoff_discount` in civ_appender emits `MULT attr 100 ×0.75` on **18 building
ids** — Mill, Lumber Camp and Mining Camp (four each, one per age), Folwark (three) and Settlement
(three). Each age needs its own id: all four Mills share `language_dll_name` 5157 and differ only
in `standing_graphic`, with just the Dark Age one shipping `enabled=1`, so missing one leaves that
age at full price.

This one could not be an `ec_list` entry: **the bonus dispatch is exclusive** — a bonus with a
tech list `continue`s before `ec_list` is ever read, and 312 maps eight techs. So it runs as a
supplement after the tech branch, the same shape bonus 105 uses after its ec_list.

### 11. Bonus 302 — Galleon is missing, so the bonus disappears on upgrade — **FIXED**
Card says "Navy". The effect covers GALLY 21, WARGA 442, DROMON 1795 — **not SGALY 539
(Galleon)**. A civ takes the bonus and loses it the moment it reaches Imperial.

**Fix:** 539 is the standard Galleon (the line is GALLY 21 → WARGA 442 → SGALY 539). Added
`+2 melee / +2 pierce` (`1026` / `770`), matching War Galley and Dromon rather than inventing a
third tier — the existing pattern is base ship +1, upgraded ship +2.

### 12. Bonus 213 — same shape: base Mangonel only — **WON'T FIX**
`ADD 280:MANGO attr 9 += 4708` (class 18, +100). Onager 550 and Siege Onager 588 are absent, so
"Mangonels can cut trees" stops being true after the first upgrade.

**Won't fix:** Onagers and Siege Onagers already cut trees in the base game, so the omission is
correct — the bonus exists to extend the ability down to the Mangonel.

### 13. Bonus 191 — "Explosive units 2× HP" is Petards only — **FIXED**
`MULT class 35:Petard HP ×2`. Demolition ships — the card's own icon — get nothing. Contrast
bonus 274 ("increased blast radius"), which does list RMSHP/CRMSH/SDGAL explicitly.

**Less broken than it looked:** class 35 holds Petard (440), Flaming Camel (1263) and Saboteur
(706), so three explosive units were already covered. **706 is the campaign-only Saboteur** —
`language_dll_name` 5588, `enabled=0` in all 45 civs, train location `-1`, so nothing can build
it; it rides along harmlessly.

**Fix:** demolition ships are class **22 (Warship)**, the same class as Galleys, so they can never
be swept in by class — added 527 / 528 / 1104 by id, plus the Grenadier (1911, class 44).

### 14. Bonus 241 — "All units heal at a faster rate" is really garrison healing — **FIXED**
The effect doubles attr **108 GarrisonHealRate** on class 52 Towers and class 3 Buildings. It has
nothing to do with Monks (the card's icon) or with units healing in the field.

**Fix:** wording only — the effect is what it should be. Now "Garrisoned units heal at a faster
rate", with the card reading "2× Healing / Units garrisoned in buildings and towers heal twice as
fast".

### 15. Bonus 368 — "Foragers work 25% faster" changes food and carry, not work rate — **FIXED (wording only)**
`TYPE6 a=296 d=1.25` (bush food) plus `CarryCapacity ×1.25` on VMFOR/VFFOR. Attribute 13 is never
touched. Compare bonus 5, which is a genuine work-rate bonus.

**Not a defect — the card was describing it wrong.** This is the **Mapuche** bonus, whose official
text is *"Foragers drop off +25% food"*, and that is exactly what tech 1381 implements. It is
structurally identical to tech 594, bonus 75, *"Villagers drop off 10% more gold"*:

```
tech 594  (bonus 75)              tech 1381  (bonus 368)
  cMulResource  47 gold   ×1.1      cMulResource  296 berries ×1.25
  MULT 579 VMGLD  carry   ×1.1      MULT 120 VMFOR   carry    ×1.25
  MULT 581 VFGLD  carry   ×1.1      MULT 354 VFFOR   carry    ×1.25
  MULT 2333/2334  carry   ×1.1
```

So **`cMulResource` on the resource pool + carry capacity on both gender variants is this
codebase's idiom for "drop off N% more"** — the bush holds 25% more and each trip delivers 25%
more, rather than the gather rate changing. Card and name now use the official wording; no
mechanism change. Foragers have no DLC duplicate ids (120/354 is the complete set, unlike gold
mining's 579/2333 + 581/2334), so tech 1381 is complete.

**It is also not the Franks bonus**, as first assumed — tech 1381 is `civ=58`, the Settlement civ
(which also owns 369, 370 "Mapuche Vision", 371 and 377). The Franks' forager bonus is **bonus 5**
— tech 524, `civ=2`, `work rate ×1.15`, already at its patched 15% with only the card stale at
10%. That card is now fixed too (see Tier 3). The two are mechanically distinct and both kept.

### 16. Bonus 52 — vanilla quirk worth knowing about — **FIXED**
Tech 500 "Gunpowder units cost -20%" applies `ResourceCost ×0.8` to five units, then applies
**`Hitpoints ×1.25`** to RCKTCRT, HRCKTCRT, FLNCER, EFLNCER and GRNADR. That is what the shipped
DAT does (it is the Portuguese bonus), so matching vanilla arguably means leaving it — but a civ
taking this card gets +25% HP on those five units and no discount.

**Fix:** deliberately diverged from vanilla. Moved off tech 500 into an `ec_list` of twelve
`MULT attr 100 ×0.8`: the five vanilla already discounted (Hand Cannoneer, Bombard Cannon, Cannon
Galleon + Elite, Houfnice) plus the ones it skipped (Organ Gun + Elite, Fire Lancer + Elite,
Rocket Cart + Heavy, Grenadier). Cannon Galleons were kept because vanilla already discounted them
and dropping them would be a regression; the Grenadier was added because every other gunpowder
card in the catalog (31, 126, 217, 275, 288) includes it.

---

## Tier 3 — the number on the card is not the number in the effect

| Bonus | Card says | Effect actually does |
|---|---|---|
| 5   | Foragers work **10%** faster | `×1.15` → **+15%** — **FIXED**, card now says 15% (this is the Franks bonus at its patched value) |
| 359 | train/upgrade **+25%** faster | `×0.869565` = 1/1.15 → **+15%** |
| 180 | Cav Archers train **33%** faster | `TrainTime ×0.8` → **+25%** |
| 340 | regen **10 / 20 / 30** HP/min | techs add 10, **5**, 15 → **10 / 15 / 30** |
| 346 | **+15%** / +30% HP | effect 1058 is `×1.2` → **+20%** / +30% |
| 339 | **+65** food per building | effect adds **+55** (the effect is even named "+55f") |
| 306 | **-60%** gold | `×0.5` → **-50%** — **FIXED**, card now says -50% |

---

## Tier 4 — cosmetic / wording

- **Bonus 10** — the card's `heading` is the literal placeholder string **`"test"`**.
- **Bonus 59 / 267** — "+10 Pop per House" and "+50 Population" state the *total*, not the delta.
  The effects add +5 and +30; base values are 5 (House) and 20 (Castle/Krepost), so the totals are
  right and only the "+" is wrong.
- **Bonus 208** — stat reads "Elephant units have +25% attack"; the effect is attack **speed**
  (`AttackReloadTime ×0.8`). The heading's `[reload]` icon is right, the sentence isn't.
- **Bonus 376** — card text leaks an implementation note to players: "…+10 population space
  **(team effect via type=10)**".
- **Bonus 371** — "training speed improves per age" omits that Feudal multiplies train time by
  **2.15** first; Castle (×0.75) and Imperial (×0.62) only claw it back to roughly parity.
- **Ten visible cards carry no explanatory text at all** (no heading, stat, prog_label, lines or
  ages — just an icon and a label): **12, 16, 18, 27, 28, 61, 297, 338, 344, 349**.

---

## Checked and ruled out — do not "fix" these

- **Bonus 366** "Monks regain faith 50% faster" — `MULT class 18, attr 10, d=2.0` looks inverted,
  but vanilla **Illumination** (tech 233 → effect 219) is `MULT class 18, attr 10, d=1.875` on the
  same attribute. For Monks a *higher* attr-10 value means faster faith recovery. Correct as-is.
- **Bonus 322** Flaming Camel — effect 740 is `type=2, a=1263, b=-1`. `b=-1` is a third state of
  EC_ENABLE, not "hide" (DAT-wide: `b=1` ×156, `b=0` ×21, `b=-1` ×26). Fine.
- **Bonuses 104, 284, 296** — the giant `MULT … attr 9 … d=7037` blocks are correct: for attack,
  `d` encodes `class×256 + percent` (7037 = 27×256 + 125 = "class 27, ×1.25").
- **Bonus 70** "Foot archers fire 18% faster" — `reload ×0.85` = 17.6% more shots/sec ≈ 18%.
  Correct despite the tech being named "15%".
- **Bonuses 111, 113-119, 147-170** — no name and no card, but they are absent from
  `bonus_names.json`, so `/api/builder/bonuses/catalog` never offers them. They still build for
  legacy KM civs that reference them, which is the intent.
- **Coverage** — every one of the 350 visible bonuses has a catalog tech list, an `ec_list`, or an
  entry in `HANDLED_BONUS_IDS`. There are no fully dead cards.
- **`[SCEN]` / `[UNUSED` techs** — already swept on 2026-09-09; bonus 54 was the only one.

---

## Still open

All of Tier 1 and Tier 2 are resolved. Remaining: **Tier 3** items 359, 180, 340, 346 and 339, and
all of **Tier 4** — including bonus 10's literal `"test"` heading and the nine blank cards (12, 18,
27, 28, 61, 297, 338, 344, 349).

## Reproducing

```
./venv/bin/python scripts/dump_bonuses.py /tmp/bonus_audit.txt
```

Regenerates the full ~5,200-line dump in ~20 s (essentially all of it `load_dat`). Re-run after a
game patch — a DE update that renumbers a tech or empties an effect would show up here first.
