# Builder enhancements

**Status:** Track A complete and verified in-game; Tracks B–F proposed
**Written:** 2026-09-01, updated 2026-09-02, against `v2.0.0-beta.1.4` on `feature/ui-builder`
**Origin:** a survey of the bonus catalog against the DAT, the community threads,
and our own issue tracker — looking for gaps rather than bugs

---

## The shape of the opportunity

Three separate audits landed in the same place. The catalog is broad (358 civ
bonuses, 83 team bonuses) but a slice of it is mislabelled or inert; the schema
already reserves fields for features nobody wired up; and the engine exposes a
resource-attribute surface roughly five times wider than anything we address.

Meanwhile the recurring complaint about the tool we replaced is not that it
lacks bonuses — it is that *everything is a fixed pre-selection*. That is the
thread connecting Tracks B, C and D below: each one converts a fixed list into
something the player composes.

The community has also already specified the two features we do not have and
they most want: a point budget with category caps
([forum thread 107756](https://forums.ageofempires.com/t/custom-civilizations-builder-suggestion/107756),
[250-point mod](https://forums.ageofempires.com/t/250-point-custom-civ-data-mod/196644))
and per-civ flavour that Krakenmeister has publicly declined to build
(custom jingles, AI names —
[thread 274481](https://forums.ageofempires.com/t/aoe2-civbuilder-is-back/274481)).

---

## Track A — Catalog integrity

Cheapest track, already mostly done, and it gates Track D: you cannot price a
bonus in a point budget until you know it fires.

### Landed (uncommitted)

**13 placeholder-named bonuses labelled.** All were fully implemented; only the
label was missing, so they reached the picker as "Resource bonus" / "Unit bonus"
/ "BONUS_362". Decoded against the DAT, not the catalog. Two were nearly
misread:

- **230** targets only unit 142, which looks broken until you notice Town
  Centers have per-age variants (109 Dark / 71 Feudal / 141 Castle / **142
  Imperial**). Vanilla tech 409 uses the same four. Gated on Imperial and
  hitting the Imperial TC is correct.
- **214** uses attribute **100**, not 101. Attribute 100 is "first resource
  cost" and Siege Tower `cost[0]` is wood — a wood discount, not the train-time
  bonus 225 already provides.

**5 empty ids removed** (195, 258, 277, 278, 279). Zero references across 736
civ JSONs. Note these never reached the wizard: `app.py:1321` already filters
unsupported bonuses out of the picker. They only showed as noise on the
limitations page.

**3 inert bonuses fixed** — 132, 238, 240 wrote resources 198/199/200, which the
UGC guide documents as *Unused*. In 132 the three sit in exact positional
correspondence with vanilla tech 737's command order, so the remap was
unambiguous (→ 219 Fishing, 268 Hunting, 296 Foraging). In 238 and 240 the
existing work-rate compensation named the intent. Full write-up in
`llm/resource_ids.md`.

**Renaming alone did not surface them.** `static/data/bonus_cards.json` carries a
second, client-side visibility layer (`hidden: true`, applied in
`_parseBonusCard`) that the API knows nothing about. All 13 placeholders were
hidden there too — presumably because they had no usable label — so naming them
changed nothing a user could see. Cards are now authored for the 12 that
survived (245 stays hidden as deprecated), taking the picker from **330 to 341**
usable bonuses (+12 surfaced, −1 for hiding 402).

**Anything that hides a bonus must be checked in both places:** server-side via
`unsupported_bonuses()` / `DEPRECATED_BONUSES`, and client-side via the card
override. A bonus is only really visible when neither layer hides it.

**402 hidden, 362 promoted.** Inspecting a real build (`choppers.zip`) showed
bonus 402 emitting *no effect at all* — five techs were added and none was a
Dragon Ship upgrade, reproducing issue #28 exactly. 402 is now hidden with a
`_note` (kept valid so saved civs still load) and 362, which copies vanilla
tech 1010, takes its place in the picker pending an in-game test.

### Open

| Item | Test that settles it |
|---|---|
| ~~Every type-6 command passes `B = -1` where vanilla passes `B = 0`~~ | **Resolved 2026-09-01 — `B = -1` works, no change needed.** Bonus 235 on one villager and one tree yielded 199 wood instead of 100. All six "resources last longer" bonuses are sound. |
| ~~Bonus **362** duplicates **402** (Dragon Ships), and issue #28 says 402 does not work~~ | **Resolved 2026-09-02.** 362 worked in-game first try. 402 now maps to `[1010]` as well, its bespoke replica block in `civ_appender.py` is deleted, and it is deprecated → 362 so it still builds for civs that carry it without being offered twice. Verified by build: `tech 'Dragon Ship' civ=1 req=[103, 35]`, upgrades 529/1103/532 → 1302. **Closes #28.** |
| ~~Bonus **245** near-duplicates **364**~~ | **Resolved.** 245 deprecated in favour of 364, which also covers Champi Warriors. Hidden from the picker via `bonus_names.DEPRECATED_BONUSES`; implementation kept so KM civs in the wild that reference it still build. |
| ~~Bonuses 127 and 326 write resources 195 / 253~~ | **Accepted.** Both documented and correct (195 Construction Rate Mod — our 1.3 matches the Spanish value exactly; 253 Trade Stone Percent). Allowlisted in `tests/test_resource_ids.py`. 326 to be spot-checked in-game. |

### Guard against regression — landed

`tests/test_resource_ids.py` fails the suite if the catalog writes a resource id
that no vanilla effect writes. Dependency-free like the rest: it compares
against `llm/vanilla_resource_writes.json`, a 113-id snapshot regenerated by
`scripts/probe_resource_attrs.py` after a game update. 195 and 253 are
allowlisted with written reasons, and the test also fails if an allowlist entry
goes stale or unused. Verified by reintroducing the 198 write — it catches it.

### The "resources last longer" family — resolved, with a pricing caveat

All six of these bonuses pair a productivity multiplier with a compensating
work-rate **penalty**:

| Bonus | Productivity | Work-rate penalty |
|---|---|---|
| 132 Resources last 15% longer | 8 ids × 1.15 | 17 units × 0.87 |
| 235 Trees last 100% longer | 189 × 2.0 | 2 units × 0.5 |
| 236 Stone last 30% longer | 79 × 1.3 | 2 units × 0.769 |
| 237 Gold last 30% longer | 47 × 1.3 | 2 units × 0.769 |
| 238 Berries +35% food | 296 × 1.35 | 2 units × 0.741 |
| 240 Fish +35% food | 219 × 1.35 | 1 unit × 0.741 |

The worry was that if `B = -1` killed the type-6 multiplier the penalty would
still apply, making all six net downgrades. **Testing settled it: `B = -1` works.**
Bonus 235 yielded 199 wood from a 100-wood tree.

**But the compensation does not make them neutral, and Track D must not price
them as if it does.** The tested villager carried **32** — above any legal carry
capacity (base 10, Wheelbarrow 12, Hand Cart 19 and Imperial-only). Productivity
appears to inflate effective carry along with yield, so the gatherer makes
*fewer* trips for *more* resource. The work-rate penalty slows chopping but not
walking, so the net effect is positive and grows with distance from a drop-off.
These are stronger than their labels suggest.

The mechanism behind the carry inflation is not understood. Vanilla's Mapuche
forager bonus (tech 1381) pairs resource 296 with an explicit carry-capacity
multiplier on the same unit; ours carry no such command, yet the effect appears
anyway. Worth resolving before the composer (Track C) exposes these ids, since
a composer user picking "gather productivity" would be getting two effects.

---

## The empty-tree bug — fixed

Found while testing Track A. A saved civ carried
`tree: {units: [], buildings: [], techs: []}`, which is what the draft has
defaulted to since forever (`builder.js`), populated only when the user opens
the tree editor and picks a template. Skip Step 2 and the tree stays empty.

What made it hard to recognise is that the two layers disagree:

| Layer | With an empty tree |
|---|---|
| DAT tech tree effect | **33** disable commands — almost everything still trainable |
| Per-civ layout JSON | **166 of 170** nodes marked `NotAvailable` |

So in-game the tech tree screen reads as completely blank while the units are
still buildable — which is why a wood-gathering test on such a civ passed
normally, lumber camp and all. The only live nodes were the UU line and the two
UTs, exactly matching the report.

**Fix:** the draft now seeds the full tree on first load
(`_seedFullTreeIfEmpty`), and saving refuses an empty tree and bounces the user
to Step 2 (`_treeIsEmpty`). The regional-swap filtering used by the "full"
template was extracted to `_filterFullTree` so the seed and the button can't
drift apart.

## The unnamed-hero string bug — fixed

A hero with a blank name showed campaign dialogue in-game instead of a name
("The English castle at Falkirk is no more!" as the unit name, a line of Kaimbasa
campaign text as the Castle tooltip).

`_apply_hero_unit` repointed `language_dll_name` / `+1000` / `+100000` at
CAMPAIGN_STRING_POOL slots **unconditionally**, while both string writers
(`wizard_build.py`, `app.py`) gate their writes on a non-empty hero name. Pool
entries are *existing* vanilla strings, so repointing without writing does not
blank the name — it swaps in whatever campaign line occupies that id. No warning
fired, because the warning path also required a non-empty name.

**Fix, three layers:** `_apply_hero_unit` only claims the SIDs when a name is
present (otherwise the hero keeps its vanilla strings, always a sane fallback);
selecting a hero now defaults the name field to the catalog display name rather
than `""`; and Step 8 refuses to advance with a hero selected but unnamed.

**The general trap:** claiming a pool SID and writing text to it must happen
together. A SID claimed but unwritten is worse than no SID at all, because it
silently displays unrelated campaign prose.

## Parked — external, not ours to fix

### Civ preview panel shows the overwritten civ's text

**Status: confirmed game-side, 2026-09-02. Do not "fix" this in the build system.**

Symptom: the civ preview panel shows the replaced civ's bonuses, unique unit and
unique techs. All three come from one string — the civ description at
`name_sid + 109879` (`120150` for the Britons slot) — so it is a single override
not landing, not three separate failures. The UU *icon* is correct because it
comes from `civilizations.json` in the data mod, which applies fine.

The decisive evidence is Unhinged Empires: a hand-authored mod, independent of
this tool, previously working. It writes a genuine custom description to `120150`
and that is ignored, while its `10271` civ-name override in the *same file* is
honoured. No mod can cause that asymmetry.

Ruled out, in order: string ids, the `+109879` offset (`120150` really is the
Britons description), file content, path and filename (identical to Unhinged),
encoding/BOM/line endings (identical to Unhinged), competing string files
(nothing else defines `1201xx`), mod collision (all other mods disabled), the UI
mod not loading (local UI mods cannot be disabled), our code (an older commit
fails identically), and install integrity (Steam verify + reboot).

Reported to the AoE2 modding community; awaiting an answer on whether `1201xx`
overrides need a different file now or the panel stopped reading the string
table. Re-test before touching anything here.

### `unique_tech_id_1` / `unique_tech_id_2` never patched — unconfirmed

`app.py`'s `civilizations.json` patch sets the civ name, UU icon, UU ids and UU
string ids, but leaves `unique_tech_id_1` / `unique_tech_id_2` at the replaced
civ's values (Britons keeps Yeomen 3 / Warwolf 461).

Flagged as a bug from a static read of the JSON, but **no observed symptom** —
UTs display correctly in-game and in the preview panel, with a screenshot from
early September 2026 showing them working. The fields are likely vestigial for
display: the preview panel takes UT names from inside the `120150` description
string, and the tech tree screen takes them from the per-civ CivTechTrees JSON,
which we do patch. Check before changing anything; do not "fix" on the strength
of the JSON alone.

## Track B — Tech tree node inspector

**The problem with the obvious design.** "Mark techs free" wants to be a paint
mode on the tech tree. So does "available one age sooner". So will cost
overrides, research time, and eventually unit stats. Five paint modes is a mess,
and each one needs its own affordance, legend and undo story.

**The design.** One inspector panel, opened by clicking a node:

```
┌─ Crossbowman ──────────────┐
│ ● Enabled                  │
│ ○ Free    ○ One age sooner │
│ Cost   45f  25w  ⟲ default │
│ Train time  27s            │
│ HP 35   Attack 5   ...     │
└────────────────────────────┘
```

This subsumes the free-techs feature *and* the "edit unit costs and stats
directly on the tech tree" idea, and it puts every per-node property in one
place with one "changed from default" indicator.

**Why the tech tree is the right home** (per the `where a choice lives`
principle): "which techs are free" is a per-node property of the tree. Putting
it there inherits node search, cascade logic and age columns, and makes it
structurally impossible to mark a tech free that the civ does not have. A flat
list on the bonus page would need its own search and would happily let you mark
a tech you disabled two steps earlier.

**Build order**

1. **Read-only stat panel.** Useful on its own as an inspector, and it proves
   the click-target and layout before anything is mutable.
2. **Free techs.** Storage already exists: `free_techs` is a pass-through in
   `civ_schema.py:157`. Generalises ~15 catalog entries ("Loom instant", "free
   Pikeman upgrade", 49/72/86/91/96/110/112/146/261/365…) into one control.
3. **Cost / train time overrides.** `civ_overrides.py:65` already does exactly
   this for unique units; the work is generalising a proven path from one unit
   to any node. `unit_overrides` is already a schema pass-through
   (`civ_schema.py:155`).
4. **One age sooner.** Mechanically easy — swap the age prerequisite in
   `required_techs`; vanilla does it constantly (our bonuses 221, 247, 283, 342,
   352). The hard half is *display*: the per-civ CivTechTrees JSON positions
   nodes by age column, so the node has to move too. Same machinery as the
   known `_patch_per_civ_techtree` gap where units do not appear at all. Do this
   last, and only after that gap is closed.

---

## Track C — Custom bonus composer

The answer to "everything is a fixed pre-selection". We already have the EC
engine and `_scale_ec_for_multiplier`; a guided composer turns 358 fixed
bonuses into arbitrary ones.

**Tier 1 — unit attributes** (`EC_ADD` / `EC_MULTIPLY`, `c` parameter):

| c | Attribute | c | Attribute |
|---|---|---|---|
| 0 | HP | 12 | Max range |
| 1 | Line of sight | 13 | Work rate |
| 5 | Movement speed | 22 | Blast radius |
| 8 | Armor | 24 | Incoming bonus damage |
| 9 | Attack | 100 | First resource cost |
| 10 | Reload time | 101 | Train time |
| 11 | Accuracy | 109 | HP regen / min |

Armor and attack encode as `class × 256 + amount`, so "+2 vs cavalry" is
`8 × 256 + 2`. Targeting is a unit id, or `a = -1, b = class_id` for a whole
class (4 Civilian, 6 Infantry, 12 Cavalry, 13 Siege Weapon).

**Tier 2 — player resource attributes.** Graded by
`scripts/probe_resource_attrs.py`: **35 READY** (some `civ = -1` tech writes
them), **51 PROBE** (only civ-gated writers — one in-game test each), **9
ORPHAN**, **23 IN USE**. This is where the genuinely novel bonuses live:
gather productivity, building trickles, relic rates, kill rewards, auras.

PROBE is not a blocklist — 236/266 sit there by shape and are confirmed to
travel. Cross-civ portability is not statically decidable; `tech.civ` says where
vanilla ships an effect, not where it refuses to fire.

**Constraints.** Cap composed effects against the ~189-command Effect limit.
Trickle writes (`b = -1`) need `repeatable = 1` — the EC-list path already sets
it (`civ_appender.py:1275`), but any new path must too.

---

## Track D — Point budget

The most-requested mechanic in the community, and no builder has it. The
[forum spec](https://forums.ageofempires.com/t/custom-civilizations-builder-suggestion/107756)
is unusually concrete: ~266-point budget, 9 categories (Economy, Military,
Infantry, Ranged, Cavalry, Siege, Navy, Monastery, Defence), max 3 picks per
category, and **each additional pick in a category costs +3 more** (Economy
allows 2 before escalation).

We have no civ bonus cap by design, so an advisory budget is the natural
governor.

**Competitive mode should mean auditable, not restricted.** A tournament-legal
civ must be reproducible from its JSON by anyone. That rules out anything whose
power cannot be priced — composed bonuses (Track C), arbitrary stat overrides
(Track B step 3) — while leaving the whole catalog available, since every
catalog entry can carry a fixed value. Ship the meter as advisory everywhere
first, let the community argue the numbers, then add a "tournament legal" badge
as a thin layer.

**Depends on Track A.** A bonus that does not fire cannot be priced.

---

## Track E — Flavour and coherence

Small, high-visibility, and two of the three are things Krakenmeister has
declined to build.

- **Custom jingle / civ theme.** The actual forum ask was narrow — "upload
  custom jingles and themes", i.e. civ music, not voice lines. Mostly the
  packaging problem already solved for voices.
- **AI player names.** Skirmish opponents matching the civ's theme.
  `aiconfig.json` and `ai_stubs/` are already in the repo.
- **Pre-game hints generated from the selected bonuses.** The civ description
  panel on the lobby screen. Reuses the string-id offset scheme we already own,
  and it is the feature that makes the linter's output player-visible instead of
  a build-time warning.
- **Coherence linter.** Warn when a bonus references a unit that is not in the
  tree ("you picked *Can recruit Slingers* but the Archery Range is disabled"),
  when picks do not stack, or when mutually-exclusive lines are both on. This is
  the class of problem behind issues #20 and #25.

---

## Track F — Unknowns, do not build on these yet

**Button pages.** Whether a building's UI can hold more than 15 buttons is
**unresolved**. A first pass at the DAT looked like evidence for a second page
(Thirisadai at Dock button 15, heroes at 24, a tech at 27) but that reading does
not survive contact with the game: if button 15 is the bottom-right of the 5×3
grid then the slots are 1–15, not 0–14 — which fits, since the 23 units sitting
at button 0 are non-trainable variants like packed Trebuchets. Heroes at 24 fit
no page model either. Krakenmeister's "I can't add pages" may well be an engine
limit, not a tooling one.

*The lead worth chasing:* the lobby "all techs" option reportedly grants all
techs **and** units without the overlap problem. If the engine can render that
overflow, something handles it. Test: start an "all techs" game, count what
renders at a full Archery Range, and see whether a 16th entry appears, scrolls,
or silently vanishes. Until then, treat button remapping as *rearranging within
15 slots* — still useful, since that is what frees space up.

**Second UU.** `second_uu` is a schema pass-through (`civ_schema.py:154`) with
no handler. Blocked on the same button-space question.

---

## Suggested order

1. ~~**Track A**~~ — done. Both in-game tests passed (`B = -1` control, Dragon
   Ships). D is unblocked.
2. **Track B step 1** — read-only stat panel. Small, self-contained, proves the
   inspector.
3. **Track E** — pre-game hints + AI names. Visible, cheap, differentiating.
4. **Track D** — advisory budget meter.
5. **Track B steps 2–3**, then **Track C**.
6. **Track F** only after someone tests "all techs" in a real lobby.

## Files touched so far

| File | Change |
|---|---|
| `bonus_names.json` | 13 renamed, 5 removed |
| `bonus_catalog_raw.json` | 132 / 238 / 240 resource ids fixed |
| `llm/resource_ids.md` | resource-attribute survey, the "resources last longer" family, dormant-tech warning |
| `llm/resource_attrs.json` | new — 284 id → name table |
| `scripts/probe_resource_attrs.py` | new — grades every resource id by vanilla usage |
