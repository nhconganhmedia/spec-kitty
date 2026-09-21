"""spec-kitty#4842 — prose-only (comment/docstring-only) ``.py`` diff down-routing.

The CI path router routes on file PATHS, so a diff that edits only comments
and docstrings inside ``src/**.py`` is classified as a full code change and
fans out the entire code test matrix + the heavy architectural battery (PR
#4841 burned ~2h of aggregate shard compute on a docstring-only correction;
the ``tests (docs)`` lane — the one a documentation change should run — was
skipped). These tests pin the whole #4842 contract:

* **Detector** (:func:`scripts.ci.gate_selection.python_diff_is_prose_only`)
  — a docstring/comment-only blob pair is prose-only; every real-code shape
  (flipped default, added branch, mixed docstring+code), every doubt shape
  (missing blob side, parse error, ``# type:`` comment delta) is NOT.
* **Verdict** (:func:`prose_only_verdict`) — all-or-nothing per PR: any code
  change anywhere, any unprovable file, any non-documentation non-``.py``
  file blocks the down-route.
* **Routing** (:func:`select_gates` / :func:`select_modules` ``py_blobs``) —
  a PROVEN prose-only diff runs the always-on + docs lanes and skips the
  module-test matrix and the architectural battery; ``py_blobs=None`` (the
  fail-closed default) routes exactly as before #4842; non-src group matches
  and the #4454 tests-mirror are untouched by the refinement.
* **Wiring** — the ci-router.yml prose-only fold and the ci-modules.yml
  blob plumbing actually encode the same refinement the authority answers
  (one parser, one answer — the #2476 contract).

This file lives in ``tests/ci`` on purpose: the ``ci`` module shard runs it
on every PR, including a CI-infrastructure-only PR like the one that landed
this contract — the exact PR shape whose routing it pins.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci.gate_selection import (
    Router,
    load_router,
    prose_only_verdict,
    python_diff_is_prose_only,
    select_gates,
    select_modules,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_ROUTER = _REPO_ROOT / ".github" / "workflows" / "ci-router.yml"
_CI_MODULES = _REPO_ROOT / ".github" / "workflows" / "ci-modules.yml"

# ---------------------------------------------------------------------------
# Shared fixtures: a module whose base/head blob pairs exercise every
# detector shape. The paths are real router paths (src/specify_cli/cli/**)
# so the routing tests below select real groups.
# ---------------------------------------------------------------------------
_BASE_PY = '''"""Module summary."""

DEFAULT = 1


def f(x):
    """Doc of f.

    Long form.
    """
    # a comment
    return x  # trailing
'''

_PROSE_HEAD_PY = '''"""Module summary, corrected."""

DEFAULT = 1


def f(x):
    """Doc of f, short."""
    # a different comment
    return x  # trailing (clarified)
'''

_CODE_HEAD_PY = '''"""Module summary."""

DEFAULT = 2


def f(x):
    """Doc of f.

    Long form.
    """
    # a comment
    return x + 1
'''

_PROSE_SRC_PATH = "src/specify_cli/cli/commands/status.py"
_PROSE_BLOBS = {_PROSE_SRC_PATH: (_BASE_PY, _PROSE_HEAD_PY)}
_CODE_BLOBS = {_PROSE_SRC_PATH: (_BASE_PY, _CODE_HEAD_PY)}


@pytest.fixture(scope="module")
def router() -> Router:
    return load_router()


# ---------------------------------------------------------------------------
# Detector: prose-only proof and its fail-closed boundaries
# ---------------------------------------------------------------------------
@pytest.mark.fast
def test_docstring_and_comment_only_change_is_prose_only() -> None:
    """The #4842 motivating shape: docstring rewording + comment edits, zero code lines."""
    assert python_diff_is_prose_only(_BASE_PY, _PROSE_HEAD_PY)


@pytest.mark.fast
def test_docstring_added_or_removed_is_prose_only() -> None:
    """Adding or deleting a docstring where none/e one existed is prose."""
    no_doc = "def f(x):\n    return x\n"
    with_doc = 'def f(x):\n    """New doc."""\n    return x\n'
    assert python_diff_is_prose_only(no_doc, with_doc)
    assert python_diff_is_prose_only(with_doc, no_doc)


