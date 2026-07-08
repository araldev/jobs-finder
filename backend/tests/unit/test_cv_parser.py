"""Unit tests for `cv._parser` hyperlink extraction.

The change `cv-link-preservation` adds `extract_cv_hyperlinks()` to
the PDF parser so the ORIGINAL PDF's hyperlink URLs (the real URLs
embedded as PDF link annotations) are preserved verbatim instead of
being invented by the LLM.

PyMuPDF is used for both text and link extraction. We construct
minimal PDFs in-test via `pymupdf.open()` + `page.insert_link()` so
the suite stays offline (no live scraping — AGENTS.md convention #1).

Per design §3.3 of `cv-link-preservation` (extraction algorithm) +
spec REQ-CLP-001 (scenario matrix).
"""

from __future__ import annotations

import pymupdf

from jobs_finder.infrastructure.cv._parser import (
    CVData,
    HyperlinkEntry,
    extract_cv_data,
    extract_cv_hyperlinks,
    extract_cv_text,
)

# ── PDF builder helpers ─────────────────────────────────────────


def _make_pdf_with_links(
    links: list[tuple[str, str, tuple[float, float, float, float]]],
    extra_text_blocks: list[tuple[str, tuple[float, float, float, float]]] | None = None,
) -> bytes:
    """Build a minimal 1-page PDF with the given hyperlinks.

    Args:
        links: list of `(label, url, rect)` tuples. The rect is the
            bounding box for the link annotation AND the text label.
            PyMuPDF uses top-left-origin coordinates in PDF points.
        extra_text_blocks: optional list of `(text, rect)` to write to
            the page BEFORE inserting the links (used by tests that
            want text at a different rect than the link — e.g.
            icon-only link cases where the link rect has no text).
    """
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page(width=612, height=792)  # Letter size

    # Write labels first so the link rects overlap visible glyphs.
    for label, _url, rect in links:
        page.insert_text(
            (rect[0], rect[3] - 4),  # baseline ~4pt above bottom
            label,
            fontsize=11,
        )
    if extra_text_blocks is not None:
        for text, rect in extra_text_blocks:
            page.insert_text(
                (rect[0], rect[3] - 4),
                text,
                fontsize=11,
            )

    # Insert link annotations.
    for _label, url, rect in links:
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(*rect),  # type: ignore[no-untyped-call]
                "uri": url,
            }
        )

    pdf_bytes = doc.tobytes()  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    return pdf_bytes  # type: ignore[no-any-return]


# ── extract_cv_hyperlinks ────────────────────────────────────────


class TestExtractCVHyperlinks:
    """PyMuPDF-driven extraction of `(label, url, page)` triples."""

    def test_no_annotations_returns_empty(self) -> None:
        # Plain PDF, no links at all.
        doc = pymupdf.open()  # type: ignore[no-untyped-call]
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "plain text, no links", fontsize=11)
        pdf_bytes = doc.tobytes()  # type: ignore[no-untyped-call]
        doc.close()  # type: ignore[no-untyped-call]

        assert extract_cv_hyperlinks(pdf_bytes) == []

    def test_single_http_link_extracted(self) -> None:
        pdf_bytes = _make_pdf_with_links(
            links=[
                ("Github", "https://github.com/u/v", (50.0, 50.0, 200.0, 70.0)),
            ],
        )
        result = extract_cv_hyperlinks(pdf_bytes)
        assert len(result) == 1
        entry = result[0]
        assert isinstance(entry, HyperlinkEntry)
        assert entry.label == "Github"
        assert entry.url == "https://github.com/u/v"
        assert entry.page == 1

    def test_three_http_links_extracted(self) -> None:
        # The user's typical case: V12-UI project with 3 chips.
        pdf_bytes = _make_pdf_with_links(
            links=[
                ("Github link", "https://github.com/u/v12-ui", (50.0, 50.0, 200.0, 70.0)),
                (
                    "Storybook link",
                    "https://storybook.js.org/?path=/story/v12-ui",
                    (50.0, 80.0, 250.0, 100.0),
                ),  # noqa: E501
                ("npm link", "https://www.npmjs.com/package/v12-ui", (50.0, 110.0, 200.0, 130.0)),
            ],
        )
        result = extract_cv_hyperlinks(pdf_bytes)
        assert len(result) == 3
        assert [(e.label, e.url) for e in result] == [
            ("Github link", "https://github.com/u/v12-ui"),
            ("Storybook link", "https://storybook.js.org/?path=/story/v12-ui"),
            ("npm link", "https://www.npmjs.com/package/v12-ui"),
        ]
        assert all(e.page == 1 for e in result)

    def test_internal_goto_link_dropped(self) -> None:
        # Only a LINK_GOTO (internal page-jump) annotation → empty.
        doc = pymupdf.open()  # type: ignore[no-untyped-call]
        page = doc.new_page(width=612, height=792)
        page.insert_link(
            {
                "kind": pymupdf.LINK_GOTO,
                "from": pymupdf.Rect(50.0, 50.0, 200.0, 70.0),  # type: ignore[no-untyped-call]
                "page": 0,
                "to": pymupdf.Point(0, 0),  # type: ignore[no-untyped-call]
            }
        )
        pdf_bytes = doc.tobytes()  # type: ignore[no-untyped-call]
        doc.close()  # type: ignore[no-untyped-call]

        assert extract_cv_hyperlinks(pdf_bytes) == []

    def test_mailto_link_dropped(self) -> None:
        # mailto: scheme is NOT http(s) → dropped.
        pdf_bytes = _make_pdf_with_links(
            links=[
                ("Email me", "mailto:foo@bar.com", (50.0, 50.0, 200.0, 70.0)),
            ],
        )
        assert extract_cv_hyperlinks(pdf_bytes) == []

    def test_icon_only_link_skipped(self) -> None:
        # A link rect exists but NO text is at that rect (icon-only link
        # like a social-media glyph). Algorithm must skip it because
        # the chip would have no label to pair with the URL.
        # Build a PDF where the link's rect (50,50,80,70) has NO text,
        # while an unrelated text block lives at (200, 200, 400, 220).
        pdf_bytes = _make_pdf_with_links(
            links=[
                # Use a label that's clearly NOT inside the link rect;
                # we then manually move/erase it via extra_text_blocks.
                # Simplest approach: write the label at a DIFFERENT rect.
                ("REMOVE_ME", "https://github.com/icon", (50.0, 50.0, 80.0, 70.0)),
            ],
            extra_text_blocks=[
                # Real text lives somewhere else — NOT inside the link rect.
                ("Section header", (200.0, 200.0, 400.0, 220.0)),
            ],
        )
        # We wrote "REMOVE_ME" inside the link rect; for the icon-only
        # test we need to ensure the algorithm sees no word centered
        # inside the link rect. PyMuPDF's text glyphs are written at
        # the link's bottom-4 baseline. The word center for "REMOVE_ME"
        # would land INSIDE the rect (50,50,80,70). To get a true
        # icon-only link, re-derive by writing text FAR from the rect.
        # Easier: build manually.
        doc = pymupdf.open()  # type: ignore[no-untyped-call]
        page = doc.new_page(width=612, height=792)
        # Text FAR from the link rect.
        page.insert_text((400, 400), "Far away text", fontsize=11)
        # Link rect with NO text under it.
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(50.0, 50.0, 80.0, 70.0),  # type: ignore[no-untyped-call]
                "uri": "https://github.com/icon",
            }
        )
        pdf_bytes = doc.tobytes()  # type: ignore[no-untyped-call]
        doc.close()  # type: ignore[no-untyped-call]

        assert extract_cv_hyperlinks(pdf_bytes) == []


