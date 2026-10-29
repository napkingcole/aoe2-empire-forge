# Extending an Empire Forge mod

Empire Forge covers what most civs need: tech trees, the bonus catalog, custom
bonuses, unique units and techs. Some ideas are deliberately out of its scope —
*villagers can build rams*, *Petards garrison in rams*, *Outposts explode when
destroyed*. You can still make them. This guide shows how to add your own
changes **on top of** a mod Empire Forge built, the same way the Unhinged
Empires mod adds its custom unique techs and second unique units.

> **This is the advanced route.** Empire Forge itself needs no tools at all.
> Everything below needs Python on your computer and some comfort with a
> terminal — or an AI code editor to do the typing for you. Nothing here can
> break your game install: you only ever edit the mod's own files, and the
> script keeps a copy of Empire Forge's original.

## What you need

- **Age of Empires II: Definitive Edition**, and a mod you built with Empire Forge.
- **Python 3.11 or newer** (genieutils-py requires it) — [python.org/downloads](https://www.python.org/downloads/).
  On Windows, tick *Add python.exe to PATH* in the installer.
- **genieutils-py**, the library that reads and writes the game's data file.
  In a terminal: `pip install genieutils-py==0.1.2` (the version Empire Forge uses).
- **The template script and the modding notes** from this repository:
  [`extend/post_build_template.py`](../extend/post_build_template.py) and the
  [`llm/`](../llm/) folder. Download the repository as a zip from GitHub
  (*Code → Download ZIP*) or clone it.
- **Optional, recommended:** an AI code editor (Claude Code, Cursor, GitHub
  Copilot, …). You describe the idea; it writes the change, using the notes.

## How it works

A mod from Empire Forge is two folders: `<name>-data` holds the game's data
file, `empires2_x2_p1.dat` — every unit, tech and effect — and `<name>-ui`
holds the names, descriptions and icons. Your changes are a small Python
script that opens the **data file in your installed mod**, edits it, and saves
it. Empire Forge never sees the script, so:

- rebuilding your civ in Empire Forge never loses your changes — run the script again;
- a new Empire Forge version never conflicts with them;
- your script is yours to share, alongside your mod.

## Step by step

1. **Build and install your mod** as usual: Build Mod in Empire Forge, then
   unzip both folders into your game's `mods/local/` folder. On Windows that is
   `%USERPROFILE%\Games\Age of Empires 2 DE\<your id>\mods\local\`.
2. **Find your civ's name in the data file.** A custom civ keeps the name of
   the vanilla civ whose slot it replaced — your civ in the Britons slot is
   `British` in the data file. List them all:

   ```
   python post_build_template.py "<...>/mods/local/MyMod-data" --list-civs
   ```
3. **Try the example.** As shipped, the template gives your civ's villagers
   +15 HP — the exact command Loom uses:

   ```
   python post_build_template.py "<...>/mods/local/MyMod-data" --civ British
   ```

   Start a skirmish with your mod as the data mod and check a villager's HP.
4. **Write your own change** in `apply_my_changes()` in the template. With an
   AI code editor, open the template, paste the brief from the top of the
   file into its chat, then describe your idea. (See *Briefing an AI* below.)
5. **Run it and test in game.** Run it as often as you like: each run starts
   again from Empire Forge's original file, so nothing is applied twice.
6. **After rebuilding in Empire Forge**, unzip the new mod over the old one and
   run your script again. It notices the new file and starts from it.

## Briefing an AI

The top of the template holds a brief to paste in before your idea. It points
the AI at the [`llm/`](../llm/) notes — effect commands, unit quirks, advanced
techniques — and at the *Critical Quirks* in [`CLAUDE.md`](../CLAUDE.md). That
matters: the game engine has rules that look wrong and aren't, and those notes
record what was confirmed in game. A good request is specific:

> *Make my civ's Outposts deal 50 damage to nearby enemy units when destroyed.
> Find a vanilla unit that already damages things around it when it dies, and
> copy how it does it.*

Ask it to explain what it changed and how to check it in game. If it can't
find a vanilla precedent for your idea, treat that as a warning sign — the
engine may not support it.

## Rules that save you hours

- **Find the precedent first.** Before changing anything, search the data for
  a vanilla effect or tech that already does something similar, and copy its
  shape. Loom is the precedent for "+15 villager HP"; nearly every idea has one.
- **Find Empire Forge's things by name, never by id.** Ids of techs and effects
  Empire Forge creates change between builds. Its own techs carry readable
  names (`<Civ> Castle UT`, `<Civ> Imperial UT`, `C-Bonus, Custom`);
  `civ_techs()` in the template lists them. Vanilla ids are stable and fine.
- **Keep each effect under ~180 commands.** The game crashes on load near 189.
  Split a big change across several techs (`add_civ_bonus` once per chunk).
- **Self-researching techs need one research location at -1.** An empty list
  makes the game silently ignore the tech; `add_civ_bonus` gets this right.
- **Text needs an existing string id.** The game ignores brand-new string ids.
  To rename something, reuse an id from your game's own strings file —
  `<game>/resources/en/strings/key-value/key-value-strings-utf8.txt` — and put
  your text for that id in **your installed UI mod's** strings file:
  `<name>-ui/resources/en/strings/key-value/key-value-modded-strings-utf8.txt`
  (each line is `ID "text"`). See *Language String Pitfalls* in
  [`llm/advanced_techniques.md`](../llm/advanced_techniques.md).
- **Internal unit names lie.** `unit.name` is a codename — 775 is `MONKY`, the
  Missionary. Check what a unit really is before relying on it.

## When something goes wrong

| What you see | Usually |
|---|---|
| The game crashes or hangs while loading | An effect over ~189 commands, or a command pointing at something that doesn't exist. Undo your last change and add it back in halves. |
| Nothing changed in game | The data mod isn't selected in the lobby; the wrong `--civ`; or the tech has no research location. |
| Your civ plays like the original civ | The data mod isn't selected in the lobby's Data Mod dropdown. |
| Names or descriptions are wrong | A brand-new string id (use an existing one), or the UI mod's priority is too low in the mod manager. |
| The change applied twice | You ran a script that doesn't start from a clean copy. The template does; keep its plumbing. |

## Sharing

Your mod is yours to publish. If you share a mod built this way, a mention of
Empire Forge is appreciated. The template, like the rest of Empire Forge, is
GPL-3.0 licensed: if you share your script, share it open source under the
same license.

Questions, or an idea that might belong in Empire Forge itself? Ask on the
[Discord](https://discord.com/invite/cQ5x7bfxDB) or open a
[GitHub issue](https://github.com/napkingcole/aoe2-empire-forge/issues).
