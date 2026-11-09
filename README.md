# Personal agent skills

The skills in this repository are authored in `~/.agents/skills` and mirrored
here. That directory also holds third-party skills; only the personal set in
`personal-skills.json` is published.

## Mirror

```sh
uv run --no-dev --project . python scripts/sync-skills.py          # source -> repo
uv run --no-dev --project . python scripts/sync-skills.py --check  # fail on drift
```

`--dry-run` prints the changes without writing. The mirror is exact: a file
removed from a personal skill is removed from this repository too. Vendor
skills and other top-level directories are untouched.

## Pre-push gate

Enable the committed hook once per clone:

```sh
git config core.hooksPath .githooks
```

The hook runs `--check` and blocks a push when a personal skill in
`~/.agents/skills` is not reflected here.

## Adding a personal skill

1. Create it in `~/.agents/skills/<name>` with a `SKILL.md` whose `name`
   frontmatter matches `<name>`.
2. Add `<name>` to `personal-skills.json`.
3. Run the mirror and commit the result.
