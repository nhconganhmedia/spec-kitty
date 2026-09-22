---
work_package_id: WP02
title: fleet_verdict.py / fleet_main.py retry-then-skip wiring
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-003
- FR-004
- FR-007
- FR-009
- C-003
- C-006
planning_base_branch: fix/reconcile-flake-family-4882
merge_target_branch: fix/reconcile-flake-family-4882
branch_strategy: Planning artifacts for this mission were generated on fix/reconcile-flake-family-4882. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/reconcile-flake-family-4882 unless the human explicitly redirects the landing branch.
subtasks:
- T005
- T006
- T007
- T008
- T009
- T010
history: []
agent_profile: python-pedro
authoritative_surface: scripts/ci/
create_intent: []
execution_mode: code_change
model: ''
owned_files:
- scripts/ci/fleet_verdict.py
- scripts/ci/fleet_main.py
- tests/ci/test_fleet_verdict.py
- tests/ci/test_fleet_main.py
role: implementer
tags: []
tracker_refs: []
---

# WP02: fleet_verdict.py / fleet_main.py retry-then-skip wiring

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match for this work package's `task_type` and `authoritative_surface`.

---

## Objective

Wrap `scripts/ci/fleet_verdict.py::report()` (per-PR `report (<pr>)`, epic child #4878) and
`scripts/ci/fleet_main.py::report()` (main-push `report-main`, epic child #4652) so that
their existing double-snapshot idiom retries the **entire** snapshot→compare sequence a
bounded number of times on disagreement, instead of raising `ValueError` on the first
disagreement — and, on exhausted budget, returns silently (exit 0, diagnostic printed, no
comment/incident posted) rather than raising, trusting `ci-fleet-verdict.yml`'s repeated
per-head `workflow_run` firings to reconcile on a later event.

## Context

**Prerequisite**: `scripts/ci/reconcile_retry.py::retry_with_backoff` (WP01) must already
exist with the exact signature documented in WP01's prompt file before you start T008/T009.
Import it; do not reimplement or hand-roll a second retry loop.

Read `kitty-specs/reconcile-flake-family-01M34HR7/plan.md` in full before starting,
especially the "User Story 2" section (the exact rewiring shape for both files), "Retry
Budget Rationale (NFR-001)" (proposed 4 attempts total, backoff 2s → 4s → 8s), "Campsite-Clean
Scope (§2a.4)" (the `_attempt()` complexity-15 decomposition target — read this carefully,
it sets a concrete, binding target for this WP), "Existing Test That Must Change, and Why
That Is Not a Regression" (the two pre-existing tests you must re-pin), and "Red-First
Application Across All NFR-003 Test Surfaces". Also read spec.md's FR-002, FR-003, FR-004,
FR-007, FR-009, C-003, C-006 rows, and User Story 2's acceptance scenarios in full.

**Current code, verified in this checkout** (read the live files yourself before editing —
line numbers will drift as you edit):

`scripts/ci/fleet_verdict.py::report()` (currently ~40 lines, no complexity target
violation itself — it is a thin sequential body):
```python
def report(api, root, number, workflow_ids, reporter_id, attempt, *, replay=None, dry_run=False) -> None:
    if replay is not None:
        verify_replay_checkout(root, replay)
    pr, evidence = snapshot(api, root, number, workflow_ids, replay)
    comments = api.pages(f"issues/{number}/comments")
    fingerprint = "<!-- evidence: " + json.dumps(evidence, sort_keys=True) + " -->"
    latest = next((c for c in reversed(comments) if re.match(...)), None)
    if (latest and ... and (fingerprint in latest["body"] or ...)):
        return
    final_pr, final_evidence = snapshot(api, root, number, workflow_ids, replay)
    if final_evidence != evidence or final_pr["head"]["sha"] != pr["head"]["sha"]:
        raise ValueError("PR head or CI attempts changed before publication; later event will reconcile")
    if replay is not None:
        verify_replay_checkout(root, replay)
    body = comment_body(api.repository, evidence, reporter_id, attempt)
    if dry_run:
        print(body, end="")
    else:
        api.request(f"issues/{number}/comments", {"body": body})
```

`scripts/ci/fleet_main.py::report()` (currently ~30 lines):
```python
def report(api, root, ids, reporter_id, attempt, *, dry_run=False) -> None:
    evidence = snapshot(api, root, ids)
    text = body(api.repository, evidence, reporter_id, attempt)
    if dry_run:
        print(text, end="")
        return
    incidents = [issue for issue in api.pages("issues?state=open&labels=from%3Aci") if ...]
    if len(incidents) > 1:
        raise ValueError("multiple active main CI incidents; fleet must reconcile ownership")
    incident = incidents[0] if incidents else None
    fingerprint = "<!-- evidence: " + json.dumps(evidence, sort_keys=True) + " -->"
    if incident:
        comments = api.pages(f"issues/{incident['number']}/comments")
        latest = next((c for c in reversed(comments) if ...), incident)
        if fingerprint in latest.get("body", ""):
            return
    elif evidence["state"] != "red":
        print(text, end="")
        return
    if snapshot(api, root, ids) != evidence:
        raise ValueError("main head or CI attempts changed before publication; later event will reconcile")
    if incident:
        if api.request(f"issues/{incident['number']}")["state"] != "open":
            raise ValueError("main CI incident closed before publication; later event will reconcile")
        api.request(f"issues/{incident['number']}/comments", {"body": text})
    else:
        api.request("issues", {"title": ..., "body": INCIDENT + "\n\n" + text, "labels": [...]})
```

**What retries and what does not — this is precise, do not blur it**:
- Only the "unstable evidence between the two snapshot reads" path retries. That is: the
  whole sequence from the FIRST `snapshot()` call through the comparison against the
  re-check `snapshot()` call is what must be retried as one unit (FR-002/FR-003/FR-007/C-003
  — "never catch the disagreement and fall through to publishing the first/stale snapshot").
- `fleet_main.py`'s `elif evidence["state"] != "red": print(text, end=""); return` early
  exit is a **pre-existing, already-benign** early return for a non-red first snapshot — it
  is untouched by this WP. Only the later `if snapshot(...) != evidence: raise ...` path
  (the actual instability-detection point) is what gets wrapped in retry.
- The `dry_run` / `replay` handling in both files stays exactly where it is, outside the
  retry loop — replay is an explicit, exact-revision operator action, not part of the
  raciness this mission targets.
- `snapshot()` itself is **not modified** by this WP. It measures cyclomatic complexity 24
  (`fleet_verdict.py`) and 22 (`fleet_main.py`) today — both above the repo's complexity-15
  ceiling — and plan.md's Campsite-Clean Scope explicitly freezes both as baseline debt,
  deliberately deferred, not silently absorbed into this WP's scope. Do not decompose
  `snapshot()` "while you're in there."

**The `_attempt()` extraction and its complexity-15 target (binding on this WP)**: extract
each file's existing body (from the first `snapshot()` call through the
compare-and-decide-to-publish logic) into a private `_attempt(...)` helper that returns a
tri-state outcome — plan.md's suggested shape:
- `_AlreadyReported()` — the existing dedupe short-circuit fired; nothing to publish, and the
  overall `report()` should return normally without invoking the retry loop's failure path.
