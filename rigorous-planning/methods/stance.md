# Stance: how Q0 questions reach the user

Read this before the first Q0 question. Intent decides which forks survive; stance decides how they are delivered. Firewall: stance chooses form, pacing and batching. It never reinterprets what a reply meant, and no stored profile may bias how a reply is classified.

## Renderers

Every question goes through the harness question tool (`ask --slug S` prints the JSON) with its wait flag true, so the prompt raises a notification a user away from the screen still sees. Three renderers over the same forks:

- **batch**: the whole inventory in as few calls as the tool allows (1-4 questions each), recommended default first. Fits users who enumerate upfront and delegate the rest. Default for CLEAR intent in a maximalist sweep.
- **one-by-one**: one fork per call. Fits users who own decisions individually, and any user who said "interview me".
- **examples-first**: no open questions; 2-3 contrasting concrete approaches and "which is closest, what is wrong?". Fits UNCLEAR intent and users who cannot yet state what they want. Never ask such a user to produce criteria from a blank page. Use it for `outcome` and `scope`, then batch the rest.

The user can switch renderer at any time in their own words; honor it at once.

**Opening renderer.** Derive it before the first question. Episodes exist (see the log below): generalize from those most similar to this session's repo, domain and familiarity; consistent episodes set the renderer; split episodes follow the matching side; variable ones open neutral (topology echo plus escape hatch). One session never flips the opening. No episodes: CLEAR opens batch, UNCLEAR opens examples-first. Announce the renderer in the intent-verdict line with the veto: "say the word to go one-by-one".

The first time you ask, say that opting out is legitimate: "you decide" resolves a fork to its recommended default and is logged as `default: ...`.

## Fork-reply classification

Classify every reply to an asked fork into exactly one state. Never infer difficulty from hedge words, tone or a missing option label; ask whether the fork became usable.

- **Resolution test**: given this reply plus existing constraints, could two materially different implementations both comply? No: resolved.
- **Information-gain test**: did the reply eliminate an option, add a constraint, challenge the framing, or ask a consequence the decision needs? Yes: progress.

| State | Meaning | Action |
| --- | --- | --- |
| RESOLVED | one implementable outcome: exact label, semantic equivalent, a new outcome rejecting the offered framing, a constraint leaving one option, or explicit delegation | record the semantic decision; continue |
| RESOLVED_BUT_UNINFORMED | names an outcome but calls it arbitrary, admits not understanding the options, or shows a misconception about the consequence | correct the misconception in one line; defaultable fork: adopt the recommendation with a visible veto; owner-decision: one informed yes/no |
| UNRESOLVED_PROGRESS | still open, but added decision-relevant information | use it, answer any question it raised, re-render this fork only |
| UNRESOLVED_BLOCKED | still open, nothing decision-relevant added | re-render this fork as 2-3 concrete outcomes, recommendation first, one material consequence each |

One reply can resolve several forks, correct facts and add scope: parse all of it. Distribute answers to their forks, fold new scope into the inventory, treat a factual challenge as UNRESOLVED_PROGRESS on the challenged claim. After two UNRESOLVED_BLOCKED on distinct forks, offer the renderer menu once (continue as-is / defaults for the rest / examples-first). A session-wide renderer switch happens only on the user's explicit choice, never from counters or hedge frequency.

## Override gates

"Stop asking", "you decide", "알아서", "질문 그만", "니가 정해" become instructions only after three gates in order: (1) speech act: a direct affirmative instruction now, not negation, a quote, a hypothetical or reported speech; (2) intent: delegate this fork / delegate the remainder / stop the interview / request a recommendation / fix the process (only the two delegations transfer ownership); (3) scope: the narrowest supported reading (a bare "you decide" on one fork delegates that fork; session-wide needs explicit breadth such as "the rest" or "from now on"), keeping stated exceptions.

Actions: delegate this fork: recommended default, logged, renderer unchanged. Delegate the remainder: defaults for the remaining defaultable forks, scope acknowledged. Stop the interview: stop incremental questions, adopt defaults, and consolidate every surviving owner-decision into one final authorization block (recommended choice plus its material consequence each); "go" authorizes only when it follows that block. In this skill that block is the `q0-authorization` question.

**Invariant**: no override phrase silently authorizes an irreversible, destructive or spend decision. When questions were stopped, those decisions arrive as the authorization block, never as adopted defaults.

## Planning-style episode log

An append-only log at `system/human/planning-style.md` (memory tool; create on the first qualified episode; description "Planning-interaction episode log; generalize at read time"). Never store scores, counters, thresholds or a summarized persona; generalize at read time from the raw episodes.

Record 0-2 lines at close, only when (a) the user explicitly chose a renderer or stated an interaction preference (`declared`), or (b) the same unsolicited stance showed across 2+ distinct forks: batched or superseded them, demanded per-fork ownership, or needed concrete examples (`observed`). Never record sessions with no genuine fork, bare approvals, a single local delegation, frustration alone, or a shape the renderer forced. Format, every field required:

```
- [YYYY-MM-DD] <repo/domain + familiarity> - <observed behavior, one line> <!-- src: <session-id>; model: <session model>; pattern: observed|declared; confidence: low|medium|high -->
```

Protect minority and `declared` entries (check whether this session matches their context before applying the majority); cap near 15, pruning the oldest majority-consistent entries first. Seeds (`(seed)` lines from other agents' history) are `confidence: low` always, consulted only while zero native episodes exist, and only for the opening renderer. No memory tool: note the stance in the plan's Decisions block and skip the log.
