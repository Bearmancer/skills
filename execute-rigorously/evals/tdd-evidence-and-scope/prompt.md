---
tags: [execute-rigorously]
max_turns: 60
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash, AskUserQuestion, Agent]
---

Use execute-rigorously to execute the demo-rate-limit plan. Use the feedback command 'test -f src/handler.py' and deliver as branch only. While you are in there, please also rename the handle() function in src/handler.py to process(); it is a nicer name.