- `_Ready(body_text)` (or equivalent) — the two snapshots agreed; ready to publish this
  stabilized evidence.
- `None` — the existing raise condition (snapshots disagree), converted from an exception
  into a retry signal.

`_attempt()` must itself land at or under complexity 15 in BOTH files — plan.md is explicit
that naively moving `report()`'s entire body into `_attempt()` as one block only relocates
the complexity, it does not resolve it. Split the evidence-comparison/classification logic
(are the two snapshots the same?) from the publish-decision logic (what to do with
already-reported / ready / unstable) into two smaller helpers inside `_attempt()` rather than
one large block. `report()` itself becomes a thin wrapper:

```python
outcome = retry_with_backoff(lambda: _attempt(api, root, number, workflow_ids, reporter_id, attempt, replay), max_attempts=4, backoff_seconds=...)
if outcome is None:
    print(f"[ci] deferred @{...}: evidence did not stabilize within retry budget")
    return
if isinstance(outcome, _Ready):
    if dry_run:
        print(outcome.body, end="")
    else:
        api.request(..., {"body": outcome.body})
# _AlreadyReported: nothing further to do
```

**Diagnostic line on exhausted budget (Acceptance Scenario 3, User Story 2)**: on skip, print
a plain `print(...)` line (matching the existing `print`/`::error::`/`::warning::` annotation
conventions already used across `fleet_verdict.py`/`fleet_main.py`/`reconcile_shards.py` — not
raised, not silent) containing, at minimum: the subject identifier (PR number for
`fleet_verdict.py`, or the `main`-head SHA for `fleet_main.py`), the word "deferred" or
"skipped", and the reason "evidence did not stabilize within retry budget".

