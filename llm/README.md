# LLM Context Directory

This directory contains reference documentation for LLM assistants (Claude Code, Copilot, etc.) working on this codebase. It captures AoE2 DE dat file modding knowledge that isn't easily derivable from the code alone — engine quirks, undocumented parameter semantics, known limitations, and hard-won workarounds.

## Why this exists

AoE2 dat file modding is sparsely documented. Each session of debugging tends to uncover engine behavior that looks like a bug but is actually a constraint. Without a written record, that knowledge gets re-derived from scratch. These files prevent that.

## How to use it

If you are an LLM: read the files in this directory when working on bonus handlers, tech tree building, unit enabling/disabling, or resource effects. The information here is authoritative — it reflects actual in-game-tested behavior, not assumptions from the dat format spec alone.

If you are a human contributor: please add to these files when you discover new engine behavior. The format is intentionally plain markdown — no tooling required.

## Files

- `effect_commands.md` — EffectCommand type signatures, full attribute ID table, parameter semantics
- `tech_tree.md` — How the tech tree effect works (type=8 unlocks, type=102 disables)
- `unit_quirks.md` — Unit enabling/trainability, orphan patterns, special unit slots
- `resource_ids.md` — Standard and civ-specific resource IDs
- `known_limitations.md` — Documented engine constraints with confirmed workarounds
- `advanced_techniques.md` — New unit creation, hero units, auras, charge, multi-building training, age-scaling bonuses, task-based gold

## Extended Reference

`modding-notes.md` — Comprehensive modding reference from the custom mod project built on top of Krakenmeister output. Contains debugging tips, full building/unit ID tables, civ slot mappings, hotkey reference, and extended mechanism patterns. Read it when working on anything not covered by the other files here.
