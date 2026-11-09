# Debug ledger — <one-line bug label>

created: <YYYY-MM-DDTHH:MM>

<!-- Two layers. Journal: append-only, one line per event, never edited
     (corrections are new lines referencing old ids). Gates: fill in order;
     exit artifacts are pasted evidence, not claims. Waivers only via the
     cause-found collapse rule — a bare WAIVED() fails check_gates.py. -->

## Journal

- <HH:MM> [obs] <raw observation> @<file:line | command>
- <HH:MM> [cause-found] <claim> @<discovery evidence>
- <HH:MM> [down-rank] H<n> <contradicted|predicted-observation-missing|ad-hoc-assumptions|explains-fewer-facts|lost-rebuttal|merged-into-parent> @<locator>

## Stage gates

### Stage 0 · STOP

- changes_halted: yes
- redacted: yes
- evidence: |
  <error/output as it arrived, secrets replaced with <REDACTED>>

### Stage 1 · LOOP

- command: `<the one command>`
- run_once: |
  <actual output that went red>
- red_capable: yes
- deterministic: yes
- fast: <seconds>
- agent_runnable: yes

### Stage 2 · REPRO

- exact_symptom: yes
- minimal_scenario: |
  <what survived minimisation; each element load-bearing>
- load_bearing: yes

### Stage 3 · SCOPE

- failing_layer: <UI|API|DB|build|external|test>
- boundary_evidence: |
  <per-edge in/out probes>

### Stage 4 · RESEARCH (no stage-5 text until rows close; may collapse post-fix)

- project_docs: consulted(<file:line>) | N/A(<reason>)
- recent_changes: consulted(<sha/diff>) | N/A(<reason>)
- working_examples: consulted(<file:line>) | N/A(<reason>)
- reference_read_completely: consulted(<locator + pages/sections>) | N/A(<reason>)
- official_docs: consulted(<url>) | N/A(<reason>)
- upstream_issues: consulted(<issue id/url>) | N/A(<reason>)
- environment_deltas: consulted(<comparison>) | N/A(<reason>)

### Stage 5 · HYPOTH

- ranked: |
  1. If <X>, then <changing Y> will <disappear / worsen>. [T<n> · chosen]
  2. If <Z>, then <test W> distinguishes it. [T<n> · backup]
- critical_unknown: <single missing fact keeping #1 and #2 apart>
- discriminating_probe: <cheapest observation separating them> -> tests H1 vs H2
- chosen: <n>

### Stage 6 · PROBE

- probes: |
  [DEBUG-xxxx] <probe location> -> tests H<n>
- one_variable: yes

### Stage 7 · FIX

- seam: <file:line | MISSING-SEAM: <why + architecture note>>
- test_red: |
  <failing-test output>
- negative_control: yes(<revert reproduces>) | N/A(<reason>)
- fix: <the single change>
- test_green: |
  <passing output>
- single_change: yes

### Stage 8 · VERIFY

- original_loop: |
  <un-minimised repro output, green>
- full_suite: |
    <summary line>
- build: |
  <result>
- e2e_spot: |
  <what was exercised>
- mitigations: none | <list of open interim fallbacks>

### Stage 9 · CLOSE

- debug_tags_gone: yes
- prototypes_cleaned: yes
- post_fix_sweep: no-waivers | done(<rows re-checked, outcome>)
- breaker: no | discussion(<attempt count + what was discussed with partner>)
- commit: <sha — message records root cause + winning hypothesis>
