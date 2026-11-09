# The circuit breaker

Three failed `attempt` lines freeze the pipeline — mechanically, since
`check_gates.py` counts them. Each fix revealing a new problem in a different
place is not bad luck: it is the signature of a wrong _architecture_, not a
wrong hypothesis. Stop, write what the attempts showed, and take it to the
human partner before any fourth attempt: is the pattern fundamentally sound,
are we sticking with it through inertia, should the seam move? Run the
premortem lens over what the attempts showed before that conversation
(`references/lenses.md`): the attempts are the evidence, "what would
embarrass this ledger later" is the question. A fourth fix
without that conversation is a rail violation by definition.

Also question the chain's own conclusion: if a closed ledger genuinely finds
no root cause, that is a completed investigation, not a failed one — document
what was checked, add appropriate handling (retry, timeout, clearer error),
set up monitoring for the signature. But expect most "no root cause" cases to
be an un-closed ledger; re-run the sweep before reaching for this exit.
PY