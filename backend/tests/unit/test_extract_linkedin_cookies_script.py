"""Pin the script refactor (REQ-LCR-006).

Two assertions:
1. `scripts/extract_linkedin_cookies.py` imports `PlaywrightLinkedInCookieRefresher`
   from `jobs_finder.infrastructure.linkedin.cookie_refresher` — this proves the
   script uses the shared class instead of inlining its own Playwright session.
2. The CLI surface (`--output`, `--wait-seconds`) is unchanged from the pre-refactor
   version — `argparse` parses the same flags.

These pin REQ-LCR-006 against future regression where a developer might revert the
script to its pre-refactor inline Playwright implementation.
"""

from __future__ import annotations

import ast
import runpy
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "extract_linkedin_cookies.py"


def _read_script_source() -> str:
    return _SCRIPT_PATH.read_text(encoding="utf-8")


def _parse_script_ast() -> ast.Module:
    return ast.parse(_read_script_source())


def test_extract_script_uses_new_refresher_class() -> None:
    """`extract_linkedin_cookies.py` imports `PlaywrightLinkedInCookieRefresher`.

    The refactor pulls the login flow out of the script and into the
    `infrastructure.linkedin.cookie_refresher` module. The script is
    now a thin CLI wrapper around `PlaywrightLinkedInCookieRefresher`.
    """
    tree = _parse_script_ast()

    found: list[tuple[str, str]] = []  # (module, name)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == (
            "jobs_finder.infrastructure.linkedin.cookie_refresher"
        ):
            for alias in node.names:
                found.append((node.module, alias.name))

    assert any(name == "PlaywrightLinkedInCookieRefresher" for _, name in found), (
        "extract_linkedin_cookies.py must import PlaywrightLinkedInCookieRefresher "
        "from jobs_finder.infrastructure.linkedin.cookie_refresher (REQ-LCR-006)."
    )


def test_extract_script_does_not_inline_playwright_launch() -> None:
    """The script must NOT directly call `p.chromium.launch(...)`.

    Defense-in-depth: even if the import is preserved, a regression that
    re-inlines the Playwright launch (e.g., to add a feature flag) would
    duplicate the login flow. This AST assertion catches that.
    """
    source = _read_script_source()
    assert "p.chromium.launch" not in source, (
        "extract_linkedin_cookies.py must delegate to PlaywrightLinkedInCookieRefresher "
        "instead of calling p.chromium.launch directly (REQ-LCR-006)."
    )
    assert "async_playwright" not in source, (
        "extract_linkedin_cookies.py must not import async_playwright directly; "
        "use PlaywrightLinkedInCookieRefresher (REQ-LCR-006)."
    )


def test_extract_script_cli_unchanged() -> None:
    """The CLI surface (`--output`, `--wait-seconds`) is preserved.

    Operators running the script from cron or shell aliases depend on
    these flags. A regression that renames or removes them would break
    manual verification flows.
    """
    # The script module-level `argparse.ArgumentParser` must define --output
    # and --wait-seconds. AST inspection is sufficient; we don't execute
    # the script (it would launch Chromium).
    tree = _parse_script_ast()

    flag_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # argparse `add_argument("--output", ...)` or `parser.add_argument(...)`
            if isinstance(func, ast.Attribute) and func.attr == "add_argument":
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and arg.value.startswith("--")
                    ):
                        flag_names.add(arg.value)

    assert "--output" in flag_names, (
        "extract_linkedin_cookies.py must expose --output flag (REQ-LCR-006 CLI compat)."
    )
    assert "--wait-seconds" in flag_names, (
        "extract_linkedin_cookies.py must expose --wait-seconds flag (REQ-LCR-006 CLI compat)."
    )


def test_extract_script_help_includes_flag_descriptions() -> None:
    """The flags have help text (operator UX invariant).

    Without help, operators running `--help` get a bare flag list and
    have to guess intent. We assert each required flag has a `help=`
    keyword argument in the `add_argument` call.
    """
    tree = _parse_script_ast()

    flag_help: dict[str, bool] = {"--output": False, "--wait-seconds": False}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "add_argument":
            continue

        flag_name: str | None = None
        has_help = False
        for arg in node.args:
            if (
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and arg.value.startswith("--")
            ):
                flag_name = arg.value
        for kw in node.keywords:
            if kw.arg == "help" and kw.value is not None:
                has_help = True

        if flag_name in flag_help and has_help:
            flag_help[flag_name] = True

    missing = [f for f, ok in flag_help.items() if not ok]
    assert not missing, f"extract_linkedin_cookies.py flags missing help text: {missing}"


@pytest.mark.parametrize("flag", ["--output", "--wait-seconds"])
def test_extract_script_flag_appears_in_argparse_help_output(
    flag: str,
) -> None:
    """`--help` output for the script mentions each flag.

    End-to-end check via argparse: build the parser from the script
    without executing the login flow, run `--help`, and confirm the
    flag name appears in stdout. This catches both renames and
    accidental removal.
    """
    # Load the script as a module via runpy; we intercept the login flow
    # by NOT calling main(). We call the module-level `_parse_args` with
    # `--help` to exercise the argparse shape end-to-end.
    script_module = runpy.run_path(str(_SCRIPT_PATH), run_name="__not_main__")

    parse_fn = script_module.get("_parse_args")
    assert parse_fn is not None and callable(parse_fn), (
        "extract_linkedin_cookies.py must expose a callable `_parse_args` function."
    )

    import contextlib
    import io

    buf = io.StringIO()
    with (
        contextlib.redirect_stdout(buf),
        contextlib.redirect_stderr(buf),
        pytest.raises(SystemExit),
    ):
        parse_fn(["--help"])

    help_text = buf.getvalue()
    assert flag in help_text, (
        f"extract_linkedin_cookies.py --help output does not mention {flag} "
        f"(REQ-LCR-006). Got:\n{help_text}"
    )
