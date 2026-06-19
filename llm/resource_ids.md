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
