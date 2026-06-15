"""PDF text and image extraction using pdfplumber.

pdfplumber is a BSD-licensed library for extracting text and images
from PDFs, built on top of PDFMiner.
"""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass

import pdfplumber


@dataclass
class CVData:
    """Structured data extracted from a CV PDF."""

    full_text: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    photo_base64: str | None = None


def extract_cv_text(pdf_bytes: bytes) -> CVData:
    """Extract text and metadata from a CV PDF.

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        CVData with full text and any detected contact info.
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = pdf.pages
        full_text_parts: list[str] = []

        for page in pages:
            text = page.extract_text()
            if text:
                full_text_parts.append(text)

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
        )


def extract_cv_image(pdf_bytes: bytes) -> str | None:
    """Extract the first image from a CV PDF as base64.

    Returns the image as a base64-encoded PNG data URL, or None if
    no image is found.
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            images = page.images
            if not images:
                continue

            # Use the first (largest?) image found on the page
            for img_info in images:
                try:
                    raw_data = img_info.get("rawdata")
                    if raw_data is None:
                        continue

                    b64 = base64.b64encode(raw_data).decode("utf-8")
                    return f"data:image/png;base64,{b64}"
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
        "Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao",
        "Málaga", "Murcia", "Cádiz", "Zaragoza", "Palma",
        "Las Palmas", "Santa Cruz", "Valladolid", "Granada",
    ]
    for city in cities:
        if city in text:
            return city

    return None
