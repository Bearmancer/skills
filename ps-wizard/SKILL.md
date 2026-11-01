---
name: ps-wizard
description: Generate admin-ready pwsh 7 one-shot wizards as single .ps1 files with self-elevation, goal-sufficiency gate, blocker force-close, screen+file logging, Desktop output, backup, auto-uninstall, and max tracing. Use this skill whenever the user asks for a Windows setup, install, migration, or admin wizard, mentions pwsh, PowerShell script, .ps1, self-elevating script, or wants a one-shot Windows automation — even if they do not say "wizard". Also use it to diagnose a wizard run that failed, skipped a prompt, or froze until a key was pressed.
---

# PS-Wizard

A **ps-wizard** is a single `.ps1` script, run under **pwsh**, that walks a human step by step through a one-shot Windows admin procedure the agent cannot perform itself: installs, setup, migrations, cutovers, dashboard steps only a human can click through. It self-elevates to admin, checks goal sufficiency before starting, force-closes apps that block its task, logs to screen and to a file, drops its output on the Desktop, takes one quick backup first, auto-uninstalls anything it newly installed, and traces maximally so any failure is diagnosable after the fact.

The delightful UX is already solved by `template.ps1`: stage framing with progress counters (`Invoke-Step`), colored instruction lines (`Write-Say` / `Write-Step` / `Write-Note` / `Write-Warn`), URL opening (`Open-Url`), human-action gates (`Wait-HumanAction`, `Confirm-Choice`), visible and secret prompts (`Read-PlainValue`, `Read-SecretValue`), persisted-value writes (`Write-PersistedValue`), native programs with a timeout and exit code (`Invoke-NativeProcess`), Windows optional features through `dism.exe` (`Get-OptionalFeatureState`, `Disable-OptionalFeature`), isolated goal checks (`Test-WizardGoal`), and a closing summary that reports failures (`Show-Summary`). **Your job is only to scope the procedure and author its stages.** The library above the `STAGES` marker is identical in every wizard; that consistency is the point: never hand-edit it.

A wizard is ephemeral by default: built for one run, saved to a scratch or `scripts/` path, deleted when the job's done. Commit it only when the user wants a repeatable setup path that should live in the repo.

## Rules

- **`.ps1` only (a).** Every generated wizard is one `.ps1` file. Never emit `.sh`, `.bash`, or `.bat` content.
- **Targets pwsh (b), requires pwsh 7.x (h).** Every generated file starts with `#Requires -Version 7.0`, which is the whole host check. No step hands work to Windows PowerShell 5.1: no `powershell.exe`, no `-UseWindowsPowerShell` compatibility layer, which runs a hidden 5.1 process. In the loom repo, `tests/test_ps_wizard_pwsh7.py` checks the template for both.
- **Analyzer-clean (c).** Every generated wizard must pass `Invoke-ScriptAnalyzer` at Error and Warning severity with zero findings, except the single justified `Write-Host` suppression below.
- **Colored text via Write-Host (d), tolerated via one justified suppression (e).** Colored say/step output uses `Write-Host -ForegroundColor` only, and the template carries a single narrow `Invoke-ScriptAnalyzer` suppression of just `PSAvoidUsingWriteHost` with a justification comment. No other `Write-Host` use, no other suppressed rule.
- **Consult powershell-expert (f).** Before authoring stages, consult the `powershell-expert` skill for cmdlet syntax, quoting, parameter design, and error-handling patterns, and cite what you applied. Quoting rule: single-quote static literals, double-quote only with interpolation (`$()` subexpressions).
- **Subagents are Muse Spark (q).** Every subagent spawned while generating a wizard uses Muse Spark.

## Setup

How to scope and shape the generated wizard's setup section:

- **No Enter-pauses except human-action gates (g).** The wizard never pauses for pacing. `Wait-HumanAction` (`Read-Host`) appears only where the human must physically act (click something in a browser, plug in a device, confirm a reboot). Pacing pauses are forbidden. The one library exception is the closing hold: the elevated window closes as soon as the script ends, and without the hold the summary or failure would vanish unread.
- **No exposed cmdlet parameters or flags (g).** The generated `.ps1` exposes no `param()` block and no switches/flags to the human. All choices are answered in-flow via `Read-PlainValue` / `Read-SecretValue` / `Confirm-Choice`. The human double-clicks or runs one command and answers prompts.
- **Single quick backup (g).** The generated wizard takes exactly one quick backup before stage 1 (registry export, config-file copy, or restore point — whichever the procedure risks), records the backup path in `$script:BackupPath`, and announces it in the closing summary. Never more than one backup step.

