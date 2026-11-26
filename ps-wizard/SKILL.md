---
name: ps-wizard
description: "Use for any step the agent cannot do itself (elevation, a click, a physical action, a go-ahead before an irreversible run), or when asked for a Windows setup, install or admin wizard, a .ps1 wizard, or a wizard run failed or froze. Builds short .ps1 wizards on the PsWizard module: unattended runs, hidden secrets, backup, goal checks, rollback."
---

# PS-Wizard

A wizard is one `.ps1` under pwsh 7 for a procedure needing admin rights or a human action. A job with neither is a plain script: write the smallest `.ps1`, run it on real-sized input, lint it, done. Shell commands failing or quoting wrong: see `shell-gotchas` first. Cmdlet syntax and quoting: consult `powershell-expert`.

Deliver it unasked: any step you cannot do yourself (elevation, a human click or physical action, a human go-ahead before an irreversible live run) becomes a wizard, never a list of manual instructions in chat.

Wizards run start to finish with no pacing pauses, whether the owner or the agent starts them. The only stops are human-only input: a secret, a typed value, or a hands-on step; an interactive run also ends with one ENTER to close the window (`Stop-WizardRun`; skipped when input or output is redirected, as in agent launches). Decisions are settled before the run via the question tool, never mid-run.

## Skeleton

Every wizard is exactly this shape with its steps filled in. No comments, no `param()` block.

```powershell
#Requires -Version 7.0
#Requires -RunAsAdministrator
Import-Module "$HOME\.agents\skills\ps-wizard\PsWizard.psm1" -Force

$code = Start-WizardRun -Title '<procedure>' -Steps <n>
try {
    Assert-WizardPrerequisite -Path @('<paths the job needs>')
    Invoke-WizardStep 'Back up'
    Invoke-QuickBackup -Path @('<only the sinks a step writes>')
    Invoke-WizardStep '<step>'
    # ... one Invoke-WizardStep per step, dependency order ...
    Invoke-WizardStep 'Verify'
    Test-WizardGoal '<goal>' { <prove the goal state; last output exactly $true> }
    $code = Complete-WizardRun
}
catch { $code = Complete-WizardFailure $_ }
finally { Stop-WizardRun }
exit $code
```

## Toolbox (PsWizard.psm1)

Never read the module into context; `Get-Help <function> -Full` when a detail is needed.

- Run: `Start-WizardRun`, `Invoke-WizardStep`, `Stop-WizardRun`, `Complete-WizardRun` (exit code), `Complete-WizardFailure` (logs, uninstalls registered installs, exit 1)
- Output: `Write-WizardStatus -Level Info|Step|Ok|Warn|Fail` (screen + log), `Write-WizardLog` (log only)
- Human-only: `Read-SecretValue` (hidden, returns SecureString), `Read-PlainValue` (ENTER keeps current), `Wait-HumanAction -Url` (hands-on step)
- Values: `Get-ExistingValue`, `Write-PersistedValue -Sink Environment|Registry|File` (accepts SecureString; logs names only)
- Work: `Invoke-QuickBackup`, `Invoke-NativeProcess` (timeout + exit code; absolute paths), `Close-BlockingProcess` (`-NoUnsavedWork` or prior-consent `-AllowUnsavedWorkLoss`), `Get-OptionalFeatureState` / `Disable-OptionalFeature` (dism.exe), `Register-InstalledSoftware`
- Checks: `Assert-WizardPrerequisite`, `Test-WizardGoal`, `Add-ManualFollowUp`

## Authoring

1. Scope: read the machine first (installed programs, registry, env vars, configs, tasks). Show the owner the ordered stages and each captured value's sink and secrecy; confirm before writing.
2. Map each stage's journey: exact URL, exact action, where the value lands. Never invent UI steps; check docs or ask.
3. Fill the skeleton. One backup of exactly the sinks written. Register every install right after it. A failed goal check does not uninstall; only a thrown error does.
4. Verify: `pwsh -File scripts/verify-wizard.ps1 -Path <wizard>` — fix every FAIL. Then exercise each non-elevated, non-human stage command in a scratch pwsh on real-sized input; trace the rest statically and say which ran for real.

Judgement rules the verifier cannot check:

- Refuse to start when an ancestor process is an app the wizard closes or whose config it deletes (walk `Win32_Process.ParentProcessId`; anchor names with `(\.exe)?$`).
- Per-user Appx removal is a human gate (`ms-settings:appsfeatures`); the Appx module does not load in pwsh 7. Verify by file or uninstall entry, never `Get-AppxPackage`.
- Uninstall before deleting leftovers, then rescan with the same discovery function; package managers recreate folders.
- Delete exact known paths only, never globs; print the resolved list first. A missing target is not grounds to prune a PATH entry or shortcut (offline share).
- Run a downloaded installer only after a Valid Authenticode signature from the expected signer, or a SHA-256 published apart from the download.
- Read existing config before writing it; never hardcode a source the machine already declares.
- Mark a reboot only when a disable/install reports it. Scheduled tasks: read `references/windows-task-scheduler.md` first.
- Never verify secret handling with a real secret; use a synthetic value of the same shape.

## Run and diagnose

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File <wizard>` (no arguments). The agent launches it itself (`Start-Process <pwsh> -File <wizard> -Wait`) and reads the run's `wizard.log`; this rig has no UAC prompt, so wizards run unattended. The owner can double-click: the `.ps1` open verb runs it under pwsh 7 and the window stays open on any outcome (the verb self-elevates silently, so admin wizards run even where the double-clicked window would otherwise run non-elevated and be refused). A wizard with `#Requires -RunAsAdministrator` needs an elevated terminal when run by hand; a double-click shows the refusal in the kept-open window. No run folder on the Desktop means the run died before step 1 — read the error there. Artifacts: `Desktop\ps-wizard\<name>\<stamp>\` — `wizard.log`, `transcript.log`, `backup\`, `output\`. When `wizard.log` stops early, the failure is in the transcript.

| Symptom | Cause |
| --- | --- |
| Gate passed in the same second it opened | Buffered ENTER (module clears the queue; report if seen) |
| Output frozen until Esc | QuickEdit click (module disables it; report if seen) |
| `Class not registered` on a DISM cmdlet | Use the module's dism.exe helpers |
| Paths "removed" but present at verification | Uninstall recreated them; rescan |

One wizard per procedure: edit the existing file, never a `-v2` or dated copy. Repeatable setup lives at `scripts\<name>-setup.ps1` in the owning repo (committed); ephemeral at `Desktop\ps-wizard\<name>\<name>.ps1`.
