# TDD: seams, tests, mocks

Contract: gates, CLI and the state machine are in ../SKILL.md. This playbook is the detail for this phase.

TDD is the red-green loop. The plan records the contract; execution records the runs.

**Seams.** A seam is the public boundary where you observe behaviour without reaching inside. Test only at pre-agreed seams, confirmed with the user: give each proposed seam one line on what it catches and what it misses. No test is written at an unconfirmed seam, and the ideal number of new seams is one. When the interface's shape is itself in question (how deep the module is, where the seam belongs, what it exposes), read `codebase-design.md` for the module/interface/depth/seam vocabulary.

**The plan's fields.** `test_seam` is `"<interface> | catches: ... | misses: ... | class: in-process|local-substitutable|remote-owned|true-external"`; the class is the dependency category from `codebase-design.md`, and G4 rejects a seam without one. `test_file` is the test path; `red` names the failing test and the expected failure (a `fix` names its repro); `green` names the minimal pass condition. Red and green must be observably different. G4 rejects a missing or prose-only seam, a missing test file, or identical red/green.

**The loop.** Write one failing test at the seam, watch it fail for the expected reason, write the minimal code to pass, repeat. No tests for imagined behaviour. Refactoring is a separate step after green, not part of the red-green cycle. Executed evidence is recorded with `test-run --task T1 --phase red|green --cmd ... --exit ... --artifact ...`; the plan can publish without runs, but a handoff claiming a test ran cites the run row.

**What a good test is.** Tests verify behaviour through public interfaces, not implementation details; code can change entirely and the test should not. A test reads like a specification and survives refactors. Expected values come from an independent literal, a worked example or a spec line, never recomputed the way the code does (tautological tests are banned). One logical assertion.

**Mocking.** Mock only at system boundaries: external APIs, time and randomness, sometimes the DB or filesystem. Never mock your own modules. Prefer real implementation over fake over stub over mock; verify through the interface, never a side channel. Crash or rollback behaviour is exercised at the real boundary, not an injected exception.

**Sizes.** Small = one process, no I/O; medium = localhost; large = external. Keep most tests small.

**Anti-patterns.** Implementation-coupled tests (private methods, internal collaborators, querying the database instead of using the interface); tests that break on refactor although behaviour did not change; skipped or deleted tests without a reason; assertions that recompute the implementation.
