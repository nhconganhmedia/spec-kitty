---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: reconcile-flake-family-01M34HR7
mission_id: 01M34HR7VHXP24GDY7S68YJ3NT
generated_at: '2026-09-22T15:48:07.398485+00:00'
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
verdict: ready
issue_counts:
  critical: 0
  medium: 0
  high: 0
  low: 1
  info: 0
findings:
- id: T2
  severity: low
  category: coverage
  summary: WP02 and WP03's YAML frontmatter requirement_refs omit NFR-001, even though both WPs' bodies substantively author the NFR-001 per-call-site exact-attempt-count pinning obligation (WP02 T008/T010, WP03 T012/T015) that NFR-001's own testability clause and plan.md's 'NFR-003 exact-attempt-count requirement' paragraph require at each wired call site.
---

## Specification Analysis Report

Independent fresh re-run of `/spec-kitty.analyze` (verifier pass) over
`kitty-specs/reconcile-flake-family-01M34HR7/` at commit `858bdfff0` (post fix-round for
findings I1/T1). Full artifact set re-read from scratch (spec.md, plan.md, tasks.md, all four
WP files, charter.md), and cross-checked against the live code in `scripts/ci/`,
`.github/workflows/ci-aggregate.yml`, `.github/workflows/ci-fleet-verdict.yml` — not just the
planning prose.

### Verification of the two prior-round fixes (re-derived independently, not trusted)

