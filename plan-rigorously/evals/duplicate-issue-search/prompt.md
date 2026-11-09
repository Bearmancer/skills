---
tags: [plan-rigorously]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash, AskUserQuestion, Agent]
---

plan-rigorously: publish the finished plan in .rigor/plans/ to GitHub. Use a dry run first. The gh command here is a fake in ./fakebin; put that directory first on PATH. The working folder was just restored from backup, so run start demo-rate-limit --rebaseline first.

Input files: fakebin/gh, .rigor
