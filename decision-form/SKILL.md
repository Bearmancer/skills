---
name: decision-form
description: Clickable web page that collects the user's decisions through granular tick boxes with an inline remedial explanation for every question and every box, white and dark mode, no limit on questions or boxes, answers saved to a secret gist and served on the tailnet. All form text is written with the ultracave skill. Use whenever the user asks for a decision form, questionnaire, interactive page, interactive gist, tick boxes or a web page to answer questions, dismisses the question tool and wants to click instead, or when many decisions are waiting on the user, even if they never say "form".
---

# Decision form

User clicks. Agent asks only real decisions.

## Voice

Load `ultracave` skill first. Form text and chat: ultracave only.

- Ultracave switches to plain prose for questions. Not here.
- Ultracave floor stays: keep not, never, no, only, except, numbers, error strings.
- Fragment with two readings: full sentence.

## 1. Before asking

- Facts: agent's job. Look up. Ask only what user must choose.
- Run or read proof for each claim a question rests on. No proof: say so in `explain`.
- Earlier note asked something: answer it first.

## 2. Write `questions.json`

Put in durable form folder (project or EPIC folder, never temp).

```json
{
  "title": "Search tool decisions",
  "questions": [
    {
      "id": "tavily-command",
      "group": "Search tools",
      "title": "Tavily typed command",
      "text": "Keep it?",
      "explain": "Tavily: web search company. Skill can call it two ways: MCP (tool agent calls itself) or typed command `tvly search`. Today both listed. Example: MCP call fails, agent types `tvly search`.",
      "options": [
        { "label": "Keep typed command", "explain": "`tvly search` stays listed as second way.", "rec": true },
        { "label": "Remove typed command", "explain": "Only MCP stays. MCP fails: no Tavily search." }
      ]
    }
  ]
}
```

Optional: `group`, `rec`. Rest required.

No limit: questions, boxes per question, ticks. Never trim or merge to shorten.

### Granular, mandatory

- One box, one thing. No list, group or combo inside a box.
- Banned in `label`: `,` `;` `/` `+` `&` `|`, and, or, nor, plus, all, both, every, everything, either, each, rest, etc. Script refuses form.
- Script sees words only. Agent checks meaning: "Vendor backups", "Safety checks" hide groups. One box per member.
- Never "Keep all" or "Remove all". User ticks each.

### Remedial `explain`, every question and every box

- Reader: zero context, no files open.
- Define each term at first use. No metaphor, no codename. "Two witnesses" failed: user could not tell what a witness was.
- Name real tool, file or page. Bare "the tool", "the tag", "the table" fails.
- Give one concrete example.
- Question `explain`: what thing is, what happens today, why asking.
- Box `explain`: what ticking does, what is lost. That box only.
- No card, decision-record or document references.

Never pre-tick. `rec` only prints "recommended". Page adds note field per question plus "Anything else".

## 3. Serve

```powershell
uv run <skill dir>/scripts/form.py check <folder>
& <skill dir>/scripts/host.ps1 up -Form <folder>
```

`up` creates secret gist once (`gist-id.txt`), runs server as scheduled task `decision-form-<port>`, runs `tailscale serve`, prints form link and gist link.

- Edited questions: run `up` again.
- `-Port` default 8765. One form per port.
- Needs pwsh 7, uv, `gh` logged in, tailscale.
- Secret gist is unlisted, not private: anyone with link can read it. Keep keys, passwords and personal data out of questions.
- Form link works only on user's tailnet devices.

Give user both links. Stop. Wait.

## 4. Test

Never press Submit on user's form: it writes answers user never gave.

Test copy: put `questions.json` in temp folder, `up -Form <temp> -Port 8766`, click, Submit, `read`, `down -Port 8766`, delete that temp gist with `gh gist delete <id> --yes`.

## 5. Read answers

```powershell
uv run <skill dir>/scripts/form.py read <folder>
```

Saves `answers.json`. Prints ticks, notes, open ids.

- No tick and no note: unanswered. Never apply recommendation.
- Note beats tick.
- Note without tick: answer or question. Read literally.
- "Huh", "what is X": explanation failed. Explain from zero, ask again. Never guess.
- Note says find something out: find it, report it, then ask what remains.
- Ticks conflict, or tick conflicts with note: ask. Never pick.
- Next round: new folder, only open items.

## 6. Close

```powershell
& <skill dir>/scripts/host.ps1 down
```

Gist stays.
