# Ledger protocol reference

The ledger has two layers.

**Layer 1 — stage gates.** Fill stages in order. An exit artifact is _pasted
evidence_ — the command run and its real output — never a claim that it
worked. Before acting on stage N, read the ledger and confirm stage N-1's
required fields are filled; if they aren't, you are not at stage N yet.

**Layer 2 — the journal.** Append one line per event, forever, in this shape:

```
- HH:MM [type] <=20 words @locator
```

Vocabulary (fixed, so the checker and future readers can grep it):

| tag           | records                                                                                                                                                                            |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `obs`         | raw observation, before interpretation                                                                                                                                             |
| `finding`     | established fact with locator                                                                                                                                                      |
| `hypothesis`  | claim + prediction + evidence tier + status: `chosen` / `backup` / `killed-by-probe`                                                                                               |
| `down-rank`   | hypothesis moved down the list + reason: `contradicted` / `predicted-observation-missing` / `ad-hoc-assumptions` / `explains-fewer-facts` / `lost-rebuttal` / `merged-into-parent` |
| `probe`       | `[DEBUG-xxxx]` tag mapped to the prediction it tests                                                                                                                               |
| `attempt`     | N — change made → `OK` / `REJECTED` (the breaker counts these)                                                                                                                     |
| `deadend`     | branch ruled out and how it was ruled out                                                                                                                                          |
| `sideissue`   | found in passing, out of scope — logged, never "fixed"                                                                                                                             |
| `mitigation`  | interim fallback opened; must be closed by Stage 8's record                                                                                                                        |
| `cause-found` | early claim + the evidence that discovered it                                                                                                                                      |
| `waiver`      | stage collapsed by citation, reason + locator                                                                                                                                      |
| `question`    | asked of the user + answer                                                                                                                                                         |
| `decision`    | choice made + why                                                                                                                                                                  |

The journal is append-only: a correction is a new line referencing the old
one, because the path through the investigation is itself evidence — the
breaker, the commit message, the handoff, and your own re-entry all read it.
One line per event is what makes recording everything affordable; a narrative
journal dies at entry forty.

Mechanical audit:

```
uv run --no-project python scripts/check_gates.py <ledger> --scan <changed paths>
```

The script needs Python 3.10 or newer. It reports OPEN stages, counts failed
`attempt` lines against the breaker, validates that every waiver carries
reason + locator, flags bare waivers, and refuses to pass while debug tags
remain. A non-zero result means you are not done. The script checks _shape_;
the truth of pasted evidence stays your judgment and the user's review.
PY