#!/usr/bin/env bash
# Multi-version validation for the anakin-sdk PyPI package.
#
# Builds the wheel once (pure Python — universal across versions),
# then installs and smoke-tests it in a fresh venv per Python version.
# Used as the publish-readiness gate before each release.
#
# Compatible with bash 3.2 (macOS default) — no associative arrays.
#
# Usage:
#   scripts/test-multiver.sh            # default: 3.10, 3.11, 3.12, 3.13
#   PY_VERSIONS="3.11 3.12" scripts/test-multiver.sh   # only specified versions
#
# Requirements:
#   Each Python version in PY_VERSIONS must be on $PATH as `python3.X`.
#   On macOS:  brew install python@3.10 python@3.11 python@3.12
#   On Linux:  use pyenv, deadsnakes ppa, or your distro's packages.

set -u  # treat unset variables as errors (but DON'T set -e — we want the
        # summary to print even when individual versions fail)

# Resolve the repo root (parent of scripts/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
WORK=/tmp/anakin-py-multiver

PY_VERSIONS="${PY_VERSIONS:-3.10 3.11 3.12 3.13}"

# Track outcomes for the summary at the end.
RESULTS_FILE="$WORK.results.tmp"

record() { echo "$1:$2" >> "$RESULTS_FILE"; }
get()    { grep -E "^$1:" "$RESULTS_FILE" 2>/dev/null | tail -1 | awk -F':' '{print $NF}'; }

step() { printf '\n\033[1m── %s ──\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$*"; }

# ── 0. Pre-flight ────────────────────────────────────────────────
step "Pre-flight: confirming Python versions ($PY_VERSIONS) and repo layout"
MISSING=0
for PY in $PY_VERSIONS; do
  if which python$PY >/dev/null 2>&1; then
    ok "python$PY: $(python$PY --version 2>&1) at $(which python$PY)"
  else
    fail "python$PY: NOT FOUND on \$PATH"
    MISSING=1
  fi
done
if [ "$MISSING" = "1" ]; then
  fail "Missing one or more required Python versions. Install them and re-run."
  exit 1
fi

if [ ! -f "$REPO/pyproject.toml" ]; then
  fail "anakin-py repo not found at $REPO (no pyproject.toml). Aborting."
  exit 1
fi
ok "repo: $REPO"

# Clean workspace
rm -rf "$WORK" && mkdir -p "$WORK"
> "$RESULTS_FILE"
ok "clean workspace: $WORK"

# ── 1. Build the wheel ───────────────────────────────────────────
# Use the highest Python version requested for the build (any version
# >= the project's requires-python works since this is a pure-Python
# package; we pick the highest for forward-compat with build tooling).
HIGHEST_PY=$(echo "$PY_VERSIONS" | tr ' ' '\n' | sort -V | tail -1)

step "Building wheel with Python $HIGHEST_PY (pure Python — universal across all $PY_VERSIONS)"
python$HIGHEST_PY -m venv "$WORK/buildenv"
"$WORK/buildenv/bin/pip" install --quiet --upgrade pip build

(
  cd "$REPO"
  rm -rf dist
  "$WORK/buildenv/bin/python" -m build 2>&1 | tail -10
)

if ls "$REPO/dist/"*.whl >/dev/null 2>&1; then
  WHEEL=$(ls "$REPO/dist/"*.whl)
  SDIST=$(ls "$REPO/dist/"*.tar.gz)
  ok "wheel: $(basename "$WHEEL")"
  ok "sdist: $(basename "$SDIST")"
  record "build" "ok"
else
  fail "Build did not produce a .whl"
  record "build" "FAIL"
  exit 1
fi

# ── 2. Per-version install + smoke + tests ───────────────────────
for PY in $PY_VERSIONS; do
  step "Python $PY ($(python$PY --version 2>&1))"
  VENV="$WORK/py$PY"
  python$PY -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip

  # Install the built wheel
  if "$VENV/bin/pip" install --quiet "$WHEEL" 2>&1 | tail -5; then
    ok "wheel install"
    record "py$PY:install" "ok"
  else
    fail "wheel install failed"
    record "py$PY:install" "FAIL"
    continue
  fi

  # Import smoke test — verify the public surface exists
  IMPORT_OUT=$("$VENV/bin/python" -c "
import sys, anakin
from anakin import Anakin, AnakinError
client = Anakin(api_key='ak-fake-test')
public_methods = [m for m in dir(client) if not m.startswith('_') and callable(getattr(client, m))]
print(f'  module loc:      {anakin.__file__}')
print(f'  python:          {sys.version.split()[0]}')
print(f'  client class:    {Anakin.__name__}')
print(f'  public methods:  {public_methods[:10]}')
print(f'  total methods:   {len(public_methods)}')
" 2>&1)
  IMPORT_RC=$?
  if [ $IMPORT_RC -eq 0 ]; then
    ok "import smoke test"
    echo "$IMPORT_OUT" | sed 's/^/    /'
    record "py$PY:import" "ok"
  else
    fail "import smoke test"
    echo "$IMPORT_OUT" | sed 's/^/    /'
    record "py$PY:import" "FAIL"
  fi

  # Dev deps + tests
  echo "  [installing dev deps for tests…]"
  if "$VENV/bin/pip" install --quiet -e "$REPO[dev]" 2>&1 | tail -3; then
    PYTEST_OUT=$("$VENV/bin/pytest" "$REPO/tests" -q --no-header 2>&1 | tail -8)
    echo "$PYTEST_OUT" | sed 's/^/    /'
    if echo "$PYTEST_OUT" | grep -q "passed"; then
      ok "tests"
      record "py$PY:tests" "ok"
    elif echo "$PYTEST_OUT" | grep -q "no tests"; then
      ok "tests (no tests collected)"
      record "py$PY:tests" "ok-empty"
    else
      fail "tests"
      record "py$PY:tests" "FAIL"
    fi
  else
    fail "dev deps install failed — skipping tests"
    record "py$PY:tests" "skipped"
  fi
done

# ── 3. Summary ───────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "                       SUMMARY"
echo "═══════════════════════════════════════════════════════════"
printf '%-30s %s\n' "Build wheel + sdist:" "$(get build)"
echo ""
printf '%-25s %-9s %-9s %-9s\n' "" "install" "import" "tests"
for PY in $PY_VERSIONS; do
  printf '%-25s %-9s %-9s %-9s\n' \
    "  python $PY" \
    "$(get "py$PY:install")" \
    "$(get "py$PY:import")" \
    "$(get "py$PY:tests")"
done
echo ""
echo "Build artifacts:"
ls -la "$REPO/dist/" 2>&1 | grep -v '^total' || true

# Exit non-zero if anything failed
if grep -q "FAIL" "$RESULTS_FILE"; then
  echo ""
  fail "One or more checks failed — see SUMMARY above."
  rm -f "$RESULTS_FILE"
  exit 1
fi

# Cleanup tracking file
rm -f "$RESULTS_FILE"
echo ""
ok "All checks passed."
