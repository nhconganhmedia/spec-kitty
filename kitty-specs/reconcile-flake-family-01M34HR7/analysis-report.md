---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: reconcile-flake-family-01M34HR7
mission_id: 01M34HR7VHXP24GDY7S68YJ3NT
generated_at: '2026-09-22T16:04:29.183964+00:00'
analyzer_agent: unknown
input_artifacts:
  spec.md:
    path: kitty-specs/reconcile-flake-family-01M34HR7/spec.md
    sha256: 236346efef7fce3e4bd26b3ef7525f4dbbf1111c5aa8e331c50039efb2c66cd5
  plan.md:
    path: kitty-specs/reconcile-flake-family-01M34HR7/plan.md
    sha256: 75f38e0825b82f6619dcb88aea1c82fc88c397279f70cbd1e9b4c8d0ef0d7597
  tasks.md:
    path: kitty-specs/reconcile-flake-family-01M34HR7/tasks.md
    sha256: dc3604ca47d4be5f85e2409952fe5440f43cf5f54bf055c172dbd9db61133f56
  charter:
    path: .kittify/charter/charter.yaml
    sha256: a2b2f62cf1c0fa8987b67f6759d18bcc18b2fb47a8d3ad2783f8fac68b192c77
verdict: blocked
issue_counts:
  medium: 0
  low: 0
  high: 2
  critical: 0
  info: 0
findings:
- id: I1
  severity: high
  category: inconsistency
  summary: "tasks.md's WP02/WP03 'Requirement Refs' rows are stale relative to wps.yaml and the WP prompt-file frontmatter: WP02's row omits NFR-001/NFR-003 and WP03's row omits NFR-001. tasks.md has not been touched since its initial generation (60ea6204f) despite three subsequent rounds of fixes to the same traceability data in wps.yaml (99dd3fa59) and the WP##.md frontmatter (858bdfff0, 0a68bd4d7)."
- id: I2
  severity: high
  category: inconsistency
  summary: WP03's prompt states the 'exact same predicate' reconcile_shards.reconcile() uses for must-be-fresh as `selected is None or shard.module in selected`, but the actual `must_be_fresh` variable in scripts/ci/reconcile_shards.py:126 is `selected is not None and shard.module in selected` -- the opposite condition when `selected is None` (e.g. the selected-modules download step fails/is absent on an ordinary PR run). Building wait_for_artifacts.py to WP03's literal formula would make the poller wait on the ENTIRE registry in exactly that case, reintroducing the multi-minute latency-on-every-PR regression plan.md's own 'Why the poller targets only the SELECTED shard set' section explicitly designed to avoid.
---

## Specification Analysis Report

