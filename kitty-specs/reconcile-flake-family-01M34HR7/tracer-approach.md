# Tracer: Approach — reconcile-flake-family-01M34HR7

Seeded at plan phase (2026-09-22). Append entries during implementation; assess at mission close.

## Plan phase

- Read the spec, the charter, `AGENTS.md`, `CONTRIBUTING.md`, and the actual code for all three
  surfaces (`fleet_verdict.py`, `fleet_main.py`, `reconcile_shards.py`) plus both CI workflow
  YAML files (`ci-aggregate.yml`, `ci-fleet-verdict.yml`) before drafting the plan, per
  `AGENTS.md`'s "never improvise" standing order.
- Grounded the FR-005 artefact-visibility polling design in the ACTUAL artifact-name convention
  already enforced by `scripts/ci/select_source_artifacts.py`'s `ARTIFACT` regex
  (`module-tests-{module}-shard-{n}-of-{count}-attempt-{attempt}-reports`), rather than inventing
  a parallel naming scheme — the new polling step reuses that regex and reuses
  `reconcile_shards.py`'s own exported `parse_registry`/`read_selected_modules` helpers
  (already in its `__all__`) to compute the must-be-fresh target set, instead of re-deriving
  shard expansion or selection logic a second time (single-canonical-authority governing
  principle).
- Verified the FR-008 shared-helper decision against the codebase's own existing precedent:
  `fleet_main.py` already imports five symbols directly from `fleet_verdict.py`
  (`AGGREGATE, PR_WORKFLOWS, GitHub, automatic_aggregate, classify, comment_body`) — so adding one
  more shared symbol for the retry primitive follows an established reuse path rather than
  introducing a new one.
- Verified gate facts first-hand rather than trusting the dispatch's summary at face value:
  confirmed `ruff check .` / `ruff format --check .` are hard-enforced (`ci-quality.yml:29-32`,
  no `continue-on-error`); confirmed `mypy` has zero references anywhere under
  `.github/workflows/`; confirmed `sonar-pr` in `ci-aggregate.yml` is `continue-on-error: true`
  and excluded from `aggregate-gate`'s `needs: [collect, diff-cover]`; confirmed
  `.github/ci-module-registry.yml`'s `ci` module row's `cov_targets` are `kernel` /
  `specify_cli.core`, not `scripts/ci`, so the diff-cover ≥90% floor structurally does not apply.
  Also found (not asserted by the dispatch, discovered independently): `ci-router.yml`'s
  `commit-msg` job is currently vacuous as written (`git log ... || true` — cannot fail), and no
  standalone Bandit/pip-audit CI *job* exists in `.github/workflows/`; both are dev dependencies
  and Bandit's ruleset is already folded into `ruff check .`'s `S` rule family. Recorded in
  plan.md's gate statement rather than silently assumed.
