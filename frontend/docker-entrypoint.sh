#!/bin/sh
set -eu

lock_hash=$(sha256sum package-lock.json | cut -d ' ' -f 1)
lock_marker="node_modules/.supportpilot-package-lock-hash"

if [ ! -f "$lock_marker" ] || [ "$(cat "$lock_marker")" != "$lock_hash" ]; then
  npm ci --no-audit --no-fund
  printf '%s\n' "$lock_hash" > "$lock_marker"
fi

# Keep vendored shadcn animation CSS in sync when node_modules is present.
npm run vendor:shadcn-css --silent 2>/dev/null || true

exec npm run dev -- --hostname 0.0.0.0
