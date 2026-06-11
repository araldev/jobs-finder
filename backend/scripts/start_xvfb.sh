#!/usr/bin/env bash
# start_xvfb.sh — start a sidecar Xvfb server for the LinkedIn scraper.
#
# Spec: REQ-LXV-004 (T-003 of `backend-linkedin-xvfb`).
#
# The script is supervisor-agnostic (works in `tmux`, `systemd`,
# `supervisord`, plain shell). It spawns a single Xvfb process on
# the display number from `LINKEDIN_XVFB_DISPLAY` (default `:99`),
# runs a 1-second liveness check, and prints the PID. The operator
# can then `export DISPLAY=:99` and start the FastAPI service —
# the same Chromium binary, now running with a real windowing
# context, real TLS / HTTP-2 SETTINGS frame, and a fingerprint
# indistinguishable from a real desktop Chrome.
#
# USAGE:
#   bash scripts/start_xvfb.sh &              # default display :99
#   LINKEDIN_XVFB_DISPLAY=:42 bash scripts/start_xvfb.sh &  # custom display
#   XVFB_DRY_RUN=1 bash scripts/start_xvfb.sh # print + exit 0 (no real spawn)
#
# The `XVFB_DRY_RUN=1` mode is the canonical "no live Xvfb in CI"
# contract (the test at `tests/integration/test_start_xvfb.py`
# drives the script in this mode and asserts the `Xvfb :99`
# literal substring).

set -euo pipefail

DISPLAY_NUM="${LINKEDIN_XVFB_DISPLAY:-:99}"
SCREEN="1280x720x24"

if [ "${XVFB_DRY_RUN:-0}" = "1" ]; then
    echo "Xvfb ${DISPLAY_NUM} -ac -screen 0 ${SCREEN} (DRY RUN, no real Xvfb spawned)"
    exit 0
fi

# Spawn Xvfb in the background. `-ac` disables host access control
# (the scraper connects from the same host). `-screen 0 WxHxD` sets
# the default screen; 1280x720x24 is a standard desktop resolution
# that Chromium renders cleanly under Xvfb.
Xvfb "${DISPLAY_NUM}" -ac -screen 0 "${SCREEN}" &
XVFB_PID=$!

# Liveness check: `pgrep -x Xvfb` returns 0 if any Xvfb process
# is running. The 1-second sleep gives Xvfb a moment to initialize
# before the check (Xvfb takes ~100-200ms to come up on most hosts).
sleep 1
if ! pgrep -x Xvfb >/dev/null; then
    echo "Xvfb failed to start on ${DISPLAY_NUM} (pid=${XVFB_PID})" >&2
    exit 1
fi

echo "Xvfb running on ${DISPLAY_NUM} (pid=${XVFB_PID})"
