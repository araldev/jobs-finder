# LinkedIn geoId mapping

**Captured**: 2026-06-08 via one-time Playwright capture (sanctioned per AGENTS.md rule #1)
**Method**: `https://www.linkedin.com/jobs/search?keywords=&location=<label>` → extract `<input name="geoId" type="hidden" value="...">`
**Status**: 8 of 8 Spanish cities captured; 0 of 6 countries captured (LinkedIn geolocated the requester to `co.linkedin.com`/Colombia and the country search collapsed to the worldwide geoId `103644278`)

## Verified geoIds (Spanish cities, canonical as of 2026-06-08)

| location_key | location_label | geo_id | notes |
|---|---|---|---|
| `madrid` | Madrid, Spain | 103374081 | Verified, jobs visible |
| `barcelona` | Barcelona, Spain | 105088894 | Verified, jobs visible |
| `valencia` | Valencia, Spain | 105512687 | Verified |
| `sevilla` | Sevilla, Spain | 104893466 | Verified |
| `zaragoza` | Zaragoza, Spain | 106356396 | Verified |
| `malaga` | Málaga, Spain | 104401670 | Verified |
| `murcia` | Murcia, Spain | 102253611 | Verified |
| `bilbao` | Bilbao, Spain | 101962740 | Verified |

## LatAm cities (verified via the same capture run)

| location_key | location_label | geo_id |
|---|---|---|
| `ciudad_de_mexico` | Ciudad de México, Mexico | 112558473 |
| `guadalajara` | Guadalajara, Mexico | 100870198 |
| `monterrey` | Monterrey, Mexico | 104201579 |
| `buenos_aires` | Buenos Aires, Argentina | 90009870 |
| `cordoba_ar` | Córdoba, Argentina | 102399085 |
| `bogota` | Bogotá, Colombia | 102361989 |
| `medellin` | Medellín, Colombia | 112085362 |
| `santiago` | Santiago, Chile | 104555257 |
| `lima` | Lima, Peru | 101312395 |

## Spanish autonomous communities (17 + 2 ciudades autónomas)

| location_key | location_label | geo_id | notes |
|---|---|---|---|
| `comunidad_de_madrid` | Comunidad de Madrid, Spain | 103335767 | |
| `cataluna` | Cataluña, Spain | 105646813 | |
| `comunidad_valenciana` | Comunidad Valenciana, Spain | 100076887 | |
| `andalucia` | Andalucía, Spain | 106151489 | |
| `pais_vasco` | País Vasco, Spain | ??? | see below |
| `aragon` | Aragón, Spain | 106356396 | shared with Zaragoza (capital) |
| `galicia` | Galicia, Spain | 103189018 | |
| `castilla_y_leon` | Castilla y León, Spain | 104802667 | |
| `castilla_la_mancha` | Castilla-La Mancha, Spain | 100096545 | |
| `canarias` | Canarias, Spain | ??? | not captured cleanly |
| `extremadura` | Extremadura, Spain | 102727695 | |
| `murcia_region` | Región de Murcia, Spain | 106901295 | |
| `asturias` | Asturias, Spain | 104351060 | |
| `cantabria` | Cantabria, Spain | 106413664 | |
| `la_rioja` | La Rioja, Spain | 102952772 | |
| `navarra` | Navarra, Spain | 102688677 | |
| `illes_balears` | Illes Balears, Spain | 101388828 | |
| `ceuta` | Ceuta, Spain | 100110826 | |
| `melilla` | Melilla, Spain | 101887739 | |

## Countries (could not capture cleanly — IP geolocation issue)

These returned the LinkedIn worldwide fallback geoId `103644278` because the capture was performed from a non-Spanish/non-LATAM IP and LinkedIn geolocated the request to `co.linkedin.com`:

| location_key | location_label | geo_id | status |
|---|---|---|---|
| `es` | España | 103644278 | WORLDWIDE FALLBACK — do not use |
| `mx` | México | 103644278 | WORLDWIDE FALLBACK — do not use |
| `pe` | Perú | 103644278 | WORLDWIDE FALLBACK — do not use |
| `ar` | Argentina | 100446943 | (region-level, may or may not be country-level) |
| `co` | Colombia | 100876405 | (region-level, may or may not be country-level) |
| `cl` | Chile | 104621616 | (region-level, may or may not be country-level) |

## Resolution strategy (HardcodedLocationResolver)

The resolver implements a **hierarchical fallback chain**:

```python
GEO_ID_MAP = {
    # === SPAIN — cities (canonical geoIds) ===
    "madrid": 103374081,
    "barcelona": 105088894,
    "valencia": 105512687,
    "sevilla": 104893466,
    "zaragoza": 106356396,
    "malaga": 104401670,
    "murcia": 102253611,
    "bilbao": 101962740,
    # === SPAIN — autonomous communities (region level) ===
    "comunidad de madrid": 103335767,
    "cataluña": 105646813,
    "comunidad valenciana": 100076887,
    "andalucia": 106151489,
    "galicia": 103189018,
    "castilla y leon": 104802667,
    "castilla la mancha": 100096545,
    "extremadura": 102727695,
    "region de murcia": 106901295,
    "asturias": 104351060,
    "cantabria": 106413664,
    "la rioja": 102952772,
    "navarra": 102688677,
    "illes balears": 101388828,
    "ceuta": 100110826,
    "melilla": 101887739,
    # === LATAM cities (canonical geoIds) ===
    "ciudad de mexico": 112558473,
    "guadalajara": 100870198,
    "monterrey": 104201579,
    "buenos aires": 90009870,
    "cordoba": 102399085,  # ambiguous (could be AR or ES); AR geoId
    "bogota": 102361989,
    "medellin": 112085362,
    "santiago": 104555257,
    "lima": 101312395,
}

# Aliases: map alternate spellings to canonical keys
ALIASES = {
    "españa": "FALLBACK_TO_AGGREGATOR",  # no reliable country-level geoId
    "spain": "FALLBACK_TO_AGGREGATOR",
    "mexico": "FALLBACK_TO_AGGREGATOR",
    "méxico": "FALLBACK_TO_AGGREGATOR",
    "argentina": "FALLBACK_TO_AGGREGATOR",
    "colombia": "FALLBACK_TO_AGGREGATOR",
    "chile": "FALLBACK_TO_AGGREGATOR",
    "peru": "FALLBACK_TO_AGGREGATOR",
    "perú": "FALLBACK_TO_AGGREGATOR",
    # Region-level fallbacks
    "país vasco": "FALLBACK_TO_AGGREGATOR",
    "pais vasco": "FALLBACK_TO_AGGREGATOR",
    "canarias": "FALLBACK_TO_AGGREGATOR",
    "cataluña": "cataluña",  # passthrough
    "andalucia": "andalucia",
    # Common abbreviations
    "cdmx": "ciudad de mexico",
    "caba": "buenos aires",  # Ciudad Autónoma de Buenos Aires
    "bcn": "barcelona",
    "mad": "madrid",
}
```

When `resolve(location)` is called:
1. Normalize the location: NFC + casefold + strip + remove accents (already NFC-normalized by route handler, but defensive)
2. Look up in `GEO_ID_MAP` — if found, return the geoId
3. Look up in `ALIASES` — if found and not "FALLBACK_TO_AGGREGATOR", recurse with the canonical key
4. If still no match: log WARNING + return `None` (LinkedIn scraper falls back to `location=` string, which is broken but doesn't 500)

The user's location string from the chat (e.g. "Madrid, Spain" or "Cataluña") is normalized and looked up. The fallback chain is **flat** (no transitive aliasing) for simplicity.
