"""Tests/integration package for jobs-finder.

The integration tests exercise the FastAPI presentation layer end-to-end
through `httpx.AsyncClient(transport=ASGITransport(app=...))`. They use
`FakeJobSearchPort` instead of a real scraper so no browser is launched
and no network call is made.
"""
