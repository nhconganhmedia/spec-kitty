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

## Analyze phase (2026-09-22)

- `spec-kitty agent mission record-analysis` behaved correctly across every one of 5 fresh-sweep
  rounds this phase — the literal `verdict` string it wrote always matched the carrier's own
  computed verdict (`ready` ×3, `blocked` ×1 when 2 HIGH findings were live, `ready` again once
  fixed). The live tracked defect this dispatch warned about (upstream #3133 / ledger SK-06:
  `record-analysis` silently writing `verdict: unknown` for an explicitly-ready report) did
  **not** reproduce on this mission, on this build (`spec_kitty_version: 4.0.0rc5`). Recorded here
  per the dispatch's standing instruction to log the outcome either way, not just on failure.
- Real, repeated friction: `wps.yaml` (the manifest) and `tasks/WP0N-*.md` (per-WP prompt-file
  frontmatter) and `tasks.md` (the human-readable summary) are three independently-writable
  copies of the same `requirement_refs` data, and nothing keeps them in sync automatically when a
  fix round patches only the WP prompt files. Two full analyze rounds were spent chasing this:
  round 1 fixed `requirement_refs` on the WP `.md` files only (commits `858bdfff0`, `0a68bd4d7`);
  a subsequent fresh sweep then had to separately catch `wps.yaml` drifting out of sync (commit
  `99dd3fa59`), and a further fresh sweep after THAT had to catch `tasks.md` drifting out of sync
  from `wps.yaml` (fixed via the canonical `spec-kitty agent mission finalize-tasks` regeneration,
  commit `ec4ceebb8` — not a hand-edit). `finalize-tasks --validate-only`'s own JSON response
  (`tasks_md_stale: true`) and its command docstring (which names this exact gap as tracked issue
  **#3221** — "tasks.md regeneration ... reported instead of repaired" in `--validate-only` mode)
  confirm this is a known, tracked drift class, not something specific to this mission. Suggest a
  future doctrine/tooling fix: either a single write path for `requirement_refs` (WP `.md`
  frontmatter generated FROM wps.yaml, never hand-patched independently) or a lint that fails
  fast when the three copies disagree, so an analyze fix round doesn't have to discover the drift
  one file at a time across multiple rounds. Not fixed here (out of scope — mission targets CI
  flake reconciliation, not spec-kitty's own tasks-authoring machinery).
