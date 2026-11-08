# Rigorous Pack

A harness-independent skill pack that replaces five third-party skill packs with script-enforced workflows, so work runs end to end without relying on the agent's reading of prose.

## Language

**Pack**:
The set of `<verb>-rigorously` skills (planning-rigorously, research-rigorously, review-rigorously, execute-rigorously, ..., init-rigorously last), taken together, that stands in for every source pack.
_Avoid_: Suite, bundle, collection, rigorous-* (prefix form)

**Source pack**:
One of the five third-party skill packs the Pack replaces: omo, omc, matt-pocock, addyosmani, superpowers.
_Avoid_: Upstream, vendor pack

**Harness**:
The agent runtime a skill executes inside: Command Code, OMO, Claude Code, OpenCode.
_Avoid_: Framework, platform, host

**Harness-agnostic**:
Behaviour that is identical in every Harness because it lives in scripts, never in a Harness feature.
_Avoid_: Portable, cross-platform

**Noise**:
A source skill that only configures, displays or administers its own plugin (hud, omc-setup, configure-notifications); dropped, never absorbed.
_Avoid_: Legacy, unused

**Railroad**:
Step order and completeness enforced by a script that refuses to advance until the current step is recorded; never left to the agent's reading of prose.
_Avoid_: Guardrail, best practice, guideline

**Question sweep**:
The up-front, maximal pass that surfaces every ambiguity before planning starts, so the run never has to stop; every question goes through the Harness's question tool, never prose, and questions are always asked in bulk as whole rounds, never one at a time.
_Avoid_: Clarification, intake, discovery

**Non-stop run**:
A run that continues until all work not blocked by an open question is finished; the Pack's own version of what omo calls ulw and omc calls ralph.
_Avoid_: ulw, ralph, autopilot, loop

**Attended run**:
A non-stop run with a user at the Harness; open questions are asked before work starts.
_Avoid_: Interactive mode

**Unattended run**:
A non-stop run with no user at the Harness; open questions are parked and asked together at the end.
_Avoid_: Headless mode, batch mode

**Parked question**:
An uncertainty collected during an Unattended run; the work that depends on it waits and all other work continues.
_Avoid_: Blocker, TODO

## Run control

**Driver**:
The script a skill's SKILL.md hands control to; it alone decides the next step, prints one step at a time, and refuses to advance until the step's artifact passes its Mechanical checks.
_Avoid_: Orchestrator, controller, workflow engine

**Rigor folder**:
The `.rigor/` folder at a project's root holding every run's state; written only by Drivers and identical for every Harness.
_Avoid_: State dir, session store

**Run ledger**:
The append-only record in the Rigor folder of every step a run took and every artifact and Receipt it produced.
_Avoid_: Log, notepad, progress file

**Receipt**:
A result the Driver recorded by itself running a command (exit code and output hash); never reported by the agent.
_Avoid_: Evidence, proof

**Mechanical check**:
A validation a Driver performs without understanding meaning: closed vocabulary, resolvable pointer, Receipt, coverage, or tree hash.
_Avoid_: Verification, review

**Adapter**:
An opt-in, thin per-Harness file (hook config or plugin shim) that re-prompts while a run is unfinished, each time the agent tries to stop while work remains counts as one failure; on the 3rd failure it lets the agent stop and records the stall; the core never depends on it.
_Avoid_: Plugin, integration

## Assimilation (build time only)

**Unit**:
The smallest structural piece of a source skill file (heading, paragraph, list item, table row, code block, frontmatter field, bundled file), produced by a parser so that the Units reassemble to the exact original bytes.
_Avoid_: Rule, feature, item

**Worksheet**:
The build-time record, never shipped inside a skill, of every Unit of every source skill and where it went; exists to prove nothing was missed. The runtime record is the Run ledger.
_Avoid_: Ledger, inventory, matrix