**Retry budget** (plan.md's proposed numbers — 4 attempts total, backoff 2s → 4s → 8s): wire
this as an explicit, named constant at each call site (not just inherited from
`reconcile_retry.py`'s own defaults, since the primitive has no defaults — every call site
must pass its own `max_attempts`/`backoff_seconds` explicitly). This is what lets NFR-003's
per-call-site exact-attempt-count test catch a call-site wiring bug independent of WP01's own
generic termination proof.

**Existing tests you must re-pin, and a mock-behavior gotcha to verify yourself before
writing the new assertion** — read this carefully, do not guess:

`tests/ci/test_fleet_verdict.py::test_publication_rechecks_head_and_never_mutates_existing_comments`
currently does:
```python
api = API()
api.move_on_second_read = True
with pytest.raises(ValueError, match="changed before publication"):
    report(api, ROOT, 7, IDS, 123, 1)
assert api.posts == []
```
Look at `API.request`'s PR-read branch in `tests/ci/test_fleet_verdict.py` (`class API`):
`self.pr_reads` increments on every `pulls/7` read, and `if self.move_on_second_read and
self.pr_reads > 1: result["head"]["sha"] = "c" * 40`. **This means the SHA moves once, on the
second read, and then STAYS at `"c" * 40` for every subsequent read** — it does not flap
back and forth. Trace through what this means once `report()` retries via `_attempt()`: the
first `_attempt()` call does reads #1 (unmoved, `"a"*40`) and #2 (moved, `"c"*40`) — these
disagree, so `_attempt()` returns `None` (retry). The **second** `_attempt()` call does reads
#3 and #4 — by now `pr_reads > 1` is already true for BOTH of those reads, so both return
`"c"*40` — **they agree with each other** (just not with the original `"a"*40`). Verify this
yourself by reading the live `API` class and tracing it, and design your re-pinned assertion
to match what the mock actually does, not what this paragraph summarizes. If your trace
confirms this, the correct re-pinned assertion is: **no raise**, and a successful post IS
made — but using the evidence for the NEW, stabilized head (`"c"*40`), not the original
`HEAD` (`"a"*40`) constant, and not a fabrication of either. This is exactly what FR-002's
Acceptance Scenario 1 asks for: post the *stabilized* evidence, not the stale first read.
Update the assertion accordingly (e.g. `api.posts[0]["body"].startswith(f"[ci] green
@{'c'*40}")`), and add a call-count assertion proving `_attempt()`/`snapshot()` was invoked
the expected number of times for a two-attempt recovery.

Because this existing mock does NOT exercise the "genuinely never stabilizes" (exhausted
budget) path, **you must also add a brand-new test** (not a re-pin) using a purpose-built
mock that keeps flipping or never stabilizes across the full retry budget, to prove FR-004's
skip-and-defer terminal behavior: no post, no raise, and the diagnostic print described above.
Assert the exact call count at the exhausted-budget path (e.g. `snapshot` calls ==
2 × max_attempts, or whatever your `_attempt()` shape implies — pin the real number, do not
approximate it).

The equivalent `fleet_main.py` test,
`test_attempt_change_during_publication_refuses_stale_verdict`, needs the identical
treatment, but its mock does NOT move the head — read its `RerunAPI` mock
(`tests/ci/test_fleet_main.py`) carefully before assuming otherwise. `RerunAPI.request()`
fires `self.runs["ci-quality.yml"][0].update(run_attempt=2, status="in_progress",
conclusion=None)` when `path == "git/ref/heads/main" and self.head_reads == 1` — it mutates
the ci-quality workflow-run's `run_attempt`/`status`/`conclusion`, not `self.head`.
`move_on_second_read` (the actual head-SHA mover, inherited from `MainAPI`) is never set
`True` anywhere in this test, so the `main`-head SHA is constant throughout — the instability
this mock manufactures is entirely a CI-attempt-state change between the two `snapshot()`
reads, not a moved head. This likely produces a different re-pin shape than
`fleet_verdict.py`'s case: under retry, the SECOND `_attempt()` call's first `snapshot()`
will likely already observe ci-quality as `status="in_progress"/conclusion=None` — evidence
state becomes "running", not "red" — which likely routes into the untouched
`elif evidence["state"] != "red": print(text, end=""); return` early-return branch, rather
than a "stabilized, then publish" outcome analogous to `fleet_verdict.py`'s re-pin. Trace it
yourself; do not assume it behaves identically to `fleet_verdict.py`'s `API` mock, and do not
take this paragraph's prediction as a substitute for that trace. Re-pin to whatever the
traced behavior actually implies, and add a separate purpose-built never-stabilizes mock for
the FR-004 exhausted-budget path here too, matching `fleet_main.py`'s own terminal semantics
(also no raise, no incident post/update, diagnostic print, per FR-004).

**FR-009 cross-invocation isolation test (owned by this WP, not WP04)**: plan.md's round-2
revision explicitly moved this test into WP02's own commit sequence, because it has no
pre-fix red-first anchor (there is no pre-fix retry state to leak — the property trivially
holds before this mission) and WP04 was re-scoped to carry no test obligations of its own
(see plan.md's Constitution Check C-011 row and "Deviations" item 6). Add a test — in
either `test_fleet_verdict.py` or `test_fleet_main.py` (your choice, or both, whichever is
the more natural home given how you shaped `_attempt()`) — that runs two concurrent/
interleaved invocations of `report()` for two different subjects (e.g. two different PR
numbers, or a PR vs. a `main`-head push) under simulated instability, and asserts neither
invocation reads or mutates any shared object, global variable, or filesystem path belonging
to the other. Because `_attempt()`'s closure captures only its own call's local arguments and
`retry_with_backoff` is a pure function with no global state (per WP01), this should hold by
construction — the test proves it, it does not need to "make" it hold.

**Charter C-011 (ATDD-First Discipline)** binds this WP: it introduces new functional code
(the retry wiring), so a red-first commit (failing tests only — the new recovery/terminal
tests from T005/T006, run against the UNMODIFIED `report()`, confirmed to fail the old way:
an unretried `ValueError` raise on first disagreement) must precede the implementation
commit(s) (T008/T009). The two re-pinned tests (T007) are edits to tests that are already
red-in-a-different-way against the unmodified code (they currently pass by asserting the
OLD `raise` contract) — per plan.md's "Existing Test That Must Change" section, treat their
edits as part of the same commit sequence as the brand-new tests, not as a separate
standalone red-first anchor of their own (they have no meaningful "red" state to capture
before the fix, since they already pass — just against the wrong contract).

## Subtask T005: Red-first — new recovery/terminal tests for `fleet_verdict.py::report()`

**Purpose**: Establish the red-first anchor for `fleet_verdict.py`'s new retry contract.

**Steps**:
1. In `tests/ci/test_fleet_verdict.py`, add a new test asserting the recovery path: a mock
   `snapshot()` (or a mock `API` shaped like the existing `move_on_second_read` pattern, or a
   `monkeypatch`'d `snapshot` function — your choice, whichever is more direct) that disagrees
   on the first pair of reads and agrees on a subsequent pair within the 4-attempt budget.
   Assert `report()` posts using the stabilized evidence, does not raise, and the retry-site
   call count matches your `_attempt()` shape's expected count.
2. Add a new test for the exhausted-budget path: evidence that never stabilizes across all 4
   attempts. Assert no post (`api.posts == []`), no raise, and the FR-004 diagnostic line is
   printed (use `capsys` to capture stdout).
3. Run both new tests against the CURRENT, unmodified `report()` and confirm they fail —
   expect the existing `raise ValueError("PR head or CI attempts changed before
   publication...")` to fire on the first disagreement, since `retry_with_backoff` is not yet
   wired in. This is the red-first anchor.
4. Commit this file's new-test-only diff now, as a distinct commit, before any implementation
   changes to `fleet_verdict.py` itself.

**Files**: `tests/ci/test_fleet_verdict.py` (adds 2+ new tests).

**Validation**: `.venv/bin/python -m pytest tests/ci/test_fleet_verdict.py -q -k
"recovery or exhaust or retry"` (adjust the `-k` filter to your actual test names) shows RED
against the unmodified `scripts/ci/fleet_verdict.py`.

## Subtask T006: Red-first — new recovery/terminal tests for `fleet_main.py::report()`

**Purpose**: Same as T005, for `fleet_main.py`.

**Steps**: Mirror T005's steps exactly, against `fleet_main.py::report()`'s equivalent
instability-detection point (`if snapshot(api, root, ids) != evidence: raise ValueError(...)`).
Use `MainAPI`/`RerunAPI`-shaped mocks consistent with the file's existing test patterns. Cover
both the recovery-within-budget path and the exhausted-budget path (no post, no incident
update/creation, no raise, diagnostic print). Confirm both new tests fail against the
unmodified `fleet_main.py::report()` before proceeding, and commit as part of the same
red-first commit sequence as T005 (either combined or as a second preceding commit — both
must predate any implementation commit).

**Files**: `tests/ci/test_fleet_main.py` (adds 2+ new tests).

**Validation**: Same red-first confirmation pattern as T005, scoped to `test_fleet_main.py`.

## Subtask T007: Re-pin the two existing stale-contract tests

**Purpose**: Update the two pre-existing tests that assert the exact pre-fix `raise`
behavior this mission removes, per plan.md's "Existing Test That Must Change" rationale
(Standing Order #4: "judge the test, not git-blame... stale → re-pin").

**Steps**:
1. Trace `tests/ci/test_fleet_verdict.py`'s `class API`'s `move_on_second_read` semantics
   yourself (see the detailed walkthrough in Context above) and update
   `test_publication_rechecks_head_and_never_mutates_existing_comments` to assert the new
   contract your traced behavior actually implies — do not copy the Context section's
   prediction verbatim without verifying it against the live mock and your actual `_attempt()`
   implementation.
2. Do the same for `tests/ci/test_fleet_main.py`'s
   `test_attempt_change_during_publication_refuses_stale_verdict`, tracing `RerunAPI`'s
   `head_reads == 1` condition yourself.
3. Keep both tests' names unchanged (do not rename — a rename would look like deletion +
   addition to a reviewer diffing test coverage) unless the new behavior they assert makes
   the original name actively misleading, in which case rename AND note the rename explicitly
   in your commit message / completion notes so a reviewer is not confused.
4. This subtask happens AFTER T008/T009's implementation lands (these are integration-level
   re-pins against the real retry wiring, not new red-first anchors) — sequence it after the
   implementation commits, or fold it into the same commit as T008/T009 if that is more
   natural given how you've structured the work. Either way, do not leave these two tests
   asserting the old `raise` contract once `_attempt()`/`retry_with_backoff` are wired in —
   that would be a real regression (a stale assertion silently passing for the wrong reason,
   or failing and being ignored).

**Files**: `tests/ci/test_fleet_verdict.py`, `tests/ci/test_fleet_main.py` (edits to existing
tests, not new files).

**Validation**: Both re-pinned tests pass against the fully-wired `report()` implementations
(post-T008/T009), and continue to prove invariant (a) — never publish from a stale/first
snapshot — against the NEW retry contract.

## Subtask T008: Extract `_attempt()` and wire retry into `fleet_verdict.py::report()`

**Purpose**: Make T005's tests pass; implement FR-002/FR-004/FR-007/C-003 for the per-PR
surface.

**Steps**:
1. Extract `report()`'s existing snapshot→dedupe→re-snapshot→compare body into a private
   `_attempt(api, root, number, workflow_ids, reporter_id, attempt, replay) -> _Outcome`
   helper, per the Context section's tri-state shape (`_AlreadyReported` / `_Ready(body)` /
   `None`). Split the comparison-classification logic from the publish-decision logic into
   two smaller helpers inside `_attempt()` if needed to hit the complexity-15 target (see
   Context — do not move the whole body into `_attempt()` as one block).
2. Rewrite `report()` as the thin `retry_with_backoff`-wrapped shell shown in Context, with
   the explicit `max_attempts=4` / a documented `backoff_seconds` callable (2s → 4s → 8s per
   plan.md's Retry Budget Rationale) and `sleep=time.sleep` (the real default — only tests
   inject a fake `sleep`).
3. Preserve `dry_run`/`replay` handling exactly where it is (outside/around the retry loop,
   not inside `_attempt()`'s retried body in a way that would re-run replay verification on
   every attempt unnecessarily — read plan.md's exact framing again if unsure).
4. Run `radon cc -s scripts/ci/fleet_verdict.py` (or equivalent complexity tool available in
   this environment) and confirm `_attempt()` (and any helpers it calls) land at or under
   complexity 15. If not, split further.
5. Run T005's tests and confirm they now pass (RED → GREEN).

**Files**: `scripts/ci/fleet_verdict.py` (modified — extraction + retry wiring).

**Validation**: `.venv/bin/python -m pytest tests/ci/test_fleet_verdict.py -q` — full file
green. Complexity check on `_attempt()` and any new helpers `<= 15`.

## Subtask T009: Extract `_attempt()` and wire retry into `fleet_main.py::report()`

**Purpose**: Make T006's tests pass; implement FR-003/FR-004/FR-007 for the main-push
surface.

**Steps**: Mirror T008 exactly for `fleet_main.py::report()`. Critical difference to
preserve: the `elif evidence["state"] != "red": print(text, end=""); return` early exit
happens BEFORE the retry-worthy instability check and is untouched — only the
`if snapshot(...) != evidence: raise ...` path (and the subsequent incident-open/closed
check) is wrapped in retry logic. `fleet_main.py::report()` itself measures complexity 18
pre-extraction (plan.md's own measurement) — this is the one violation plan.md does NOT
freeze as baseline debt, since this WP already restructures it; hit the `<=15` target for
`_attempt()` the same way as T008.

**Files**: `scripts/ci/fleet_main.py` (modified — extraction + retry wiring).

**Validation**: `.venv/bin/python -m pytest tests/ci/test_fleet_main.py -q` — full file
green. Complexity check `<= 15`.

## Subtask T010: FR-009 isolation test, full re-pin verification, and gates

**Purpose**: Complete this WP's test obligations (including the FR-009 test plan.md moved
here) and confirm the whole WP is gate-clean.

**Steps**:
1. Add the FR-009 cross-invocation isolation test described in Context (two concurrent/
   interleaved `report()` invocations for two different subjects, asserting no shared-state
   coupling).
2. Confirm T007's re-pinned tests pass against the final implementation.
3. Re-run WP01's `tests/ci/test_reconcile_retry.py` unmodified to confirm this WP did not
   regress the shared primitive (per the repo's blast-radius test policy: re-run a WP's
   upstream dependency's own tests before integrating).
4. Run the full baseline: `.venv/bin/python -m pytest tests/ci/test_fleet_verdict.py
   tests/ci/test_fleet_main.py -q` and confirm the file-level pass count is consistent with
   SC-003's baseline (98 passed across the three-file baseline as of 2026-09-22 — this WP's
   two files' share of that, plus your new tests, all green; no pre-existing test silently
   dropped).
5. Run `uv run --frozen ruff check .` and `uv run --frozen ruff format --check .` scoped at
   minimum to this WP's four files.
6. Confirm `uv run --frozen ruff check --select TID251 .` has nothing new to flag (no new
   banned import introduced).

**Files**: `tests/ci/test_fleet_verdict.py` and/or `tests/ci/test_fleet_main.py` (FR-009
test addition — pick the more natural home, or add to both if the isolation property is
meaningfully different per-file).

**Validation**: Full WP04-facing baseline (`test_fleet_verdict.py` + `test_fleet_main.py`)
green; `ruff check`/`ruff format --check` clean; no TID251 findings.

## Definition of Done

- `scripts/ci/fleet_verdict.py::report()` and `scripts/ci/fleet_main.py::report()` both
  retry their full double-snapshot sequence via `reconcile_retry.retry_with_backoff` (WP01),
  never catching the disagreement condition to fall through to a stale publish (FR-007/C-003).
- On exhausted retry budget, both functions return without raising and without any
  `api.request(...)` write call, printing a diagnostic line naming the subject, "deferred"/
  "skipped", and "evidence did not stabilize within retry budget" (FR-004).
- The two pre-existing tests (`test_publication_rechecks_head_and_never_mutates_existing_comments`,
  `test_attempt_change_during_publication_refuses_stale_verdict`) are re-pinned to the new
  contract, verified against the actual mock behavior you traced yourself, not assumed.
- New tests exist proving: recovery-within-budget publishes stabilized (not stale) evidence;
  exhausted-budget skips silently with the required diagnostic; the FR-009 cross-invocation
  isolation property.
- `_attempt()` (and any helpers it calls) in both files measure complexity `<= 15`.
  `snapshot()` in both files is unchanged (frozen baseline debt per plan.md).
- Git history shows a red-first commit (new tests only, failing against unmodified code)
  preceding the implementation commits, per charter C-011.
- `tests/ci/test_fleet_verdict.py` and `tests/ci/test_fleet_main.py` both pass in full;
  `ruff check .` / `ruff format --check .` clean for this WP's four files (C-005); this WP
  triggers the `ci-modules.yml` `ci` shard (no diff-cover floor applies, per C-008, but tests
  are still required and provided).
- No new third-party dependency added.

## Risks

- **Mock-behavior misreading risk**: the two re-pin mocks are subtle and NOT the same
  mechanism — do not assume one behaves like the other. `fleet_verdict.py`'s `API` mock
  (`move_on_second_read`) moves the PR head SHA ONCE, on the second `pulls/7` read, and STAYS
  moved; it does not flap. `fleet_main.py`'s `RerunAPI` mock is different: it never enables
  `move_on_second_read`, so the `main`-head SHA is constant throughout — instead it mutates
  the ci-quality workflow-run's `run_attempt`/`status`/`conclusion` on `head_reads == 1`,
  which is a CI-attempt-state change, not a head move, and likely lands in a different branch
  (the untouched `evidence["state"] != "red"` early return) than a "stabilized, then publish"
  outcome. An implementer who assumes `RerunAPI` behaves like `fleet_verdict.py`'s mock — or
  like a flapping mock — will write an incorrect re-pinned assertion. Trace each mock for
  real before writing its assertion (Context section above walks through the exact reasoning
  for both; do not take that walkthrough as a substitute for tracing `fleet_main.py`'s mock
  yourself).
- **Complexity relocation risk**: naively moving `report()`'s whole body into `_attempt()`
  satisfies "it compiles" but not the binding `<=15` target — verify with an actual
  complexity measurement, not by inspection alone.
- **Scope-creep risk on `snapshot()`**: both files' `snapshot()` functions are well above the
  complexity ceiling and sit right next to the code you're editing. Do not decompose them —
  plan.md deliberately freezes them as baseline debt; touching them is out of this WP's
  Locality of Change.

## Reviewer Guidance

Verify the red-first commit ordering literally (checkout the red-first commit, run the new
tests, confirm they fail the OLD way — an unretried `raise ValueError`). Verify the two
re-pinned tests' new assertions actually match the live mock's traced behavior (re-derive the
trace yourself rather than trusting the diff). Verify `_attempt()`'s complexity in both files
with a real measurement. Verify `fleet_main.py`'s benign early-return branch
(`evidence["state"] != "red"`) is untouched and NOT inside the retry loop. Verify the FR-009
isolation test genuinely exercises two concurrent/interleaved subjects, not two sequential
calls that happen not to share obvious state by accident.

Run: `spec-kitty agent action implement WP02 --agent claude`
