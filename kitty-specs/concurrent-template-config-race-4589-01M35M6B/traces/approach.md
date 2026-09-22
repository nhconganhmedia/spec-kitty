# Approach Evolution

> Track how your approach changed as the mission progressed.

**Prompting questions**
- What approach did you start with (as stated in the spec or plan)?
- What changed during implementation, and why?
- What would you try differently on a similar mission?

---

## Entries

<!-- YYYY-MM-DD — 1-3 sentences: what approach was tried and what shifted. -->

- 2026-09-22 — Mission seeded from a readiness pass, not a fresh
  investigation: the spec starts from a hypothesis (YAML-singleton +
  functools.cache cache-miss race) rather than a confirmed root cause,
  because 0/300 cold-subprocess reruns and 0/2000 Barrier-synchronized
  trials failed to reproduce the race naturally. Approach is: research the
  hypothesis first (FR-001), then fix concurrency-safety in the cache
  population path (FR-002), then add a red-first, by-construction
  regression test (FR-004/FR-005) — in that order, not fix-then-hope-a-test-
  catches-it.