Fresh, independent re-run of `/spec-kitty.analyze` (round 4) over
`kitty-specs/reconcile-flake-family-01M34HR7/{spec.md,plan.md,tasks.md,wps.yaml,tasks/WP0[1-4]*.md,checklists,charter.md}`,
cross-checked against `scripts/ci/{fleet_verdict.py,fleet_main.py,reconcile_shards.py,select_source_artifacts.py}`
and `.github/workflows/ci-aggregate.yml`. Built independently of prior rounds' reports.

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| I1 | Inconsistency | HIGH | `kitty-specs/reconcile-flake-family-01M34HR7/tasks.md` (WP02/WP03 rows) vs `wps.yaml` and `tasks/WP02-*.md`/`tasks/WP03-*.md` frontmatter | `tasks.md`'s "Requirement Refs" line for WP02 lists `FR-002, FR-003, FR-004, FR-007, FR-009, C-003, C-006` (missing NFR-001, NFR-003) and for WP03 lists `FR-005, FR-006, NFR-003, C-002, C-008` (missing NFR-001). Both `wps.yaml` (fixed round 3, commit `99dd3fa59`) and the WP `.md` frontmatter (fixed rounds 1-2, commits `858bdfff0`/`0a68bd4d7`) now correctly include these refs. `tasks.md` itself has never been regenerated since `60ea6204f` (mission creation) and is the one remaining stale rendering of this same traceability data. | Regenerate `tasks.md` from the now-correct `wps.yaml` (e.g. re-run `spec-kitty agent mission finalize-tasks` or the tasks-phase regeneration path), or hand-edit its two WP rows to match, so all three of {wps.yaml, WP frontmatter, tasks.md} agree. |
| I2 | Inconsistency | HIGH | `kitty-specs/reconcile-flake-family-01M34HR7/tasks/WP03-ci-aggregate-artifact-poll.md:172-176` vs `scripts/ci/reconcile_shards.py:118-126` | WP03 tells the implementer the must-be-fresh predicate to copy is `selected is None or shard.module in selected`. The actual `must_be_fresh` variable in `reconcile()` is `selected is not None and shard.module in selected` (confirmed by reading the live file, including its docstring: "`None` means no selection info is known... in that case every registry shard is required" -- i.e. NOT all shards are must-be-fresh when `selected is None`, since a stale shard can still legitimately be backfilled from `previous_available` per `elif shard.key in previous_available and not must_be_fresh`). WP03's stated formula agrees with the real code only when `selected is not None`; it diverges exactly when `selected is None` -- a real, reachable state (the "download/parse failure" case `read_selected_modules()`'s own docstring names), since the new polling step is gated the same way as `download-selected-modules` (`if: github.event_name != 'workflow_dispatch'`) and therefore still runs even if that upstream download step failed via its `continue-on-error: true`. | Correct WP03's Context section (and re-verify T012's implementation guidance) to state the true predicate: `selected is not None and shard.module in selected`. Flag to the implementer that `selected is None` must poll for ZERO must-be-fresh shards (exit 0 immediately per step 8's own "no must-be-fresh shards to wait for" terminal path), not the full registry. |

**Coverage Summary Table** (computed from `wps.yaml`, the authoritative source -- fully consistent after round 3's fix):

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|
| FR-001 | Yes | T016-T019 (WP04) | |
| FR-002 | Yes | T005, T007, T008, T010 (WP02) | |
| FR-003 | Yes | T006, T007, T009, T010 (WP02) | |
| FR-004 | Yes | T005, T006, T008, T009 (WP02) | |
| FR-005 | Yes | T011-T013 (WP03) | |
| FR-006 | Yes | T011, T012, T014 (WP03) | |
| FR-007 | Yes | T005-T010 (WP02) | |
| FR-008 | Yes | T001-T004 (WP01) | |
| FR-009 | Yes | T010 (WP02) | |
| NFR-001 | Yes | T002 (WP01), wiring in WP02/WP03 | tasks.md under-represents this for WP02/WP03 -- see I1 |
| NFR-002 | Yes | T003 (WP01) | |
| NFR-003 | Yes | T005-T010 (WP02), T011-T014 (WP03) | tasks.md under-represents this for WP02 -- see I1 |
| C-001 | Yes | T018 (WP04) | |
| C-002 | Yes | T014 (WP03) | |
| C-003 | Yes | T007, T008, T009 (WP02) | |
| C-004 | Yes | T003 (WP01) | |
| C-005 | Yes | T004, T010, T015, T016 (all WPs, gate verification) | |
| C-006 | Yes | WP02 (reflexivity, implicit across T005-T010) | |
| C-007 | Yes | T017 (WP04) | |
| C-008 | Yes | T015 (WP03) | |

**Charter Alignment Issues:** None found. C-011 (ATDD-First Discipline) is correctly cited and exists at `.kittify/charter/charter.md:622`; plan.md's Constitution Check table and per-WP red-first sequencing (WP01/WP02/WP03 red-first, WP04 explicitly and correctly exempted) are consistent with it.

**Unmapped Tasks:** None -- every subtask T001-T019 maps to its owning WP's requirement_refs set.

**Verified code/workflow claims (spot-checked, all confirmed accurate):**
- `fleet_verdict.py::report()`/`snapshot()` structure, the `ValueError("...changed before publication; later event will reconcile")` raise, and `dry_run` placement match plan.md exactly.
- `fleet_main.py::report()`'s pre-loop `snapshot()`/`dry_run` sequencing (lines 100-104) and the `elif evidence["state"] != "red"` branch match plan.md's line-numbered claims exactly.
- `reconcile_shards.py` already exports `parse_registry`/`read_selected_modules` via `__all__`.
- `ci-aggregate.yml`'s current step order (`select-current` -> `download-current` -> `last-success` -> `download-previous` -> `download-selected-modules` -> ...) matches plan.md's claimed pre-fix order, confirming the required reorder is real and correctly scoped.
- Both cited `env:` blocks (`ci-aggregate.yml` "Prepare exact source registry..." and "Select reports...") declare `GH_TOKEN` + 3 `SOURCE_*` vars as claimed; the two `download-artifact` `uses:` steps correctly have no `env:` block (inline expression instead).
- Test mocks `API.move_on_second_read`/`pr_reads` (test_fleet_verdict.py) and `RerunAPI`/`head_reads` (test_fleet_main.py) match WP02's detailed behavioral walkthrough exactly.
- SC-003's claimed baseline (`98 passed`) reproduced exactly: `.venv/bin/python -m pytest tests/ci/test_fleet_verdict.py tests/ci/test_fleet_main.py tests/ci/test_reconcile_shards.py -q` -> `98 passed in 5.79s`.
- `scripts/ci/reconcile_retry.py`, `scripts/ci/wait_for_artifacts.py`, and their test files correctly do not yet exist (pre-implementation state, consistent with plan.md's "NEW" designation).
- Issue references (#4652/#4675/#4878/#4882) are already correctly tracked in `issue-matrix.json` (three as `unknown`/pending-WP-implementation, `#4882` auto-classified `not-applicable`/context-only) -- non-gating per the analyze prompt's Issue-Matrix heads-up.

**Metrics:**

- Total Requirements: 20 (9 FR, 3 NFR, 8 C)
- Total Tasks: 19 (T001-T019)
- Coverage % (requirements with >=1 task): 100%
- Ambiguity Count: 0
- Duplication Count: 0
- Critical Issues Count: 0
- High Issues Count: 2

## Next Actions

Two HIGH findings block this round:

1. **I1** -- Regenerate or hand-correct `tasks.md`'s WP02/WP03 "Requirement Refs" rows to match `wps.yaml` (now correct as of round 3).
2. **I2** -- Correct WP03's stated must-be-fresh predicate in `tasks/WP03-ci-aggregate-artifact-poll.md` to `selected is not None and shard.module in selected`, matching `reconcile_shards.py`'s actual `must_be_fresh` variable, and confirm T012's implementation guidance and T011/T014's test coverage reflect the corrected predicate (in particular, that a `selected is None` state polls for zero shards, not the full registry).

Both are fixable without touching spec.md's binding Clarifications/Decision Record. Recommend resolving both before `/spec-kitty.implement`.
