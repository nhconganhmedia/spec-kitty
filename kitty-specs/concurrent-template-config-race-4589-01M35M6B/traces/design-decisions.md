# Design Decisions

> Capture the rationale that would otherwise evaporate.

**Prompting questions**
- What decision was made?
- What alternatives were considered?
- What was the rationale — why this option over the others?

---

## Entries

<!-- YYYY-MM-DD — Decision: [what]. Alternatives: [what else]. Rationale: [why this one]. -->

- 2026-09-22 — Decision: adopt Option A (fix production + deterministic
  red-first regression test) per operator instruction, recorded verbatim in
  spec.md Clarifications CL-001. Alternatives considered: (a) quarantine the
  test as `type:flake` with a bounded retry, rejected because the charter's
  test-remediation discipline (Standing Order 4) forbids retry-to-green when
  the underlying defect is real or unruled-out; (b) make the test
  deterministic without touching production code, rejected because the issue
  itself instructs "if production-side, fix the race — do not just
  quarantine it." Rationale: the causal theory, even unproven, points at a
  real code smell (shared mutable module state + `functools.cache`'s
  non-serializing cache-miss execution) worth closing regardless of natural
  reproduction rate.
- 2026-09-22 — Decision: cite `src/charter/offering/missions/` (not
  `src/doctrine/missions/`) and
  `src/charter/offering/templates/mission-tracer-files/` (not
  `src/doctrine/templates/mission-tracer-files/`) throughout this mission's
  artifacts. Alternatives considered: keep the readiness brief's original
  path names for consistency with the GitHub issue's wording. Rationale: the
  `src/doctrine/` paths do not exist on this checkout (verified with `ls`);
  citing them would violate the charter's "canonical sources, never
  improvise" principle and the spec-content rule requiring every named path
  to actually exist.
