---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: reconcile-flake-family-01M34HR7
mission_id: 01M34HR7VHXP24GDY7S68YJ3NT
generated_at: '2026-09-22T15:39:58.675105+00:00'
analyzer_agent: unknown
input_artifacts:
  spec.md:
    path: kitty-specs/reconcile-flake-family-01M34HR7/spec.md
    sha256: 236346efef7fce3e4bd26b3ef7525f4dbbf1111c5aa8e331c50039efb2c66cd5
  plan.md:
    path: kitty-specs/reconcile-flake-family-01M34HR7/plan.md
    sha256: 62917258eac2230231914c1fc3ac19f070f6e54cae7152fc99f0acff61da557f
  tasks.md:
    path: kitty-specs/reconcile-flake-family-01M34HR7/tasks.md
    sha256: dc3604ca47d4be5f85e2409952fe5440f43cf5f54bf055c172dbd9db61133f56
  charter:
    path: .kittify/charter/charter.yaml
    sha256: a2b2f62cf1c0fa8987b67f6759d18bcc18b2fb47a8d3ad2783f8fac68b192c77
verdict: ready
issue_counts:
  medium: 1
  critical: 0
  low: 1
  high: 0
  info: 0
findings:
- id: I1
  severity: medium
  category: inconsistency
  summary: "plan.md's fleet_main.py rewiring paragraph is silent on the report()-level pre-loop snapshot() dry_run boundary that ruling #1 (TASKS-FRESH2-002) required and WP02 correctly implements, and its 'differs...in ONE...way' framing understates the actual divergence from fleet_verdict.py."
- id: T1
  severity: low
  category: coverage
  summary: WP02's YAML frontmatter requirement_refs omits NFR-003, even though WP02's body (T005/T006/T007/T010) is the primary owner of NFR-003(1)/(2)/(4) test-surface coverage; a traceability gap, not a functional defect.
---

## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| I1 | Inconsistency | MEDIUM | plan.md:426-448 (fleet_main.py rewiring paragraph) vs. `scripts/ci/fleet_main.py:99-104` vs. `tasks/WP02-fleet-verdict-fleet-main-retry.md:154-164,446-453` | plan.md's "fleet_main.py::report() rewiring" paragraph says the file's terminal behavior "differs slightly from fleet_verdict.py's in ONE pre-existing way" and names only the `elif`/four-state branch. It never mentions the separate, `report()`-level pre-loop `snapshot()` call that must precede the `dry_run` check and stay outside `retry_with_backoff`/`_attempt()` — the exact fix operator ruling #1 (TASKS-FRESH2-002) mandated for `fleet_main.py` specifically (WP02 itself, line 281, calls this pre-loop snapshot something "added this round to fix the dry_run boundary"). Verified against live code: `scripts/ci/fleet_main.py:99-104` today calls `snapshot()` once, unconditionally, before the `dry_run` check, then (if not dry_run) proceeds through incident lookup/elif/re-check-snapshot — a structurally different `dry_run` placement than `fleet_verdict.py::report()`, where `dry_run` is checked once, near the very end, after both snapshots already ran inside what becomes `_attempt()`. plan.md's "identical shape...the same way" / "ONE...way" language is therefore incomplete against what WP02 (correctly) specifies and the live code requires — a second, real structural divergence (the extra pre-loop snapshot) exists and is un-described in plan.md. | Amend plan.md's fleet_main.py rewiring paragraph to name the pre-loop-snapshot dry_run mechanism as a second, explicit divergence from fleet_verdict.py's shape (or generalize "in ONE...way" to "in the following ways"), matching WP02's already-correct T009 text. No functional-code risk today — WP02/tasks.md is the artifact implementers actually follow and it states the requirement correctly — this is a plan.md documentation-consistency gap. |
| T1 | Coverage | LOW | tasks.md WP02 frontmatter `requirement_refs` vs. `tasks/WP02-fleet-verdict-fleet-main-retry.md` body (T005/T006/T007/T010) | WP02's `requirement_refs` frontmatter list (FR-002, FR-003, FR-004, FR-007, FR-009, C-003, C-006) omits `NFR-003`, even though WP02's body is the primary implementer of NFR-003(1) (fleet_verdict.py mocked-retry tests), NFR-003(2) (fleet_main.py mocked-retry tests), and NFR-003(4) (the FR-009 cross-invocation isolation test, explicitly moved into WP02 by plan.md's round-2 revision). WP01 also owns none of NFR-003 in its refs (correctly, since WP01's tests are the generic primitive proof, not a call-site NFR-003 surface), and WP03 does correctly list NFR-003. | Add `NFR-003` to WP02's `requirement_refs` for traceability parity with WP03. Purely a metadata/traceability nit; the prose obligations are already fully and correctly specified in WP02's body. |

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|
| fr-001-cover-all-three-job-shapes | Yes | WP04 (T016-T019) | Also structurally satisfied by WP02+WP03 jointly covering all three job shapes |
| fr-002-bounded-retry-fleet-verdict | Yes | WP02 (T005, T008) | |
| fr-003-bounded-retry-fleet-main | Yes | WP02 (T006, T009) | |
| fr-004-skip-and-defer-fleet-verdict-pair | Yes | WP02 (T005, T006, T008, T009) | |
| fr-005-bounded-artefact-visibility-retry | Yes | WP03 (T011, T012, T013) | |
| fr-006-fail-closed-floor-preserved | Yes | WP03 (T014) | |
| fr-007-never-post-stale-evidence | Yes | WP02 (T008, T009) | |
| fr-008-consider-shared-helper | Yes | WP01 (whole WP; generalized per plan.md) | |
| fr-009-no-cross-run-coupling | Yes | WP02 (T010) | Moved from originally-envisioned WP04 by plan round-2, per plan.md's own Deviations item 6 |
| nfr-001-retry-must-be-bounded | Yes | WP01 (T002), WP02, WP03 (call-site pinning) | |
| nfr-002-no-new-runtime-dependency | Yes | WP01, WP02, WP03 (verification steps) | |
| nfr-003-unit-test-coverage-retry-under-raciness | Yes | WP02 (T005-T007, T010), WP03 (T011, T012, T014) | See finding T1 — traceability metadata gap only |
| c-001 through c-008 | Yes | Distributed across WP01-WP04 per requirement_refs | |

