#!/usr/bin/env bash
# Phase 9 reproducible, non-destructive static baseline.
# Requires backend Python dependencies and frontend Node dependencies installed.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$ROOT/phase-9-baseline-results}"
mkdir -p "$OUT"
summary="$OUT/summary.tsv"
printf 'check\tstatus\tlog\n' > "$summary"
run_check() {
  local name="$1"; shift
  local logfile="$OUT/$name.log"
  printf 'Running %s...\n' "$name"
  if ( "$@" ) >"$logfile" 2>&1; then
    printf '%s\tPASS\t%s\n' "$name" "$logfile" >>"$summary"
  else
    local code=$?
    printf '%s\tFAIL(%s)\t%s\n' "$name" "$code" "$logfile" >>"$summary"
  fi
}
run_check backend_ruff bash -c 'cd "$1/backend" && ruff check app tests migrations scripts' _ "$ROOT"
run_check backend_openapi bash -c 'cd "$1/backend" && python scripts/export_openapi.py --check' _ "$ROOT"
run_check backend_tests bash -c 'cd "$1/backend" && pytest -q' _ "$ROOT"
run_check frontend_widget_syntax node --check "$ROOT/frontend/public/supportpilot-widget.js"
run_check frontend_lint bash -c 'cd "$1/frontend" && npm run lint' _ "$ROOT"
run_check frontend_typecheck bash -c 'cd "$1/frontend" && npx tsc --noEmit' _ "$ROOT"
printf '\nBaseline results (never treat skipped prerequisites as passing):\n'
cat "$summary"
printf '\nLogs saved in %s. Review FAIL entries and distinguish missing services/dependencies from code failures.\n' "$OUT"
