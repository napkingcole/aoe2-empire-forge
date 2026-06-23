# AOE2: Empire Forge

A local desktop tool for building custom civilizations for **Age of Empires II: Definitive Edition** — no modding experience required. Import a [KrakenMeister](https://krakenmeister.com/civbuilder) (or Fritz' [forked version here](https://civbuilder.velarix.space/)) civ JSON, point it at your own game files, and it generates a ready-to-install mod.

> **This is an early, stopgap release.** Empire Forge will eventually grow into a full app with its own UI for designing tech trees, selecting unique units and bonuses — including user-submitted bonus presets, and, possibly, in-app bonus creation. For now, it focuses on turning existing KrakenMeister civ designs into working AoE2:DE mods, reliably and without a third-party service.

## Download

Grab the latest build from the [Releases page](https://github.com/napkingcole/aoe2-empire-forge/releases). Download the `.exe` (Windows) — no Python or other installation required.

## How to use it

1. **Launch the app.** Double-click the `.exe`. It starts a local server and opens your browser automatically — nothing leaves your machine.
2. **Upload your civ(s).** Drop in one or more KrakenMeister civ JSON files, and point it at your `empires2_x2_p1.dat` (usually under `resources/_common/dat/` in your AoE2:DE install — the app will try to auto-detect it).
3. **Configure.** Reorder your civs, assign each one to the vanilla civ slot it should replace, and name your mod.
4. **Build.** Hit "Build Mod" and watch the live log as it applies bonuses, unique techs, and your unique unit.
5. **Install.** Download the resulting zip and unzip it — you'll get two mod files (`-data` and `-ui`). Import **both** via AoE2:DE's **Mods → My Mods → Import Mod**, and make sure both show as active before launching a game.

## Questions / feedback

- Email: [aoenapkingcole@gmail.com](mailto:aoenapkingcole@gmail.com)
- Discord: `napkingcole84` ([profile](https://discord.com/users/napkingcole84))
