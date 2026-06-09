"""Bootstrap smoke test for jobs-finder.

This is the seed test that ships with the bootstrap commit (T-001). It exists
only to prove that `uv run pytest`, `uv run mypy`, and `uv run ruff check` are
wired correctly against a real, importable package. Future tasks (T-002 onward)
will REPLACE this file with real TDD-driven tests for the domain, application,
infrastructure, and presentation layers.
"""


def test_smoke() -> None:
    """Trivial assertion that the test runner is operational."""
    assert 1 + 1 == 2
