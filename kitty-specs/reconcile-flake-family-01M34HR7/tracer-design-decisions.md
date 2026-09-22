# Tracer: Design Decisions — reconcile-flake-family-01M34HR7

Seeded at plan phase (2026-09-22). Append entries during implementation; assess at mission close.
See `plan.md` for full rationale; this file is the running log of decisions and their "why", for
a future reader who does not want to re-read the whole plan.

## Plan phase

1. **One generic, stdlib-only bounded-retry primitive (`scripts/ci/reconcile_retry.py`), shared
   by all three retrying surfaces** (`fleet_verdict.py::report()`, `fleet_main.py::report()`,
   the new `wait_for_artifacts.py`), rather than three hand-copied loops or a GitHub-specific
   helper limited to the FR-008-named pair. Rationale: FR-008 already flags the
   fleet_verdict/fleet_main duplication risk; the same risk applies a third time to
   `wait_for_artifacts.py` if its loop is hand-rolled separately. A single primitive that takes an
   `attempt: Callable[[], T | None]` and returns the stabilized `T` or `None` on exhaustion keeps
   the *terminal-behavior* decision (skip-and-defer vs. fail-loudly) with each caller, so it does
   not encode FR-004's fleet-verdict-only semantics into a primitive `wait_for_artifacts.py` must
   not inherit. Reviewers should scrutinize whether this over-generalizes relative to FR-008's
   literal (fleet_verdict/fleet_main-only) framing — it is a plan-phase judgment call, not spec
   text.
2. **`wait_for_artifacts.py` polls only the SELECTED (must-be-fresh) shard set, not the full
   registry.** Polling for the full registry would exhaust its budget on every ordinary
   diff-scoped PR, because `ci-modules.yml`'s diff-scoping deliberately never runs unselected
   modules' shards at all (documented in `ci-aggregate.yml`'s own header comment) — those
   artifacts will never appear, retried or not. This requires moving the existing "Download the
   triggering run's selected-module set" step earlier in `ci-aggregate.yml`'s `collect` job (from
   after `download-previous` to before the new polling step), which is a real re-sequencing of
   existing steps, not just an insertion — flagged for reviewer attention.
3. **`reconcile_shards.py` is imported from, never edited.** `wait_for_artifacts.py` calls its
   exported `parse_registry`/`read_selected_modules` to avoid a second, drifting shard-naming
   authority. This is read-only reuse and does not change `reconcile_shards.py`'s own shape or
   behavior (Key Entities item 3 in spec.md is preserved).
