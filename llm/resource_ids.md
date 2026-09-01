# Resource IDs

Used as the `a` parameter in `EC_RESOURCE` commands and as `b` in `EC_TECH_COST`.

## Standard Resources (0-3)

| ID | Resource |
|----|----------|
| 0  | Food     |
| 1  | Wood     |
| 2  | Stone    |
| 3  | Gold     |

## Civ-Specific Resource Slots

These slots are "owned" by vanilla civs in the dat file but are **cross-civ compatible** — you can use EC_RESOURCE to write to them for any civ.

| ID  | Vanilla owner  | Purpose                          |
|-----|---------------|----------------------------------|
| 236 | Burgundians   | Vineyards gold trickle rate      |
| 266 | Vietnamese    | Paper Money gold trickle rate    |

**History:** These were originally thought to be engine-restricted to their owner civs. Testing confirmed this is false — any civ can use EC_RESOURCE with a=236 or a=266. The original bug (Vineyards not generating gold) was caused by `tech.repeatable=0` on our UT stubs, not a resource slot restriction.

## Trickle Resources

For gold-per-second generation via farms or trade routes, use `EC_RESOURCE` with `b=-1`:
```python
EffectCommand(type=EC_RESOURCE, a=resource_id, b=-1, c=-1, d=rate_per_second)
```

The parent tech **must** have `repeatable=1`. Our `_make_tech` defaults to `repeatable=0`. Set it explicitly:
```python
tech.repeatable = 1
```
before appending the tech. This is already the correct baseline for all Castle/Imperial UT techs that have trickle effects.

## Surveying the rest of the surface

`scripts/probe_resource_attrs.py` walks the DAT and buckets every resource id by
how vanilla uses it:

| Verdict | Meaning |
|---------|---------|
| READY   | some civ-agnostic (`civ = -1`) tech writes it — safe to build on |
| PROBE   | only civ-gated techs write it — needs one in-game test (236/266 were this, and they travel) |
| ORPHAN  | an effect writes it but no tech owns that effect — live, but no civ gate to read |
| IN USE  | our catalog already writes it |

It also flags ids our catalog writes that no vanilla effect ever touches. The
full id table lives in `llm/resource_attrs.json`; authoritative descriptions are
in `AoE2DE_UGC_Guide-main/docs/general/resources/resources.md`.

**Always check the guide's entry before using an id.** Resources 198/199/200 are
documented as *Unused* — writing them does nothing. Bonuses 132, 238 and 240
each targeted one or more of them and were silently inert until 2026-09-01;
they now use 219/268/296, matching vanilla's own set (47/79/189/190/216/219/
268/296 — see tech 737).

### The "resources last longer" family

Vanilla raises a *productivity* multiplier and then slows the matching gatherer's
work rate, so the player gathers at the same speed but the node yields more in
total. Both halves are required: raise productivity alone and you have also
handed out a gather-rate buff.

Match the compensated units to what the productivity id actually covers.
219 is **fishing ships only**, so compensating shore fishermen (VMFIS 56 /
VFFIS 57) alongside it just makes them slower for nothing — that pairing was
removed from bonus 240. 190 (Food Gathering) covers every food source, which is
why tech 737 compensates the whole villager roster.

**Open question:** every type-6 command in our catalog passes `B = -1`; every
vanilla type-6 passes `B = 0`. Bonuses 235/236/237 use valid resource ids with
`B = -1`, so they are a clean control — if "Trees last 100% longer" works
in-game, `B = -1` is harmless and no further change is needed.

Do not reference techs 737-747 directly. They are the lobby "resources last X%"
ladder: `civ = -1` with `required_tech_count = 1` and no valid prerequisite, so
they never fire on their own, and our global-tech path treats an unmodified
global as already-firing. Copy their commands into an ec_list instead.
