#!/usr/bin/env bash
# Run the tests. From the repo root:
#
#   ./tests/run_all.sh                 everything, 6 files at a time
#   ./tests/run_all.sh --quick         data checks + build smoke + changed tests
#   ./tests/run_all.sh --quick test_ambuscade.py   ...plus the files named
#   ./tests/run_all.sh test_ambuscade.py           just the files named
#   ./tests/run_all.sh -j 1            one at a time
#
# SKIP_SMOKE=1 skips the build tests; ROUNDTRIP=1 adds the route round-trip.
# The test list and the runner live in tests/run_tests.py.
set -uo pipefail
cd "$(dirname "$0")/.."

# Prefer the project venv; genieutils lives there.
PY=./venv/bin/python
[ -x "$PY" ] || PY=python3

exec "$PY" tests/run_tests.py "$@"