# ── CVData.hyperlinks field ─────────────────────────────────────


class TestCVDataHyperlinksField:
    """`extract_cv_text` now also populates `cv_data.hyperlinks`."""

    def test_extract_cv_text_populates_hyperlinks(self) -> None:
        pdf_bytes = _make_pdf_with_links(
            links=[
                ("Github", "https://github.com/u/v", (50.0, 50.0, 200.0, 70.0)),
                ("Storybook", "https://sb.com/u/v", (50.0, 80.0, 200.0, 100.0)),
            ],
        )
        cv_data = extract_cv_text(pdf_bytes)
        assert isinstance(cv_data, CVData)
        assert len(cv_data.hyperlinks) == 2
        assert {(e.label, e.url) for e in cv_data.hyperlinks} == {
            ("Github", "https://github.com/u/v"),
            ("Storybook", "https://sb.com/u/v"),
        }

    def test_extract_cv_text_no_links_yields_empty_hyperlinks(self) -> None:
        # PDF with text but no link annotations.
        doc = pymupdf.open()  # type: ignore[no-untyped-call]
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), "Plain CV text — no hyperlinks anywhere", fontsize=11)
        pdf_bytes = doc.tobytes()  # type: ignore[no-untyped-call]
        doc.close()  # type: ignore[no-untyped-call]

        cv_data = extract_cv_text(pdf_bytes)
        assert cv_data.hyperlinks == []

    def test_cv_data_hyperlinks_default_is_empty_list(self) -> None:
        # Backward compat: constructing CVData without the new field
        # MUST yield `hyperlinks=[]` (not an AttributeError).
        cv = CVData(full_text="just text")
        assert cv.hyperlinks == []


# ── extract_cv_data wrapper ──────────────────────────────────────


class TestExtractCVDataWrapper:
    """`extract_cv_data(pdf_bytes)` returns a `CVData` with hyperlinks
    populated. Currently an alias for `extract_cv_text` (which now
    also extracts hyperlinks) — the wrapper exists so the use case
    can import a single name and so future schema growth stays
    backwards-compatible (e.g. splitting text + image extraction)."""

    def test_returns_cv_data(self) -> None:
        pdf_bytes = _make_pdf_with_links(
            links=[
                ("Demo", "https://demo.example.com", (50.0, 50.0, 200.0, 70.0)),
            ],
        )
        cv_data = extract_cv_data(pdf_bytes)
        assert isinstance(cv_data, CVData)
        assert cv_data.full_text  # non-empty
        assert len(cv_data.hyperlinks) == 1
        assert cv_data.hyperlinks[0].label == "Demo"
        assert cv_data.hyperlinks[0].url == "https://demo.example.com"
