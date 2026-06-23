"""Extract LinkedIn cookies via the production `PlaywrightLinkedInCookieRefresher`.

This script is the manual fallback for `LinkedInCookieRefresherPort`:
when the auto-refresh path fails (e.g. 2FA checkpoint, network outage,
or the operator's env-var creds are stale), you can run this script
to log in interactively and write a fresh `linkedin_cookies.json`.

The login + cookie extraction logic is now a thin wrapper around
`PlaywrightLinkedInCookieRefresher.refresh()` (REQ-LCR-006). The
class owns the actual Playwright session, the credential injection,
and the post-login URL poll — this script only handles CLI parsing,
JSON persistence, and the diagnostic output the operator wants
when running manually.

Usage:
    DISPLAY=:99 uv run --env-file .env python scripts/extract_linkedin_cookies.py \\
        --output linkedin_cookies.json --wait-seconds 300

Credentials are read from environment variables (or the `--password`
flag — see CLI help):
    LINKEDIN_EMAIL    - LinkedIn login email
    LINKEDIN_PASSWORD - LinkedIn login password

CLI flags:
    --output <path>         Output JSON path (default: ./linkedin_cookies.json)
    --wait-seconds <float>  Max seconds to wait for post-login redirect
                            (default: 300.0). Maps to
                            `LinkedInCookieRefresherSettings.timeout_seconds`.

NOTE — the script does NOT log cookie values. The diagnostic output
shows cookie NAMES only (and the first 15 chars of `li_at` /
`JSESSIONID` for operator convenience — the production refresher
path masks them via `SecretStr`; this script's stdout is the
operator's own terminal, so partial visibility is acceptable).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from pydantic import SecretStr

from jobs_finder.infrastructure.linkedin.cookie_refresher import (
    LinkedInCookieRefresherSettings,
    PlaywrightLinkedInCookieRefresher,
)

DEFAULT_OUTPUT = "linkedin_cookies.json"
DEFAULT_WAIT_SECONDS = 300.0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args. Preserves the spec's `argparse` contract."""
    parser = argparse.ArgumentParser(
        description=(
            "Manually extract LinkedIn session cookies via "
            "Playwright. The login flow delegates to "
            "`PlaywrightLinkedInCookieRefresher`; this script "
            "only handles JSON persistence and CLI ergonomics."
        )
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help=(
            "Output JSON file path for the cookie dicts "
            f"(default: {DEFAULT_OUTPUT!r}). The script writes "
            "the full `context.cookies()` shape (name, value, "
            "domain, path, expires, httpOnly, secure, sameSite) "
            "via `os.replace` for atomicity."
        ),
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=DEFAULT_WAIT_SECONDS,
        help=(
            "Max seconds to wait for the post-login redirect "
            "(default: %(default)s). Maps to "
            "`LinkedInCookieRefresherSettings.timeout_seconds`."
        ),
    )
    return parser.parse_args(argv)


async def _extract_cookies(
    *,
    email: str,
    password: str,
    wait_seconds: float,
) -> list[dict[str, object]] | None:
    """Run `PlaywrightLinkedInCookieRefresher.refresh()`.

    Returns the cookie list on success, `None` on any failure
    (the spec's `refresh()` contract — never raises).
    """
    refresher = PlaywrightLinkedInCookieRefresher(
        LinkedInCookieRefresherSettings(
            enabled=True,
            timeout_seconds=wait_seconds,
            email=SecretStr(email),
            password=SecretStr(password),
            # The production refresher launches Chromium non-headless
            # so the operator can see the browser window (mirrors the
            # v1 script's behavior). Xvfb is the standard way to
            # provide a virtual display in CI / Docker.
            headless=False,
        )
    )
    return await refresher.refresh()


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    email = os.environ.get("LINKEDIN_EMAIL")
    password = os.environ.get("LINKEDIN_PASSWORD")
    if not email or not password:
        print(
            "❌ Error: LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in environment",
            file=sys.stderr,
        )
        print(
            "   Set them in backend/.env or export before running:",
            file=sys.stderr,
        )
        print("     export LINKEDIN_EMAIL='your@email.com'", file=sys.stderr)
        print("     export LINKEDIN_PASSWORD='your_password'", file=sys.stderr)
        return 1

    display = os.environ.get("DISPLAY", ":99")
    print(f"[*] DISPLAY={display}")
    print("[*] Channel: chromium (system chromium-browser)")
    print(f"[*] Cookies will be saved to: {args.output}")
    print(f"[*] Wait timeout: {args.wait_seconds}s")
    print()
    print(
        "[i] Tip — this script is the manual fallback for the auto-refresh "
        "feature. In production, the backend's "
        "`PlaywrightLinkedInCookieRefresher` handles the same flow "
        "automatically when `LINKEDIN_COOKIE_REFRESH_ENABLED=true` AND "
        "credentials are set. See README 'Cookie refresh (auto)' for "
        "the full operator guide.",
    )
    print()

    cookies = await _extract_cookies(
        email=email,
        password=password,
        wait_seconds=args.wait_seconds,
    )
    if cookies is None:
        print(
            "❌ Cookie refresh failed (no cookies returned). The "
            "production refresher swallows all exceptions internally; "
            "check the application logs for the WARNING line that "
            "preceded this script. Common causes: 2FA / SMS "
            "checkpoint, post-login URL never reached /feed or /m/, "
            "or a LinkedIn anti-bot block. Re-run the script after "
            "resolving manually.",
            file=sys.stderr,
        )
        return 1

    # ── Persist cookies atomically (os.replace) ──────────────────────
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = str(output_path) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, output_path)
    print(f"[4/4] Cookies written to {output_path}")
    print(f"    → {len(cookies)} cookies saved")
    # Diagnostic: show the first 15 chars of `li_at` and `JSESSIONID`
    # so the operator can confirm the new session is fresh without
    # exposing the full value.
    li_at = next((c for c in cookies if c.get("name") == "li_at"), None)
    if isinstance(li_at, dict):
        value = li_at.get("value", "")
        expires = li_at.get("expires")
        expires_iso = (
            datetime.fromtimestamp(expires).isoformat()
            if isinstance(expires, (int, float))
            else "N/A"
        )
        if isinstance(value, str):
            print(f"    ✅ li_at: {value[:15]}... (expira: {expires_iso})")
    else:
        print("    ❌ li_at NO encontrada en cookies extraídas")
    jsess = next((c for c in cookies if c.get("name") == "JSESSIONID"), None)
    if isinstance(jsess, dict):
        value = jsess.get("value", "")
        if isinstance(value, str):
            print(f"    ✅ JSESSIONID: {value[:15]}...")
    names = sorted({str(c.get("name", "")) for c in cookies if c.get("name")})
    print(f"\n    Cookies disponibles ({len(names)}): {', '.join(names)}")
    print("\n✨ Listo!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
