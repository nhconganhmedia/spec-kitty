"""Red-first + full coverage for ``wait_for_artifacts.py``'s bounded artefact poll (FR-005/006).

RED-FIRST (charter C-011): ``wait_for_artifacts.py`` does not exist before this
mission, so "red-first through the pre-existing entry point" cannot apply
literally (plan.md's own resolution). Instead, the recovery-path tests below
are written against a single, UNRETRIED-poll STUB version of
``poll_for_artifacts`` and confirmed to fail the way a single, unretried poll
attempt fails today -- a transiently-missing artifact is treated as
permanently missing, exactly the "fails once, passes on retry no longer
reliably holds" defect #4675 describes. They pass once ``poll_for_artifacts``
is wired to WP01's ``retry_with_backoff``.

Mirrors ``test_fleet_verdict.py``'s ``API``/``GitHub``-mocking convention: a
fake implementing the same ``request``/``pages`` interface as
``GitHub``/``GitHubCLI``, returning a controllable, evolving list of artifact
names across calls.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.ci.reconcile_shards import RegistryShard
from scripts.ci.wait_for_artifacts import (
    MAX_ATTEMPTS,
    match_artifacts,
    must_be_fresh_shards,
    poll_for_artifacts,
    required_keys,
)

pytestmark = pytest.mark.fast

RUN_ID = "999"
_MERGE = RegistryShard(tier="standard", module="merge", shard_index=1, shard_count=2)
_MERGE_2 = RegistryShard(tier="standard", module="merge", shard_index=2, shard_count=2)
_UNSELECTED = RegistryShard(tier="standard", module="unselected", shard_index=1, shard_count=1)


def _artifact_name(shard: RegistryShard, attempt: int = 1) -> str:
    return f"module-tests-{shard.module}-shard-{shard.shard_index}-of-{shard.shard_count}-attempt-{attempt}-reports"


class FakeArtifactsAPI:
    """A controllable, evolving artifact list across ``pages()`` calls."""

    def __init__(self, names_by_call: list[list[str]]) -> None:
        self._names_by_call = names_by_call
        self.calls = 0

    def pages(self, path: str, field: str | None = None) -> list[dict[str, Any]]:
        assert path == f"actions/runs/{RUN_ID}/artifacts"
        assert field == "artifacts"
        self.calls += 1
        index = min(self.calls, len(self._names_by_call)) - 1
        return [{"name": name} for name in self._names_by_call[index]]


def _never_sleep(_seconds: float) -> None:
    """Keep the retry-wired path instant in tests (NFR-002/NFR-003)."""


# --- must-be-fresh predicate / key derivation ------------------------------


def test_must_be_fresh_matches_reconcile_predicate() -> None:
    """Side-by-side with reconcile_shards.py::reconcile()'s own predicate:
    `selected is not None and shard.module in selected`."""
    assert must_be_fresh_shards([_MERGE, _UNSELECTED], {"merge"}) == [_MERGE]
    assert must_be_fresh_shards([_MERGE, _UNSELECTED], None) == []
    assert must_be_fresh_shards([_MERGE, _UNSELECTED], set()) == []


def test_required_keys_is_module_shard_index_shard_count() -> None:
    assert required_keys([_MERGE, _MERGE_2]) == frozenset({("merge", 1, 2), ("merge", 2, 2)})


def test_match_artifacts_honors_carried_forward_attempt_tolerance() -> None:
    """An artifact's own attempt may be <= run_attempt, matching
    select_source_artifacts.py's own tolerance -- not necessarily equal."""
    required = required_keys([_MERGE])
    artifacts = [{"name": _artifact_name(_MERGE, attempt=1)}]
    assert match_artifacts(artifacts, run_attempt=3, required=required) == {("merge", 1, 2): _artifact_name(_MERGE, attempt=1)}
    # An artifact from a LATER attempt than the current run must never match.
    later = [{"name": _artifact_name(_MERGE, attempt=4)}]
    assert match_artifacts(later, run_attempt=3, required=required) == {}


def test_match_artifacts_ignores_unrelated_and_unselected_names() -> None:
    required = required_keys([_MERGE])
    artifacts = [{"name": "some-other-artifact"}, {"name": _artifact_name(_UNSELECTED)}]
    assert match_artifacts(artifacts, run_attempt=1, required=required) == {}


# --- red-first recovery-path anchors ----------------------------------------


def test_recovery_within_budget_becomes_visible_after_retry() -> None:
    """RED-FIRST ANCHOR: absent on poll 1, present on poll 2. FAILS against
    the T011 single-attempt stub (it only polls once, so it never sees the
    artifact appear); PASSES once T012 wires retry_with_backoff."""
    api = FakeArtifactsAPI([[], [_artifact_name(_MERGE)]])
    required = required_keys([_MERGE])

    found, missing = poll_for_artifacts(api, run_id=RUN_ID, run_attempt=1, required=required, sleep=_never_sleep)

    assert missing == frozenset()
    assert found[("merge", 1, 2)] == _artifact_name(_MERGE)
    assert api.calls == 2


def test_present_by_final_attempt_within_the_real_budget() -> None:
    """RED-FIRST ANCHOR: present only on the 8th poll (the last one inside the
    real 8-attempt budget). FAILS against the T011 stub (one poll only);
    PASSES once T012 wires retry_with_backoff with MAX_ATTEMPTS=8."""
    calls = [[] for _ in range(MAX_ATTEMPTS - 1)] + [[_artifact_name(_MERGE)]]
    api = FakeArtifactsAPI(calls)
    required = required_keys([_MERGE])

    found, missing = poll_for_artifacts(api, run_id=RUN_ID, run_attempt=1, required=required, sleep=_never_sleep)

    assert missing == frozenset()
    assert found[("merge", 1, 2)] == _artifact_name(_MERGE)
    assert api.calls == MAX_ATTEMPTS


def test_exhausted_budget_never_raises_and_reports_missing() -> None:
    """Terminal path: the artifact never appears within the budget. Must
    never raise -- returns the still-missing key set instead (the caller,
    main(), is what turns this into exit 0 with a diagnostic)."""
    api = FakeArtifactsAPI([[]])
    required = required_keys([_MERGE])

    found, missing = poll_for_artifacts(api, run_id=RUN_ID, run_attempt=1, required=required, sleep=_never_sleep)

    assert found == {}
    assert missing == frozenset({("merge", 1, 2)})
    assert api.calls == MAX_ATTEMPTS


def test_no_must_be_fresh_shards_never_polls() -> None:
    """No must-be-fresh shards selected -- poll_for_artifacts is never even
    called by main() in that case; this pins the required-set-empty shape
    poll_for_artifacts itself must also handle harmlessly if ever called."""
    api = FakeArtifactsAPI([[]])
    found, missing = poll_for_artifacts(api, run_id=RUN_ID, run_attempt=1, required=frozenset(), sleep=_never_sleep)
    assert found == {}
    assert missing == frozenset()
    assert api.calls == 1
