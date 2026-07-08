"""PDF text and image extraction using PyMuPDF.

PyMuPDF (fitz) is used for both text and image extraction because it
preserves PDF reading order better than pdfplumber for complex layouts
(multi-column, tables, mixed content).

The `cv-link-preservation` change adds hyperlink extraction: each
PDF page is also scanned for `LINK_URI` annotations so the REAL URLs
embedded as PDF link annotations are preserved verbatim (instead of
being invented by the LLM). See design §3.3 + spec REQ-CLP-001.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

import pymupdf


@dataclass(frozen=True)
class HyperlinkEntry:
    """A single hyperlink extracted from the original CV PDF.

    Pairs the visible label (text at the link's bounding rect) with
    the URL it points to. Used by the LLM prompt (Approach A — the
    HYPERLINKS MAP section) AND by the post-processor (Approach B —
    `substitute_hyperlinks_in_cv`) to preserve the original CV's
    hyperlink targets verbatim instead of letting the LLM invent them.

    Attributes:
        label: Visible text at the link's bounding rect, words
            concatenated in reading order with single spaces. Empty
            when the link is icon-only (the algorithm skips those).
        url: Full URI from the PDF annotation (verbatim from PyMuPDF).
            Guaranteed to start with `http://` or `https://`.
        page: 1-indexed page number where the link lives.
    """

    label: str
    url: str
    page: int


@dataclass
class CVData:
    """Structured data extracted from a CV PDF."""

    full_text: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    photo_base64: str | None = None
    # PDF hyperlink annotations (label + URL + page). Empty for CVs
    # that have no link annotations or that the algorithm filtered out
    # (non-URI kinds, mailto:, icon-only). Per REQ-CLP-006: backward-
    # compatible — old callers that don't populate this field get [].
    hyperlinks: list[HyperlinkEntry] = field(default_factory=list)


# PDF link kind constants — PyMuPDF exposes these as ints (1=GOTO,
# 2=URI, 3=LAUNCH, 4=NAMED). We pin the integer for the URI filter so
# the parser doesn't accidentally drift across PyMuPDF versions where
# the LAUNCH kind was renumbered to 5.
_LINK_URI: int = 2


def extract_cv_text(pdf_bytes: bytes) -> CVData:
    """Extract text, metadata, and hyperlinks from a CV PDF.

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        CVData with full text, detected contact info, and the list of
        hyperlink annotations (label + URL + page) extracted from the
        PDF's link annotations. Hyperlinks are extracted in the same
        page loop as the text (single PDF read — no perf regression).
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    full_text_parts: list[str] = []
    hyperlinks: list[HyperlinkEntry] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()  # type: ignore[no-untyped-call]
        if text:
            full_text_parts.append(text)
        hyperlinks.extend(_extract_page_hyperlinks(page, page_num))

    doc.close()  # type: ignore[no-untyped-call]
    full_text = "\n\n".join(full_text_parts)

    name = _extract_name(full_text)
    email = _extract_email(full_text)
    phone = _extract_phone(full_text)
    location = _extract_location(full_text)

    return CVData(
        full_text=full_text,
        name=name,
        email=email,
        phone=phone,
        location=location,
        hyperlinks=hyperlinks,
    )


def extract_cv_hyperlinks(pdf_bytes: bytes) -> list[HyperlinkEntry]:
    """Extract hyperlinks from a CV PDF using PyMuPDF.

    Per design §3.3 + spec REQ-CLP-001:
      1. Open PDF, iterate pages.
      2. Per page: `links = page.get_links()`.
      3. Filter: `kind == LINK_URI` AND `uri.startswith(("http://", "https://"))`.
      4. For each kept link, intersect word centers with `link["from"]`
         rect to derive the visible label.
      5. Skip degenerate rects (zero area), icon-only links (no text
         at the rect), and links with empty URI.

    Returns:
        List of `HyperlinkEntry(label, url, page)` in reading order
        (page 1 first, then page 2, etc.). Empty when the PDF has no
        qualifying hyperlink annotations.
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    hyperlinks: list[HyperlinkEntry] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        hyperlinks.extend(_extract_page_hyperlinks(page, page_num))

    doc.close()  # type: ignore[no-untyped-call]
    return hyperlinks


def extract_cv_data(pdf_bytes: bytes) -> CVData:
    """Extract all CV data (text + hyperlinks) from a PDF.

    Convenience wrapper around `extract_cv_text` (which now also
    populates `hyperlinks`). The wrapper exists so the use case can
    import a single name; future schema growth stays backwards-
    compatible (e.g. splitting text + image extraction into two passes).

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        CVData with `full_text`, contact info, AND `hyperlinks`.
    """
    return extract_cv_text(pdf_bytes)


def _extract_page_hyperlinks(
    page: pymupdf.Page,
    page_num: int,
) -> list[HyperlinkEntry]:
    """Extract hyperlink entries from a single PDF page.

    Internal helper shared by `extract_cv_text` and
    `extract_cv_hyperlinks` so the page loop is the same code path.
    Uses the center-point intersection algorithm from explore #853
    §2.3 (empirically verified against PyMuPDF 1.27.2.3).
    """
    entries: list[HyperlinkEntry] = []
    try:
        links = page.get_links()
    except Exception:
        return entries
    words = page.get_text("words")  # type: ignore[no-untyped-call]

    for link in links:
        if link.get("kind") != _LINK_URI:
            continue
        uri = link.get("uri", "")
        if not isinstance(uri, str) or not uri:
            continue
        if not (uri.startswith("http://") or uri.startswith("https://")):
            continue
        from_rect = link.get("from")
        if from_rect is None:
            continue
        # Skip degenerate rects (zero area).
        if from_rect.x0 == from_rect.x1 and from_rect.y0 == from_rect.y1:
            continue
        label = _derive_link_label(from_rect, words)
        if not label:
            # Icon-only link — no visible text at the rect.
            continue
        entries.append(HyperlinkEntry(label=label, url=uri, page=page_num + 1))
    return entries


def _derive_link_label(
    rect: pymupdf.Rect,
    words: list[tuple[float, float, float, float, str, int, int, int]],
) -> str:
    """Find the visible text inside `rect` by center-point intersection.

    Returns the matched words concatenated in reading order with
    single spaces. Returns "" when no word's center falls inside the
    rect (icon-only link case).
    """
    parts: list[str] = []
    for w in words:
        # Word tuple shape: (x0, y0, x1, y1, text, block_no, line_no, word_no)
        wx0, wy0, wx1, wy1, wtext = w[0], w[1], w[2], w[3], w[4]
        if not isinstance(wtext, str) or not wtext.strip():
            continue
        cx = (wx0 + wx1) / 2.0
        cy = (wy0 + wy1) / 2.0
        if rect.x0 <= cx <= rect.x1 and rect.y0 <= cy <= rect.y1:
            parts.append(wtext.strip())
    return " ".join(parts)


def extract_cv_image(pdf_bytes: bytes) -> str | None:
    """Extract the first photo/image from a CV PDF as base64 PNG.

    Uses PyMuPDF (fitz) which handles more PDF image formats than
    pdfplumber.  Returns the image as a base64-encoded PNG data URL,
    or None if no image is found.

    The 4 KB threshold (was 10 KB) matches the TypeScript frontend's
    `MIN_IMAGE_BYTES` constant so a small CV photo (e.g. a 5 KB
    passport-style headshot) is NOT silently dropped just because
    it's smaller than a full-resolution photo. The threshold only
    filters out genuinely tiny images (favicons, social icons,
    inline logos).
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception:
        return None

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Get all images on this page
        image_list = page.get_images(full=True)  # type: ignore[no-untyped-call]
        for _img_index, img in enumerate(image_list):
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)  # type: ignore[no-untyped-call]
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                # Filter out tiny images (likely icons/logos, not a photo)
                if len(image_bytes) < 4_000:
                    continue
                b64 = base64.b64encode(image_bytes).decode("utf-8")
                mime = f"image/{image_ext}"
                if image_ext in ("jpeg", "jpg"):
                    mime = "image/jpeg"
                elif image_ext == "png":
                    mime = "image/png"
                return f"data:{mime};base64,{b64}"
            except Exception:
                continue

    return None


