"""PDF generation from HTML using weasyprint.

weasyprint converts HTML/CSS to PDF using cairo and pango.
The HTML must be self-contained (all styles inline).
"""

from __future__ import annotations

import io

from weasyprint import HTML  # type: ignore[import-untyped]

from ._template import AdaptedCV


def generate_cv_pdf(cv: AdaptedCV) -> bytes:
    """Render an AdaptedCV to a PDF binary.

    Args:
        cv: Structured CV data with name, experience, education, etc.

    Returns:
        Raw PDF bytes ready to be saved or sent as a response.
    """
    html_string = cv.to_html()

    pdf_buffer = io.BytesIO()
    HTML(string=html_string).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)
    return pdf_buffer.read()
