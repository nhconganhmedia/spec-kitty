"""Reconcile main-push CI into the fleet's existing P0 issue intake.

The reporter consumes metadata only. It uses the existing main-push CI gates,
not the nightly/full release acceptance suite. PROGRAM.md section 9 and planning
agents/ci.md step 6 own the red-main P0 policy; groom/controller consume the
from:ci + status:triage queue. An open incident gets subsequent observations,
including recovery, but only the fleet closes or changes its priority.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import time
from pathlib import Path
from typing import Any, TypeAlias, cast

import yaml

from scripts.ci.fleet_verdict import AGGREGATE, PR_WORKFLOWS, GitHub, automatic_aggregate, classify, comment_body
from scripts.ci.reconcile_retry import retry_with_backoff

INCIDENT = "<!-- spec-kitty-main-ci-incident-v1 -->"


def main_workflows(root: Path) -> tuple[set[str], set[str]]:
    """Read unconditional and conditional main-push gates from trusted YAML."""
    required: set[str] = set()
    conditional: set[str] = set()
    for name in PR_WORKFLOWS:
        document = yaml.safe_load((root / ".github/workflows" / name).read_text(encoding="utf-8"))
        trigger = document.get("on", document.get(True, {})).get("push")
        if trigger is None:
            continue
        if set(trigger) - {"branches", "paths"}:
            raise ValueError(f"unsupported main push policy in {name}")
        if not any(fnmatch.fnmatchcase("main", pattern) for pattern in trigger.get("branches", [])):
            continue
        (conditional if trigger.get("paths") else required).add(name)
    if not {"ci-router.yml", "ci-modules.yml", "ci-quality.yml", "packs.yml", "ci-windows.yml"} <= required:
        raise ValueError("continuous main-push CI inventory changed")
    return required, conditional


def snapshot(api: GitHub, root: Path, workflow_ids: dict[str, int]) -> dict[str, Any]:
    head = api.request("git/ref/heads/main")["object"]["sha"]
    if not isinstance(head, str) or not re.fullmatch("[0-9a-f]{40}", head):
        raise ValueError("main has an invalid head")
    required, conditional = main_workflows(root)
    found = api.pages(f"actions/runs?head_sha={head}&event=push&branch=main", "workflow_runs")
    runs: dict[str, Any] = {}
    for name in sorted(required | conditional):
        matching = [
            run
            for run in found
            if run.get("workflow_id") == workflow_ids[name]
            and run.get("repository", {}).get("full_name") == api.repository
            and run.get("head_repository", {}).get("full_name") == api.repository
            and run.get("head_sha") == head
            and run.get("head_branch") == "main"
            and run.get("event") == "push"
            and run.get("path") == f".github/workflows/{name}"
            and type(run.get("id")) is int
            and run["id"] > 0
            and type(run.get("run_attempt")) is int
            and run["run_attempt"] > 0
        ]
        latest = max(matching, key=lambda run: (run["id"], run["run_attempt"]), default=None)
        if name in required or latest:
            runs[name] = latest
    modules = runs.get("ci-modules.yml")
    runs[AGGREGATE] = (
        automatic_aggregate(api, workflow_ids[AGGREGATE], modules, f"CI Aggregate source {modules['id']} attempt {modules['run_attempt']}") if modules else None
    )
    evidence = {
        name: ({key: run.get(key) for key in ("id", "run_attempt", "head_sha", "event", "status", "conclusion", "html_url")} if run else None)
        for name, run in sorted(runs.items())
    }
    return {
        "head": head,
        "state": classify(runs, set()),
        "runs": evidence,
        "scope": "continuous-main-push",
        "conditional_gates_not_observed": sorted(conditional - runs.keys()),
    }


def body(repository: str, evidence: dict[str, Any], reporter_id: int, attempt: int) -> str:
    report = comment_body(repository, evidence, reporter_id, attempt)
    return report + (
        "\nThis observes the current main head, not nightly/full-suite release acceptance. "
        "Path-filtered gates are included when a matching push run exists; absent conditional gates are listed in the evidence.\n"
        "\nRed main is P0 under PROGRAM.md section 9 and agents/ci.md step 6. "
        "The fleet should investigate the named failing gates; this report does not attribute a culprit PR or test node. "
        "A later green observation is recovery evidence for the fleet to assess, not automatic closure.\n"
    )


_MAX_ATTEMPTS = 4


def _backoff_seconds(attempt: int) -> float:
    """2s -> 4s -> 8s (plan.md's Retry Budget Rationale for the fleet-verdict pair)."""
    return float(2.0 * (2 ** (attempt - 1)))


class _AlreadyReported:
    """The existing dedupe short-circuit fired; nothing to publish."""


class _NothingToReport:
    """The pre-existing `evidence["state"] != "red"` early return fired.

    Condition and action are unchanged from the pre-fix code (same check, same
    print-and-return behavior) -- this outcome only marks that it now runs inside
    _attempt(), evaluated fresh on every retry attempt using that attempt's own
    snapshot, distinct from both _Ready (ready to publish) and None (retry-worthy).
    """


class _Ready:
    """The two snapshots agreed; ready to publish this stabilized evidence."""

    def __init__(self, text: str, head: str, incident_number: int | None) -> None:
        self.text = text
        self.head = head
        self.incident_number = incident_number


_Outcome: TypeAlias = _AlreadyReported | _NothingToReport | _Ready | None


def _open_incidents(api: GitHub) -> list[dict[str, Any]]:
    incidents = [
        issue
        for issue in api.pages("issues?state=open&labels=from%3Aci")
        if not issue.get("pull_request") and issue.get("user", {}).get("type") == "Bot" and INCIDENT in (issue.get("body") or "")
    ]
    if len(incidents) > 1:
        raise ValueError("multiple active main CI incidents; fleet must reconcile ownership")
    return incidents


def _already_reported_to_incident(api: GitHub, incident: dict[str, Any], evidence: dict[str, Any]) -> bool:
    comments = api.pages(f"issues/{incident['number']}/comments")
    latest = next(
        (comment for comment in reversed(comments) if comment.get("user", {}).get("type") == "Bot" and "<!-- evidence:" in comment.get("body", "")), incident
    )
    fingerprint = "<!-- evidence: " + json.dumps(evidence, sort_keys=True) + " -->"
    return fingerprint in latest.get("body", "")


def _attempt(api: GitHub, root: Path, ids: dict[str, int], reporter_id: int, attempt: int) -> _Outcome:
    """One full snapshot -> incident-lookup -> re-snapshot -> compare cycle.

    Retries the WHOLE pair as one unit (FR-003/FR-007): the two snapshot reads below are
    never partially reused across attempts, and a disagreement here converts to ``None``
    (a retry signal), never a fall-through publish of stale evidence. Performs its own
    fresh snapshot() call(s) -- it never reuses report()'s pre-loop evidence.
    """
    evidence = snapshot(api, root, ids)
    text = body(api.repository, evidence, reporter_id, attempt)
    incidents = _open_incidents(api)
    incident = incidents[0] if incidents else None
    if incident:
        if _already_reported_to_incident(api, incident, evidence):
            return _AlreadyReported()
    elif evidence["state"] != "red":
        print(text, end="")
        return _NothingToReport()
    if snapshot(api, root, ids) != evidence:
        return None
    return _Ready(text, evidence["head"], incident["number"] if incident else None)


def report(api: GitHub, root: Path, ids: dict[str, int], reporter_id: int, attempt: int, *, dry_run: bool = False) -> None:
    evidence = snapshot(api, root, ids)
    text = body(api.repository, evidence, reporter_id, attempt)
    if dry_run:
        print(text, end="")
        return

    def attempt_once() -> _AlreadyReported | _NothingToReport | _Ready | None:
        return _attempt(api, root, ids, reporter_id, attempt)

    # mypy cannot solve T for Callable[[], T | None] against a Union-returning callback
    # (it joins to `object` instead of the real outcome union); attempt_once()'s own
    # signature above is the real, checked contract, so this narrows what mypy could not.
    outcome = cast(
        "_AlreadyReported | _NothingToReport | _Ready | None",
        retry_with_backoff(
            attempt_once,
            max_attempts=_MAX_ATTEMPTS,
            backoff_seconds=_backoff_seconds,
            sleep=time.sleep,
        ),
    )
    if outcome is None:
        print(f"[ci] deferred @{evidence['head']}: evidence did not stabilize within retry budget")
        return
    if isinstance(outcome, (_AlreadyReported, _NothingToReport)):
        return
    if outcome.incident_number is not None:
        if api.request(f"issues/{outcome.incident_number}")["state"] != "open":
            raise ValueError("main CI incident closed before publication; later event will reconcile")
        api.request(f"issues/{outcome.incident_number}/comments", {"body": outcome.text})
    else:
        api.request(
            "issues",
            {
                "title": f"main-push CI is red at {outcome.head[:12]}",
                "body": INCIDENT + "\n\n" + outcome.text,
                "labels": ["type:fix", "priority:P0", "from:ci", "status:triage"],
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--reporter-id", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    api = GitHub(args.repository)
    definitions = api.pages("actions/workflows", "workflows")
    ids = {Path(row["path"]).name: row["id"] for row in definitions if row["path"].startswith(".github/workflows/")}
    if not (PR_WORKFLOWS | {AGGREGATE}) <= ids.keys():
        raise ValueError("required Actions workflow definition missing")
    report(api, Path(__file__).resolve().parents[2], ids, args.reporter_id, args.attempt, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