@pytest.mark.fast
def test_class_and_async_docstrings_are_stripped_too() -> None:
    """Class/async-function docstring edits are prose, not code."""
    base = "class A:\n    '''doc.'''\n    x = 1\n\n\nasync def g():\n    '''g doc.'''\n    return 2\n"
    head = "class A:\n    '''DOC!'''\n    x = 1\n\n\nasync def g():\n    '''other.'''\n    return 2\n"
    assert python_diff_is_prose_only(base, head)


@pytest.mark.fast
def test_flipped_default_is_not_prose_only() -> None:
    """A flipped default value is a code change even with identical docstrings."""
    assert not python_diff_is_prose_only(_BASE_PY, _CODE_HEAD_PY)


@pytest.mark.fast
def test_added_branch_is_not_prose_only() -> None:
    """An added branch is a structural AST change."""
    head = _BASE_PY.replace("    return x  # trailing\n", "    if x:\n        return x\n    return 0\n")
    assert not python_diff_is_prose_only(_BASE_PY, head)


@pytest.mark.fast
def test_mixed_docstring_and_code_change_is_not_prose_only() -> None:
    """A docstring rewording riding along with a code change is code."""
    assert not python_diff_is_prose_only(_BASE_PY, _PROSE_HEAD_PY.replace("return x", "return x + 1"))


@pytest.mark.fast
def test_non_docstring_string_constant_change_is_not_prose_only() -> None:
    """A bare string constant that is not a docstring is code (fail-closed)."""
    base = 'MSG = "a"\n'
    head = 'MSG = "b"\n'
    assert not python_diff_is_prose_only(base, head)


@pytest.mark.fast
def test_docstring_becoming_code_is_not_prose_only() -> None:
    """A statement that stops being a bare docstring position is code."""
    base = '"""doc."""\n'
    head = 'x = "doc"\n'
    assert not python_diff_is_prose_only(base, head)


@pytest.mark.fast
def test_bytes_docstring_change_is_not_prose_only() -> None:
    """A ``b"..."`` expression is not a docstring, so changing it is code."""
    base = 'def f():\n    b"bytes"\n    return 1\n'
    head = 'def f():\n    b"BYTES"\n    return 1\n'
    assert not python_diff_is_prose_only(base, head)


@pytest.mark.fast
def test_parse_error_fails_closed() -> None:
    """An unparsable side is not proof — neither head nor base."""
    assert not python_diff_is_prose_only(_BASE_PY, "def broken(:\n")
    assert not python_diff_is_prose_only("def broken(:\n", _BASE_PY)


@pytest.mark.fast
def test_missing_blob_side_fails_closed() -> None:
    """An added file (no base) or deleted file (no head) is code surface."""
    assert not python_diff_is_prose_only(None, _PROSE_HEAD_PY)
    assert not python_diff_is_prose_only(_BASE_PY, None)
    assert not python_diff_is_prose_only(None, None)


@pytest.mark.fast
def test_type_comment_delta_fails_closed() -> None:
    """``# type:`` comments feed mypy, invisible to the AST — any delta is code."""
    base = "x = []\n"
    assert not python_diff_is_prose_only(base, "x = []  # type: list[int]\n")  # added
    assert not python_diff_is_prose_only("x = []  # type: list[int]\n", base)  # removed
    assert not python_diff_is_prose_only("x = []  # type: list[int]\n", "x = []  # type: list[str]\n")  # edited
    assert not python_diff_is_prose_only("y = 1  # type: ignore\n", "x = 1  # type: ignore\n")  # moved to another line


@pytest.mark.fast
def test_type_comment_unchanged_alongside_docstring_change_is_prose_only() -> None:
    """A docstring edit over an unchanged ``# type:`` stream is still prose."""
    base = '"""D."""\nx = []  # type: list[int]\n'
    head = '"""D2."""\nx = []  # type: list[int]\n'
    assert python_diff_is_prose_only(base, head)