def _extract_name(text: str) -> str | None:
    """Best-effort name extraction: first non-empty line."""
    for line in text.split("\n")[:5]:
        cleaned = line.strip()
        if cleaned and len(cleaned) < 60 and "@" not in cleaned:
            # Looks like a name: short, no email
            return cleaned
    return None


def _extract_email(text: str) -> str | None:
    """Extract email address from text."""
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    return match.group(0) if match else None


def _extract_phone(text: str) -> str | None:
    """Extract phone number from text."""
    # Spanish phone patterns: +34, 6xx, 9xx, with or without spaces/dots/dashes
    patterns = [
        r"\+34\s?[67]\d{2}\s?[0-9]{3}\s?[0-9]{3}",  # +34 612 345 678
        r"\+34[67]\d{9}",  # +34612345678
        r"0034\s?[67]\d{2}\s?[0-9]{3}\s?[0-9]{3}",
        r"[67]\d{2}\s?[0-9]{3}\s?[0-9]{3}",  # 612 345 678
        r"[69]\d{9}",  # 612345678
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def _extract_location(text: str) -> str | None:
    """Best-effort location extraction: look for city names or postal codes."""
    # Spanish postal codes: 28001, 28002, etc.
    postal_match = re.search(r"\b28\d{3}\b", text)
    if postal_match:
        return postal_match.group(0)

    # Common Spanish cities
    cities = [
        "Madrid",
        "Barcelona",
        "Valencia",
        "Sevilla",
        "Bilbao",
        "Málaga",
        "Murcia",
        "Cádiz",
        "Zaragoza",
        "Palma",
        "Las Palmas",
        "Santa Cruz",
        "Valladolid",
        "Granada",
    ]
    for city in cities:
        if city in text:
            return city

    return None
