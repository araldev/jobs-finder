#!/usr/bin/env python3
"""
One-time Playwright capture for LinkedIn geoIds.

Sanctioned by AGENTS.md rule #1 (live scraping only via sanctioned one-time
captures; this is a fixture-creation script, not a CI test).

USAGE
-----
1. From the project root, run:
       uv run python scripts/capture_linkedin_geo_ids.py

2. The script opens a headless Chromium, visits LinkedIn's public job search
   for each location in the LOCATION_LIST, extracts the `geoId` from the HTML
   (`<input name="geoId" type="hidden" value="...">`), and writes the mapping
   to stdout (CSV) and to `tests/fixtures/linkedin_geo_ids.csv`.

3. Copy the mapping into the next change's hardcoded resolver.

WHY A SCRIPT (not just webfetch)
--------------------------------
- LinkedIn's public search page works for guest browsing (no auth required)
  when accessed from a browser (not a raw HTTP request). Playwright mimics
  a browser; raw `httpx`/`curl` would get a stripped-down response.
- LinkedIn geolocates the response based on the requester's IP. A
  `webfetch` from a US-based fetch server will get US-targeted pages even
  for Spanish locations. A local Playwright run from the user's actual
  machine gets the correct geolocated response.
- The script uses Chromium with `headless=True` and a normal User-Agent
  (mirroring what the project's LinkedIn scraper uses in production).

LOCATIONS COVERED
-----------------
- 17 autonomous communities of Spain (comunidades autónomas)
- 2 autonomous cities (Ceuta + Melilla)
- Top 5-10 Spanish cities (Madrid, Barcelona, Valencia, Sevilla, etc.)
- Top 5-10 Latin American countries + cities (México, Argentina, Colombia,
  Chile, Perú, etc.)
- "Remote" / "Anywhere" sentinel geoIds (LinkedIn's `f_WT=2` filter)

OUTPUT FORMAT
-------------
CSV with columns: `location_key, location_label, geo_id, source_url, captured_at`
where:
- `location_key`: canonical lowercase key used by the resolver (e.g. "madrid",
  "barcelona", "es", "mx")
- `location_label`: human-readable label (e.g. "Madrid, Spain", "España")
- `geo_id`: the LinkedIn geoId as a string (LinkedIn uses 9-digit IDs; string
  avoids 32-bit int overflow concerns)
- `source_url`: the URL that was visited to extract the geoId
- `captured_at`: ISO 8601 UTC timestamp
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

# Canonical location keys → human-readable label for the LinkedIn search.
# Order matters: cities are listed before the country they belong to, so
# the canonical resolver prefers cities (e.g. "madrid" before "es").
LOCATION_LIST: list[tuple[str, str]] = [
    # === ESPAÑA — 17 comunidades autónomas + 2 ciudades autónomas ===
    # Ciudades principales
    ("madrid", "Madrid, Spain"),
    ("barcelona", "Barcelona, Spain"),
    ("valencia", "Valencia, Spain"),
    ("sevilla", "Sevilla, Spain"),
    ("zaragoza", "Zaragoza, Spain"),
    ("malaga", "Málaga, Spain"),
    ("murcia", "Murcia, Spain"),
    ("bilbao", "Bilbao, Spain"),
    # Comunidades autónomas (region-level)
    ("comunidad_de_madrid", "Comunidad de Madrid, Spain"),
    ("cataluna", "Cataluña, Spain"),
    ("comunidad_valenciana", "Comunidad Valenciana, Spain"),
    ("andalucia", "Andalucía, Spain"),
    ("pais_vasco", "País Vasco, Spain"),
    ("aragon", "Aragón, Spain"),
    ("galicia", "Galicia, Spain"),
    ("castilla_y_leon", "Castilla y León, Spain"),
    ("castilla_la_mancha", "Castilla-La Mancha, Spain"),
    ("canarias", "Canarias, Spain"),
    ("extremadura", "Extremadura, Spain"),
    ("murcia_region", "Región de Murcia, Spain"),
    ("asturias", "Asturias, Spain"),
    ("cantabria", "Cantabria, Spain"),
    ("la_rioja", "La Rioja, Spain"),
    ("navarra", "Navarra, Spain"),
    ("illes_balears", "Illes Balears, Spain"),
    # Ciudades autónomas
    ("ceuta", "Ceuta, Spain"),
    ("melilla", "Melilla, Spain"),
    # País
    ("es", "España"),
    # === LATAM ===
    # México
    ("ciudad_de_mexico", "Ciudad de México, Mexico"),
    ("guadalajara", "Guadalajara, Mexico"),
    ("monterrey", "Monterrey, Mexico"),
    ("mx", "México"),
    # Argentina
    ("buenos_aires", "Buenos Aires, Argentina"),
    ("cordoba_ar", "Córdoba, Argentina"),
    ("ar", "Argentina"),
    # Colombia
    ("bogota", "Bogotá, Colombia"),
    ("medellin", "Medellín, Colombia"),
    ("co", "Colombia"),
    # Chile
    ("santiago", "Santiago, Chile"),
    ("cl", "Chile"),
    # Perú
    ("lima", "Lima, Peru"),
    ("pe", "Perú"),
    # === REMOTE / ANYWHERE ===
    # Sentinel for "remote work anywhere" — the linkedin remote filter uses
    # f_WT=2 but the geoId for "worldwide remote" is a special value
    # (LinkedIn's `https://www.linkedin.com/jobs/search?f_WT=2` is the
    # canonical "remote" landing; we'll capture the geoId if the
    # `worldwide` search has one, or use a sentinel)
    ("remote", "Remote / Anywhere (worldwide)"),
]


def extract_geo_id(html: str) -> str | None:
    """Parse the geoId from LinkedIn's public job search HTML.

    The geoId is always in a hidden input:
        <input name="geoId" type="hidden" value="103374081"/>

    Sometimes the value is empty if the location wasn't resolved (e.g. the
    search auto-redirected to a different page). In that case, return None.
    """
    # Use a simple regex; BeautifulSoup is overkill for a single input field.
    match = re.search(r'<input name="geoId" type="hidden" value="(\d+)"', html)
    if match:
        return match.group(1)
    # Also try the form action variant (less common)
    match = re.search(r"geoId=(\d+)", html)
    if match:
        return match.group(1)
    return None


def main() -> int:
    output_csv = Path(__file__).parent.parent / "tests" / "fixtures" / "linkedin_geo_ids.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    captured_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
        )
        page = context.new_page()

        for key, label in LOCATION_LIST:
            encoded_label = label.replace(" ", "+").replace(",", "%2C")
            url = f"https://www.linkedin.com/jobs/search?keywords=&location={encoded_label}"
            print(f"Capturing {key!r} ({label}) ...", file=sys.stderr)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                # Give LinkedIn a moment to render the hidden input
                page.wait_for_selector('input[name="geoId"]', timeout=5000)
                html = page.content()
                geo_id = extract_geo_id(html)
                if geo_id:
                    rows.append(
                        {
                            "location_key": key,
                            "location_label": label,
                            "geo_id": geo_id,
                            "source_url": page.url,
                            "captured_at": captured_at,
                        }
                    )
                    print(f"  → geoId={geo_id}", file=sys.stderr)
                else:
                    print(
                        "  → NO geoId found in HTML (page may have auto-redirected)",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(f"  → ERROR: {exc}", file=sys.stderr)

        browser.close()

    # Write CSV
    with output_csv.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["location_key", "location_label", "geo_id", "source_url", "captured_at"],
        )
        writer.writeheader()
        writer.writerows(rows)

    # Also print CSV to stdout for easy copy-paste
    print(f"\n# Captured {len(rows)} of {len(LOCATION_LIST)} locations → {output_csv}\n")
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=["location_key", "location_label", "geo_id", "source_url", "captured_at"],
    )
    writer.writeheader()
    writer.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