# ---------------------------------------------------------------------------
# Verdict: all-or-nothing per PR
# ---------------------------------------------------------------------------
@pytest.mark.fast
def test_all_prose_py_plus_markdown_is_prose_only(router: Router) -> None:
    assert prose_only_verdict([_PROSE_SRC_PATH, "docs/context/team-kitty.md"], _PROSE_BLOBS, router=router)


@pytest.mark.fast
def test_any_code_py_blocks_the_verdict(router: Router) -> None:
    """All-or-nothing: one real-code .py anywhere blocks the down-route."""
    blobs = {**_PROSE_BLOBS, "src/kernel/thing.py": (_BASE_PY, _CODE_HEAD_PY)}
    assert not prose_only_verdict([_PROSE_SRC_PATH, "src/kernel/thing.py"], blobs, router=router)


@pytest.mark.fast
def test_unprovable_py_blocks_the_verdict(router: Router) -> None:
    """A .py with no blob entry is unproven — fail closed."""
    assert not prose_only_verdict([_PROSE_SRC_PATH], {}, router=router)
    assert not prose_only_verdict([_PROSE_SRC_PATH], {_PROSE_SRC_PATH: (None, _PROSE_HEAD_PY)}, router=router)


@pytest.mark.fast
def test_non_documentation_non_py_file_blocks_the_verdict(router: Router) -> None:
    """A workflow/manifest/lockfile change is not documentation — fail closed."""
    for other in ("pyproject.toml", ".github/workflows/ci-router.yml", "uv.lock", "package-lock.json"):
        assert not prose_only_verdict([_PROSE_SRC_PATH, other], _PROSE_BLOBS, router=router)


@pytest.mark.fast
def test_documentation_group_paths_count_as_documentation(router: Router) -> None:
    """Non-markdown paths the router's docs group already claims (docs/**,
    scripts/docs/**) are documentation, just like any *.md."""
    assert prose_only_verdict([_PROSE_SRC_PATH, "docs/diagram.png"], _PROSE_BLOBS, router=router)
    assert prose_only_verdict([_PROSE_SRC_PATH, "scripts/docs/reference.yml"], _PROSE_BLOBS, router=router)
    assert prose_only_verdict([_PROSE_SRC_PATH, "README.md"], _PROSE_BLOBS, router=router)


@pytest.mark.fast
def test_no_py_files_is_not_a_prose_verdict(router: Router) -> None:
    """A diff with no .py needs no proof — docs/data-only diffs already route as docs/data."""
    assert not prose_only_verdict(["docs/x.md", "packs/built-in/missions/m/spec.md"], {}, router=router)


# ---------------------------------------------------------------------------
# Routing: the down-route and its fail-closed default
# ---------------------------------------------------------------------------
@pytest.mark.fast
def test_prose_only_src_diff_down_routes_off_the_code_matrix(router: Router) -> None:
    """GOLDEN lane set: a proven prose-only src/**.py diff keeps every
    always-on lane + the docs lane, and skips the module-test matrix, the
    heavy architectural battery, and every code shard."""
    selection = select_gates([_PROSE_SRC_PATH], router=router, py_blobs=_PROSE_BLOBS)
    assert selection.prose_only is True
    # matched_groups stays the RAW path match (the paths DID match cli)...
    assert selection.matched_groups == frozenset({"cli"})
    # ...but nothing code-backed runs: no shard, no heavy battery.
    assert selection.selected_code_shards == frozenset()
    assert "architectural-heavy" not in selection.selected_jobs
    assert not any(job.startswith("tests-") and job != "tests-docs" for job in selection.selected_jobs)
    # The always-on lanes survive — including the CLI-reference drift lane
    # (regen-check) and the fast arch poles the #4842 issue names as "keep".
    assert {"ruff", "terminology", "layer-rules", "regen-check"} <= selection.selected_jobs
    # The inversion fix: the docs lane runs for the docstring change.
    assert "tests-docs" in selection.selected_jobs
    # Exactly always-on + docs-dependent jobs, nothing else.
    assert selection.selected_jobs == router.always_on_jobs | {"tests-docs"}
    # The module-test matrix selects zero modules.
    assert select_modules([_PROSE_SRC_PATH], router=router, py_blobs=_PROSE_BLOBS) == frozenset()