- **I1 (plan.md's fleet_main.py two-way divergence)**: RESOLVED. plan.md:442-452 now states
  `fleet_main.py::report()` keeps a single pre-loop `snapshot()` + `dry_run` check entirely
  OUTSIDE `retry_with_backoff`/`_attempt()`, citing `scripts/ci/fleet_main.py:99-104`. Verified
  directly against the live file: lines 99-104 are exactly `def report(...) -> None:` /
  `evidence = snapshot(api, root, ids)` / `text = body(...)` / `if dry_run:` /
  `print(text, end="")` / `return` — matches verbatim. `fleet_verdict.py::report()`'s `dry_run`
  check (lines ~347-350) is verified to sit at the very end of the function, after the second/
  re-check `snapshot()` call and its `ValueError` guard, gating only print-vs-post for an
  already-computed `body` — matches the paragraph's claim that it does not gate entry into the
  (future) retry-wrapped body the way `fleet_main.py`'s does. Both files today have no
  `retry_with_backoff`/`_attempt()` yet (this mission's WPs are still pre-implementation), which
  is consistent with plan.md describing the pre-existing structure the WPs will wrap.
- **T1 (WP02 NFR-003 frontmatter)**: RESOLVED. `NFR-003` is present in
  `tasks/WP02-fleet-verdict-fleet-main-retry.md`'s `requirement_refs`. WP02's body substantively
  owns NFR-003(1)/(2) (T005/T006/T008/T009: new recovery+terminal-path tests plus re-pins for
  both `report()` functions) and NFR-003(4) (T010, explicitly "owned by this WP, not WP04").
  NFR-003(3) (the `wait_for_artifacts.py` polling tests) is correctly left to WP03, which already
  lists NFR-003.
- **Scope check**: `git show --stat 858bdfff0` touches exactly two files (`plan.md`,
  `tasks/WP02-...md`, 26 insertions/12 deletions). `spec.md` has zero diff in that commit; no
  plan.md architecture/retry-seam/gate-set/campsite/WP-split section was touched outside the
  one "fleet_main.py::report() rewiring" paragraph; no `/home/<user>/...` path was introduced.

### Fresh findings

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| T2 | Coverage | LOW | `tasks/WP02-fleet-verdict-fleet-main-retry.md` frontmatter vs. body (T008 line 223-228, T010 line 265); `tasks/WP03-ci-aggregate-artifact-poll.md` frontmatter vs. body (T012 lines 194-197, T015 line 275) | Both WP02 and WP03 wire an explicit, named `max_attempts`/`backoff_seconds` constant at their own call site and pin the exhausted-budget path's exact call count in their own tests — this is the literal content of NFR-001's testability clause ("bounded... testable by a unit test that asserts the loop terminates... when the mocked evidence source never stabilizes") applied per call site, and plan.md's own "NFR-003 exact-attempt-count requirement" paragraph says this pins "this plan's stated budget numbers (Retry Budget Rationale, **NFR-001**)". Neither WP02's nor WP03's frontmatter `requirement_refs` lists NFR-001 (only WP01, the primitive's own generic-termination-proof owner, lists it). This is the same traceability-gap pattern the prior round's T1 finding already corrected for NFR-003 on WP02, just left unaddressed for NFR-001 on both WP02 and WP03. | Add `NFR-001` to WP02's and WP03's `requirement_refs` for traceability parity with WP01, mirroring the same fix already applied for NFR-003. Purely a metadata/traceability nit — the prose obligations are already fully and correctly specified in both WPs' bodies. |

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
| nfr-001-retry-must-be-bounded | Yes | WP01 (T002); WP02/WP03 (call-site pinning, body-only) | See finding T2 — frontmatter traceability gap on WP02/WP03 |
| nfr-002-no-new-runtime-dependency | Yes | WP01, WP02, WP03 (verification steps, body-only) | Not flagged as a frontmatter gap — this is a negative/absence constraint with no requirement-specific test content to own, unlike NFR-001/NFR-003 |
| nfr-003-unit-test-coverage-retry-under-raciness | Yes | WP02 (T005-T007, T010), WP03 (T011, T012, T014) | Frontmatter now correct on both WPs (T1 fix verified RESOLVED) |
| c-001 through c-008 | Yes | Distributed across WP01-WP04 per requirement_refs | |

**Charter Alignment Issues:** None found. Verified against the live charter (`.kittify/charter/charter.md`): Standing Order #2 (campsite cleaning), #4 (test-remediation/red-first), #9 (red-main discipline), and the ATDD-First Discipline (C-011) section all exist as cited and plan.md's/tasks.md's framing of each matches the charter's actual text. No MUST-principle conflicts identified.

**Unmapped Tasks:** None — all subtasks T001-T019 map to declared FR/NFR/C requirement refs on their owning WP.

**Metrics:**

- Total Requirements: 9 FR + 3 NFR + 8 C = 20
- Total Tasks (subtasks): 19 (T001-T019) across 4 WPs
- Coverage %: 100% (every FR/NFR/C has at least one owning WP/subtask; T2 is a frontmatter-metadata gap, not a missing-coverage gap)
- Ambiguity Count: 0 (scanned spec.md/plan.md for vague adjectives — fast/scalable/secure/intuitive/robust — and unresolved placeholders — TODO/TKTK/???/TBD/FIXME — across spec.md, plan.md, tasks.md, all WP files: none found; every retry budget, terminal behavior, and boundary is numerically or structurally pinned)
- Duplication Count: 0 (FR-002/FR-003's structural near-duplication is intentional — it documents the same real duplicate-code defect this mission fixes in two files, per FR-008's own framing)
- Critical Issues Count: 0

### Live-code cross-checks performed (not just artifact prose)

- `scripts/ci/fleet_main.py:99-104` and `scripts/ci/fleet_verdict.py`'s `report()`'s `dry_run`
  placement — both verified directly (see I1 verdict above).
- `scripts/ci/reconcile_shards.py`'s `__all__` — confirmed it exports `parse_registry` and
  `read_selected_modules` (both already public), matching plan.md's/WP03's "already-exported"
  claim.
- `.github/workflows/ci-aggregate.yml`'s live `collect` job step order — confirmed it matches
  WP03's documented "current order" exactly (`select-current` → `download-current` →
  `last-success` → `download-previous` → `download-selected-modules` → install PyYAML →
  `reconcile`), so the required re-sequencing WP03 describes is accurate against the real file.
- `scripts/ci/select_source_artifacts.py`'s `ARTIFACT` regex — confirmed it exists verbatim as
  cited by plan.md/WP03.
- `scripts/ci/fleet_verdict.py:141-142`'s `GitHub.request()` — confirmed `token =
  os.environ["GH_TOKEN"]` is a bare subscript with no fallback, matching WP03's `GH_TOKEN`-must-
  not-be-dropped rationale.
- `ci-fleet-verdict.yml`'s `report`/`report-main` jobs and `ci-aggregate.yml`'s `collect` job —
  confirmed all three carry `timeout-minutes: 15`, matching plan.md's Retry Budget Rationale's
  stated timeout headroom.
- `issue-matrix.json` — confirmed rows already exist for #4652/#4675/#4878 (`verdict: unknown`,
  pending WP-implementation-time fill) and #4882 (correctly auto-classified `not-applicable`,
  context-only epic reference) — consistent with the analyze prompt's non-gating Issue-Matrix
  Approval Heads-Up.

## Next Actions

- No CRITICAL or HIGH findings exist; nothing blocks proceeding to `/spec-kitty.implement`.
- Optional, non-blocking improvement: add `NFR-001` to WP02's and WP03's `requirement_refs`
  frontmatter (finding T2), mirroring the fix already applied to WP02 for NFR-003 in the prior
  fix round.
