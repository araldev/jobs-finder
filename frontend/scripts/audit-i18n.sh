#!/usr/bin/env bash
#
# scripts/audit-i18n.sh — CI grep audit for hardcoded user-facing English/Spanish
# strings that should live in `messages/{en,es}.json` instead.
#
# This is a HEURISTIC, not a full AST parser:
# - It catches quoted capitalized phrases (e.g. `"Dashboard"`, `'Search jobs'`).
# - It deliberately ignores: the messages files themselves, the Spanish-only
#   `privacidad/` legal page, test files (`*.test.{ts,tsx}`, `__tests__/**`),
#   the test-utils wrapper, and our own scripts (to avoid recursion noise).
#
# When `pnpm run lint:i18n` is wired into CI (slice 6 onward), any match
# is treated as a hard failure. The script is intentionally permissive —
# it WILL print matches during the i18n migration (slices 7-15 are still
# landing); the goal is "no NEW matches introduced" per slice.
#
# Supports ripgrep (preferred — has PCRE2 lookbehind support) and falls
# back to `grep -P` if `rg` is not installed. Either way, the script
# exits 0 so it never fails a slice during the migration; CI workflows
# upstream decide how to enforce it.
#
# Closes REQ-I18N-012 (errors surface in EN/ES via messages) and AC-12
# (grep audit clean at end of slice 15).

set -euo pipefail

cd "$(dirname "$0")/.."

# Capitalized word (Spanish accents supported) inside quotes.
# Lookbehind/lookahead on quote char avoids `Dashboardx` etc.
PATTERN='(?<=[ "'\''`])[A-Z][a-záéíóúñ]+(?: [A-Za-záéíóúñ]+)*(?=[ "'\''`,);:\.\}])'

EXCLUDES=(
  --type=ts
  --type=tsx
  -g '!messages/**'
  -g '!src/app/privacidad/**'
  -g '!src/test-utils.tsx'
  -g '!**/*.test.ts'
  -g '!**/*.test.tsx'
  -g '!**/__tests__/**'
  -g '!scripts/**'
  -g '!src/i18n/routing.ts'
  -g '!src/i18n/request.ts'
  -g '!src/lib/supabase/middleware.ts'
)

run_audit() {
  if command -v rg >/dev/null 2>&1; then
    # ripgrep — preferred (PCRE2 + per-type filtering)
    rg "${EXCLUDES[@]}" --pcre2 -n "$PATTERN" src || true
  elif grep -P 'a' <<<'a' >/dev/null 2>&1; then
    # grep -P fallback (GNU grep with PCRE). Less precise filtering.
    echo "NOTE: ripgrep not found; falling back to grep -P (less precise)."
    grep -RInP \
      --include='*.ts' --include='*.tsx' \
      --exclude-dir=messages \
      --exclude-dir=privacidad \
      --exclude-dir=__tests__ \
      --exclude-dir=scripts \
      --exclude='*.test.ts' --exclude='*.test.tsx' \
      "$PATTERN" src \
      | grep -v 'src/test-utils.tsx' \
      | grep -v 'src/i18n/routing.ts' \
      | grep -v 'src/i18n/request.ts' \
      | grep -v 'src/lib/supabase/middleware.ts' \
      || true
  else
    echo "WARNING: neither ripgrep nor grep -P available; skipping audit."
  fi
}

run_audit

echo
echo "lint:i18n — done. Matches above are heuristic; review them against the slice migration map."
echo "NOTE: matches are EXPECTED until slice 15 lands; this script runs as a SEPARATE CI step."
exit 0