@pytest.mark.fast
def test_no_blobs_routes_exactly_as_today(router: Router) -> None:
    """Fail-closed default: py_blobs=None keeps the pre-#4842 answer byte-for-byte."""
    paths = [_PROSE_SRC_PATH]
    before = select_gates(paths, router=router)
    assert before.prose_only is False
    assert before.selected_code_shards == frozenset({"architectural-heavy", "tests-cli"})
    assert select_modules(paths, router=router) == frozenset({"cli"})


@pytest.mark.fast
def test_real_code_change_with_blobs_routes_as_today(router: Router) -> None:
    """Blobs that prove a code change change nothing: today's full routing."""
    paths = [_PROSE_SRC_PATH]
    selection = select_gates(paths, router=router, py_blobs=_CODE_BLOBS)
    assert selection.prose_only is False
    assert selection == select_gates(paths, router=router)
    assert select_modules(paths, router=router, py_blobs=_CODE_BLOBS) == frozenset({"cli"})


@pytest.mark.fast
def test_unproven_blob_entry_routes_as_today(router: Router) -> None:
    """A missing blob entry for a changed .py is doubt — full routing."""
    selection = select_gates([_PROSE_SRC_PATH], router=router, py_blobs={})
    assert selection.prose_only is False
    assert "tests-cli" in selection.selected_jobs


@pytest.mark.fast
def test_prose_only_unmapped_src_no_longer_forces_run_all(router: Router) -> None:
    """FR-004 refinement: a PROVEN prose-only unmapped src/** change is not
    the unmapped CODE the catch-all exists to catch — it down-routes instead
    of forcing run-all (the raw unmatched_src signal stays honest)."""
    paths = ["src/specify_cli/__unmapped_probe__/thing.py"]
    blobs = {paths[0]: (_BASE_PY, _PROSE_HEAD_PY)}
    selection = select_gates(paths, router=router, py_blobs=blobs)
    assert selection.unmatched_src is True
    assert selection.prose_only is True
    assert selection.selected_code_shards == frozenset()
    assert selection.selected_jobs == router.always_on_jobs | {"tests-docs"}
    assert select_modules(paths, router=router, py_blobs=blobs) == frozenset()


@pytest.mark.fast
def test_unmapped_src_code_change_still_forces_run_all(router: Router) -> None:
    """The FR-004 catch-all is untouched for real code: no proof, run-all."""
    paths = ["src/specify_cli/__unmapped_probe__/thing.py"]
    blobs = {paths[0]: (_BASE_PY, _CODE_HEAD_PY)}
    selection = select_gates(paths, router=router, py_blobs=blobs)
    assert selection.selected_code_shards == router.code_shard_jobs
    assert select_modules(paths, router=router, py_blobs=blobs)  # every module


@pytest.mark.fast
def test_full_mode_wins_over_the_down_route(router: Router) -> None:
    """An explicit run-all is run-all, even for a proven prose-only diff."""
    selection = select_gates([_PROSE_SRC_PATH], router=router, mode="full", py_blobs=_PROSE_BLOBS)
    assert selection.selected_code_shards == router.code_shard_jobs
    assert select_modules([_PROSE_SRC_PATH], router=router, mode="full", py_blobs=_PROSE_BLOBS)


