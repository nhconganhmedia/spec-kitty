#!/usr/bin/env python3
"""The ci-router.yml ``changes`` job's prose-only step (spec-kitty#4842).

Prints ``true``/``false`` (exit 0) for one question: is this diff PROVEN
comment/docstring-only (prose-only) in every changed ``.py`` file, with every
other changed path documentation? The verdict is computed by the single
gate-selection authority (:func:`scripts.ci.gate_selection.prose_only_verdict`)
— this script contributes no routing knowledge of its own; it only gathers
the evidence (the changed-path list and each changed ``.py``'s base/head blob
text, via git) and prints the authority's answer.

Fail-closed by construction: ANY doubt — no resolvable base SHA (dispatch,
first push, force push), an unfetchable base, a git failure, an undecodable
blob, a parse error, a real code change anywhere, any non-documentation
non-``.py`` file — prints ``false``, and ``false`` routes exactly as today.

Invocation (from the repo root of the checked-out head)::

    python3 scripts/ci/prose_only_step.py <base-sha> <head-sha>

The changed-path set is the plain two-dot ``git diff --name-only base head``
— the same idiom ci-modules.yml's changed-files step uses for module
scoping, so both prose consumers classify the same diff the same way.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ci.gate_selection import load_router, prose_only_verdict  # noqa: E402

__all__ = ["changed_paths", "collect_py_blobs", "main", "py_blob_text"]


def _git(args: list[str], *, repo_root: Path) -> subprocess.CompletedProcess[bytes]:
    """Run git in *repo_root*, byte output, never raising."""
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, timeout=60, check=False)


def changed_paths(base: str, head: str, *, repo_root: Path | None = None) -> list[str] | None:
    """The two-dot changed-path list, or ``None`` on any git failure."""
    proc = _git(["diff", "--name-only", base, head], repo_root=repo_root or _REPO_ROOT)
    if proc.returncode != 0:
        return None
    return [line for line in proc.stdout.decode("utf-8", errors="replace").splitlines() if line]


def py_blob_text(rev_path: str, *, repo_root: Path | None = None) -> str | None:
    """One blob's text (``git show <rev>:<path>``), or ``None`` on any doubt.

    ``None`` — an unfetchable blob (added/deleted file), a non-UTF-8 blob, a
    git failure — is exactly the fail-closed signal the authority reads as
    "not prose-only".
    """
    proc = _git(["show", rev_path], repo_root=repo_root or _REPO_ROOT)
    if proc.returncode != 0:
        return None
    try:
        return proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def collect_py_blobs(base: str, head: str, paths: list[str], *, repo_root: Path | None = None) -> dict[str, tuple[str | None, str | None]]:
    """Base/head blob text for every changed ``.py`` path."""
    root = repo_root or _REPO_ROOT
    blobs: dict[str, tuple[str | None, str | None]] = {}
    for path in paths:
        if path.endswith(".py"):
            blobs[path] = (py_blob_text(f"{base}:{path}", repo_root=root), py_blob_text(f"{head}:{path}", repo_root=root))
    return blobs


def main(argv: list[str] | None = None, *, repo_root: Path | None = None) -> int:
    """Print the authority's prose-only verdict for ``base..head``."""
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: prose_only_step.py <base-sha> <head-sha>", file=sys.stderr)
        return 2
    base, head = args
    root = repo_root or _REPO_ROOT
    paths = changed_paths(base, head, repo_root=root)
    if paths is None:
        print("false")
        return 0
    blobs = collect_py_blobs(base, head, paths, repo_root=root)
    verdict = prose_only_verdict(paths, blobs, router=load_router())
    print("true" if verdict else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
