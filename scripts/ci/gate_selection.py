"""Single gate-selection authority (FR-016 / #2476).

This module is the one authority for "which shards/gates does a changed-path set
select". It **parses** the two hand-authored routing authorities straight out of
the on-disk ``.github/workflows/ci-router.yml``:

1. the dorny ``changes`` filter block — ``group -> globs[]`` (path -> group), and
2. the job ``if: needs.changes.outputs.<group>`` gates — group -> job.

It never re-encodes the routing as a second hand-maintained map: that duplication
is the very #2476 hazard this module exists to close. It is reused by CI routing,
the WP17 completeness oracle, and WP18 local pre-PR parity — one parser, one
answer, no drift.

Public API:
    ``load_router(path=None) -> Router``   parse the two authorities.
    ``select_gates(changed_paths, *, router=None, mode="pr", py_blobs=None)
                                            -> GateSelection``
                                            answer the selection question.
    ``select_modules(changed_paths, *, router=None, registry_path=None,
                     mode="pr", py_blobs=None) -> frozenset[str]``
                                            answer the module-matrix twin.
    ``python_diff_is_prose_only(base_text, head_text) -> bool``
                                            prove a ``.py`` blob pair differs
                                            only in comments/docstrings.
    ``prose_only_verdict(changed_paths, py_blobs, *, router=None) -> bool``
                                            the all-or-nothing per-PR verdict.
"""

from __future__ import annotations

import ast
import fnmatch
import io
import re
import tokenize
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "DEFAULT_REGISTRY_PATH",
    "DEFAULT_ROUTER_PATH",
    "PROBE_GROUPS",
    "PyBlobPair",
    "PyBlobs",
    "GateSelection",
    "Router",
    "load_router",
    "prose_only_verdict",
    "python_diff_is_prose_only",
    "select_gates",
    "select_modules",
]

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTER_PATH = _REPO_ROOT / ".github" / "workflows" / "ci-router.yml"
DEFAULT_REGISTRY_PATH = _REPO_ROOT / ".github" / "ci-module-registry.yml"

# The ``any_src`` filter row is the FR-004 fail-closed PROBE (matches any
# ``src/**``), consumed only by the router's ``unmatched`` step. It is never a
# routing group and is never gated on a job (contract Invariant 1).
PROBE_GROUPS = frozenset({"any_src"})

_GROUP_REF = re.compile(r"needs\.changes\.outputs\.([A-Za-z0-9_]+)")

# ---------------------------------------------------------------------------
# spec-kitty#4842 — prose-only (comment/docstring-only) ``.py`` diff proof.
#
# The router routes on file PATHS, so a diff that edits only comments and
# docstrings inside ``src/**.py`` is classified as a full code change and
# fans out the entire code test matrix + the heavy architectural battery —
# none of which a prose-only diff can flip (PR #4841 burned ~2h of aggregate
# shard compute on a docstring-only correction). The detector below PROVES
# prose-only-ness from blob content; the routing refinement (the ``py_blobs``
# parameter of :func:`select_gates` / :func:`select_modules`) down-routes ONLY
# on that proof, and every form of doubt — missing blob, undecodable text,
# parse error, any structural difference, any ``# type:`` comment delta —
# fails closed to today's path-based routing. Never skip the code matrix
# without proof; the safe failure is "run everything", which is no worse than
# today.
# ---------------------------------------------------------------------------

#: ``# type:`` comments feed mypy, so an AST compare (which cannot see
#: comments at all) is not enough to prove a diff inert: any change in the
#: ``# type:`` comment stream keeps the diff classified as code.
_TYPE_COMMENT = re.compile(r"#\s*type:")

#: A changed ``.py`` file's two blob texts: ``base`` is the pre-diff blob,
#: ``head`` the post-diff blob. ``None`` marks an unreadable side (added or
#: deleted file, unfetchable blob, undecodable text) and always fails closed.
PyBlobPair = tuple[str | None, str | None]

