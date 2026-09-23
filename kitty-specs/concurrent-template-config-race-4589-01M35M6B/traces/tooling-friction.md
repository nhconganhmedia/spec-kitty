# Tooling Friction Log

> Log every place the tooling fought you so it can feed the tooling-gap backlog.

**Prompting questions**
- What tooling or command did you have to work around?
- What blocked you unexpectedly, and how long did it take to unblock?
- Was this a known issue or something discovered fresh?

---

## Entries

<!-- YYYY-MM-DD — 1-3 sentences: what happened, why it slowed you down. -->

- 2026-09-22 — `spec-kitty agent mission create` produced a mission slug
  with an appended ULID suffix
  (`concurrent-template-config-race-4589-01M35M6B`) rather than the exact
  slug string passed on the command line
  (`concurrent-template-config-race-4589`). This is expected/documented
  disambiguation behavior, not a defect, but it means any downstream
  reference to "the mission directory" must resolve the actual created path
  from the command's JSON output rather than assuming the literal slug
  string names the directory.
- 2026-09-22 — The `mission-tracer-files` doctrine procedure's own prose
  (`packs/built-in/procedures/mission-tracer-files.procedure.yaml`) cites a
  stale template source path
  (`src/doctrine/templates/mission-tracer-files/`) that does not exist on
  this checkout; the real path is
  `src/charter/offering/templates/mission-tracer-files/`. Worth a doctrine-doc
  fix in a future mission so the procedure's own text does not mislead the
  next agent who follows it literally.
- 2026-09-23 — Plan round-5's item 4 (core_misc baseline extension +
  packaging-parity re-run) was dispatched twice by the phase agent. The
  first author's long-running background test batch (`tests/specify_cli/
  tool_surface`, ~17 min) meant its final `SubagentHandback` report was
  delayed and did not re-invoke the phase agent's turn; the orchestrator's
  own process-level visibility (watching for the pytest PID) was needed to
  notice the first author had actually finished (plan.md diff static,
  +133/-24, item 4 absent at that point) before the phase agent could tell
  from its own tool results alone. Acting on that read, the phase agent
  dispatched a second, narrowly-scoped author for item 4 — which turned out
  to be redundant: the first author's report, also delayed, had in fact
  completed item 4 in full (plan.md diff now +239/-34, all 9 `core_misc`
  test_dirs covered) but the report simply hadn't surfaced yet. The phase
  agent stopped the second author immediately (its in-flight
  `test_packaging_parity.py` run was killed via `pkill`, and a SendMessage
  STOP was sent) upon learning of the duplicate dispatch; the second author
  made **zero** file edits (confirmed via `git status`/`git diff --stat`
  before and after), so no reconciliation of conflicting content was
  needed — only ~2 minutes of a redundant `test_packaging_parity.py`
  re-run, which incidentally cross-confirmed the first author's recorded
  "3 passed" result (22.19s vs. 21.90s, same pass count). Root cause: no
  reliable signal in this harness distinguishes "subagent still running a
  long background command" from "subagent finished but its handback has
  not yet drained" — a phase agent watching only its own conversation
  cannot tell the two apart without an outside process check. Worth a
  tooling improvement: a lighter-weight "is this background agent still
  alive" probe that doesn't require inspecting OS-level process lists.
- 2026-09-23 — The design-pipeline doc's literal text for the tasks-finalize
  step names the command `spec-kitty agent tasks finalize-tasks`. That is a
  legacy command family that requires `tasks.md` to already exist on disk
  (it errors `tasks.md not found` when it doesn't) — it does **not** generate
  `tasks.md` from `wps.yaml`. The current, correct command for a mission
  whose `tasks.md` does not yet exist is `spec-kitty agent mission
  finalize-tasks` (confirmed via `--help` and its own docstring, matching
  `packs/built-in/missions/mission-steps/software-dev/tasks-finalize/prompt.md`'s
  own text): `--validate-only` first for preflight, then without the flag to
  regenerate `tasks.md`, update WP frontmatter, compute lanes, and commit —
  all in one call. This is a generally-useful, non-mission-specific finding:
  any doc or prompt still citing the bare `agent tasks finalize-tasks` name
  for first-time `tasks.md` generation is stale and should be corrected to
  `agent mission finalize-tasks`.
- 2026-09-23 — During the tasks-phase R4 round-2 fix, a `spec-kitty
  safe-commit` invocation failed once with an unrelated transient error
  ("Global asset input changed:
  `~/.agent/workflows/spec-kitty.analyze.md`") surfaced from
  the CLI's own global-agent-command sync step
  (`ensure_global_agent_commands`) — most likely a concurrent-peer race
  against another agent process in this multi-agent session touching the
  same shared `~/.agent/` install surface at the same moment, not a defect
  in this mission's own artifacts or branch. An immediate retry of the
  identical `safe-commit` command succeeded cleanly with no other change.
  Worth a tooling note: `ensure_global_agent_commands`'s freshness check
  appears not to be safe against concurrent invocations from independent
  agent processes sharing one `~/.agent/` install.
- 2026-09-23 — **Confirmed live instance of the tracked `record-analysis`
  verdict-drift defect (#3133, ledger SK-06).** `spec-kitty agent mission
  record-analysis` silently wrote `verdict: unknown` on the first analyze
  attempt for this mission even though the submitted report body explicitly
  said "Verdict: READY" and carried zero findings. Root cause, read directly
  from `src/specify_cli/analysis_report.py`
  (`parse_structured_findings`/`_split_carrier`, lines ~320-463): the
  recorder derives the verdict **only** from a leading YAML frontmatter
  block whose top-level key is literally `schema: analysis-findings/v1`
  (plus `findings: [...]` and, optionally, `counts`/`verdict_hint`) —
  **never** from prose, and never from any other carrier field name. The
  the orchestrator's design-pipeline guidance (external) §4a text this
  mission followed says only "Produce an analysis report with the
  analysis-findings/v1 YAML carrier" without giving the exact required key
  names, and a real precedent report already committed in this repo
  (`kitty-specs/doctrine-glossary-architecture-consolidation-01KTNWFC/analysis-report.md`)
  uses a *different*, non-matching frontmatter shape (`schema_version: 1`,
  `artifact_type: spec-kitty.analysis-report`, top-level `verdict:` and
  `issue_counts:` keys) that also silently recorded as `verdict: unknown` —
  confirming this is a repeatable trap, not a one-off authoring slip: an
  agent copying the closest available precedent in-repo reproduces the same
  silent-unknown outcome. Fix applied here: re-submitted with the literal
  `schema: analysis-findings/v1` + `findings: []` + `counts: {...}` +
  `verdict_hint: ready` shape; `record-analysis --json` then correctly
  returned `"verdict": "ready"`. Two throwaway commits
  (`d4c476655`, `87eb2397d`) recorded the wrong-schema/malformed-body
  attempts before the clean one (`dd1c0fb9f`) landed — left in mission
  history rather than rewritten, per this pipeline's no-amend discipline.
  Worth a doctrine/tooling fix: either the design-pipeline references should
  state the exact required carrier keys (`schema`, `findings`, `counts`,
  `verdict_hint`) verbatim with a copy-pasteable example, or
  `record-analysis` should reject an unrecognized-but-frontmatter-shaped
  block loudly (as it already does for a *malformed* v1 carrier) instead of
  silently downgrading it to legacy/`unknown` (C-FIND-3's current behavior
  makes "wrong key names" indistinguishable from "no carrier at all").
