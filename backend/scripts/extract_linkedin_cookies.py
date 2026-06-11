"""Extract LinkedIn cookies from chromium-browser (system channel).
Matches the exact browser fingerprint the scraper uses.

Usage:
    DISPLAY=:99 uv run python scripts/extract_linkedin_cookies.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime

from playwright.async_api import async_playwright


LINKEDIN_EMAIL = "raul.rodriguez.raul.80@gmail.com"
LINKEDIN_PASSWORD = r"%{>7+3$oBTycQ42}/')l"
COOKIES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "linkedin_cookies.json",
)


async def main() -> None:
    display = os.environ.get("DISPLAY", ":99")
    print(f"[*] DISPLAY={display}")
    print(f"[*] Channel: chromium (system chromium-browser)")
    print(f"[*] Cookies will be saved to: {COOKIES_PATH}")
    print()

    async with async_playwright() as p:
        # ── Launch identical to scraper ──────────────────────────────────
        browser = await p.chromium.launch(
            headless=False,
            channel="chromium",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # ── Go to LinkedIn login ─────────────────────────────────────────
        print("[1/5] Navegando a linkedin.com/login ...")
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        print(f"    → URL actual: {page.url}")

        # ── Fill credentials ─────────────────────────────────────────────
        print("[2/5] Llenando credenciales ...")

        # LinkedIn usa IDs dinámicos. Buscar primer input email/password VISIBLE.
        await asyncio.sleep(2)  # dar tiempo a JS

        email_input = page.locator('input[type="email"]').nth(1)  # visible
        pass_input = page.locator('input[type="password"]').nth(1)  # visible

        await email_input.fill(LINKEDIN_EMAIL)
        await pass_input.fill(LINKEDIN_PASSWORD)
        await page.wait_for_timeout(500)

        # ── Click Sign In ────────────────────────────────────────────────
        print("[3/5] Click en Sign In ...")

        # LinkedIn muestra "Iniciar sesión con Apple" + "Iniciar sesión" — usar exact=True
        signin_btn = page.get_by_role("button", name="Iniciar sesión", exact=True).first
        await signin_btn.wait_for(state="visible", timeout=10000)
        await signin_btn.click()
        print("    → Click enviado. Esperando redirección ...")

        # ── Wait for successful login (poll URL, up to 180s) ─────────────
        login_ok = False
        for attempt in range(180):
            current_url = page.url
            if any(k in current_url for k in ["feed", "jobs", "mynetwork", "notifications", "checkpoint"]):
                login_ok = True
                print(f"    ✅ Redirección detectada en {attempt}s: {current_url[:80]}")
                break
            await asyncio.sleep(1)

        if not login_ok:
            print(f"    ⚠️  Sin redirección después de 180s. URL actual: {page.url}")
            print("    → Continuando con cookies actuales ...")

        print(f"    → URL final: {page.url}")

        # ── Extract cookies ──────────────────────────────────────────────
        print("[4/4] Extrayendo cookies ...")
        cookies = await context.cookies()
        print(f"    → {len(cookies)} cookies extraídas")

        # Save all cookies
        with open(COOKIES_PATH, "w") as f:
            json.dump(cookies, f, indent=2)

        # Show li_at
        li_at = next((c for c in cookies if c["name"] == "li_at"), None)
        if li_at:
            print(f"    ✅ li_at: {li_at['value'][:15]}... (expira: {datetime.fromtimestamp(li_at['expires']).isoformat() if li_at.get('expires') else 'N/A'})")
        else:
            print("    ❌ li_at NO encontrada en cookies extraídas")

        # Show JSESSIONID too
        jsess = next((c for c in cookies if c["name"] == "JSESSIONID"), None)
        if jsess:
            print(f"    ✅ JSESSIONID: {jsess['value'][:15]}...")

        # Show all cookie names
        names = sorted(set(c["name"] for c in cookies))
        print(f"\n    Cookies disponibles ({len(names)}): {', '.join(names)}")

        await browser.close()
        print("\n✨ Listo!")


if __name__ == "__main__":
    asyncio.run(main())
