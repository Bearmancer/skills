# Windows Task Scheduler, measured

Shapes verified on Windows 11 with Store pwsh 7.6.9 and the `ScheduledTasks` module (2026-11-07/08), by registering scratch tasks, reading them back, exporting the XML, and unregistering them. The cmdlets work from pwsh 7; `schtasks.exe` is not needed.

## Register a daily task that runs a script

```powershell
$action = New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'pwsh.exe') `
    -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\path\to\script.ps1'
$trigger = New-ScheduledTaskTrigger -Daily -At '09:00AM'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances Parallel -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'My Task' -Action $action -Trigger $trigger -Settings $settings -Principal $principal
```

## The traps, each measured

| Trap | What happens | Do this instead |
| --- | --- | --- |
| `-ExecutionTimeLimit 'PT0S'` | `Cannot convert value "PT0S" to type System.TimeSpan` — the parameter is a `TimeSpan` | `-ExecutionTimeLimit ([TimeSpan]::Zero)`, which registers as `PT0S` = no limit |
| Assigning `''` to `$settings.ExecutionTimeLimit` after creation | Reads back as the `PT72H` default; the assignment does not stick | Pass the `TimeSpan` to `New-ScheduledTaskSettingsSet` |
| `$settings.AllowStartIfOnBatteries` | Property does not exist; the switches set `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries` (both `$false`) | Assert the two `Disallow*`/`StopIfGoing*` properties |
| `$settings.MultipleInstances` | Enum printing `Parallel` | Compare with `'Parallel'` |
| `$task.Principal.Id` | Reads back as the literal `Author`, never the username or SID | Prove the run-as user from `Export-ScheduledTask` XML `<UserId>S-1-5-...</UserId>` against `[Security.Principal.WindowsIdentity]::GetCurrent().User.Value` |
| `-At '09:00AM'`, then matching `StartBoundary` as text | In memory it is `...T03:30:00Z`; once registered it is `...T09:00:00+05:30` on a UTC+5:30 host | Parse `[DateTimeOffset]` and compare `.ToLocalTime().ToString('HH:mm')` |
| `Get-ScheduledTask` for a task that is not there | Throws a CIM error containing `No MSFT_ScheduledTask objects` | Catch it and report "not registered"; do not let the raw CIM text stand in for the reason |
| `New-ScheduledTaskPrincipal -UserId X` in memory | `Id` and `Name` are empty before registration | Register first, then prove identity from the exported XML |

## Read back what was registered

```powershell
$task = Get-ScheduledTask -TaskName 'My Task' -TaskPath '\'
$task.State                                  # Ready
$task.Actions[0].Execute                     # absolute pwsh.exe
$task.Actions[0].Arguments                   # round-trips verbatim
$task.Triggers[0].CimClass.CimClassName      # MSFT_TaskDailyTrigger
$task.Settings.ExecutionTimeLimit            # PT0S
$task.Settings.StartWhenAvailable            # True
$task.Settings.MultipleInstances             # Parallel
(Get-ScheduledTaskInfo -TaskName 'My Task').LastTaskResult
Export-ScheduledTask -TaskName 'My Task' -TaskPath '\'   # <UserId> SID lives here
```

A missing task makes `Get-ScheduledTask` throw rather than return `$null`; a never-run task returns `LastTaskResult` `267009`/"has not yet run" style values, so assert `0` only after a real `Start-ScheduledTask` run.

## Working directory

`New-ScheduledTaskAction` has no `-WorkingDirectory` in the module shipped with pwsh 7.6.9. A task therefore starts in `C:\Windows\System32`; a script that needs a repo either `Set-Location` itself first or resolves every path absolutely.
