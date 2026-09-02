#!/usr/bin/env bash
# Run every test. From the repo root:  ./tests/run_all.sh
#
# Deliberately dependency-free — plain scripts, no pytest, no node_modules.
# Adding a test means dropping a file in here and adding a line below.
set -uo pipefail
cd "$(dirname "$0")/.."

# Prefer the project venv; genieutils lives there.
PY=./venv/bin/python
[ -x "$PY" ] || PY=python3

failed=0

run() {
    local label="$1"; shift
    echo
    echo "════ $label"
    if "$@"; then
        echo "──── $label: PASS"
    else
        echo "──── $label: FAIL"
        failed=1
    fi
}

if command -v node >/dev/null 2>&1; then
    run "editor layout (node)" node tests/test_editor_layout.js
else
    echo "!! node not found — skipping tests/test_editor_layout.js"
    failed=1
fi

run "in-game tech tree (python)"  "$PY" tests/test_civtechtrees.py
run "civ_def formats (python)"    "$PY" tests/test_civ_def_formats.py
run "no direct civ_def reads"     "$PY" tests/test_no_direct_civdef_reads.py
run "catalog resource ids"        "$PY" tests/test_resource_ids.py

# Route round-trip needs the real game DAT and ~75s, so it is opt-in.  It skips
# itself cleanly when no DAT is found; ROUNDTRIP=1 makes it run.
if [ "${ROUNDTRIP:-0}" = "1" ]; then
    run "route round-trip (python)" "$PY" tests/test_route_roundtrip.py
else
    echo
    echo "──── route round-trip: SKIPPED (ROUNDTRIP=1 to run, needs game DAT, ~75s)"
fi

echo
if [ "$failed" -eq 0 ]; then
    echo "All test files passed."
else
    echo "Some test files FAILED."
fi
exit "$failed"
