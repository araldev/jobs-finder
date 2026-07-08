"""CV adaptation module.

Parses user-uploaded CVs, adapts them to job descriptions using LLM,
and generates professional PDF output in Harvard/ATS-friendly format.
"""

from ._parser import (
    HyperlinkEntry,
    extract_cv_data,
    extract_cv_hyperlinks,
    extract_cv_image,
    extract_cv_text,
)

__all__ = [
    "HyperlinkEntry",
    "extract_cv_data",
    "extract_cv_hyperlinks",
    "extract_cv_image",
    "extract_cv_text",
]