## Runtime contract

Every generated wizard obeys this contract; trace each item to the template:

- **Always runs as admin (i).** The wizard self-elevates and relaunches at start when not elevated. No manual "run as admin" instruction.
- **Force-stop blockers auto-integrated (j); force-close apps that block the task (m).** Each stage declares its blocker processes/services; `Close-BlockingProcess` lists the running ones and asks once before force-closing. Pass `-NoUnsavedWork` only for processes that hold no user data (updaters, tray agents). Never set `$ConfirmPreference = 'None'`.
- **Always logs to screen and to a file (k).** `Start-Transcript` plus an explicit per-stage log file; secrets are never written to either log.
- **Wizard output created on the Desktop (l).** All artifacts, reports, and the log file land under the user's Desktop path. No other output directory.
- **Auto-uninstall anything newly installed (n).** The wizard records everything it installs and removes it when a stage throws, unless the goal of the wizard was the install itself. A failed goal check does not uninstall: the summary lists it and the installs stay for the human to judge.
- **Maximize tracing events (o).** `$VerbosePreference = 'Continue'` and `$DebugPreference = 'Continue'`; every stage emits `Write-Verbose`/`Write-Debug` with state so failures are diagnosable post-run.
- **Check goal sufficiency before starting (p).** A goal-sufficiency gate runs before stage 1: required values, privileges, network, and disk preconditions are verified, and the wizard refuses to start with a precise missing-items message rather than failing halfway.
- **Report only what this run proved.** Every goal is one `Test-WizardGoal` in the last stage. "Setup complete." and exit 0 appear only when at least one check ran and all passed; otherwise the summary lists the failures and the wizard exits 1. Run outputs land in a fresh `WizardOutput\<stamp>` folder, so an earlier run's files never satisfy a check.

## Authoring rules from failed runs

The 2026-10-26 Reset-PC-Wizard run failed at stage 8 and wrote no report; the findings are summarized in https://github.com/Bearmancer/loom/issues/365. The template now fixes the library defects. These rules cover the stage code it cannot fix. Most of them come from one cause: the stage code relied on hidden state (which pwsh host is running, error preference, what is already in the input buffer, PATH, what earlier runs left behind) as if it were fixed. Make that state explicit and check it.

