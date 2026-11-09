# Work-audit handoff

This section is the single home for work-audit routing; work-audit and its
indices only point here.

work-audit already finds the candidates (index 4 stale artifacts, index 15
empty dirs) and records their `safety` facts. Do not let it delete them ad
hoc: convert the report into a purge manifest and let this engine do the
deleting.

```powershell
uv run <skill>\scripts\from-work-audit-report.py --report "<records>\<repo>-<hash>\<tree>\report.json" --repo "C:\path\to\repo"
uv run <skill>\scripts\purge.py --manifest "<written manifest>"            # plan
uv run <skill>\scripts\purge.py --apply --manifest "<written manifest>"    # journal + residue
```

Mapping: `4.zero_byte`/`tmp_bak_orig`/`pycache`/`ignored_untracked_old` and
`15.empty_dirs` become PURGE rows, each reason carrying the report's safety
facts; `--include-duplicates` turns index 16 pairs into OWNER rows (first
path, keeper named in the reason), because a duplicate needs a human keeper
choice. Routing runs 4, then 15, then 16, ascending: every row is stamped
with its index, entries sort by index then path, and the adapter echoes the
order line (`order: 4 -> 15 -> 16`). The canonical ordered index table
(1..21: name, kind, purge routing) lives in work-audit's
`references/indices.md`.

`--home-config` also routes omo's generated state (#216). The repo manifest
drops every row outside the repo, so this writes a second manifest, `Purge
Manifest - work-audit home-config - <date>.json`. Its root is the report's
`~\.omo` config root (index 4 `config_root_entries`), never the home folder,
a drive root or a linked folder. Plan and apply it with `--root <that .omo>`.
The rules, settled by the owner on 2026-10-25:

- **Rows.** Each child of `evidence`, `drafts`, `tmp`, `reports`, `plans`,
  `ulw-loop` and `wayfinder` is a row; the subdirs themselves stay. Loose
  `*.bak`/`*.old` files at the omo root are rows too. Every reason carries
  the row's safety facts (files, newest mtime).
- **Verdicts.** PURGE for `evidence`, `drafts`, `tmp`, `reports` and the
  loose backups. OWNER for the executor-adjacent `plans`, `ulw-loop` and
  `wayfinder` (boulders, ledgers, waves), which need a per-path `--override`.
- **Age gate.** A row whose newest mtime falls inside 7 days
  (`--home-age-days`) stays out of the manifest and is printed as `held`, so
  plan review shows it before anything lands.
- **Engine files.** `Purge Manifest - *` and `Purge Journal - *` under
  `reports` are never routed.
- **Protected list unchanged.** `memory`, `agent\{sessions,projects,skills,
  extensions,runtime}`, `binary-runtime` and `omo.jsonc` are never routed. The
  engine refuses them even when a hand-built row names them.

When the engine scans the omo root after apply, it can report residue that
its own rules match, such as `.omo\logs`, and exit 2. Read that exit as a
list of further candidates, not as a failed delete.
PY