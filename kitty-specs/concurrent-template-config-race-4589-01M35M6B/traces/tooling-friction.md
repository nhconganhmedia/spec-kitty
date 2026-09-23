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
