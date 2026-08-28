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

run "in-game tech tree (python)" "$PY" tests/test_civtechtrees.py

echo
if [ "$failed" -eq 0 ]; then
    echo "All test files passed."
else
    echo "Some test files FAILED."
fi
exit "$failed"
