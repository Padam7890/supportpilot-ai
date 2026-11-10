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
run_check frontend_typecheck bash -c 'cd "$1/frontend" && npm run typecheck' _ "$ROOT"
run_check frontend_tests bash -c 'cd "$1/frontend" && npm test' _ "$ROOT"
run_check frontend_build bash -c 'cd "$1/frontend" && npm run build' _ "$ROOT"
run_check frontend_api_types bash -c 'cd "$1/frontend" && npm run api:types:check' _ "$ROOT"
run_check backend_rag_corpus bash -c 'cd "$1/backend" && python scripts/rag_release_gate.py' _ "$ROOT"
printf '\nBaseline results (never treat skipped prerequisites as passing):\n'
cat "$summary"
printf '\nLogs saved in %s. Review FAIL entries and distinguish missing services/dependencies from code failures.\n' "$OUT"

# A baseline with any failed check must fail the CI step too.
if grep -q 
  printf 'Baseline FAILED: inspect individual logs in %s\\n' "$OUT" >&2
  exit 1
fi
printf 'Baseline PASSED: all configured checks completed successfully.\\n'
\tFAIL(' "$summary"; then
  printf 'Baseline FAILED: inspect individual logs in %s\\n' "$OUT" >&2
  exit 1
fi
printf 'Baseline PASSED: all configured checks completed successfully.\\n'
