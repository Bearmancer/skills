---
tags: [plan-rigorously]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash, AskUserQuestion, Agent]
---

Use plan-rigorously to plan a small CLI that parses a config, validates it, and then both runs a job and prints a report. The run and the report are independent of each other.