@pytest.mark.fast
def test_prose_only_keeps_non_src_group_matches(router: Router) -> None:
    """The refinement drops only src-backed matches: corpus/e2e/ci matches
    survive a prose-only verdict exactly as the dorny filter computed them."""
    # corpus: a kitty-specs spec.md alongside the prose .py keeps the corpus lane.
    paths = [_PROSE_SRC_PATH, "kitty-specs/034-x/spec.md"]
    selection = select_gates(paths, router=router, py_blobs=_PROSE_BLOBS)
    assert "corpus" in selection.matched_groups
    assert "tests-corpus" in selection.selected_jobs
    assert "tests-docs" in selection.selected_jobs
    assert selection.selected_code_shards == frozenset()

    # e2e: a proven prose-only tests/e2e/**.py still selects the e2e lane.
    e2e_path = "tests/e2e/test_cli_flow.py"
    e2e_blobs = {e2e_path: (_BASE_PY, _PROSE_HEAD_PY)}
    e2e = select_gates([e2e_path], router=router, py_blobs=e2e_blobs)
    assert e2e.prose_only is True
    assert "e2e" in e2e.matched_groups
    assert "tests-e2e" in e2e.selected_jobs


@pytest.mark.fast
def test_prose_only_scripts_ci_keeps_the_ci_module(router: Router) -> None:
    """Fail-closed over-route pin: a prose-only scripts/ci/*.py still selects
    the `ci` module (its group is non-src, so the refinement does not drop
    it) — over-routing a prose diff is the safe direction, never under."""
    path = "scripts/ci/gate_selection.py"
    blobs = {path: (_BASE_PY, _PROSE_HEAD_PY)}
    assert select_modules([path], router=router, py_blobs=blobs) == frozenset({"ci"})


@pytest.mark.fast
def test_prose_only_tests_diff_keeps_the_4454_mirror(router: Router) -> None:
    """The #4454 mirror contract is untouched: a tests-only diff — even a
    proven prose-only one — selects the SAME module set its src twin would
    (never narrower), so its test files always run in a per-PR shard."""
    path = "tests/status/test_store.py"
    blobs = {path: (_BASE_PY, _PROSE_HEAD_PY)}
    tests_only = select_modules([path], router=router, py_blobs=blobs)
    src_twin = select_modules(["src/specify_cli/status/store.py"], router=router)
    assert src_twin <= tests_only
    assert tests_only == frozenset({"status", "core_misc", "execution_context", "unit"})


@pytest.mark.fast
def test_docs_only_diff_routes_identically_with_blobs(router: Router) -> None:
    """A docs-only diff needs no proof: with or without py_blobs, same answer."""
    paths = ["docs/architecture/status-model.md"]
    assert select_gates(paths, router=router, py_blobs={}) == select_gates(paths, router=router)


# ---------------------------------------------------------------------------
# Wiring: the workflows encode the same refinement the authority answers
# ---------------------------------------------------------------------------
_GROUP_REF = re.compile(r"needs\.changes\.outputs\.([A-Za-z0-9_]+)")


def _router_workflow() -> dict[str, Any]:
    return yaml.safe_load(_CI_ROUTER.read_text(encoding="utf-8"))


def _ci_modules_workflow() -> dict[str, Any]:
    return yaml.safe_load(_CI_MODULES.read_text(encoding="utf-8"))


def _changes_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return workflow["jobs"]["changes"]["steps"]


def _generate_matrix_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return workflow["jobs"]["generate-matrix"]["steps"]


def _eval_output_expr(expr: str, *, mode_full: bool, unmatched: bool, prose_only: bool, filter_outputs: dict[str, bool]) -> str:
    """Evaluate one ci-router.yml ``changes.outputs`` expression faithfully.

    Translates the GitHub-expression idiom this workflow uses —
    ``(A || B) && 'true' || (C && 'x' || steps.filter.outputs.G)`` — into the
    equivalent Python boolean chain over the same truthiness rules (any
    non-empty string is truthy), so the tests below can ask the YAML itself
    what a given (mode, unmatched, prose, dorny-match) tuple routes to.
    """
    body = expr.strip()
    assert body.startswith("${{") and body.endswith("}}"), f"not an expression: {expr!r}"
    body = body[3:-2]
    body = body.replace("inputs.mode == 'full'", "true" if mode_full else "false")
    body = body.replace("steps.unmatched.outputs.unmatched == 'true'", "true" if unmatched else "false")
    body = body.replace("steps.prose.outputs.prose-only == 'true'", "true" if prose_only else "false")

    def _filter_ref(match: re.Match[str]) -> str:
        return "true" if filter_outputs.get(match.group(1), False) else "false"

    body = re.sub(r"steps\.filter\.outputs\.([A-Za-z0-9_]+)", _filter_ref, body)
    body = body.replace("&&", " and ").replace("||", " or ")
    result = eval(body, {"__builtins__": {}}, {"true": True, "false": False})  # noqa: S307 - translated boolean idiom over constants only
    # GitHub renders a boolean expression result as 'true'/'false' (lowercase);
    # a chain that fell through to a filter output is already that string.
    if isinstance(result, bool):
        return "true" if result else "false"
    return str(result)