- **Never kill or delete the wizard's own process tree.** Before the blocker stage, walk the wizard's ancestor processes (`Win32_Process.ParentProcessId`). Refuse to start when an ancestor is an app the wizard will close or whose config it will delete (an editor, terminal agent or IDE). Otherwise stage 1 kills the host and stage 2 deletes its config. `Win32_Process.Name` carries `.exe`, so anchor the name regex with `(\.exe)?$`; without it the guard never matched.
- **A failed stage fails the run.** Let a stage throw. If a stage must catch its own error to continue, record a failure the summary lists and the exit code reflects, and skip every later stage that depends on it. A caught-and-logged stage error that still ends in exit 0 hides the failure.
- **Every removal has a check for every place it removed from.** If a stage removes the uninstall entry, the program folder and the config folders, verification checks all three, not just the uninstall entry.
- **System cmdlets that fail in pwsh 7 go to their native exe, not to 5.1.** Check every system module in the exact pwsh that will run the wizard; a module that loads is not proof that it works. As measured on Store pwsh 7.6.9 (2026-10-27):
  - *Optional features:* `Get-WindowsOptionalFeature` failed with `Class not registered` or hung. Use `Get-OptionalFeatureState` and `Disable-OptionalFeature`, which call `dism.exe /Online /English`, read `State : <value>`, and treat exit 3010 as "reboot needed".
  - *Provisioned Appx (for new users):* `dism.exe /Online /Get-ProvisionedAppxPackages` and `/Remove-ProvisionedAppxPackage /PackageName:<full name>`. They do not touch packages already installed for a user.
  - *Per-user Appx (`Get-AppxPackage`, `Remove-AppxPackage`):* the Appx module does not load in pwsh 7 ("Operation is not supported on this platform"), because .NET 5+ removed built-in WinRT ([Microsoft Learn](https://learn.microsoft.com/dotnet/core/compatibility/interop/5.0/built-in-support-for-winrt-removed)). Microsoft's only supported route is the 5.1 compatibility layer, which is banned here ([module compatibility](https://learn.microsoft.com/powershell/windows/module-compatibility)). The WinRT `PackageManager` API through a C#/WinRT projection (`FindPackagesForUser`, `RemovePackageAsync`) is the documented native API, but it is unproven from pwsh 7. Until it is proven, make per-user Appx removal a human-action gate: open `ms-settings:appsfeatures` with `Open-Url`, name the app, and verify by a file or uninstall-entry check, not `Get-AppxPackage`.
- **A query failure is not an absence.** Never `-ErrorAction SilentlyContinue` on a query whose empty result means "removed" or "nothing to do". Let it throw; `Test-WizardGoal` turns the throw into a failed check.
- **A check proves the goal state.** Test `State -eq 'Disabled'`, not `State -ne 'Enabled'`: a missing or failed query also passes the second. Each check computes its own data inside its scriptblock; a variable set by one check is not there for the report if that check threw.
- **Delete exact targets only.** Build delete lists from exact known paths or uninstall-entry locations, never a broad glob: `C:\Python*` also matched `C:\PythonProjects`. Print the resolved list before deleting. Do not prune a PATH entry, shortcut or file association just because its target is missing right now: it may be on an offline share or an unplugged drive. Delete a shortcut only when its target is an exact path the wizard removed, never because its name matches an app (`AnyDesk*.lnk`), which a portable copy or the user's own shortcut also matches. Judge any delete stage with the `purge-safety` skill.
- **Uninstall before deleting leftovers, then rescan.** Package managers recreate the folders you just removed (`bun remove -g` did). Run the uninstall commands, delete the leftovers, then rescan with the same discovery function rather than rechecking the original list.
- **Deduplicate objects by key.** `Sort-Object Scope, Entry -Unique`, never `Select-Object -Unique` on objects.
- **Native programs get a timeout and an exit-code decision.** Run them with `Invoke-NativeProcess`. Use the vendor's documented silent switch; never append `/S` to a command that lacks one, since only NSIS installers read it. Decide which exit codes count as success (MSI 3010 and 1641 mean reboot needed, not failure).
- **Verify downloaded code before running it.** A downloaded installer or script runs only after its Authenticode signature (`Get-AuthenticodeSignature`, status `Valid`, expected signer) or a SHA-256 published apart from the download matches. Printing a hash checks nothing.
- **Read existing config before writing it.** Take a source the machine already declares instead of hardcoding one: a hardcoded marketplace URL clashed with `extraKnownMarketplaces.omc` in `~/.claude/settings.json` and the plugin never installed.
- **Register every install.** Call `Register-InstalledSoftware` right after each install, or the auto-uninstall has nothing to remove.
- **Set the reboot flag only when something changed.** Mark a reboot when a disable or install reports `RestartNeeded`, not unconditionally.
- **Pass values to child processes as arguments, not text.** Never splice a path or pattern into a script string (`.Replace('__PATH__', $p)`); an apostrophe in the Desktop path breaks it. Use `Invoke-NativeProcess -ArgumentList`, and put temp-file cleanup in `finally`.
- **Say only what is true.** The banner counts the manual gates rather than claiming the run is "fully automated". The summary prints an output path only after `Test-Path` confirms this run wrote it.

## Diagnosing a failed run

Read the transcript (`wizard-<stamp>-transcript.log` on the Desktop) alongside the explicit log (`wizard-<stamp>.log`). When the explicit log stops early, the failure is in the transcript. Symptoms seen in the field and their causes:

| Symptom | Cause |
|---|---|
| Explicit log holds only `Wizard started.`; error only in the transcript | A `Write-Error` in a catch under `Stop` ended the fatal handler |
| A "press ENTER when done" gate opened and passed in the same second | An Enter buffered during an earlier stage satisfied `Read-Host` |
| Enter seemed dead until Space or Esc was pressed; output paused mid-install until a key | QuickEdit selection started by a click after a GUI installer took focus |
| `Class not registered`, or a hang, on a DISM cmdlet | Store pwsh cannot run the DISM module; use `dism.exe` |
| Paths "removed" but still there at verification | A package-manager uninstall recreated them after the delete |
| Only one of many dead entries cleaned | `Select-Object -Unique` collapsed distinct objects |
| "Setup complete." with exit 1, or a report path that does not exist | A summary printed without consulting the results (fixed in the template) |

## Process

### 1. Scope the procedure

Work out every manual step the human must take and every value captured along the way. Read the machine first, don't ask cold:

- For setup: installed programs, registry keys, machine/user environment variables, config files, and scheduled tasks the wizard will read or write (each value's sink is registry, env var, or file — never `.env`).
- For a migration or transition: the current state, the target state, and the irreversible actions between them. Name the blocker apps and the single backup the wizard will take.

Then show the user the ordered list of stages and the values each produces, and confirm: they may add, drop, or reorder.

**Done when:** every stage is named in order, and for each captured value you know (a) where the human gets it, (b) where it's written (registry key, env var, config file, or nowhere; some stages are pure actions), and (c) whether it's secret (hidden entry via `Read-SecretValue`) or public.

### 2. Map each stage's journey

For each stage, write the precise path a human follows: which URL to open (`Open-Url`), what to do there, where a value is shown, which persisted sink it fills: e.g. "Dashboard → Developers → API keys → Reveal test key → copy → stored to machine env var". Where you don't actually know the current UI or the exact command, say so and ask the user or check the docs: never invent steps that may not exist. Mark the human-action gates (the only places `Wait-HumanAction` may appear) and the blocker apps each stage force-closes.

**Done when:** every stage traces to concrete instructions a stranger could follow.

### 3. Author the wizard

Copy `template.ps1` to the target path. Below the `STAGES` marker, replace the example stages with one `Invoke-Step` per step, in dependency order, and replace the placeholder goal check (it fails on purpose) with one `Test-WizardGoal` per goal. Use the library helpers: `Invoke-Step`, `Write-Say`/`Write-Step`/`Write-Note`/`Write-Warn`, `Open-Url`, `Read-PlainValue`/`Read-SecretValue`, `Write-PersistedValue`, `Get-ExistingValue`, `Wait-HumanAction`/`Confirm-Choice`, `Close-BlockingProcess`, `Invoke-NativeProcess`, `Register-InstalledSoftware`, `Get-OptionalFeatureState`/`Disable-OptionalFeature`, `Test-WizardGoal`. Pass `Show-Banner -TotalStages` the number of stages you wrote.

Hold the bar the template sets: open the URL before asking for its value, use `Read-SecretValue` for anything secret (never log its value), `Write-PersistedValue` for every persisted value, and `Confirm-Choice` before any irreversible action. Each `Invoke-Step` clears the screen so only the current step is visible: keep a stage to one focused task so nothing the human needs scrolls away. Keep the goal-sufficiency gate, admin self-elevation, backup step, transcript+log, Desktop output, and auto-uninstall wiring intact. Don't touch the library above the marker. Don't add a `param()` block or pacing pauses.

### 4. Verify and hand off

- Parse check: the pwsh parser reports 0 errors on the file.
- `Invoke-ScriptAnalyzer` at Error and Warning severity: zero findings except the single justified `PSAvoidUsingWriteHost` suppression.
- Don't run it end-to-end yourself: it opens browsers, elevates, and blocks on human input. Trace it statically instead: every value from step 1 is captured and lands where step 1 said, and every persisted sink name matches its target.
- Grep the stage code for the failure patterns above: `Write-Error`, `Select-Object -Unique`, `SilentlyContinue` on a query, `-ne 'Enabled'`-style checks, `Start-Process -Wait`, `Remove-Item` on a wildcard, and installs with no `Register-InstalledSoftware`. Each hit is fixed or justified.
- Run each system query the stages rely on once, read-only, in the exact pwsh that will run the wizard (`(Get-Process -Id $PID).Path`), elevated if it needs admin (`dism.exe` exits 740 without it).
- Tell the user how to run it (`pwsh -File <script>` from an admin-capable shell; it self-elevates). If it's a repeatable setup path, commit it and link it from the README so the next person runs the script instead of asking an AI.

## Must NOT

- No bash content: no `.sh`, no `bash`, no `shellcheck`, no `chmod`, no `tput`, no `.env` upserts, no `gh secret`/`gh variable` writes.
- No edits to the upstream CLI-managed `wizard` skill, ever.
- No Enter-pauses for pacing; `Wait-HumanAction` only at human-action gates.
- No exposed cmdlet parameters or flags on the generated wizard.
- No plaintext secret logging: secret values never reach screen, transcript, or log file.
- No end-to-end live run of a generated wizard as proof (human-input and elevation blocker; static trace instead).
