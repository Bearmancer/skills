# Stage 1 — building and tightening the loop

Everything downstream consumes this signal, so spend disproportionate effort
here. Be aggressive, be creative, refuse to give up: a cause found without a
loop is a guess you happen to like.

## The ten recipes, in rough order of preference

1. Failing test at whatever seam reaches the bug (unit / integration / e2e).
2. Curl / HTTP script against a running dev server.
3. CLI invocation with a fixture input, diffed against a known-good snapshot.
4. Headless-browser script asserting DOM / console / network.
5. Replay a captured trace — save a real request, payload, or event log to
   disk; replay it through the code path in isolation.
6. Throwaway harness — minimal subset of the system, one service, mocked
   deps, one function call into the path.
7. Property / fuzz loop — 1000 random inputs, look for the failure mode.
8. Bisection harness — automate "boot at state X, check" so
   `git bisect run <loop>` works.
9. Differential loop — same input through old vs new version, or two configs,
   diff the outputs.
10. HITL script — last resort: a human must click, so drive _them_ with a
    structured loop (see `scripts/hitl-loop.template.sh` pattern) and feed
    their output back.

Note: the user's already-failing test or pasted crash output often _is_ the
loop — run it once, capture the red output, and the gate closes early rather
than being skipped (that is a collapse under the cause-found rule, not a
skip).

## Tighten the loop as a product

- Faster: cache setup, skip unrelated init, narrow the test scope.
- Sharper: assert the _specific symptom_, not "didn't crash".
- More deterministic: pin time, seed RNG, isolate the filesystem, freeze
  network.

A 30-second flaky loop is barely better than no loop; a 2-second deterministic
one is a debugging superpower.

## Non-deterministic bugs

The goal is a high reproduction _rate_, not a clean repro. Loop the trigger
100×, parallelise, add stress, narrow the timing window, inject sleeps into
suspected race paths. A 50%-flake bug is debuggable; 1% is not — keep raising
the rate until it is.

## Gate criteria (all five, into the ledger)

Name one command, already run at least once, that is red-capable (goes red on
_this_ bug, green once fixed), deterministic, fast, and agent-runnable. Paste
command + real output.

## When you genuinely cannot build a loop

Stop and say so. List what you tried in the journal. Ask the user for:
(a) access to the reproducing environment, (b) a redacted captured artifact —
HAR file, log dump, core dump, screen recording with timestamps — or (c)
permission to add temporary instrumentation. Do not proceed to hypothesising
without a loop; that is the one unrecoverable detour in this chain.