#: The per-PR evidence map a caller supplies to enable the #4842 down-route:
#: changed ``.py`` path -> ``(base_text, head_text)``. ``None`` (the default
#: everywhere) disables the refinement entirely — today's routing, exactly.
PyBlobs = Mapping[str, PyBlobPair]

#: A synthetic documentation probe path: the routing group(s) it matches are
#: the documentation lane a proven prose-only diff routes into (derived by
#: matching through the parsed router — never a hand-encoded group name).
_PROSE_DOCS_PROBE = "docs/__ci_prose_only_probe__.md"


class _DocstringStripper(ast.NodeTransformer):
    """Remove docstring nodes from a parsed tree (both sides of a compare).

    A docstring is a bare string-expression statement (``Expr`` wrapping a
    ``str`` ``Constant``) at the head of a module/class/function body — the
    same nodes :func:`ast.get_docstring` reads. Comments never appear in an
    AST at all, so stripping docstrings from both trees makes an
    ``ast.dump`` equality a proof that every non-docstring statement is
    structurally identical.
    """

    def visit_Module(self, node: ast.Module) -> ast.Module:
        return self._strip(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        return self._strip(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return self._strip(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        return self._strip(node)

    def _strip(self, node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> Any:
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:]
        self.generic_visit(node)
        return node


def _docstring_stripped_ast(text: str) -> ast.Module | None:
    """Parse *text* and strip docstrings, or ``None`` on any parse failure."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    _DocstringStripper().visit(tree)
    return tree


def _type_comments(text: str) -> tuple[tuple[int, str], ...] | None:
    """The ``(line, text)`` pairs of ``# type:`` comments, or ``None`` on tokenize failure.

    mypy reads ``# type:`` comments the AST cannot see, so a prose-only proof
    requires this stream to be identical on both sides. Each comment is paired
    with its line number (not compared as a bare ordered text sequence) so a
    type comment moved to a different line — even a pure position move with
    the same text and order and no code change at all — is still a change
    mypy could observe. A docstring edit that grows or shrinks line count
    shifts the pairs below it and likewise fails closed: over-routing a
    prose diff is the safe direction, never under.
    """
    try:
        return tuple(
            (token.start[0], token.string)
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT and _TYPE_COMMENT.search(token.string)
        )
    except (tokenize.TokenError, SyntaxError, ValueError, IndentationError):
        return None


def python_diff_is_prose_only(base_text: str | None, head_text: str | None) -> bool:
    """Prove a ``.py`` blob pair differs only in comments/docstrings (#4842).

    True ONLY on proof; every doubt returns False (fail closed — the caller
    then routes the diff as code, which is never worse than today):

    * either side missing — an added or deleted file is new/removed code
      surface, not prose;
    * either side failing to parse — an unfamiliar construct is not proof;
    * any structural difference between the docstring-stripped ASTs — real
      code (a flipped default, an added branch, a changed string constant
      that is not a docstring);
    * any difference in the ``# type:`` comment stream — mypy reads those,
      so the AST alone cannot prove the diff inert.
    """
    if base_text is None or head_text is None:
        return False
    base_ast = _docstring_stripped_ast(base_text)
    head_ast = _docstring_stripped_ast(head_text)
    if base_ast is None or head_ast is None:
        return False
    if ast.dump(base_ast) != ast.dump(head_ast):
        return False
    base_types = _type_comments(base_text)
    head_types = _type_comments(head_text)
    return base_types is not None and head_types is not None and base_types == head_types


def _documentation_groups(router: Router) -> frozenset[str]:
    """The routing group(s) a documentation probe matches (today: ``docs``).

    Derived by feeding the probe through the parsed router's own filter
    block — never a hand-encoded group name (the #2476 hazard).
    """
    return _match_groups([_PROSE_DOCS_PROBE], router)


def _is_documentation_path(path: str, *, router: Router) -> bool:
    """Whether a non-``.py`` changed path is documentation (#4842).

    Documentation is any Markdown file (``*.md``) or any path the router's
    documentation group globs already claim (``docs/**``, ``tests/docs/**``,
    ``scripts/docs/**`` — derived, never re-listed here).
    """
    if path.endswith(".md"):
        return True
    return any(fnmatch.fnmatch(path, glob) for group in _documentation_groups(router) for glob in router.filters[group])


def prose_only_verdict(
    changed_paths: Iterable[str | Path],
    py_blobs: PyBlobs,
    *,
    router: Router | None = None,
) -> bool:
    """The all-or-nothing per-PR prose-only verdict (#4842).

    True only when EVERY changed path is either a documentation path or a
    ``.py`` whose blob pair :func:`python_diff_is_prose_only` proves differs
    only in comments/docstrings. Any real code change anywhere, any file the
    detector cannot prove, any non-documentation non-``.py`` file (a
    ``pyproject.toml``, a workflow, a lockfile) ⇒ False ⇒ today's full
    routing. A diff with no ``.py`` file at all is also False: it needs no
    proof, because a docs/data-only diff already routes as docs/data.
    """
    router = router or load_router()
    paths = [str(path) for path in changed_paths]
    py_changed = [path for path in paths if path.endswith(".py")]
    if not py_changed:
        return False
    for path in py_changed:
        pair = py_blobs.get(path)
        if pair is None:
            return False
        if not python_diff_is_prose_only(pair[0], pair[1]):
            return False
    return all(_is_documentation_path(path, router=router) for path in paths if not path.endswith(".py"))


@dataclass(frozen=True)
class Router:
    """The two parsed routing authorities of ``ci-router.yml``.

    ``filters`` is authority 1 (path -> group); ``job_gates`` is authority 2
    (job -> the groups its ``if:`` references). Everything else below is derived.
    """

    filters: dict[str, tuple[str, ...]]
    job_gates: dict[str, frozenset[str]]

    @property
    def routing_groups(self) -> frozenset[str]:
        """Every filter group except the fail-closed probe."""
        return frozenset(group for group in self.filters if group not in PROBE_GROUPS)

    @property
    def src_backed_groups(self) -> frozenset[str]:
        """Routing groups carrying at least one ``src/`` glob (code, not data)."""
        return frozenset(group for group in self.routing_groups if any(glob.startswith("src/") for glob in self.filters[group]))

    @property
    def always_on_jobs(self) -> frozenset[str]:
        """Jobs with no filter-group gate — they run unconditionally."""
        return frozenset(job for job, groups in self.job_gates.items() if not groups)

    @property
    def code_shard_jobs(self) -> frozenset[str]:
        """Gated jobs whose ``if:`` references at least one src-backed group."""
        src = self.src_backed_groups
        return frozenset(job for job, groups in self.job_gates.items() if groups & src)


@dataclass(frozen=True)
class GateSelection:
    """The answer to "what does this diff select", derived from the two authorities."""

    matched_groups: frozenset[str]
    unmatched_src: bool
    selected_jobs: frozenset[str]
    selected_code_shards: frozenset[str]
    #: The #4842 prose-only verdict this selection applied: True only when the
    #: caller supplied ``py_blobs`` proving every changed ``.py`` differs only
    #: in comments/docstrings (and every other changed path is documentation).
    prose_only: bool = False


def _dorny_filters(workflow: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    changes = workflow["jobs"]["changes"]
    for step in changes["steps"]:
        if "dorny/paths-filter" in str(step.get("uses", "")):
            raw = step["with"]["filters"]
            parsed = yaml.safe_load(raw) if isinstance(raw, str) else raw
            return {group: tuple(str(g) for g in (globs or ())) for group, globs in parsed.items()}
    raise ValueError("ci-router.yml `changes` job has no dorny/paths-filter step")


def _job_gates(workflow: dict[str, Any]) -> dict[str, frozenset[str]]:
    gates: dict[str, frozenset[str]] = {}
    for name, job in workflow["jobs"].items():
        if name == "changes" or not isinstance(job, dict):
            continue
        condition = job.get("if")
        gates[name] = frozenset(_GROUP_REF.findall(str(condition))) if condition else frozenset()
    return gates


def load_router(path: Path | None = None) -> Router:
    """Parse the two routing authorities out of ``ci-router.yml``."""
    workflow = yaml.safe_load((path or DEFAULT_ROUTER_PATH).read_text(encoding="utf-8"))
    return Router(filters=_dorny_filters(workflow), job_gates=_job_gates(workflow))


def _match_groups(paths: list[str], router: Router) -> frozenset[str]:
    hit: set[str] = set()
    for group, globs in router.filters.items():
        if group in PROBE_GROUPS:
            continue
        if any(fnmatch.fnmatch(path, pattern) for pattern in globs for path in paths):
            hit.add(group)
    return frozenset(hit)


def select_gates(
    changed_paths: Iterable[str | Path],
    *,
    router: Router | None = None,
    mode: str = "pr",
    py_blobs: PyBlobs | None = None,
) -> GateSelection:
    """Return which jobs / code shards a changed-path set selects.

    ``mode="full"`` (or an unmapped ``src/**`` change — the FR-004 fail-closed
    catch-all) forces run-all: every routing group is selected. Otherwise only
    the groups the paths matched are selected. Always-on jobs (no filter group)
    are always included; ``selected_code_shards`` is the src-backed subset.

    ``py_blobs`` (spec-kitty#4842) optionally supplies base/head blob text for
    the changed ``.py`` files. When it PROVES the whole diff is prose-only
    (comment/docstring-only — :func:`prose_only_verdict`), the src-backed
    (code) group matches are dropped and the documentation lane is selected
    instead, and a proven-prose-only unmapped ``src/**`` change no longer
    forces run-all: prose cannot flip any runtime gate, so the code matrix and
    the heavy architectural battery are skipped while every always-on lane
    (ruff, terminology, regen/CLI-reference drift, ...) still runs. Non-src
    group matches (``docs``/``corpus``/``e2e``/``ci``) are untouched by the
    refinement. ``py_blobs=None`` (the default) is fail-closed: no proof, no
    down-route — exactly today's routing. ``mode="full"`` always wins over the
    down-route: an explicit run-all is run-all.
    """
    router = router or load_router()
    paths = [str(path) for path in changed_paths]
    matched = _match_groups(paths, router)
    prose_only = py_blobs is not None and prose_only_verdict(paths, py_blobs, router=router)

    any_src = any(path.startswith("src/") for path in paths)
    unmatched_src = any_src and not (matched & router.src_backed_groups)

    run_all = mode == "full" or (unmatched_src and not prose_only)
    if run_all:
        selected_groups = router.routing_groups
    elif prose_only:
        # #4842 down-route: under the all-or-nothing verdict, src-backed
        # matches can only come from proven-prose-only .py paths (a
        # documentation path cannot match a src/ glob), so dropping them is
        # exactly "drop what the prose files contributed". Non-src matches
        # stay, and the documentation lane is selected in the prose files'
        # place — the inversion fix: a docstring change runs the docs lane,
        # not the code matrix.
        selected_groups = (matched - router.src_backed_groups) | _documentation_groups(router)
    else:
        selected_groups = matched

    gated_selected = frozenset(job for job, groups in router.job_gates.items() if groups and (groups & selected_groups))
    return GateSelection(
        matched_groups=matched,
        unmatched_src=unmatched_src,
        selected_jobs=router.always_on_jobs | gated_selected,
        selected_code_shards=gated_selected & router.code_shard_jobs,
        prose_only=prose_only,
    )


def _registry_rows(path: Path | None = None) -> list[dict[str, Any]]:
    """The ``modules[]`` rows from ``.github/ci-module-registry.yml`` (WP08).

    The registry is the single data source for the module set; reading its
    inventory (``module`` names, ``roots``, ``test_dirs``) here is not a second
    routing map (the #2476 hazard is re-encoding the path->group filter, which
    this does not do — src routing still comes from the parsed router)."""
    registry = yaml.safe_load((path or DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8"))
    return [dict(row) for row in registry["modules"]]


def _registry_module_names(path: Path | None = None) -> frozenset[str]:
    """The module inventory (``modules[].module``) from the registry."""
    return frozenset(str(row["module"]) for row in _registry_rows(path))


def _within(path: str, directory: str) -> bool:
    """Whether ``path`` is ``directory`` itself or a descendant of it."""
    directory = directory.rstrip("/")
    return path == directory or path.startswith(f"{directory}/")


def _canonical_test_mirror(root: str) -> str:
    """The canonical ``tests/`` mirror directory of a registry ``roots`` glob.

    Deterministic transform (the "canonical test mirror"): the mirror of a
    directory glob ``<prefix>/<leaf>/**`` is ``tests/<leaf>``; the mirror of a
    single-file root ``<prefix>/<name>.py`` is ``tests/<name>``. This is how a
    module *without* an explicit ``test_dirs`` declares its test tree — the
    authority stays the registry (its own ``roots``), never a hand-authored
    test-dir->module table (the #2476 hazard).
    """
    root = root.rstrip("/")
    if root.endswith("/**"):
        leaf = root[:-3].rstrip("/").rsplit("/", 1)[-1]
        return f"tests/{leaf}"
    name = root.rsplit("/", 1)[-1]
    stem = name.split("*", 1)[0].rsplit(".", 1)[0]
    return f"tests/{stem}"


def _probe_path(root: str) -> str:
    """A representative concrete path under a registry ``roots`` glob.

    The probe is fed back through the parsed router (:func:`select_gates`) so
    the src-routing answer for a test tree is computed by the ONE routing
    authority, not re-derived here. A directory glob yields a file under it; a
    single-file root yields the file itself.
    """
    root = root.rstrip("/")
    if root.endswith("/**"):
        return f"{root[:-3].rstrip('/')}/__ci_probe__.py"
    return root


def _modules_for_test_paths(
    paths: list[str],
    *,
    router: Router,
    registry_path: Path | None,
    modules: frozenset[str],
) -> frozenset[str]:
    """Modules a tests-only change selects, derived from the registry (#4454).

    ``select_gates`` only matches ``src/`` (and other router) globs, so a diff
    confined to ``tests/<dir>/**`` matches no routing group and selects nothing
    — a false green (the test files run in no per-PR shard). This maps each
    changed test path back to its owning module(s) using the registry, then
    mirrors that back to the SAME module set the corresponding src change would
    select, so a tests-only diff is never narrowed relative to its src twin:

    * **explicit ``test_dirs``** — a module that declares its test directories
      owns any changed path within them (preferred, per the registry);
    * **canonical mirror** — every module ``root`` also declares its test tree
      via :func:`_canonical_test_mirror`, so a module without explicit
      ``test_dirs`` still owns ``tests/<leaf>`` for each ``src/<...>/<leaf>/**``
      root. The matched roots are probed through the router (:func:`select_gates`)
      so the resulting module set equals the src change's set exactly.

    A test path with no derivable owning module contributes nothing (it falls
    through to the caller's src/full behavior) — no module is fabricated.
    """
    test_paths = [path for path in paths if _within(path, "tests")]
    if not test_paths:
        return frozenset()

    owners: set[str] = set()
    probes: set[str] = set()
    for row in _registry_rows(registry_path):
        name = str(row["module"])
        for test_dir in row.get("test_dirs") or ():
            if any(_within(path, str(test_dir)) for path in test_paths):
                owners.add(name)
        for root in row.get("roots") or ():
            mirror = _canonical_test_mirror(str(root))
            if any(_within(path, mirror) for path in test_paths):
                probes.add(_probe_path(str(root)))

    if probes:
        mirrored = select_gates(sorted(probes), router=router).matched_groups & modules
        owners |= mirrored
    return frozenset(owners & modules)


def select_modules(
    changed_paths: Iterable[str | Path],
    *,
    router: Router | None = None,
    registry_path: Path | None = None,
    mode: str = "pr",
    py_blobs: PyBlobs | None = None,
) -> frozenset[str]:
    """Return which module-registry rows (``.github/ci-module-registry.yml``
    ``modules[].module``) a changed-path set selects.

    The module universe is the registry's own ``modules[].module`` set — NOT
    ``router.src_backed_groups``. Most registry modules are 1:1 with a
    src-backed routing group, but spec-kitty#4386 added the ``ci`` module,
    whose routing group (``scripts/ci/**`` + ``.github/workflows/**``) carries
    no ``src/`` glob and so is NOT src-backed. Intersecting against
    ``src_backed_groups`` would therefore silently drop the ``ci`` module on
    every scoped PR (including one that changes CI infra — the exact diff that
    should run ``tests/ci``). We intersect the router's matched groups against
    the registry inventory instead. Routing still comes from the parsed router
    via :func:`select_gates` — the registry supplies only the module list, so
    no second path->group map is introduced (the #2476 hazard stays closed).
    ``docs``/``corpus``/``e2e`` are non-src routing groups with no registry
    row and are excluded by the intersection.

    ``mode="full"`` or a fail-closed unmatched ``src/**`` diff (FR-004) selects
    every module — run-all, never a silent narrowing of the matrix. Otherwise
    only the matched groups that are registry modules are selected (a docs-only
    diff selects zero modules; overlapping glob ownership between groups, e.g.
    ``core_misc``/``unit``/``execution_context`` each also owning
    ``src/specify_cli/status/**``, is preserved exactly as the router already
    encodes it — never narrowed to a single "owning" module).

    A diff confined to ``tests/<dir>/**`` matches no router glob and would
    otherwise select nothing (spec-kitty#4454 — the test files run in no per-PR
    shard, a false green). Such paths are mapped back to their owning modules
    from the registry (:func:`_modules_for_test_paths`) and unioned in, so a
    tests-only diff selects the SAME module set the corresponding src change
    selects (mirror, never narrow).

    ``py_blobs`` (spec-kitty#4842) applies the prose-only down-route to the
    module matrix: a PROVEN comment/docstring-only diff selects no module
    shard — prose cannot flip a test — while fail-closed defaults (no blobs,
    any unproven file, any real code change) select exactly as today. The
    #4454 tests-mirror is deliberately still computed for proven-prose-only
    test files: "never narrower than the src twin" is the mirror's own
    contract, and over-routing a prose-only tests diff is the safe direction.
    """
    router = router or load_router()
    modules = _registry_module_names(registry_path)
    paths = [str(path) for path in changed_paths]
    selection = select_gates(paths, router=router, mode=mode, py_blobs=py_blobs)
    if mode == "full" or (selection.unmatched_src and not selection.prose_only):
        return modules
    # #4842 down-route: src-backed matches are dropped (they can only come from
    # proven-prose-only .py paths under the all-or-nothing verdict); non-src
    # matches (e.g. the `ci` module via a prose scripts/ci/*.py) keep selecting
    # their module — over-routing, never under.
    matched_groups = selection.matched_groups - router.src_backed_groups if selection.prose_only else selection.matched_groups
    src_selected = matched_groups & modules
    test_selected = _modules_for_test_paths(paths, router=router, registry_path=registry_path, modules=modules)
    return src_selected | test_selected
