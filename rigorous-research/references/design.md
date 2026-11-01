# rigorous-research design record

ADRs 0001-0034 (system-config `docs/decisions.md` is numbered apart). One decision per entry; code comments cite the numbers.

**0001 Ledger is canonical, pages are generated.** Pages are never hand-edited; a fix propagates from the ledger.
**0002 Per-claim loop, 5 rounds, forced rotation.** Each round uses a paradigm not yet tried for that claim. Terminal statuses: true, untrue, interpretive, not-found. No token budget; waves are capped (`max_waves`).
**0003 Source and output live in bearmancer.github.io.** Auto-commit and push only when every gate passes.
**0004 Plain SKILL.md plus scripts.** No harness-specific tool names in prose; ledger, URL audit and render live in scripts.
**0005 One layout per page,** picked from claim shape by the agent; the layout step may arrange sentences, never change one.
**0006 YAML ledger; a re-run keeps settled claims** and re-opens `not-found` once.
**0007 Claims-first for learn and rules;** verify splits claims from the input afterwards.
**0008 Truth bar.** `true` = one primary source, or two independent T1/T2 secondaries, no credible contradiction. Discovery stops at saturation: two waves in a row that add no new claim.
**0009 Fetched text is data.** Only a tool-less extractor reads raw pages; the rest see claims and short quotes. A failed gate leaves a draft branch and a report, nothing on main.
**0010 Lawful acquisition.** No shadow libraries; paraphrase and cite; quotes 25 words or fewer; unreachable sources are logged, never circumvented.
**0011 Surfaces are the MCP fleet** (registry.yaml). Route per capability: MCP, then vendor CLI, then POST script; keyed servers rotate keys.
**0012 Key exhaustion, visual reads, verify exposure.** A whole pool exhausted: stop and ask. `visual-read` claims need two separate visual reads, or one read plus text corroboration (model families dropped by 0033). Verify pages are `noindex` and unlisted. The verifier re-checks every claim.
**0013 Model roles across families.** _Superseded by 0033 (#340)._ Tiers, families and fallbacks live in `registry/roles.yaml`; every role is a plain `opencode run`, no custom agent (#308). No checking role shares a family with the author.
**0014 Prose conforms to the ledger.** A claim in the final prose absent from the ledger fails the conformance gate. Status labels only in verify cards, debate blocks, errata. Reader is India-aware global.
**0015 Two ladders.** Discovery rotates per round per claim; the fetch ladder escalates per URL on a block. Rotation unit is the paradigm, then vendor; MCP, CLI and POST within one server are never a new surface. Attempts are logged by the driver from the agent's reply.
**0016 Round order:** keyword, semantic, answer engines, scholarly or archive, crawl or browser. Each round rewrites the query: supporting, opposing, primary, other-language.
**0017 Key state.** Per-key exhaustion by fingerprint; one rotation per exhaustion event under a lock; unknown errors retry once and rotate only when two different URLs fail alike. Raw fetches stay in gitignored `work/`.
**0018 Ledger layout.** Per topic `claims.yaml`, `sources.yaml`, `attempts.jsonl`. Evidence needs a locator and a quote of 25 words or fewer. A reply counts only as one fenced block whose quotes appear verbatim; one whose quote was spliced is re-asked once, then flagged in the run record. An empty extraction from a page carrying every number in the claim flags `suspect_empty` and blocks the barren stop. `open` is working state and fails the publish gate.
**0019 Status invariants.** true needs the truth bar; untrue the same on the contradicting side with no credible support; interpretive two positions each with a T1/T2 source; not-found after three genuine rounds that surfaced no new read source and left the claim with no evidence and no `suspect_empty` flag, or at the five-round cap, and `not_found_reason` records which. A round is genuine only when fewer than three claims in that wave returned the same attempts-and-count reply print, so template replies never count toward a stop. Two-source paths need two distinct publishers plus the verifier's independence note. The check audits `attempts.jsonl` for rotation.
**0020 Run lifecycle.** _Superseded by 0033 (#340) where it names agent steps; phases, waves, draft branch and exit codes stand._ A Python driver owns phases and `run.yaml`; resume re-runs the current phase. Phases: infer_mode, ingest, discover, verify, write, conformance, layout, render, gates, publish, live_check (verify mode: extract instead of discover and write). Draft branch per run; a failed live check reverts the merge. Waves: size 8, halved on 429, one shared deadline, never two copies of a hung task, across waves too (`verify._guarded_round`). Exit 0 done, 1 failed, 2 suspended. A failed or suspended run calls `DEEP_RESEARCH_NOTIFY`.
**0021 No oh-my-opencode dependency.** _Superseded by 0033 (#340)._ Plain `opencode run` agents and `{file:}` key rotation.
**0022 Rules mode.** Authority order: publisher rulebook, rules page, FAQ, official errata (supersedes), designer or publisher forum posts; player posts are `interpretive`. BGG public pages and XML API only, never log in. One labelled "easiest strategy" section.
**0023 Verify mode.** Atomic factual claims only (opinions and predictions skipped, counted). Cards for untrue and interpretive; not-found and failed sources in the appendix. `answers/verify-<slug>-<date>.html`.
**0024 Site shell.** `assets/lesson.css`, `shell.js`, `course-index.js`. The topic select is the page's name and navigation: no title above it. The feed lists courses (with chapters when more than one) then single pages; verify pages stay unlisted and show their own title. Home index is one section per subject, numbered rows. One run per topic, publish serialized by a lock.
**0025 Front-loaded questions.** One batch at the start (mode, depth, scope), then unattended; the mode goes in as `--mode`. The only mid-run stop is `NEEDS_YOU.md`.
**0026 Answer mode.** One cited-prose page `answers/answer-<slug>.html`, layout `concept`, never chapters. "Is it true" is an answer, not a verify. Vague wording becomes measurable aspects.
**0027 Recommend mode and domain rules.** Classical picks; every pick fact is a ledger claim; a pick survives only if all its claims are true or interpretive. Domain files in `references/domains/`; the streaming-host ban and the composer ban list are enforced in code.
**0028 Long media.** Only a recording over 30 minutes is split: built-in chapters, else the extractor decides. Answer pages never split.
**0029 Subject order.** `<site>/site.json` `subjects_last` pins sections to the end.
**0030 Topic removal.** `cli remove` deletes a topic's pages, course dir and ledger, republishes the index, live-checks the 404s and reverts on mismatch.
**0031 Run robustness (audit 2026-10-07).**

- Out-of-round or repeated-paradigm attempts are rejected when logged, so a bad agent report costs a retry of the round, not the run.
- _Superseded by 0033 (#340):_ independence is judged against the author only. A role answered by two families is fine; media stays on one. Fallbacks: author muse, extractor and media longcat, verifier space-bunny.
- _Superseded by 0033 (#340):_ which models answered, fallbacks included, is saved in `run.yaml` (`provenance`) and restored on resume.
- The gate verifier re-asks about a disputed claim once, alone, before it counts.
- A lone weaker contradiction no longer demotes a claim on round one: both sides must meet the truth bar, or the rounds run out.
- `cli start --mode`, `cli doctor`, `DEEP_RESEARCH_NOTIFY`; round failures stop a run after three.
- Open: no token cap; a not-found claim needs five logged rounds, so a persistently failing round still stops the run (resumable).

**0032 Run hardening (second audit 2026-10-07).**

- A failed live check reverts and marks the run `reverted`; resume refuses (a new run is needed). `pre_publish_base` keeps the revert range if a crash lands between push and state save; the publish handler restores live state on any interrupt.
- A discovery agent's own text is used only when the driver cannot fetch the URL, and then the source is `unknown` (never a tier). Agent URLs must be http(s); `file:` and other schemes never fetch.
- Fetch step ids are lock-guarded and destination files derive from the step id. Git conflicts on revert or rebase abort and raise.
- Slugs are validated; `remove` matches `verify-<topic>-<date>` exactly; verify mode ships only a hash of the pasted input.
- Claim hash keeps sign and decimal point; domain routing ignores PHP Composer and "orchestration"; failed inputs stop learn, answer and rules runs like verify; failed misconception tasks are retried and never count as a quiet wave.
- Open: no token cap; agent-supplied text for an unfetchable URL stays unverified, not re-fetched by another route.

**0033 Everything stays in the app that loaded the skill (#340, owner ruling 2026-10-26).** No script starts another agent program or calls a model: no external caller, no runner, no fallback, no model ids, families or session cleanup. The agent that loaded the skill answers every AI step. A phase that needs one writes `<site>/work/<topic>/agent/<run>/<step>-<hash>.ask.md` (gitignored: asks carry raw text and the verify input) and the run exits 3 with `ASKS.md`; the agent writes the reply file and resumes. The hash covers role, prompt and attached files, so a changed payload asks again. Checking steps (extractor, verifier, media) run in fresh subagents with no conversation history, one subagent per batch file: the driver groups a wave's asks by role (extractor cap 6, verifier cap 10, media alone), writes `<run>/batches/<role>-<hash>.batch.md` listing ask and reply paths, and lists the batch files under `## batches` in `ASKS.md` while keeping the flat ask list. Ask and reply files stay one per step, so hashes and caches are untouched; a worker reads each source before answering its own ask. The family-independence gate is gone; `--model` records in `answered_by` which model answered. A test fails if skill code starts an agent CLI.

**0034 Publish to the Pages branch (#349, owner ruling 2026-10-26).** Publish, live check, revert and topic removal always target the branch GitHub Pages serves (`main`), whatever branch the site clone has checked out. Drafts start from that branch; publish pushes the draft checkout to it; revert works in a temporary detached checkout; removal reads its footprint from the draft checkout; the live check compares against the published files. The clone's checked-out branch, index and working tree are never touched.
