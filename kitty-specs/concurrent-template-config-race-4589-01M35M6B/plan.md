# Implementation Plan: Concurrent `create_mission_core` TemplateConfigurationError race

**Branch**: `fix/concurrent-template-config-race-4589` | **Date**: 2026-09-23
**Spec**: `kitty-specs/concurrent-template-config-race-4589-01M35M6B/spec.md`
**Research**: `kitty-specs/concurrent-template-config-race-4589-01M35M6B/research.md`

This plan honours every Clarification (CL-001..CL-007), Functional/
Non-Functional Requirement, Constraint, and Success Criterion in `spec.md`
explicitly and does not soften or re-derive any of the operator's binding
decisions. Every path cited below has been verified with `ls`/`grep`/`Read`
against this checkout during this planning pass (C-004).

## Summary

Two module-level `ruamel.yaml.YAML(typ="safe")` singletons —
`_YAML` (`src/charter/offering/missions/mission_step_repository.py:72`) and
`_LAYERED_YAML` (`src/charter/offering/missions/mission_type_repository.py:318`,
found in this mission's own plan-phase research, not named in `spec.md`'s
Readiness Findings) — are shared across every thread and every call for the
life of the process. `research.md` confirms, by reading the installed
`ruamel.yaml` source and this project's actual (C-extension-free) dependency
resolution, that `YAML.load()` mutates cross-call cached parser state
(`self.reader.stream`, `self.tags`) with no locking. Both singletons feed
`functools.cache`-wrapped functions
(`_resolve_all_for_mission_type_cached`, `resolve_layered_mission_types`)
whose unbounded cache-miss path (confirmed from CPython's own `functools.py`)
never serializes concurrent execution of the wrapped body. The two facts
compose: two threads racing a cache miss can corrupt each other's YAML parse
on the shared instance, `_load_step_yaml`'s blanket `except Exception: return
None` (`mission_step_repository.py:134`) turns that into a silently dropped
`MissionStep`, and a dropped step that carried the `template:` ref for
`artifact_kind="spec"` produces exactly the observed
`TemplateConfigurationError(reason="is missing the requested mapping key")`
at `src/specify_cli/runtime/resolver.py:499`.

The fix (Option A, CL-001): eliminate the shared, non-thread-safe YAML state
at both singleton sites (thread-local `YAML` instances — no lock needed,
because there is no shared object left to race on) and add a per-key lock
around each cache's miss path (defense against redundant concurrent work and
against `functools.cache`'s own lock-free cache-dict write racing on a
result). A deterministic, `threading.Barrier` + monkeypatch-forced regression
test proves the fix closes the exact interleaving identified in
`research.md`, committed before the fix per CL-004/ATDD (C-011).

## Research summary

See `research.md` in full. Bottom line, restated for plan-readers who have
not opened it: **both halves of CL-002's hypothesis are independently
confirmed by direct source reading** — (a) `YAML(typ="safe")`'s `.load()`
mutates cross-call cached reader/scanner/parser/composer state with no
synchronization, confirmed live on this checkout (`CParser is None`, no
`ruamel.yaml.clib` in `uv.lock`, so the vulnerable pure-Python path is what
actually runs); (b) `functools.cache`'s unbounded cache-miss path
(`functools.py:549-562` in the installed CPython 3.11.15 stdlib) has no lock
at all around the wrapped call. Neither fact alone explains a dropped key;
together they do. Research also found a **second, previously uncatalogued**
instance of the identical defect shape (`_LAYERED_YAML` /
`resolve_layered_mission_types`, reachable eagerly from
`create_mission_core` via `_resolve_action_slot`), and definitively ruled
`src/charter/activation/resolver.py` **out** of scope (its `template_set` is
an unrelated charter-selection scalar, confirmed by direct read — this
resolves `spec.md`'s open "scope its involvement" instruction).

**Open risk carried forward** (CL-002's "resolve or carry forward as risk"):
the research pass is static/source-level, not a live-witnessed reproduction.
The red-first regression test (Test strategy, below) is what will
empirically confirm the mechanism by construction; if that test does not, in
fact, fail pre-fix, the static analysis above — however well-evidenced — has
not been validated as the actual production mechanism, and the WP must stop
and re-investigate rather than treat a passing "red-first" test as proof
(CL-003 severity-4 bar).

## 1. Seam

This change lands entirely inside the `charter/offering/missions`
doctrine-data package:

- `src/charter/offering/missions/mission_step_repository.py` — the `_YAML`
  singleton (line 72) and `_resolve_all_for_mission_type_cached` (lines
  446-470). **Primary fix site.**
- `src/charter/offering/missions/mission_type_repository.py` — the
  `_LAYERED_YAML` singleton (line 318) and `resolve_layered_mission_types`
  (lines 477-601). **Second fix site**, found in this mission's own
  research (not in `spec.md`'s Readiness Findings), same defect shape.
- `src/charter/offering/missions/step_projection.py` — read-only in this
  plan; `project_template_set`/`iter_template_refs` are pure functions with
  no shared state and need no change. Included in the seam because a test
  may need to assert on its output shape, not because it is modified.

**`src/charter/activation/resolver.py` is NOT in scope**, resolving
`spec.md`'s open candidate-blast-radius question. Confirmed by direct read
in `research.md` ("Ruled out / out of scope"): its `template_set` is the
charter-selection scalar (e.g. `"software-dev-default"`), an unrelated
domain object per `step_projection.py`'s own scope-fence docstring
(lines 24-30). It imports nothing from `mission_step_repository.py` /
`step_projection.py` and shares no code path with this defect.

`src/charter/activation/mission_type_profiles.py` is **read but not
modified** — it is the call site (`_resolve_template_set_slot`,
`_resolve_action_slot`) that reaches into the two fix sites above; fixing
the two singletons closes the race for every caller, including this one,
with no change needed at the call site itself.

No CLI command reaches past a service/repository seam into kernel
internals for this fix. **`src/kernel/**` is not touched** — no caller in
the traced `create_mission_core` → `resolve_mission_type_context` →
`_resolve_template_set_slot`/`_resolve_action_slot` →
`MissionStepRepository`/`MissionTypeRepository` chain touches
`src/kernel/` at any point (confirmed by the call-chain trace in
`research.md`).

## 2. Generated artifacts

**This fix touches no generated artifact.** No doctrine schema
regeneration, no Contextive glossary change, no agent command copy. The
change is Python source only, inside `src/charter/offering/missions/`. It
does not edit anything under `packs/built-in/` or `packs/internal/`, so the
pack-manifest regen gate (`spec-kitty doctrine regenerate-graph`) is not
triggered and does not need to run.

## 3. Contracts

None of the following move: doctrine schemas (`MissionStep`/`MissionType`
Pydantic models in `.../missions/models.py` — unmodified), mission step
contracts, action indices, the orchestrator-api surface, or the vendored
`spec-kitty-events` package. Per CL-007/C-001, the fix only changes the
**concurrency safety** of how already-in-memory structures are built and
cached — it does not change what `MissionStep`, `MissionType`, or
`template_set` *are* or *look like*, only guarantees that building them
under concurrent load no longer corrupts the process. `step.yaml`'s on-disk
format, the `MissionType`/`MissionStep` schema shapes, and `meta.json` are
untouched.

## 4. Migration chain

This mission does **not** touch the upgrade/migration chain
(`src/specify_cli/upgrade/migrations/`). There is no on-disk format change
to migrate old projects toward — the defect and its fix are entirely
in-process (per-`spec-kitty`-invocation) cache/concurrency behavior, per
CL-007.

## 5. Cache-contract preservation (FR-003/NFR-003)

`MissionTypeRepository.default.cache_clear()` and
`MissionStepRepository.cache_clear()` (`mission_step_repository.py:323-333`
— the public `@staticmethod` wrapper that internally calls the private
`_resolve_all_for_mission_type_cached.cache_clear()`, which that private
function's own docstring, lines 464-465, forbids calling directly from
outside the module) remain present, callable, synchronous, and **unchanged
in signature and observable behavior**. Concretely:

- The chosen fix mechanism (Section 6) adds **no new lock that
  `cache_clear()` needs to know about, acquire, or release.** The per-key
  locks introduced live in a *separate* module-level structure (a plain
  `dict[key, threading.Lock]` guarded by one small bootstrap lock, detailed
  below) that `cache_clear()` never touches. `cache_clear()` continues to
  do exactly one thing: call `functools.cache`'s own `.cache_clear()` on the
  wrapped function, which only empties that function's internal cache dict
  — an operation that has never taken, and will continue to never take, any
  lock this fix introduces.
- **Edge case — `cache_clear()` racing an in-flight cache-miss population**:
  if thread A is mid-population (holding its per-key lock, executing the
  now-safe, thread-local-YAML body) when thread B calls
  `MissionStepRepository.cache_clear()`, B's call clears the **data** cache
  dict immediately and returns (it never blocks on A's lock — it does not
  acquire it, because it does not touch the per-key lock structure at all).
  A's in-flight population completes normally and writes its result into
  `cache[key] = result` per `functools.cache`'s own unbounded-path logic
  (`functools.py:558-559`) — into what is, by then, a *freshly emptied*
  cache dict. The net effect is benign: the next caller for that key gets a
  cache miss again (A's write landed in the just-cleared dict, so it is
  present again after A finishes) or, in the tightest possible interleaving,
  A's write is the only entry present — either way, no deadlock, no
  exception, no corruption. This satisfies NFR-003's falsifiable test ("a
  test that calls `MissionStepRepository.cache_clear()` mid-population and
  asserts no deadlock/exception").
- Both files' existing "production never mutates the bundled trees
  mid-process" cache-safety argument (`mission_type_repository.py:84-88`,
  `mission_step_repository.py:326-331`) **still holds** after this fix: it
  was always an argument about the *filesystem* not changing under a
  running process, which this fix does not touch or need to revisit — the
  new argument this fix adds is a *narrower*, additional one (the in-memory
  YAML-parsing state doesn't need to be shared to be efficient), which is
  additive, not a revision of the existing one.

## 6. Fix mechanism (FR-002)

Two changes, one per singleton, identical shape, informed directly by
`research.md`'s conclusion that (a) the shared YAML instance's cross-call
state is the corrupting mechanism and (b) `functools.cache`'s cache-miss
path is what creates the opportunity for two threads to reach that shared
state at the same time:

### 6a. Thread-local YAML instances (removes the shared mutable state)

Replace each module-level singleton —

```python
_YAML = YAML(typ="safe")                      # mission_step_repository.py:72
_LAYERED_YAML = YAML(typ="safe")              # mission_type_repository.py:318
```

— with a `threading.local()`-backed accessor that hands each thread its own
private `YAML(typ="safe")` instance, built once per thread and reused by
that thread only (mirrors `MissionTypeRepository._load`'s own
already-thread-safe pattern at `mission_type_repository.py:160`, which
constructs a fresh `_yaml = YAML(typ="safe")` — the difference here is
*per-thread*, not *per-call*, reuse, to avoid rebuilding a `YAML` object on
every single `_load_step_yaml`/`_load_layered_mission_type_file` call, which
would be wasteful given how many step files a single `resolve_all_for_mission_type`
walk can touch). Concretely, a small module-level helper such as:

```python
_yaml_local = threading.local()

def _get_yaml() -> YAML:
    try:
        return _yaml_local.instance
    except AttributeError:
        instance = YAML(typ="safe")
        _yaml_local.instance = instance
        return instance
```

replacing every `_YAML.load(...)` / `_LAYERED_YAML.load(...)` call site with
`_get_yaml().load(...)`. This is the primary fix: with no object shared
across threads, there is nothing left to race on, and **no lock is needed
for this half of the fix at all** — each thread's reader/scanner/parser/
composer/tags state is private to that thread for the process's whole
lifetime, at zero synchronization cost on every read (satisfies NFR-002,
Section 7).

### 6b. Per-key lock around each cache's miss path (closes the redundant-work / cache-poisoning window)

Thread-local YAML instances alone remove the *corruption* mechanism, but
`functools.cache`'s lock-free cache-miss path (research.md, Question (b))
still means two threads can independently execute the full uncached body
for the *same* key concurrently — wasteful (two redundant filesystem
walks), and, in the small window between both finishing and both writing
`cache[key] = result` (`functools.py:558-559`), whichever write lands second
"wins" non-deterministically. Neither of those two computed results would
now be *corrupt* (6a already removed the only shared mutable state), so this
is not a correctness bug post-6a — but it is worth closing by construction
rather than leaving as a residual "two threads did the same disk walk
twice" inefficiency, and it gives the fix a second, independent layer of
protection instead of relying solely on 6a.

Add a small per-key lock registry, keyed identically to each
`functools.cache`'s own key shape, guarding only the miss path:

```python
_locks_guard = threading.Lock()
_locks: dict[tuple, threading.Lock] = {}

def _lock_for(key: tuple) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock
```

`_resolve_all_for_mission_type_cached` and `resolve_layered_mission_types`
keep their `@functools.cache` decorator (preserving the existing cache
object and its `cache_clear()` contract untouched, per Section 5) but their
bodies acquire `_lock_for(key)` around the actual filesystem-walk-and-parse
work. Because the lock is acquired **only inside the already-cache-missed
function body** — never around the outer `functools.cache` wrapper's own
dict lookup — a warm cache hit returns from `functools.cache`'s own fast
path (`cache_get(key, sentinel)`, `functools.py:553`) without ever calling
into our function body, and therefore without ever touching a lock. Only
two-or-more *simultaneous cold misses for the same key* ever contend on a
lock, and they contend for the duration of one filesystem walk, not for the
life of the cache.

The `_locks` dict itself is intentionally **never cleared** by
`cache_clear()` (Section 5) — leftover `threading.Lock` objects for keys no
longer in the data cache are harmless (a `Lock` costs nothing to leave
around, and stale entries do not affect correctness since a lock is only
ever contended by two calls racing the *same* key at the *same* moment).

### Both fix sites raise, never degrade (CL-006/FR-006)

If either lock acquisition needs a bound (see Section 7 — this plan does
**not** add a blocking-forever wait; see the timeout discussion there), the
timeout path raises `TemplateConfigurationError` (or, for
`mission_type_repository.py`'s roster-level cache — which is one layer
below and does not itself carry mission-type/artifact-kind context — a
new, equally explicit typed exception, e.g. a `MissionStepCacheError`/
reuse of `TemplateConfigurationError` with the caller supplying context),
never returns `None`, an empty dict, or a partial result. This is a purely
additive requirement on the *new* code this mission writes; it does not
touch the existing `resolve_configured_template` raise sites in
`src/specify_cli/runtime/resolver.py:474-531`, which already satisfy
CL-006 and are left unmodified.

## 7. Performance (NFR-002)

The lock design **does not serialize warm-cache reads**. A cache hit never
enters our function body at all (`functools.cache`'s own dict lookup
returns first, `functools.py:553-556`), so it never calls `_lock_for(...)`
and never blocks. Only a genuine cold-miss-on-the-same-key contends, and
only for the duration of one filesystem walk plus YAML parse of that
mission type's step files (typically single-digit milliseconds on local
disk for the built-in tree's step count) — a cost every concurrent-miss
call already pays today serially-by-accident-of-scheduling; this fix makes
that serialization deterministic instead of a race, it does not add new
serialization that wasn't effectively happening (badly) before.

Per the Edge Cases in `spec.md` ("a lock held across an I/O-bound YAML parse
on slow filesystem... must not turn a rare race into a routine
serialization bottleneck"): because the lock is per-*key*
(`mission_type_id` + `pack_context`, mirroring the cache's own key), two
concurrent requests for *different* mission types never contend on the same
lock and proceed fully in parallel — only the narrower "same mission type
+ same pack context, both cold" case serializes, which is both rare (a
process resolves a handful of distinct mission types, and warms almost
immediately) and, per Section 5, was already what a correct outcome
requires (redoing the identical walk twice is waste, not parallelism worth
preserving). This plan does **not** add a lock-acquisition timeout that
would itself need a raise path for the *common* case — a bounded wait that
fires under normal I/O latency would violate C-002's no-retry/no-bounded-
degradation spirit by turning ordinary slow-disk I/O into a manufactured
failure. Instead, SC-006's dedicated failure-path test (Section 8) exercises
the lock/cache-error raise via **fault injection** (a monkeypatched
lock/cache object that simulates a timeout or corruption deterministically),
not via a real wall-clock timeout in the production code — this keeps the
production path simple (an ordinary blocking `Lock.acquire()`, no timeout
argument, no new failure mode for the healthy case) while still exercising
FR-006's raise contract under the injected-fault condition the test forces.

Single-threaded `create_mission_core` stays under 2 seconds: the added
per-key-lock acquisition on a single-threaded run is uncontended
(`Lock.acquire()` on an unheld lock is effectively free), and the
thread-local YAML swap has identical per-call cost to the existing shared
instance (same `YAML(typ="safe")` construction, just once per thread
instead of once per process — for a single-threaded CLI invocation this is
one construction either way). The existing test suite already demonstrates
this margin: `tests/core/test_mission_creation_identity.py`'s 4 tests
(including two `create_mission_core` calls in
`test_concurrent_creates_no_collision` alone) complete in 0.90s total in
this checkout (Section 9, Baseline) — orders of magnitude under the 2s
per-call bar. The implementation WP should still add or reuse an explicit
single-call timing assertion per NFR-002's falsifiable bar, rather than
relying solely on this aggregate baseline number as post-fix proof.

## 8. Test strategy (per FR/AC)

Every changed behaviour gets a test that fails when the change is reverted.

### 8a. Red-first, Barrier-synchronized regression test (CL-003/CL-004/FR-004/FR-005)

New test in `tests/core/test_mission_creation_identity.py` (the existing
ATDD entry point, alongside `test_concurrent_creates_no_collision`), e.g.
`test_concurrent_creates_force_cache_miss_race`:

- **Outer call**: `create_mission_core` (via the same
  `_patched_mission_creation_context`/`_run_create` helpers already in that
  file) — per CL-004, the monkeypatch forces *timing*, not the code path.
- **Forced interleave construction**: monkeypatch the thread-local YAML
  accessor (`_get_yaml`, Section 6a) — or, for the pre-fix RED run only
  (see below), the pre-fix shared `_YAML.load` — so that the **first**
  thread to enter the cache-miss body blocks on a `threading.Barrier(2)`
  immediately *after* it has started its YAML `.load()` call (or, for the
  pre-fix code, immediately after `self.reader.stream = stream` is set,
  reachable by patching at the `_load_step_yaml`/`_YAML.load` call
  boundary) and the **second** thread is released to run its own
  `.load()` call for a *different* step file to completion first, then
  both threads are released together to finish. This pins the exact
  interleaving `research.md` identifies (`self.reader.stream` overwritten
  mid-parse) instead of hoping natural OS scheduling produces it — per
  CL-003, "by construction," not luck.
- **Two threads**: mirrors the existing test's shape — two
  `threading.Thread`s calling `create_mission_core` for two distinct
  slugs/mission types (or, per spec.md's Edge Cases, a variant using the
  **same** mission type + artifact kind to cover the narrower,
  higher-contention case) — with an explicit `MissionStepRepository.cache_clear()`
  and `MissionTypeRepository.default.cache_clear()` call before the test
  body, per CL-003, so the test starts from a guaranteed-cold cache and
  never depends on ambient test-ordering to produce a first-ever miss.
- **Pre-fix vs post-fix bookkeeping**: this test is committed in its own
  commit **before** the production-fix commit (CL-004). At that commit, it
  must fail — demonstrating the forced interleaving reaches the unsafe
  code path. After the fix commit, the same test (unmodified) must pass.
  The WP's own record (task/review notes, not this plan) states the actual
  red commit SHA and green commit SHA so a reviewer can check both without
  re-deriving them (User Story 2, AC1).
- **Teardown hygiene** (Edge Cases): the monkeypatch is applied via
  `pytest`'s `monkeypatch` fixture (function-scoped, auto-reverted) or an
  explicit `try/finally`, never a bare module-level patch left in place —
  satisfies "the test must clean up after itself so it does not
  destabilize unrelated tests in the same session."

### 8b. SC-006 — dedicated lock/cache-failure test (CL-006/FR-006)

A separate, new test that monkeypatches the per-key lock (Section 6b) or
the cache-population body to simulate a lock-timeout, corrupted-cache, or
retry-exhaustion condition, and asserts the call raises
`TemplateConfigurationError` (or the equivalent explicit typed exception
named in Section 6) — never returns `None`/empty/partial. The test also
asserts that replacing the raise with a silent-degrade return makes the
test fail (i.e., the test is itself checked against a deliberately
weakened implementation during development, per SC-006's own falsifiability
clause), so the assertion is proven non-vacuous before it is relied on.

### 8c. Existing natural test must not regress (AC3/SC-002)

`test_concurrent_creates_no_collision` (already passing, Section 9
baseline) continues to pass unmodified; the fix must not weaken or slow it
down. No new natural-timing-only test is added in its place (NFR-001).

### 8d. `cache_clear()` mid-population (Edge Case, NFR-003)

A focused unit test (in `tests/missions/` or `tests/doctrine/missions/`,
wherever the existing `MissionStepRepository`/`MissionTypeRepository` cache
tests already live — confirmed present via the existing `cache_clear()`
test seams cited in `spec.md`'s Readiness Findings) that starts a
population in one thread (paused mid-flight via the same monkeypatch/
Barrier instrumentation as 8a), calls `cache_clear()` from the main thread
while it is paused, and asserts: no deadlock (the test itself completes
within its normal timeout), no exception propagates from `cache_clear()`,
and the paused thread's population still completes and returns a correct
(not corrupted) result once released.

## 9. Baseline (CL-005)

Captured fresh, at this mission's own scaffold commit (`288aef2f9`, HEAD at
research/plan time, `spec.md` committed, **zero code changes** yet) — not
issue #3284's stale numbers, which do not apply to this mission.

```
$ env -u FORCE_COLOR NO_COLOR=1 PWHEADLESS=1 uv run --frozen pytest \
    tests/core/test_mission_creation_identity.py -q
....                                                                     [100%]
4 passed in 0.90s
```

Additional due-diligence runs, scoped to the two modules this fix's diff
will actually land in (per the Gate Set derivation, Section 10):

```
$ env -u FORCE_COLOR NO_COLOR=1 PWHEADLESS=1 uv run --frozen pytest tests/missions -q
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 67%]
........................................................................ [ 90%]
...............................                                          [100%]
319 passed, 3 warnings in 21.57s
```
(The 3 warnings are pre-existing `DeprecationWarning`s about a legacy
`mission.yaml` asset path unrelated to this mission's YAML-concurrency
defect — not failures.)

```
$ env -u FORCE_COLOR NO_COLOR=1 PWHEADLESS=1 uv run --frozen pytest tests/core -q \
    --ignore=tests/core/test_upgrade_probe_and_notifier.py
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 68%]
..............................................................ss........ [ 91%]
..........................                                               [100%]
312 passed, 2 skipped in 11.13s
```
(`tests/core/test_upgrade_probe_and_notifier.py` was excluded because it
fails to *collect* under a plain `uv run --frozen pytest` invocation —
`ModuleNotFoundError: No module named 'respx'`. `respx` is declared in
`pyproject.toml:107`/`uv.lock:2499` under the `test` extra, which this ad
hoc baseline invocation did not install (`--frozen` alone, no `--extra test`
/ `--all-extras`). This is an environment-invocation scoping detail, not a
code failure, not attributable to this mission, and unrelated to the YAML/
cache-concurrency defect — it is named here for completeness rather than
silently worked around.)

**Everything in the scoped surface passes cleanly. There are no
pre-existing failures to distinguish from mission-introduced ones** —
stated plainly, per CL-005's instruction not to invent hedging when the
baseline is clean. If the implementation phase's own fuller run (post-fix,
across the same surfaces) turns up any unrelated red, filing a tracker issue
for it is the **orchestrator's** job (C-003), not this mission's.

## 10. Gate set

Derived directly from `.github/ci-module-registry.yml` (read in full,
810 lines) and `.github/workflows/ci-aggregate.yml`/`ci-router.yml`/
`ci-quality.yml`/`sonar.yml` (read directly, not summarized secondhand).

**Modules selected by this fix's diff** (files under
`src/charter/offering/missions/**` + a new/changed test under
`tests/core/`):

- **`missions`** (`ci-module-registry.yml:27-39`) — roots include
  `src/charter/offering/missions/**` explicitly. **Selected.** No explicit
  `test_dirs` row, so its canonical test mirror
  (`scripts/ci/gate_selection.py:_canonical_test_mirror`) is `tests/missions`
  (confirmed present, 319 tests, all passing per Section 9). `shard_count: 1`.
- **`core_misc`** (`ci-module-registry.yml:207-...`) — an aggregate module
  whose roots *also* include `src/charter/offering/**` (broader than, and
  overlapping with, `missions`' own narrower root). **Selected** — confirmed
  by `scripts/ci/gate_selection.py:297`'s own comment acknowledging
  "overlapping glob ownership between groups" as an accepted, intentional
  condition (a changed path can and does select more than one module here;
  this is not a bug to route around). `test_dirs` explicitly lists
  `tests/core` (`ci-module-registry.yml`), which is where the new red-first
  regression test (Section 8a) and the failing-test's ATDD entry point live.
  `shard_count: 5`.
- **`next`** (`ci-module-registry.yml:80-90`, roots
  `src/specify_cli/runtime/**`, `shard_count: 2`) — **NOT selected by this
  fix's actual diff.** `spec.md`'s candidate blast radius names
  `src/specify_cli/runtime/resolver.py` as the symptom's raise site, but
  this plan (Section 1/6) makes no change there — the existing
  `TemplateConfigurationError` raise sites in `resolve_configured_template`
  are preserved unmodified, per CL-006's own framing ("this applies to both
  the existing raise sites ... and any new cache/lock code"; the existing
  ones already satisfy the requirement). If implementation discovers a need
  to touch `resolver.py` after all, the `next` gate becomes selected and
  this plan's WP scope must be revised to say so explicitly.
- **`charter`** (`ci-module-registry.yml:143-160`, roots `src/charter/**`
  broadly, `test_dirs: tests/charter, tests/doctrine`, `shard_count: 5`) —
  **NOT selected**, because this fix's diff stays inside
  `src/charter/offering/missions/**` (already covered by `missions`/
  `core_misc` above) and does not touch `src/charter/activation/**` or any
  other `src/charter/**` path outside `offering/missions/`. Confirmed: this
  plan modifies no file under `src/charter/activation/`.

**Enforced CI gates and why each does or doesn't apply**, read directly
from the workflows (not assumed from any prior brief):

- **`diff-cover` PR gate** (`ci-aggregate.yml:263-369`, job named
  `"diff-cover PR gate (>=90% changed critical-path lines)"`) — this is the
  real, enforced, >=90%-changed-critical-path-lines coverage gate. **Note
  for the record**: the hub's gate table names this gate by two older
  aliases ("kernel 90% floor" / "mission loader coverage gate"); reading
  `ci-aggregate.yml` directly shows the actual mechanism is this one
  `diff-cover` job (installing `diff-cover==10.3.0`, scoring the PR diff
  against reconciled per-module coverage XML). **Applies** — every line
  this mission's fix commits changes is a changed critical-path line by
  construction.
- **`import-linter` (TID251 banned-API lint)** (`ci-router.yml:418-433`,
  `ruff check --select TID251 .`) — **always runs, applies.** This fix adds
  no banned import; `threading` and `functools` are already used
  extensively elsewhere in `src/`.
- **`uv-lock` (`uv lock --check`)** (`ci-router.yml:406-412`) — **does not
  need to pass a *new* check specific to this PR** because this fix adds no
  dependency and changes no `pyproject.toml`/`uv.lock` entry; the existing,
  already-committed lockfile stays valid. (The job still runs per its own
  `on:` trigger — it is simply unaffected by this diff.)
- **`markdownlint`** (`ci-router.yml:400-407`) — runs on `**/*.md`
  (`plan.md`, `research.md`, and `spec.md` already committed, all `.md`),
  but its own step is `npx --yes markdownlint-cli2 "**/*.md" || true` —
  **the `|| true` makes this job unconditionally non-blocking**, whatever
  it finds. Named here for completeness, not treated as an enforced gate.
- **`commit-msg` ("commit message lint")** (`ci-router.yml:390-397`) — its
  actual step body is `git log --format=%s origin/${{ github.base_ref ||
  'main' }}..HEAD || true`, i.e. it prints commit subjects and always
  succeeds. **This is not an enforced commitlint check in this checkout** —
  named here because the task brief assumed a "commitlint" gate exists;
  direct read of `ci-router.yml` shows no tool actually validates commit
  message format, only a non-blocking log dump. Stated as a finding, not
  papered over.
- **Bandit + pip-audit** — **searched for and not found anywhere in
  `.github/workflows/*.yml` in this checkout** (`grep -rln "bandit"
  .github/` and `grep -rln "pip-audit|pip_audit" .github/` both return no
  matches). This directly contradicts an assumption in the task brief that
  these run "always" — stated here as a verified finding rather than
  invented or silently assumed. If a security-scanning gate exists under a
  different name or a non-workflow mechanism (e.g., a scheduled job outside
  `.github/workflows/`, or a third-party GitHub App with no workflow file),
  it was not discovered by this search; this plan does not claim one exists
  where direct evidence shows none.
- **SonarCloud** — confirmed via direct read of `.github/workflows/sonar.yml`
  (`on: schedule` / `workflow_dispatch` only, explicit comment "no
  `pull_request` trigger, so it structurally cannot enter any PR ... gated
  to `schedule`/`workflow_dispatch` only") and `ci-quality.yml` (has a
  `pull_request` trigger but its jobs are `lint`/`build-wheel`/
  `clean-install-verification`/`uv-lock-check`/`quality-gate` — no Sonar
  step). **SonarCloud does not run on this PR.** No Sonar verdict is
  promised for this mission's PR.
- **Per-module test matrix** (`missions` + `core_misc`, above) — the real
  enforced correctness gate for this change; both are green in the
  pre-fix baseline (Section 9) and must stay green (plus the new red→green
  test) post-fix.

## 11. Campsite-clean (Standing Order 2)

Re-reading the exact lines this fix is about to touch
(`mission_step_repository.py:68-73` around the `_YAML` singleton and its
misleading "thread-safe for reads" comment; `mission_type_repository.py:
316-318` around `_LAYERED_YAML`) for genuine, domain-matched pre-existing
debt on those specific lines: **none found worth folding as a distinct
campsite-clean commit.** The surrounding code (both singleton declarations,
both `_load_step_yaml`/`_load_layered_mission_type_file` call sites) is
otherwise well-documented and structurally sound; the "thread-safe for
reads" comment at `mission_step_repository.py:69` is not itself a
pre-existing *defect* to clean up separately — it is the exact
misconception this mission's own fix corrects in place, so rewriting it is
part of the functional change (Section 6), not a preceding, distinct,
behaviour-preserving campsite-clean step. Saying so explicitly rather than
inventing a busywork commit: **no campsite-clean commit is planned for this
mission.**

## 12. Tracer files

`kitty-specs/concurrent-template-config-race-4589-01M35M6B/traces/{approach,design-decisions,tooling-friction}.md`
were seeded during the spec phase (2026-09-22 entries already present,
covering the Option-A decision, the corrected `src/doctrine/` → 
`src/charter/offering/` path citations, and the mission-slug/ULID-suffix
tooling note). This plan **references, does not re-seed** them.
Implementation will **append** new entries as it proceeds (e.g., what the
forced-interleave monkeypatch construction actually looked like once built,
any friction hitting the exact Barrier-pinned window, and the final
red-commit/green-commit SHAs) — never replace or renumber the existing
entries.

## 13. Commit phasing

One PR to `main` (the sk overlay default), in this order:

1. ~~Campsite-clean commit~~ — **skipped** per Section 11 (no genuine debt
   found on the touched lines).
2. **Red-first failing test commit** (CL-004): the Barrier-synchronized
   regression test (Section 8a) and the SC-006 failure-path test (Section
   8b), committed against pre-fix code, verified RED.
3. **Production-fix commit(s)**: the thread-local YAML accessor + per-key
   lock at both sites (Section 6), verified the same tests now GREEN, plus
   the existing `test_concurrent_creates_no_collision` and the two modules'
   full suites (Section 9/10) still green.
4. **Doc/tracer updates**: tracer-file appends (Section 12) and any
   research/plan corrections discovered during implementation.

This mission ships as **one PR to `main`**. The diff stays reviewable in one
sitting: two singleton replacements + two lock-guarded cache bodies + two to
four new tests, all confined to three files in one package plus one test
file. If implementation later discovers the `_LAYERED_YAML` site (Section
6) needs materially different handling than mirrored here, or that
`resolver.py` needs a change after all (Section 10's `next`-gate caveat),
that is a signal to flag for a possible split — not a silent scope
expansion.

## 14. Human-in-Charge approval

**None needed.** No production secrets, no production Upsun deployment, no
live Stripe integration are touched by this change, and this repository (the
spec-kitty CLI/doctrine tooling itself) does not carry any of those surfaces
in the first place — stated here for completeness per the pipeline's own
requirement, not because any such surface exists to approve.
