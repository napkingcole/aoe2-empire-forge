#!/usr/bin/env python3
"""Every text file the app reads or writes names its encoding.

Without one, Python uses the platform default: UTF-8 on a Mac, cp1252 on
Windows.  v2.5.0 added the first character cp1252 cannot decode ("Sannāhya" in
bonus_names.json) and the Windows exe could not list civ bonuses at all
(reported 2026-10-06) — while every test here passed, because they run on a
Mac.  Older accented names had been decoding as mojibake on Windows all along.

This is a lint over the app's modules and the tests: open() in text mode, read_text()
and write_text() must pass encoding=.  No DAT needed.

    venv/bin/python tests/test_explicit_encoding.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
bad = []
for path in sorted(ROOT.glob("*.py")) + sorted((ROOT / "tests").glob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        kws = {k.arg for k in node.keywords}
        if "encoding" in kws:
            continue
        if name in ("read_text", "write_text"):
            bad.append(f"{path.name}:{node.lineno} {name}()")
        elif name == "open" and isinstance(fn, ast.Name):
            mode = ""
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            for k in node.keywords:
                if k.arg == "mode" and isinstance(k.value, ast.Constant):
                    mode = k.value.value
            if "b" not in str(mode):
                bad.append(f"{path.name}:{node.lineno} open()")

if bad:
    print("  FAIL text I/O without an explicit encoding (cp1252 on Windows):")
    for b in bad:
        print(f"       {b}")
    sys.exit(1)
print("  ok   every text read/write names its encoding")