@pytest.mark.fast
def test_router_folds_every_src_backed_output_on_prose() -> None:
    """Every src-backed group output suppresses on the prose proof; the docs
    output forces on; corpus/e2e/ci stay exactly as dorny computed them."""
    workflow = _router_workflow()
    router = load_router()
    outputs = workflow["jobs"]["changes"]["outputs"]
    for group in sorted(router.src_backed_groups):
        expr = str(outputs[group])
        assert "steps.prose.outputs.prose-only == 'true' && 'false'" in expr, f"src-backed output {group!r} does not fold the prose-only proof to false: {expr!r}"
    assert "steps.prose.outputs.prose-only == 'true' && 'true'" in str(outputs["docs"]), "the docs output must force on for a proven prose-only diff"
    for group in ("corpus", "e2e", "ci"):
        assert "prose" not in str(outputs[group]), f"non-src output {group!r} must stay exactly as the filter computed it"


@pytest.mark.fast
def test_router_prose_step_precedes_unmatched_and_feeds_it() -> None:
    """The prose proof step runs before the unmatched step, and the catch-all
    reads it: a PROVEN prose-only unmapped src change is not unmapped CODE."""
    workflow = _router_workflow()
    steps = _changes_steps(workflow)
    ids = [step.get("id") for step in steps]
    assert ids.index("prose") < ids.index("unmatched"), "the prose step must precede the unmatched step (its output is an input)"
    unmatched = next(step for step in steps if step.get("id") == "unmatched")
    assert unmatched["env"]["PROSE_ONLY"] == "${{ steps.prose.outputs.prose-only }}"
    assert '"$PROSE_ONLY" != "true"' in unmatched["run"]
    prose = next(step for step in steps if step.get("id") == "prose")
    assert "scripts/ci/prose_only_step.py" in prose["run"], "the step must consult the single authority, not inline a second parser"


@pytest.mark.fast
def test_router_output_fold_answers_what_the_authority_answers(router: Router) -> None:
    """ONE-ANSWER pin (#2476): evaluating the workflow's own output
    expressions and job gates for a diff yields exactly the job set
    :func:`select_gates` answers for the same diff — prose or code."""
    workflow = _router_workflow()
    outputs = workflow["jobs"]["changes"]["outputs"]
    job_gates = {
        name: frozenset(_GROUP_REF.findall(str(job.get("if")))) if job.get("if") else frozenset()
        for name, job in workflow["jobs"].items()
        if name != "changes" and isinstance(job, dict)
    }
    always_on = {name for name, gates in job_gates.items() if not gates}

    def workflow_selected_jobs(paths: list[str], py_blobs: dict[str, tuple[str | None, str | None]] | None) -> frozenset[str]:
        raw = select_gates(paths, router=router)  # dorny-equivalent raw matches
        filter_outputs = {group: group in raw.matched_groups for group in router.filters}
        prose = py_blobs is not None and prose_only_verdict(paths, py_blobs, router=router)
        unmatched = raw.unmatched_src and not prose  # the prose-aware unmatched step
        effective = {
            group: _eval_output_expr(
                str(outputs[group]),
                mode_full=False,
                unmatched=unmatched,
                prose_only=prose,
                filter_outputs=filter_outputs,
            )
            == "true"
            for group in router.routing_groups
        }
        gated = {job for job, gates in job_gates.items() if gates and any(effective.get(g) for g in gates)}
        return frozenset(always_on | gated)

    cases: list[tuple[list[str], dict[str, tuple[str | None, str | None]] | None]] = [
        ([_PROSE_SRC_PATH], _PROSE_BLOBS),  # prose-only src diff -> down-route
        ([_PROSE_SRC_PATH], _CODE_BLOBS),  # code diff -> today's routing
        ([_PROSE_SRC_PATH], None),  # no evidence -> fail-closed today's routing
        # prose unmapped src: the catch-all stands down for PROVEN prose
        (
            ["src/specify_cli/__unmapped_probe__/thing.py"],
            {"src/specify_cli/__unmapped_probe__/thing.py": (_BASE_PY, _PROSE_HEAD_PY)},
        ),
        ([_PROSE_SRC_PATH, "kitty-specs/034-x/spec.md"], _PROSE_BLOBS),  # prose + corpus data
        (["docs/architecture/status-model.md"], {}),  # docs-only, no proof needed
    ]
    for paths, blobs in cases:
        authority = select_gates(paths, router=router, py_blobs=blobs)
        workflow_side = workflow_selected_jobs(paths, blobs)
        assert workflow_side == authority.selected_jobs, (
            f"ci-router.yml fold and the gate-selection authority disagree for {paths} "
            f"(py_blobs={'yes' if blobs is not None else 'no'}): workflow={sorted(workflow_side)} authority={sorted(authority.selected_jobs)}"
        )


