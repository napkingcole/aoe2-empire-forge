#!/usr/bin/env python3
"""Voices come from the player's Wwise banks, not a bundled voice_files/ copy.

The exe used to carry 32 MB of the game's audio; the Store build must not.
voice_source reads every clip voice_wwise_map.json names straight out of the
game's `wwise/Base.pck`, so these check that:

  * the spec no longer bundles voice_files/ (the map still ships);
  * the Voice picker is the map's values, so it needs no folder on disk;
  * every mapped voice extracts in full from the banks, and the UI zip carries
    exactly the bank's bytes (KM's bundled Britons are a different encode of
    the same lines, so a build that still read voice_files/ fails here);
  * with no wwise folder the build warns and ships no voices, not a crash.

Needs a copy of the game's wwise/ folder at ignore/wwise (or EMPIREFORGE_WWISE);
the extraction checks are skipped without it.

    venv/bin/python tests/test_voice_source.py
"""
import contextlib
import io
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import voice_source  # noqa: E402

fails: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


spec = (ROOT / "aoe2civbuilder.spec").read_text(encoding="utf-8")
check("('voice_files'" not in spec, "spec does not bundle voice_files/")
check("('voice_wwise_map.json'" in spec, "spec bundles voice_wwise_map.json")

values = voice_source.voice_values()
check(len(values) >= 56, f"map offers {len(values)} voices (>= 56)")

app_src = (ROOT / "app.py").read_text(encoding="utf-8")
check("in voice_values() and" in app_src, "Voice picker is driven by the map")

wwise = voice_source.find_wwise_dir(None)
if wwise is None:
    print("  SKIP  no wwise folder (ignore/wwise or EMPIREFORGE_WWISE) — "
          "extraction not checked")
else:
    clips, missing, used = voice_source.voice_clips(values, None)
    check(missing == [], f"every mapped voice extracts (missing: {missing})")
    by_value = {e["value"]: e for e in voice_source.voice_map().values()}
    short = [v for v in clips if set(clips[v]) != set(by_value[v]["files"])]
    check(not short, f"each voice has exactly the map's files (short: {short})")

    from build_all import _build_combined_ui_zip
    vb = voice_source.voice_map()["Britons"]
    with contextlib.redirect_stdout(io.StringIO()):
        ui = _build_combined_ui_zip({}, {}, {}, lang_values={vb["value"]})
    with zipfile.ZipFile(io.BytesIO(ui)) as zf:
        wems = {Path(n).stem: zf.read(n) for n in zf.namelist() if n.endswith(".wem")}
    check(set(wems) == set(vb["files"]), "UI zip carries every Britons clip")
    check(all(wems[s] == clips[vb["value"]][s] for s in wems),
          "UI zip clips are the bank's bytes")

    # No wwise folder anywhere: warn, ship nothing, keep going.
    saved_dev, saved_env = voice_source._DEV_WWISE, os.environ.pop("EMPIREFORGE_WWISE", None)
    voice_source._DEV_WWISE = ROOT / "no-such-wwise"
    try:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ui = _build_combined_ui_zip({}, {}, {}, lang_values={0},
                                        dat_path="/nowhere/resources/_common/dat/x.dat")
        with zipfile.ZipFile(io.BytesIO(ui)) as zf:
            check(not any(n.endswith(".wem") for n in zf.namelist()),
                  "no wwise folder: no clips shipped")
        check("could not extract voice files" in out.getvalue(),
              "no wwise folder: the build log says so")
    finally:
        voice_source._DEV_WWISE = saved_dev
        if saved_env is not None:
            os.environ["EMPIREFORGE_WWISE"] = saved_env

print()
print("FAIL" if fails else "PASS")
sys.exit(1 if fails else 0)
