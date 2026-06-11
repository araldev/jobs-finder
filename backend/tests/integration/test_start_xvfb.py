"""Tests for `backend/scripts/start_xvfb.sh` (T-003 of `backend-linkedin-xvfb`).

Spec: REQ-LXV-004 — the Xvfb helper script exists, is
executable, and starts `Xvfb :99 -ac -screen 0 1280x720x24` with
a liveness check. The test pins 3 properties:

  1. The file exists at `backend/scripts/start_xvfb.sh`
     (relative to the repo root).
  2. The file is executable (`os.access(path, os.X_OK) is True`).
  3. A dry-run invocation (`XVFB_DRY_RUN=1 bash scripts/start_xvfb.sh`)
     exits 0 and prints the literal `Xvfb :99` substring.

The dry-run mode is the canonical "no live Xvfb spawned in CI"
contract. The test NEVER spawns a real Xvfb process; it only
asserts the file's existence + executable bit + dry-run output.

The script is a 12-line POSIX shell file (per design §3 T-003
step 3). The 3 assertions are independent so a regression that
breaks the executable bit, the path, OR the dry-run output
surfaces here.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _start_xvfb_path() -> Path:
    """Return the absolute path to `backend/scripts/start_xvfb.sh`."""
    # `tests/integration/test_start_xvfb.py` → `tests/integration/`
    # → `tests/` → `backend/` → `scripts/start_xvfb.sh`.
    return Path(__file__).resolve().parents[2] / "scripts" / "start_xvfb.sh"


def test_start_xvfb_sh_exists_and_is_executable() -> None:
    """REQ-LXV-004 — `backend/scripts/start_xvfb.sh` exists, is executable, dry-runs OK.

    The 3 assertions (independent; each is its own regression
    surface):

    1. `os.access(path, os.X_OK)` is `True` — the file has the
       executable bit set (`chmod +x scripts/start_xvfb.sh`).
       A regression that drops the bit would break supervisor-
       invocations (`bash scripts/start_xvfb.sh &` works
       regardless, but `systemd`'s `ExecStart=` requires the bit).
    2. The file is non-empty — a regression to an empty file
       (e.g. an interrupted write) would pass the executable
       check but fail the dry-run.
    3. `XVFB_DRY_RUN=1 bash scripts/start_xvfb.sh` exits 0 AND
       prints `Xvfb :99` — the dry-run mode is the canonical
       "no real Xvfb spawned in CI" contract (per the design's
       `set -euo pipefail` + `XVFB_DRY_RUN` sentinel).
    """
    path = _start_xvfb_path()
    # Assertion 1: file exists.
    assert path.exists(), f"start_xvfb.sh not found at {path}"
    # Assertion 2: file is executable.
    assert os.access(path, os.X_OK), f"start_xvfb.sh is not executable: {path}"
    # Assertion 3: file is non-empty.
    assert path.stat().st_size > 0, f"start_xvfb.sh is empty: {path}"
    # Assertion 4: dry-run mode exits 0 and prints `Xvfb :99`.
    result = subprocess.run(
        ["bash", str(path)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "XVFB_DRY_RUN": "1"},
        timeout=10,
    )
    assert result.returncode == 0, (
        f"start_xvfb.sh dry-run exited {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    # The dry-run output MUST contain the literal `Xvfb :99`
    # substring (the design's documented incantation).
    assert "Xvfb :99" in result.stdout, (
        f"start_xvfb.sh dry-run output missing 'Xvfb :99': {result.stdout!r}"
    )
