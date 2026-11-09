---
tags: [plan-rigorously]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash, AskUserQuestion, Agent]
---

plan-rigorously: plan upgrading the Python `urllib3` library to version 2. My notes say version 2 removed the Retry helper, which I want to rely on to simplify code. Verify that claim before planning around it.
