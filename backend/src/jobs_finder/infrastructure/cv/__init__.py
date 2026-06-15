"""CV adaptation module.

Parses user-uploaded CVs, adapts them to job descriptions using LLM,
and generates professional PDF output in Harvard/ATS-friendly format.
"""

from ._parser import extract_cv_image, extract_cv_text

__all__ = ["extract_cv_text", "extract_cv_image"]
