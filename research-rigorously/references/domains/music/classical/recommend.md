# Classical: recommend mode

Unfamiliar works, overplayed canon out. Work-level only: every pick names one work with verified timing.

## Steps

1. Confirm the domain block is in context (music `rules.md`, classical `sources.md`, `exclusions.md`; the driver loads it). Done when ban list + streaming domain list are present.
2. Scope: unclear ask (the start-batch questions left scope unanswered) = orchestral, post-1750, non-chamber, non-vocal. Renaissance: outside default, not banned; honour explicit ask. Medieval/Baroque: state era ban, decline.
3. Candidates by priority: orchestral first (symphony, concerto, tone poem, overture, suite); chamber only when ask says chamber/quartet/trio/sonata/solo; vocal last, choral-orchestral before solo-vocal, flag `[slim-pickings vocal fallback]`.
4. Banned work named as taste ("I like Rach 2"): anchor only. State once `Anchor: [work] -> deep-cut works below`, never a pick.
5. Verify each candidate through the claim ledger (every fact is a claim; a pick with an untrue or not-found claim is dropped, ADR 0027): dates, era, forces, movements, durations per `../rules.md` "Timing". Done when every pick carries two timing sources or is dropped.
6. Compose picks, then `Skipped: [banned names relevant to request] excluded per ban list.`, then an `Unverified` annex for facts without two sources.
7. The driver publishes mode `recommend` (`answers/recommend-<slug>.html`); pick blocks are the page body. Terminal: one-line summary + live link.

## Pick block

```
Composer (dates) — Work, Op./Cat. (year) [forces, duration with two timing sources]
Evidence:
- [review / program note / composer note / analysis]: sourced fact on scoring, form, theme treatment, reception. Name source.
- [second source, different type where possible]: same.
Start with: movement/section to sample first + what to listen for per cited analysis.
Recording: one recording (conductor / orchestra / label).
```

Count: default 5, min 3, max 10; explicit 20/30 request overrides max.
