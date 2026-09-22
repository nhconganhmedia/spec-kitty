"""Bounded pre-download poll for selected shard artefact visibility (FR-005/006).

``ci-aggregate.yml`` fires once per non-repeating ``workflow_run`` event (from
``CI Modules``); unlike ``ci-fleet-verdict.yml``'s repeating per-head events
(``fleet_verdict.py``/``fleet_main.py``'s retry-then-skip), there is no later
event to defer to here. This module polls the triggering run's artifact list
for every SELECTED (must-be-fresh) shard's expected artifact name, wrapped in
WP01's bounded ``reconcile_retry.retry_with_backoff``.

Architectural floor (do not regress): on budget exhaustion this module ALWAYS
exits 0 and never raises -- it only WIDENS the window before the workflow
falls through to the existing ``actions/download-artifact`` steps.
``scripts/ci/reconcile_shards.py::main()`` remains the single, unmodified,
fail-closed terminus that decides completeness (FR-006); this module is not
part of that decision and must never become one.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from scripts.ci.fleet_verdict import GitHub
from scripts.ci.reconcile_shards import RegistryShard
from scripts.ci.select_source_artifacts import ARTIFACT

__all__ = [
    "MAX_ATTEMPTS",
    "ShardKey",
    "match_artifacts",
    "must_be_fresh_shards",
    "poll_for_artifacts",
    "required_keys",
    "main",
]

ShardKey = tuple[str, int, int]

# Retry Budget Rationale (plan.md NFR-001): 8 attempts, 5s -> 10s -> 20s ->
# 30s (cap) -- 5,10,20,30,30,30,30 between the 8 attempts, ~155s (~2.6 min)
# total bounded wait.
MAX_ATTEMPTS = 8
_BACKOFF_SCHEDULE = (5.0, 10.0, 20.0, 30.0)


def _backoff_seconds(i: int) -> float:
    """5s -> 10s -> 20s -> 30s, capped at 30s for every attempt beyond that."""
    index = min(i, len(_BACKOFF_SCHEDULE)) - 1
    return _BACKOFF_SCHEDULE[index]


def must_be_fresh_shards(registry_shards: list[RegistryShard], selected: set[str] | None) -> list[RegistryShard]:
    """The exact ``must_be_fresh`` predicate ``reconcile_shards.py::reconcile()``
    applies later in the same job, computed once here and reused -- never a
    second, independently-invented definition of "must-be-fresh."
    """
    return [shard for shard in registry_shards if selected is not None and shard.module in selected]


def required_keys(shards: list[RegistryShard]) -> frozenset[ShardKey]:
    """(module, shard_index, shard_count) keys the poller must see visible."""
    return frozenset((shard.module, shard.shard_index, shard.shard_count) for shard in shards)


def match_artifacts(artifacts: list[dict[str, object]], run_attempt: int, required: frozenset[ShardKey]) -> dict[ShardKey, str]:
    """Pure: bind each REQUIRED key to the artifact name visible in ``artifacts``.

    Reuses ``select_source_artifacts.py``'s own artifact-naming regex (import,
    not a second copy that could drift) and its carried-forward-attempt
    tolerance: an artifact's own ``attempt`` may be any value ``<=
    run_attempt`` (not necessarily equal to it).
    """
    found: dict[ShardKey, str] = {}
    for artifact in artifacts:
        match = ARTIFACT.fullmatch(str(artifact.get("name", "")))
        if match is None:
            continue
        module, shard_index, shard_count, attempt = match.group(1), int(match.group(2)), int(match.group(3)), int(match.group(4))
        if attempt > run_attempt:
            continue
        key = (module, shard_index, shard_count)
        if key in required:
            found[key] = str(artifact["name"])
    return found


def poll_for_artifacts(
    api: GitHub,
    *,
    run_id: str,
    run_attempt: int,
    required: frozenset[ShardKey],
    max_attempts: int = MAX_ATTEMPTS,
    backoff_seconds: Callable[[int], float] = _backoff_seconds,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[ShardKey, str], frozenset[ShardKey]]:
    """T011 STUB -- single, UNRETRIED poll (the eventual signature is already
    final so T012 changes only the body, never the call sites or tests).

    ``max_attempts``/``backoff_seconds``/``sleep`` are accepted but ignored: a
    must-be-fresh shard whose artifact becomes visible only on a later poll is
    therefore reported missing here even though it would eventually appear --
    this is exactly the "fails once, passes on retry no longer reliably
    holds" defect #4675 describes, and it is the red-first anchor T012
    resolves by wrapping this call in ``retry_with_backoff``.
    """
    del max_attempts, backoff_seconds, sleep  # unused until T012's retry wiring
    artifacts = api.pages(f"actions/runs/{run_id}/artifacts", field="artifacts")
    found = match_artifacts(artifacts, run_attempt, required)
    return found, required - found.keys()


def main() -> int:  # pragma: no cover - CLI edge, completed in T012
    raise NotImplementedError("wait_for_artifacts.py CLI edge is completed in T012")


if __name__ == "__main__":
    sys.exit(main())
