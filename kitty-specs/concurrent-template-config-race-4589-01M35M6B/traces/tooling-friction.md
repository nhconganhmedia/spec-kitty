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
