"""Architectural guard — ``ruff format --check .`` is enforced, not advisory.

Issue #473's acceptance criterion is "``ruff format --check .`` exits 0 on
``main``, **and stays that way**". Filed against PR #531 (which turned the
whole-repo check green): nothing automated ever invoked that command --

* ``Makefile`` had a ``lint`` target (``ruff check src/``) but no
  ``format-check`` target, and ``src/`` is narrower than the repo anyway;
* ``make test-full`` (the CI agent's target) was pytest only; and
* the planning repo's CI lint step ran ``ruff check`` but never
  ``ruff format``.

So the only thing holding the gate green was manual charter compliance
(``agents/implementer.md``, "the WHOLE repo, not just your files"). The first
unformatted file an implementer adds puts the gate back where #425/#473
found it, with no red signal anywhere (#558).

This guard shells out to the repo's real, pinned ``ruff`` (the same shape
``tests/architectural/test_tid251_enforcement.py`` uses to make TID251
enforced rather than advisory) and asserts ``ruff format --check .`` exits 0.
That puts the gate inside ``make test-full``, so the CI agent's existing
green/red verdict covers it with no change needed to the planning repo's
``bin/ci-run.sh``.

The former formatter-debt exclusion (``[tool.ruff.format].exclude``) and its
shrink-only ratchet (``test_ruff_format_exclude_ratchet.py``, #559) were
retired after #4506 reformatted every live entry and removed the list. The
second guard below encodes the terminal state of that drain, per the
release-owner ruling on spec-kitty/spec-kitty-planning#2433 (2026-09-20,
option 2): the only permanent formatter exclusions left in the repo are the
governed ``kitty-specs/*/research/**`` subtree and exactly five immutable
archive files whose bytes stay frozen, and the debt list itself may not be
recreated.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.architectural]

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The exactly-enumerated immutable archive files the planning#2433 ruling
# keeps out of the formatter permanently (option 2: archive bytes stay
# immutable; test_archive_root_byte_identical.py remains authoritative).
# This tuple is deliberately NOT derived from ruff.toml at runtime -- the
# point of the guard is that the config matches this pinned enumeration, so
# a config edit cannot silently redefine "permanent" for itself.
_ARCHIVED_FORMAT_EXEMPT_FILES: tuple[str, ...] = (
    "kitty-specs/010-workspace-per-work-package-for-parallel-development/tests/integration/test_planning_workflow.py",
    "kitty-specs/phase-3-charter-synthesizer-pipeline-01KPE222/contracts/adapter.py",
    "kitty-specs/refactor-stable-gate-substrate-01KWK3FY/doctrine_content_check.py",
    "kitty-specs/refactor-stable-gate-substrate-01KWK3FY/freeze_converter.py",
    "kitty-specs/unified-charter-bundle-chokepoint-01KP5Q2G/baseline/capture.py",
)

# The one governed pattern exclusion that predates #4506 (see ruff.toml).
_RESEARCH_GLOB = "kitty-specs/*/research/**"


def test_ruff_format_check_is_clean_on_whole_repo() -> None:
    """``ruff format --check .`` must exit 0 -- issue #473's acceptance gate."""
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        "`ruff format --check .` is red on the whole repo -- issue #473's "
        "acceptance gate has regressed. Run `ruff format .` to fix the "
        "offending file(s). The formatter-debt exclusion was retired after "
        "issue #4506 drained it to zero; do not recreate it -- the only "
        "permanent exclusions are ruff.toml's extend-exclude entries guarded "
        "below.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_formatter_debt_exclude_list_stays_drained() -> None:
    """The drained formatter-debt list may not regrow in pyproject.toml.

    ``[tool.ruff.format]`` (with or without an ``exclude``) is gone from
    ``pyproject.toml`` for good: #4506 reformatted every live entry, so a
    new unformatted file must be formatted, not appended to a reborn debt
    list. Ruff silently accepts a config key that shadows nothing, so this
    asserts on the parsed TOML, not on grep output.
    """
    with (_REPO_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert "format" not in pyproject.get("tool", {}).get("ruff", {}), (
        "[tool.ruff.format] reappeared in pyproject.toml -- the formatter-debt "
        "exclusion was retired by #4506 (planning#2433 ruling). Format new "
        "files instead of recreating the list; permanent exclusions belong "
        "in ruff.toml's extend-exclude only."
    )


def test_permanent_format_exclusions_are_exactly_the_enumerated_archives() -> None:
    """ruff.toml's extend-exclude may not grow past the ruled enumeration.

    The planning#2433 ruling (option 2) fixes the permanent formatter-exclusion
    surface at exactly two authorities: the governed ``kitty-specs/*/research/**``
    subtree and the five immutable archive files pinned above. Anything else in
    ``extend-exclude`` is an unruled widening -- a new unformatted file must be
    formatted, not excluded -- and a missing entry here means an archive file
    was silently moved back into formatter scope, which the byte-identical
    gate would then catch as an archive mutation instead.
    """
    with (_REPO_ROOT / "ruff.toml").open("rb") as ruff_toml_file:
        ruff_toml = tomllib.load(ruff_toml_file)

    extend_exclude = ruff_toml.get("extend-exclude", [])
    expected = {_RESEARCH_GLOB, *_ARCHIVED_FORMAT_EXEMPT_FILES}

    assert set(extend_exclude) == expected, (
        "ruff.toml extend-exclude must be exactly the governed research glob "
        "plus the five immutable archive files enumerated by the planning#2433 "
        f"ruling. found: {sorted(set(extend_exclude) - expected)} extra, "
        f"{sorted(expected - set(extend_exclude))} missing"
    )

    missing_on_disk = [entry for entry in _ARCHIVED_FORMAT_EXEMPT_FILES if not (_REPO_ROOT / entry).is_file()]
    assert missing_on_disk == [], (
        "An immutable archive file named by the planning#2433 enumeration no "
        f"longer exists on disk -- update the enumeration only through a new "
        f"ruling, never by deleting the path to make the guard pass. "
        f"missing: {missing_on_disk}"
    )