**Charter Alignment Issues:** None found. ATDD-First Discipline (C-011) is explicitly and correctly reasoned through for all four WPs (WP01-WP03 red-first; WP04's exemption is explicitly justified by its re-scoping to zero new-code obligations). Campsite-clean scope (Standing Order #2) is explicitly measured (radon complexity citations) and dispositioned (freeze `snapshot()` as baseline debt in both files; decompose `_attempt()` to <=15). Mission tracer files (Standing Order #3) are seeded and WP04 closes them out. No charter MUST-principle conflicts identified.

**Unmapped Tasks:** None — all subtasks T001-T019 map to declared FR/NFR/C requirement refs on their owning WP.

**Metrics:**

- Total Requirements: 9 FR + 3 NFR + 8 C = 20
- Total Tasks (subtasks): 19 (T001-T019) across 4 WPs
- Coverage %: 100% (every FR/NFR/C has at least one owning WP/subtask)
- Ambiguity Count: 0 (no vague/unmeasurable adjectives found; all retry budgets, terminal behaviors, and boundaries are numerically or structurally pinned)
- Duplication Count: 0
- Critical Issues Count: 0

## Verification Against the Four Flagged Technical Points (live code, not artifact prose)

1. **`_attempt()` outcome contract is four-state for `fleet_main.py`, never bare "tri-state" anywhere it isn't qualified**: YES — grep of plan.md/tasks.md confirms every "tri-state" reference to `fleet_main.py` is immediately qualified as extending to four states with `_NothingToReport()` (plan.md:198-202, 610-612; WP02:174-186). No orphaned three-state claim survives for `fleet_main.py`.
2. **`elif`/retry-loop boundary**: YES — plan.md (lines ~430-439) and WP02 (Context, lines 142-153) both correctly state the `elif evidence["state"] != "red"` branch sits inside `_attempt()`'s wrapped body, between the incident lookup and the re-check `snapshot()`, and is re-evaluated fresh every retry attempt because `evidence` is rebound per attempt — verified directly against `scripts/ci/fleet_main.py:105-124` (elif at line 121 sits between the incident-lookup block at 105-120 and the re-check `snapshot()` call at 124, both of which read/write the `evidence` bound at line 100).
3. **`dry_run` boundary**: WP02 (the binding implementation artifact) is CORRECT and precisely verified against `scripts/ci/fleet_main.py:99-104` — the dry_run check must stay in `report()`, evaluated after `report()`'s own single pre-loop `snapshot()` and before `retry_with_backoff`/`_attempt()` is invoked. plan.md, however, does not state this for `fleet_main.py` (see finding I1) — a documentation gap in plan.md, not a defect in tasks.md/WP02.
4. **Terminal paths / mock mechanics of the re-pinned `fleet_main.py` test**: WP02 correctly and deliberately declines to prescribe exact mock internals (per operator ruling #2's explicit instruction), instead stating the binding *outcome* requirement (genuine two-attempt coverage) and requiring the implementer to trace the live `RerunAPI` mock themselves. This is correct per the ruling and is NOT flagged as underspecification.

## Next Actions

- No CRITICAL or HIGH findings exist; nothing blocks proceeding to `/spec-kitty.implement`.
- Optional, non-blocking improvement: amend plan.md's fleet_main.py rewiring paragraph (User Story 2 section) to name the pre-loop-snapshot dry_run mechanism as a second divergence from fleet_verdict.py's shape (finding I1). This is advisory — WP02/tasks.md already carries the correct, binding requirement, so implementation is not at risk from this gap.
- Optional, non-blocking improvement: add `NFR-003` to WP02's `requirement_refs` frontmatter for traceability parity with WP03 (finding T1).
