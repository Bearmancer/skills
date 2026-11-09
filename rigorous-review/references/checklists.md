# Review checklists

Contents: five axes · tests first · structural remedies · smell baseline · security · performance · architecture/SOLID · change sizing & descriptions · dependencies · dead code · specialised modes (style, API, performance, quality strategy)

## The five axes (every perform review walks all five)

1. **Correctness** — matches spec/task? Edge cases (null, empty, boundaries)? Error paths, not just happy path? Off-by-one, races, state inconsistencies? Tests pass — and do they test the right things (behaviour through public interfaces, not implementation mirrors)?
2. **Readability & simplicity** — names descriptive and convention-consistent (no bare `temp`/`data`/`result`)? Control flow straight (no nested ternaries, deep callbacks)? Related code grouped, module boundaries clear? "Clever" tricks simplified? Could it be fewer lines (1000 where 100 suffice is a failure)? Abstractions earning their complexity (generalise at the third use case, not the first)? Dead artifacts (`_unused` no-ops, backwards-compat shims, `// removed` comments)? A new conditional bolted onto an unrelated flow is a design smell, not a nit — push it into its own helper/state/policy. Repeated conditionals on the same shape signal a missing model or dispatcher; a "temporary" branch is usually permanent debt.
3. **Architecture** — follows existing patterns or justifies a new one? Clean module boundaries, dependencies one direction, no cycles? Duplication that should be shared? Abstraction level right? Does the refactor _reduce_ complexity or relocate it — count the concepts a reader must hold; prefer the version where whole branches/modes/layers disappear, prefer deleting an abstraction to polishing it. Feature-specific logic leaking into a shared module is a finding. Type boundaries explicit — gratuitous `any`/`unknown`/optional/casts and silent fallbacks paper over unclear invariants.
4. **Security** — input validated/sanitised at boundaries? Secrets out of code, logs, VCS? AuthN/AuthZ where needed? Parameterised queries, encoded outputs (XSS), CSRF on state-changing ops? Dependencies trusted, no known vulnerabilities? External data (APIs, logs, user content, config) treated as untrusted and validated before logic/rendering? For depth, follow the `security-and-hardening` skill.
5. **Performance** — N+1 patterns? Unbounded loops/fetches? Sync that should be async? Unnecessary re-renders? Pagination on list endpoints? Large objects in hot paths? Quantify ("~50 ms per item"), never "could be slow". For depth, follow `performance-optimization`.

**Tests first (before the implementation).** Tests exist? Behaviour, not implementation? Edge cases? Descriptive names? Would they catch a regression? Answer the last by experiment: invert one condition the change adds (drop a negation, swap `&&`/`||`), run the suite, restore from a copy. A mutation that stays green is a finding naming the missing test case.

**Structural remedies — name the move, not just the problem:** replace a conditional chain with a typed model/dispatcher · collapse duplicate branches · separate orchestration from business logic · move feature logic to its owning package · reuse the canonical helper · make a type boundary explicit · delete a pass-through wrapper · extract a helper / split a large file. Prefer the remedy that removes moving pieces.

## Smell baseline (Standards lane; repo standards override; always judgement calls)

Fowler, _Refactoring_ ch.3. Match against the diff; skip anything tooling enforces.

- **Mysterious Name** — name doesn't reveal what it does/holds → rename; no honest name means murky design.
- **Duplicated Code** — same logic shape in more than one hunk/file → extract the shared shape, call it from both.
- **Feature Envy** — a method reaching into another object's data more than its own → move it onto the data.
- **Data Clumps** — the same fields/params travelling together → bundle into one type.
- **Primitive Obsession** — a primitive/string standing in for a domain concept → give the concept a small type.
- **Repeated Switches** — the same switch/if-cascade on the same type recurring → polymorphism, or one shared map.
- **Shotgun Surgery** — one logical change forcing scattered edits → gather what changes together into one module.
- **Divergent Change** — one module edited for several unrelated reasons → split by reason.
- **Speculative Generality** — abstractions/hooks for needs the spec doesn't have → delete, inline until a real need shows.
- **Message Chains** — long `a.b().c().d()` the caller shouldn't depend on → hide the walk behind one method on the first object.
- **Middle Man** — a class/function mostly delegating onward → cut it, call the target directly.
- **Refused Bequest** — a subclass ignoring most of what it inherits → drop inheritance, use composition.

## Architecture / SOLID / complexity (OMC code-reviewer)

