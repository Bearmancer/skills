# Dynamic proof

Static review finds intent; the sandbox finds behaviour. Run the bundled
harness:

```powershell
uv run <skill>\scripts\purge-guards.py --script <path-to-purge-script> --apply-probes
```

It builds a throwaway fixture under `%TEMP%\PurgeGuardTest\<timestamp>` (or
`--workspace`) containing a protected tree, a personal file, an empty dir, a
`.bak`, a `node_modules`, a build dir inside a fake repo, a junction into the
keep tree, and a manifest carrying an outside-root path, a wildcard, the root
itself, a drive root and an OWNER row. Then it drives the script through
plan, apply, locked, and budget-exhausted runs and prints one
`PASS`/`FAIL`/`UNSUPPORTED` line per invariant.

The harness starts each probe as its own process with an argument list (paths
with spaces arrive whole), captures stdout and stderr, and kills a probe that
runs past `--timeout-seconds` with its process tree. A `.py` target runs on
the harness's interpreter with `--root`-style flags; a `.ps1` target runs
under `pwsh -NoProfile -File` with `-Root`-style flags. Without
`--apply-probes` only the plan probes run.

A harness that only ever passes proves nothing. Run it once against
`scripts/fixtures/lax-purge.py`, a script that speaks the manifest contract
and skips every guard: it must come back with FAILs (protected row deleted,
no journal, junction ancestor followed, missing verdict deleted). Treat a
negative control that passes as a harness bug, not as a safe script.

The harness assumes a manifest contract: root, manifest, apply, override,
out-dir, max-minutes and lock-file options (`--root` ... for Python, `-Root`
... for PowerShell). When a script speaks another interface, rebuild the same
fixture by hand and drive it the way its user would — the fixture is the
contract, not the flag names. `UNSUPPORTED` is an honest result; never turn
it into a PASS.

What the sandbox proves, and why each probe exists:

- **Parse gate** — a script with parse errors is reported and never executed; a crash must not pass for a refusal.
- **Contract gate** — a script that never references the root and manifest options (`--root`/`--manifest`, or `$Root`/`$Manifest`) is not executed at all: such a script ignores the fixture root, and even a "plan" call can delete.
- **Refusal evidence** — a non-zero plan exit counts only when the output names a refusal reason; otherwise it is a crash, not a guard.

- **Protected survival** — `.omo\memory` style path in the manifest; after apply the tree still holds its file.
- **Protected refusal** — a manifest that contains only a protected row exits non-zero and leaves the tree intact, so the refusal is proven on the delete path and not only on plan.
- **Keep survival** — a personal file next to the targets; it is still there.
- **Outside-root refusal** — a path under another root is refused, not resolved.
- **Wildcard refusal** — a `*` in a manifest path is refused.
- **Root and drive refusal** — the root itself and `C:\` are refused.
- **Owner gate** — an OWNER row is refused without an override.
- **Junction discipline** — the junction is gone; the directory it pointed at still holds its contents.
- **Junction ancestor** — a row whose path is reached through a junction (`root\hop\link\file`, `link` being a junction) is refused; following it would delete outside the root.
- **Missing verdict** — a manifest row with no `verdict` field is refused, never defaulted to PURGE.
- **Cascade** — emptied parents disappear, so the next scan finds no shells.
- **Residue zero** — the post-purge scan returns 0 candidates.
- **Live lock** — a second instance with a live owner lock exits non-zero and deletes nothing.
- **Budget** — a zero-minute budget aborts before the first delete with a journalled reason.
PY