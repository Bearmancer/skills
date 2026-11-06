# Writing the plan and handoffs

Contract: gates, CLI and the state machine are in ../SKILL.md. This playbook is the detail for this phase.

The reader has no chat history: a fresh session must act from the text alone.

**Context pointers.** A pointer is a reference held in the reader's context that names out-of-context material and the branch that should trigger reaching it. This skill's `SKILL.md` is the always-loaded contract; each `phases/` and `methods/` file is reached through a pointer whose wording says what the file is and when to read it. Front-load the leading word, give one trigger per genuinely distinct branch, and cut identity the body already carries. A must-have target behind a weak pointer is a variance bug: sharpen the wording before inlining the material.

**Two loads.** Context load is the always-loaded cost: the contract, a flag, an `AGENTS.md` line. Cognitive load is the human's cost: which document exists and when to reach for it. Material reached through a pointer escapes context load at the price of the pointer's line; material with no pointer rides entirely on cognitive load. Spend the human's load where judgement matters, not on remembering files the agent should find.

**Information hierarchy.** Put the one meaning in exactly one home. Do not restate what the script, `--help` or the layout already says; write the unwritten convention, the reason and the gotcha. Number procedures of three or more steps; end every step on a completion criterion; state when every deferral lands; phrase rules positively (pair a hard prohibition with what to do instead); use one term per referent; end the plan on a next action startable in under two minutes.
