#!/usr/bin/env bash
# =============================================================================
# jobs-finder — apply-billing-migrations.sh
# =============================================================================
#
# Applies the four billing migrations in `20260721_0001..0004_*` order via
# `psql` against a remote Supabase Postgres database. Use this when you do
# NOT have the `supabase` CLI on the target box (e.g. a deployment server
# that only has `psql` + the connection string).
#
# Usage:
#   SUPABASE_DB_URL='postgres://postgres:...' bash scripts/apply-billing-migrations.sh
#   SUPABASE_DB_URL='postgres://...' bash scripts/apply-billing-migrations.sh --dry-run
#
# Options:
#   --dry-run   Print the migration list + connection target and exit.
#               Useful for review before applying.
#
# Requirements:
#   - `psql` on PATH (Postgres client tools).
#   - The `SUPABASE_DB_URL` env var set to a Postgres connection string with
#     sufficient privileges to run DDL + GRANT statements (typically the
#     `postgres` superuser or the project's `migrator` role).
#
# Why a custom script:
#   - `supabase db push` requires the `supabase` CLI + a `config.toml`
#     (we don't ship one for this project — the dashboard SQL editor is the
#     canonical apply path; this script is the second path).
#   - The script is POSIX-sh compatible (no bash-isms) so it runs on any
#     minimal Linux container.
#
# Idempotency: each migration uses `IF NOT EXISTS` / `CREATE OR REPLACE` /
# `DROP ... IF EXISTS` patterns so re-applying is a no-op (safe to retry).
# =============================================================================

set -euo pipefail

# ── Parse args ──────────────────────────────────────────────────────────────
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help)
            sed -n '2,40p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Run with --help for usage." >&2
            exit 64
            ;;
    esac
done

# ── Locate script dir + migrations dir ──────────────────────────────────────
# Resolve symlinks so the script works whether invoked directly or via a
# symlink (e.g. /usr/local/bin/apply-billing-migrations.sh → repo path).
SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || python3 -c "import os,sys;print(os.path.realpath(sys.argv[1]))" "$0")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
MIGRATIONS_DIR="$(cd "$SCRIPT_DIR/../migrations" && pwd)"

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
    echo "ERROR: migrations directory not found at $MIGRATIONS_DIR" >&2
    exit 1
fi

# ── Verify psql is on PATH ──────────────────────────────────────────────────
if ! command -v psql >/dev/null 2>&1; then
    cat >&2 <<EOF
ERROR: \`psql\` is not on PATH.

Install the Postgres client tools:

    # Debian / Ubuntu
    sudo apt-get install -y postgresql-client

    # macOS (Homebrew)
    brew install libpq

    # Alpine
    apk add postgresql-client

Then re-run this script.
EOF
    exit 127
fi

# ── Verify connection string ────────────────────────────────────────────────
if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
    cat >&2 <<EOF
ERROR: SUPABASE_DB_URL env var is required.

Find it under Supabase Dashboard → Project Settings → Database → Connection
string (URI mode). Example:

    SUPABASE_DB_URL='postgres://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres' \\
        bash scripts/apply-billing-migrations.sh

(Use port 6543 for the pooler / 5432 for direct. The migration only opens
 short-lived transactions, so either works.)
EOF
    exit 2
fi

# ── Build the ordered migration list ───────────────────────────────────────
MIGRATIONS=(
    "20260721_0001_subscriptions.sql"
    "20260721_0002_billing_events.sql"
    "20260721_0003_default_free_trigger.sql"
    "20260721_0004_grant_sequences.sql"
)

echo "==> Migrations to apply (in order):"
for m in "${MIGRATIONS[@]}"; do
    echo "    - $m"
done

echo
echo "==> Target: $(echo "$SUPABASE_DB_URL" | sed 's#://[^@]*@#://***:***@#')"
echo

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "==> --dry-run set; exiting without applying."
    echo "    Remove --dry-run to actually run the migrations."
    exit 0
fi

# ── Apply each migration ───────────────────────────────────────────────────
for m in "${MIGRATIONS[@]}"; do
    FILE="$MIGRATIONS_DIR/$m"
    if [[ ! -f "$FILE" ]]; then
        echo "ERROR: missing migration file: $FILE" >&2
        exit 1
    fi
    echo "==> Applying $m ..."
    # -v ON_ERROR_STOP=1 → abort on the first error so a partial apply
    # doesn't leave the schema in a half-migrated state.
    if psql \
        --set ON_ERROR_STOP=on \
        --no-psqlrc \
        "$SUPABASE_DB_URL" \
        -f "$FILE"; then
        echo "    OK"
    else
        rc=$?
        echo "ERROR: $m failed (psql exit $rc)" >&2
        echo "       Apply remaining migrations manually after fixing the cause." >&2
        exit "$rc"
    fi
    echo
done

echo "==> All 4 billing migrations applied successfully."
echo
echo "Next steps:"
echo "  1. Verify the trigger fires for a new test signup:"
echo "       SELECT user_id, plan, status FROM public.subscriptions LIMIT 5;"
echo "  2. Run the RLS smoke test in backend/supabase/README.md (\"Billing"
echo "     migrations\") to confirm cross-user reads are blocked."
echo "  3. Set NEXT_PUBLIC_BILLING_ENABLED=true + STRIPE_SECRET_KEY in the"
echo "     frontend env, then trigger `stripe trigger checkout.session.completed`."