Spec compliance is Stage 1 and must pass before Stage 2 quality work. Then: run language diagnostics (`lsp_diagnostics` or the repo equivalent) on every modified file — no type errors approved; pattern-scan for empty catch blocks, `console.log`, hardcoded secrets. Logic: all branches reachable, loop bounds, null handling, type mismatches, control/data flow. Error handling: cases handled, propagation correct, resources cleaned up. Anti-patterns: God Object, spaghetti, magic numbers, copy-paste, shotgun surgery, feature envy. SOLID: SRP (one reason to change), OCP (extend without modifying), LSP (substitutable), ISP (small interfaces), DIP (depend on abstractions). Maintainability guides: functions ≲50 lines, cyclomatic complexity <10, nesting ≤4 — cited as guides with concrete extractions, never as CRITICAL on their own. Positive observations are part of the output; they reinforce good practice and make the rest credible.

## Change sizing & descriptions

~100 changed lines: good, reviewable in one sitting. ~300: acceptable if one logical change. ~1000: too large — split it. Watch _file_ size too: a small diff can push a file past ~1000 total lines; when a change materially grows an already-large file, ask whether to extract first. One change = one self-contained thing, tests included, system functional after it. Split by: **stack** (sequential), **file group** (different reviewers), **horizontal** (shared code/stubs first), **vertical** (full-stack feature slices). Large is acceptable for complete deletions and automated refactors where only intent needs verifying. Refactor and feature work are two changes; small cleanups ride along at reviewer discretion.

Every change description stands alone in history: first line short, imperative, standalone ("Delete the FizzBuzz RPC"); body carries what/why, context, decisions, links to bugs/benchmarks/design docs, acknowledged shortcomings. Anti-patterns: "Fix bug", "Phase 1", "Moving code from A to B", "Add convenience functions".

## Dependency discipline

Before adding: does the existing stack solve it? Size/bundle impact? Actively maintained? Known vulnerabilities (`npm audit`)? Licence compatible? Prefer the standard library; every dependency is a liability. Upgrades are changes like any other: read the changelog, not just the version (major: migration notes, what breaks); one dependency per change so a break has one cause and a clean revert; green suite before _and_ after — if coverage around the dependency is thin, that gap is the finding, add a test first; review the lockfile diff (the transitive graph is the real change), never hand-edit a lockfile, always commit it. Supply-chain triage verdicts belong to `security-and-hardening`.

## Dead code hygiene

After a refactor/implementation: identify what is now unreachable or unused, list it explicitly (`DEAD CODE IDENTIFIED: - fn (file) — replaced by X`), and ask before deleting. Never silently delete what you are unsure about; never leave confirmed orphans lying around either.

## Specialised modes (invoke by request, same severity rules)

- **Style** (OMC code-reviewer, lightweight model): read project config first (`.eslintrc`, `.prettierrc`, `tsconfig.json`, `pyproject.toml`) — cite project conventions, never personal preference. Formatting, naming case per language, idioms (`const`/`let` not `var`, comprehensions, `defer` cleanup), import organisation. Note what is auto-fixable (`prettier --write`, `eslint --fix`, `gofmt`). No bikeshedding: CRITICAL is mixed tabs/spaces or wildly inconsistent naming; MAJOR is wrong-case convention or a non-idiomatic pattern.
- **API contract**: breaking changes (removed fields, changed types, renamed endpoints, altered semantics)? Version bump for incompatible changes? Error semantics consistent, meaningful, no leaked internals? Existing callers still work? Contracts reflected in docs/OpenAPI?
- **Performance**: algorithmic complexity, memory leaks/allocations/GC pressure, latency paths and I/O bottlenecks, data-structure choices, caching opportunities _and invalidation correctness_, profiling instrumentation points. Rate CRITICAL (production impact) / HIGH (measurable) / LOW.
- **Quality strategy** (release readiness): coverage adequacy (unit/integration/e2e) against risk surface, missing regression tests for changed paths, blocking defects and known regressions, gates that must pass, monitoring/alerting for new features. Risk-tier the change SAFE / MONITOR / HOLD, from evidence.

## Review speed & disputes

Respond within one business day (maximum, not target); ideally shortly after the request arrives; a typical change completes several rounds in a day. Fast individual responses beat fast final approval. Too large → ask the author to split. Dispute hierarchy: technical facts/data > style guides (absolute on style) > engineering principles over personal preference > codebase consistency (if health-neutral). No "fix later" without a filed, self-assigned bug unless a genuine emergency.
