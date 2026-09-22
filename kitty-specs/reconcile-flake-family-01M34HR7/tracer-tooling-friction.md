# Tracer: Tooling Friction — reconcile-flake-family-01M34HR7

Seeded at plan phase (2026-09-22). Append entries during implementation; assess at mission close.

## Plan phase

- `spec.md` cites `contracts/artefact-naming.md` (repo-root-relative) for the `must_be_fresh`
  fail-closed floor language, but that path does not exist at the repo root. The actual file is
  `kitty-specs/ci-pipeline-reinstatement-01M1X35E/contracts/artefact-naming.md` — a *prior
  mission's* artifact directory, not a top-level/canonical contracts location. Its "Stale-artefact
  fallback" section is a one-line stub ("Needs a WP home — flagged for tasks.") with none of the
  detail actually implied by the spec's citation; the real, substantive `must_be_fresh` floor
  language lives in `reconcile_shards.py`'s own module docstring and inline comments, not in that
  contract file. Spec-kitty has no single canonical location for cross-mission CI contracts —
  each mission's `kitty-specs/<slug>/contracts/` is scoped to that mission and not cross-referenced
  from a stable root path. This is friction for any future spec that wants to cite a durable
  contract: there is no root-level `contracts/` directory to point at. Flagged, not fixed here
  (out of scope for this mission; noted for a future doctrine/tooling gap).
- `spec-kitty plan --mission <slug> --json` scaffolds `plan.md` from the built-in template
  (`packs/built-in/missions/mission-steps/software-dev/...`) with zero mission-specific content —
  as documented, this is expected (`scaffold_only: true`, `plan_substantive: false`), but it means
  every `[bracketed placeholder]` in the "Project Structure" / "Constitution Check" sections has to
  be manually reconciled against the actual charter section names (the charter here says
  "Governing Principles" + "Quality & Tech-Debt Standing Orders", not "Constitution") — a small
  but real renaming translation step every planner has to redo by hand.
