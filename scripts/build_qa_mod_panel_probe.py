#!/usr/bin/env python3
"""Probe mod for #96: which civ descriptions does the civ-selection panel show?

Mods built here (build_all) showed the panel's yellow headings with no text;
mods the user built in the web app showed it.  The two differed in layout (the
web route spaced every line break) and our probe civs never had a team bonus,
while every vanilla description ends on one.  Four civs, one per combination:

  QA Tight      (Britons, 120150)  game layout, no team bonus
  QA Tight TB   (Franks,  120151)  game layout, team bonus
  QA Spaced     (Goths,   120152)  old web layout, no team bonus
  QA Spaced TB  (Teutons, 120153)  old web layout, team bonus

    venv/bin/python scripts/build_qa_mod_panel_probe.py   # writes ignore/qa_panel/
"""
import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_all                                            # noqa: E402
from build_qa_mod_branch import B, civ, preset, tree_from   # noqa: E402
from dat_reader import find_game_dat                        # noqa: E402

OUT = ROOT / "ignore" / "qa_panel"
TEAM = [{"id": 3, "multiplier": 1}]
QA = [("britons", "QA Tight", []), ("franks", "QA Tight TB", TEAM),
      ("goths", "QA Spaced", []), ("teutons", "QA Spaced TB", TEAM)]
SPACED = {120152, 120153}


def spaced(text: str) -> str:
    """The old web route's layout: a space before every line break, and a
    trailing one; team bonuses bulleted."""
    text = re.sub(r"(?<! )(?<!\\n)\\n", r" \\n", text)
    text = text.replace("<b>Team Bonus:<b> \\n", "<b>Team Bonus:<b> \\n• ")
    return text + " \\n"


def main() -> None:
    dat_path = find_game_dat()
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for replace, alias, team in QA:
        c = civ(alias, alias.removeprefix("QA "), bonuses=B(105, 330),
                share_description="Probe for the civ-selection panel (#96).",
                unique_unit={"km_idx": 0, "name": "", "description": ""},
                castle_ut=preset(2, "castle"), imperial_ut=preset(0, "imperial"),
                team_bonuses=team, tree=tree_from("FRANKS.json"))
        f = OUT / f"{alias.replace(' ', '_')}.civbuilder.json"
        f.write_text(json.dumps(c, indent=2) + "\n", encoding="utf-8")
        entries.append({"json": str(f), "replace": replace})
    cfg = OUT / "qa_mod_config.json"
    cfg.write_text(json.dumps({"mod_name": "QA Panel", "prefix": "qa_panel", "civs": entries}, indent=2),
                   encoding="utf-8")
    out = OUT / "qa_panel.zip"
    build_all.build_mod(cfg, Path(dat_path), out)

    # Respace two descriptions, in every language, inside the UI mod.
    outer = zipfile.ZipFile(out)
    files = {n: outer.read(n) for n in outer.namelist()}
    outer.close()
    ui = next(n for n in files if n.endswith("-ui.zip"))
    src = zipfile.ZipFile(io.BytesIO(files[ui]))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename.endswith("key-value-modded-strings-utf8.txt"):
                lines = data.decode("utf-8").split("\n")
                for i, ln in enumerate(lines):
                    m = re.match(r'^(\d+) "(.*)"$', ln)
                    if m and int(m.group(1)) in SPACED:
                        lines[i] = f'{m.group(1)} "{spaced(m.group(2))}"'
                data = "\n".join(lines).encode("utf-8")
            dst.writestr(info, data)
    files[ui] = buf.getvalue()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in files.items():
            z.writestr(n, data)
    print(f"\nWrote {out}.")


if __name__ == "__main__":
    main()