@pytest.mark.fast
def test_ci_modules_collects_blobs_and_passes_them_to_the_authority() -> None:
    """ci-modules.yml: the changed-files step writes the per-.py blob evidence
    and the build step feeds it to select_modules — fail-closed when absent."""
    changed_files = next(step for step in _generate_matrix_steps(_ci_modules_workflow()) if step.get("id") == "changed-files")
    build = next(step for step in _generate_matrix_steps(_ci_modules_workflow()) if step.get("id") == "build")
    assert "changed-py-blobs.json" in changed_files["run"], "the changed-files step must gather base/head blob text for changed .py files"
    assert "select_modules(changed_files, mode=selection_mode, py_blobs=py_blobs)" in build["run"], (
        "the build step must pass the blob evidence to the single authority"
    )
    assert "except (OSError, json.JSONDecodeError):" in build["run"], (
        "missing/invalid blob evidence must fall back to py_blobs=None (today's routing), never crash the matrix build"
    )


# ---------------------------------------------------------------------------
# The router's step script — real git, real verdicts (git_repo)
# ---------------------------------------------------------------------------
def _commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message, "--no-gpg-sign"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "HOME": str(repo / ".home"),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, check=True, text=True)
    return proc.stdout.strip()


@pytest.mark.git_repo
def test_prose_only_step_prints_the_authoritys_verdict(tmp_path: Path, capsys: pytest.CaptureFixture[str], router: Router) -> None:
    """End-to-end step proof in a real repo: prose diff -> true; code diff,
    added file, and unfetchable base -> false (fail closed)."""
    from scripts.ci.prose_only_step import main as prose_main

    (tmp_path / ".home").mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, capture_output=True, check=True)
    src_dir = tmp_path / "src" / "specify_cli" / "cli" / "commands"
    src_dir.mkdir(parents=True)
    (src_dir / "status.py").write_text(_BASE_PY, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("docs\n", encoding="utf-8")
    base_sha = _commit_all(tmp_path, "base")

    # Prose-only change: docstring rewording + comment edits.
    (src_dir / "status.py").write_text(_PROSE_HEAD_PY, encoding="utf-8")
    head_sha = _commit_all(tmp_path, "prose")
    assert prose_main([base_sha, head_sha], repo_root=tmp_path) == 0
    assert capsys.readouterr().out.strip() == "true"

    # Real code change: fail closed.
    (src_dir / "status.py").write_text(_CODE_HEAD_PY, encoding="utf-8")
    code_sha = _commit_all(tmp_path, "code")
    assert prose_main([base_sha, code_sha], repo_root=tmp_path) == 0
    assert capsys.readouterr().out.strip() == "false"

    # Added .py file (no base blob): fail closed.
    (src_dir / "new.py").write_text('"""Only a docstring."""\n', encoding="utf-8")
    added_sha = _commit_all(tmp_path, "added")
    assert prose_main([base_sha, added_sha], repo_root=tmp_path) == 0
    assert capsys.readouterr().out.strip() == "false"

    # Unfetchable base SHA: fail closed, still exit 0 (the router reads stdout).
    assert prose_main([("0" * 40), head_sha], repo_root=tmp_path) == 0
    assert capsys.readouterr().out.strip() == "false"


# ---------------------------------------------------------------------------
# Local pre-PR parity — the third consumer stays in lockstep (git_repo)
# ---------------------------------------------------------------------------
@pytest.mark.fast
def test_resolve_selection_forwards_the_prose_evidence(router: Router) -> None:
    """Parity proof (#2476/#4842): the local consumer forwards py_blobs to the
    same authority, so its answer for a prose-only diff is the down-route."""
    from scripts.ci.local_gate_parity import resolve_selection

    paths = [_PROSE_SRC_PATH]
    local = resolve_selection(paths, router=router, py_blobs=_PROSE_BLOBS)
    ci = select_gates(paths, router=router, py_blobs=_PROSE_BLOBS)
    assert local == ci
    assert local.prose_only is True
    assert local.selected_code_shards == frozenset()


@pytest.mark.git_repo
def test_local_py_blobs_collects_merge_base_and_head_evidence(tmp_path: Path) -> None:
    """local_py_blobs gathers the same evidence CI gathers: merge-base + HEAD
    blob text per changed .py; a new .py is a fail-closed None base."""
    from scripts.ci.local_gate_parity import local_py_blobs

    (tmp_path / ".home").mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, capture_output=True, check=True)
    src_dir = tmp_path / "src" / "specify_cli" / "cli" / "commands"
    src_dir.mkdir(parents=True)
    (src_dir / "status.py").write_text(_BASE_PY, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("docs\n", encoding="utf-8")
    _commit_all(tmp_path, "base")
    subprocess.run(["git", "checkout", "-q", "-b", "topic"], cwd=tmp_path, capture_output=True, check=True)

    (src_dir / "status.py").write_text(_PROSE_HEAD_PY, encoding="utf-8")
    (src_dir / "new.py").write_text('"""Only a docstring."""\n', encoding="utf-8")
    _commit_all(tmp_path, "topic")

    blobs = local_py_blobs(tmp_path, "main", ["src/specify_cli/cli/commands/status.py", "src/specify_cli/cli/commands/new.py"])
    assert blobs["src/specify_cli/cli/commands/status.py"] == (_BASE_PY, _PROSE_HEAD_PY)
    assert blobs["src/specify_cli/cli/commands/new.py"][0] is None
    assert blobs["src/specify_cli/cli/commands/new.py"][1] == '"""Only a docstring."""\n'


@pytest.mark.git_repo
def test_build_report_down_routes_a_prose_only_local_diff(tmp_path: Path) -> None:
    """End-to-end local parity: a docstring-only working diff previews as the
    down-route (docs lane + always-on, no code shards) — matching what the
    router will actually do for that PR."""
    from scripts.ci.local_gate_parity import build_report

    (tmp_path / ".home").mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, capture_output=True, check=True)
    src_dir = tmp_path / "src" / "specify_cli" / "cli" / "commands"
    src_dir.mkdir(parents=True)
    (src_dir / "status.py").write_text(_BASE_PY, encoding="utf-8")
    _commit_all(tmp_path, "base")
    subprocess.run(["git", "checkout", "-q", "-b", "topic"], cwd=tmp_path, capture_output=True, check=True)
    (src_dir / "status.py").write_text(_PROSE_HEAD_PY, encoding="utf-8")
    _commit_all(tmp_path, "prose")

    report = build_report(repo_root=tmp_path, base_ref="main")
    assert report.changed_paths == ("src/specify_cli/cli/commands/status.py",)
    assert report.selection.prose_only is True
    assert report.selection.selected_code_shards == frozenset()
    assert "tests-docs" in report.selection.selected_jobs
