#Requires -Version 7.0
Set-StrictMode -Version Latest

$script:Run = $null

function Assert-RunStarted {
    if (-not $script:Run) { throw 'Start-WizardRun must run first.' }
}

<#
.SYNOPSIS
    Appends a timestamped line to this run's wizard.log.
.DESCRIPTION
    Never throws, because the failure handler logs through it and a logging
    error must not replace the error being reported. Never pass a secret value.
#>
function Write-WizardLog {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Message)
    $line = "[$((Get-Date).ToString('s'))] $Message"
    Write-Verbose $line
    if (-not $script:Run) { return }
    try { Add-Content -LiteralPath $script:Run.Log -Value $line -ErrorAction Stop }
    catch { Write-Warning "Could not write wizard.log: $($_.Exception.Message)" }
}

<#
.SYNOPSIS
    Prints one short status line for a person watching, and logs it.
.PARAMETER Level
    Info (white), Step (cyan), Ok (green), Warn (yellow) or Fail (red).
#>
function Write-WizardStatus {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification = 'Colored status lines for a person watching the run; the log carries the detail.')]
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)][string]$Message,
        [ValidateSet('Info', 'Step', 'Ok', 'Warn', 'Fail')][string]$Level = 'Info'
    )
    $color = @{ Info = 'White'; Step = 'Cyan'; Ok = 'Green'; Warn = 'Yellow'; Fail = 'Red' }[$Level]
    Write-Host $Message -ForegroundColor $color
    Write-WizardLog "$($Level.ToUpper()): $Message"
}

function Disable-ConsoleQuickEdit {
    if ([Console]::IsInputRedirected) { return }
    if (-not ('PsWizard.Console' -as [type])) {
        Add-Type -Namespace PsWizard -Name Console -MemberDefinition @(
            '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern System.IntPtr GetStdHandle(int h);'
            '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern bool GetConsoleMode(System.IntPtr h, out uint m);'
            '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern bool SetConsoleMode(System.IntPtr h, uint m);'
        ) -ErrorAction Stop
    }
    $handle = [PsWizard.Console]::GetStdHandle(-10)
    $mode = [uint32]0
    if (-not [PsWizard.Console]::GetConsoleMode($handle, [ref]$mode)) { return }
    if ([PsWizard.Console]::SetConsoleMode($handle, ($mode -band -bnot [uint32]0x50) -bor [uint32]0x80)) {
        $script:Run.ConsoleMode = @{ Handle = $handle; Mode = $mode }
        Write-WizardLog 'Console QuickEdit and mouse selection turned off for this run.'
    }
}

function Restore-ConsoleQuickEdit {
    if (-not $script:Run -or -not $script:Run.ConsoleMode) { return }
    [void][PsWizard.Console]::SetConsoleMode($script:Run.ConsoleMode.Handle, $script:Run.ConsoleMode.Mode)
    $script:Run.ConsoleMode = $null
}

function Clear-PendingInput {
    if ([Console]::IsInputRedirected) { throw 'This step needs a person at the keyboard, but input is redirected.' }
    while ([Console]::KeyAvailable) { [void][Console]::ReadKey($true) }
}

<#
.SYNOPSIS
    Starts a run: run folder, wizard.log, transcript, QuickEdit off.
.DESCRIPTION
    Each run writes only into Desktop\ps-wizard\<wizard name>\<timestamp>\
    (wizard.log, transcript.log, output\, backup\), so files from an earlier
    run can never satisfy this run's checks.
.PARAMETER ScriptPath
    The wizard's own path; defaults to the calling script.
#>
function Start-WizardRun {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][ValidateRange(1, 64)][int]$Steps,
        [string]$ScriptPath = ''
    )
    if (-not $ScriptPath) {
        $ScriptPath = @(Get-PSCallStack | Where-Object { $_.ScriptName -and $_.ScriptName -ne $PSCommandPath } | Select-Object -First 1).ScriptName
    }
    $name = if ($ScriptPath) { [IO.Path]::GetFileNameWithoutExtension($ScriptPath) } else { 'wizard' }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $root = Join-Path ([Environment]::GetFolderPath('Desktop')) "ps-wizard\$name\$stamp"
    $script:Run = [pscustomobject]@{
        Name        = $name
        Title       = $Title
        Root        = $root
        Log         = Join-Path $root 'wizard.log'
        Transcript  = Join-Path $root 'transcript.log'
        Output      = Join-Path $root 'output'
        Backup      = ''
        Steps       = $Steps
        Step        = 0
        Values      = [ordered]@{}
        Secrets     = [System.Collections.Generic.List[string]]::new()
        Manual      = [System.Collections.Generic.List[string]]::new()
        Installed   = [System.Collections.Generic.List[object]]::new()
        Checks      = [System.Collections.Generic.List[object]]::new()
        ConsoleMode = $null
    }
    [void](New-Item -ItemType Directory -Path $script:Run.Output -Force)
    Start-Transcript -LiteralPath $script:Run.Transcript | Out-Null
    Write-WizardLog "Started '$Title' ($Steps steps) as $([Environment]::UserName) on $((Get-Process -Id $PID).Path) $($PSVersionTable.PSVersion)."
    Disable-ConsoleQuickEdit
    Write-WizardStatus $Title -Level Step
}

<#
.SYNOPSIS
    Ends a run: restores the console, stops the transcript, and keeps a window a
    person is watching open until ENTER. Call it in finally.
.DESCRIPTION
    The closing hold applies only to an interactive console with a real keyboard
    (someone double-clicked or ran the wizard in a terminal); when input or
    output is redirected, as when the agent launches the run, it exits at once.
    The run's log is created automatically by Start-WizardRun and its path is
    printed in the summary.
#>
function Stop-WizardRun {
    [CmdletBinding(SupportsShouldProcess)]
    param()
    Restore-ConsoleQuickEdit
    try { Stop-Transcript | Out-Null } catch { Write-Verbose "Transcript not running: $($_.Exception.Message)" }
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected) {
        Clear-PendingInput
        [void](Read-Host 'Press ENTER to close this window')
    }
}

<#
.SYNOPSIS
    Announces the next step as "Step n of m: name".
#>
function Invoke-WizardStep {
    [CmdletBinding()]
    param([Parameter(Mandatory, Position = 0)][string]$Name)
    Assert-RunStarted
    $script:Run.Step++
    Write-WizardStatus "Step $($script:Run.Step) of $($script:Run.Steps): $Name" -Level Step
}

<#
.SYNOPSIS
    Stops the run before step 1 when a required path is missing or the Desktop drive is short of space.
#>
function Assert-WizardPrerequisite {
    [CmdletBinding()]
    param(
        [string[]]$Path = @(),
        [ValidateRange(0, 1000)][int]$MinimumFreeGB = 5
    )
    $missing = @($Path | Where-Object { -not (Test-Path -LiteralPath $_) })
    if ($missing) { throw "Missing required paths: $($missing -join ', ')" }
    $drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot([Environment]::GetFolderPath('Desktop')).Substring(0, 1))
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    if ($freeGB -lt $MinimumFreeGB) { throw "Only $freeGB GB free on $($drive.Name):; need $MinimumFreeGB GB." }
    Write-WizardLog "Prerequisites met: $($Path.Count) path(s), $freeGB GB free."
}

<#
.SYNOPSIS
    Pauses for a hands-on step only a person can do, optionally opening a web page first.
.DESCRIPTION
    Use only for physical actions or decisions in a third-party UI. Keys typed
    earlier are discarded, so a stray ENTER cannot skip the step.
#>
function Wait-HumanAction {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)][string]$Instruction,
        [string]$Url = ''
    )
    if ($Url) {
        try { Start-Process $Url } catch { Write-WizardStatus "Open this page by hand: $Url" -Level Warn }
    }
    Write-WizardStatus $Instruction -Level Step
    Clear-PendingInput
    [void](Read-Host 'Press ENTER only after you have done this')
    Write-WizardLog "Human action confirmed: $Instruction"
}

<#
.SYNOPSIS
    Asks a person to type a value that is not secret; ENTER keeps -Current.
.DESCRIPTION
    The value is returned, never printed or logged.
#>
function Read-PlainValue {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory, Position = 0)][string]$Prompt,
        [string]$Current = ''
    )
    Clear-PendingInput
    $value = Read-Host ($Current ? "$Prompt (ENTER keeps the current value)" : $Prompt)
    if (-not [string]::IsNullOrWhiteSpace($value)) { return $value }
    if ($Current) { return $Current }
    throw "No value entered for: $Prompt"
}

<#
.SYNOPSIS
    Asks a person to type a secret; returns a SecureString.
.DESCRIPTION
    Read-Host -AsSecureString echoes only '*', and the typed value lives only in
    the returned SecureString. It never reaches the screen, wizard.log, the
    transcript or command history; only -Name is recorded. Pass the result to
    Write-PersistedValue, which converts it to text only for the instant of the
    write. An empty entry returns $null when -AllowEmpty is set (keep the
    current secret), and throws otherwise.
#>
function Read-SecretValue {
    [CmdletBinding()]
    [OutputType([securestring])]
    param(
        [Parameter(Mandatory, Position = 0)][string]$Prompt,
        [Parameter(Mandatory)][string]$Name,
        [switch]$AllowEmpty
    )
    Clear-PendingInput
    $secure = Read-Host $Prompt -AsSecureString
    if ($secure.Length -gt 0) {
        $script:Run.Secrets.Add($Name)
        Write-WizardLog "Secret entered: $Name"
        return $secure
    }
    if ($AllowEmpty) { return $null }
    throw "No secret entered for: $Name"
}

<#
.SYNOPSIS
    Reads the value currently stored for -Key, or $null when there is none.
#>
function Get-ExistingValue {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Key,
        [Parameter(Mandatory)][ValidateSet('Environment', 'Registry', 'File')][string]$Sink,
        [string]$Path = ''
    )
    try {
        switch ($Sink) {
            'Environment' { return [Environment]::GetEnvironmentVariable($Key, 'Machine') ?? [Environment]::GetEnvironmentVariable($Key, 'User') }
            'Registry' { return (Get-ItemProperty -LiteralPath $Path -Name $Key).$Key }
            'File' { return (Get-Content -LiteralPath $Path | Where-Object { $_.StartsWith("$Key=") } | Select-Object -First 1)?.Substring($Key.Length + 1) }
        }
    }
    catch { return $null }
}

<#
.SYNOPSIS
    Writes one value to a User env var, a registry value, or a KEY=VALUE line in a file.
.DESCRIPTION
    -Value may be a SecureString from Read-SecretValue: it is converted to text
    only for the write, and the value is never logged. Environment writes use
    [Environment]::SetEnvironmentVariable (never setx). A File write replaces an
    existing KEY= line or appends one.
#>
function Write-PersistedValue {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$Key,
        [Parameter(Mandatory)][object]$Value,
        [Parameter(Mandatory)][ValidateSet('Environment', 'Registry', 'File')][string]$Sink,
        [string]$Path = ''
    )
    if (-not $PSCmdlet.ShouldProcess($Key, "Write $Sink value")) { return }
    $text = $Value -is [securestring] ? (ConvertFrom-SecureString $Value -AsPlainText) : [string]$Value
    try {
        switch ($Sink) {
            'Environment' { [Environment]::SetEnvironmentVariable($Key, $text, 'User') }
            'Registry' { Set-ItemProperty -LiteralPath $Path -Name $Key -Value $text }
            'File' {
                $lines = @((Test-Path -LiteralPath $Path) ? (Get-Content -LiteralPath $Path) : @()) | Where-Object { -not $_.StartsWith("$Key=") }
                Set-Content -LiteralPath $Path -Value (@($lines) + "$Key=$text")
            }
        }
    }
    finally { $text = $null }
    $script:Run.Values[$Key] = $Sink
    Write-WizardLog "Persisted: $Key -> $Sink"
}

<#
.SYNOPSIS
    Force-closes running apps that block the task.
.DESCRIPTION
    Closing an app can lose unsaved work, so the run's caller decides before the
    run: pass -NoUnsavedWork for processes that hold no user data (updaters,
    tray agents), or -AllowUnsavedWorkLoss once the owner has agreed. Without
    either, a running blocker stops the run.
#>
function Close-BlockingProcess {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string[]]$ProcessName,
        [switch]$NoUnsavedWork,
        [switch]$AllowUnsavedWorkLoss
    )
    $running = @(Get-Process | Where-Object { $_.ProcessName -in $ProcessName })
    if (-not $running) { return }
    $names = ($running | ForEach-Object { "$($_.ProcessName) ($($_.Id))" }) -join ', '
    if (-not ($NoUnsavedWork -or $AllowUnsavedWorkLoss)) { throw "Close these apps first, or rerun with -AllowUnsavedWorkLoss: $names" }
    foreach ($proc in $running) {
        if ($PSCmdlet.ShouldProcess($proc.ProcessName, 'Stop-Process')) { Stop-Process -Id $proc.Id -Force }
    }
    Write-WizardLog "Closed: $names"
}

<#
.SYNOPSIS
    Copies the paths this run will change into the run's backup folder; returns that folder.
.DESCRIPTION
    Back up only what a step writes. A missing source is reported and skipped.
    Registry keys (HKCU:\..., HKLM:\...) are exported with reg.exe to a .reg file;
    file-system paths are copied. Any copy or export failure throws.
#>
function Invoke-QuickBackup {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string[]]$Path)
    Assert-RunStarted
    $script:Run.Backup = Join-Path $script:Run.Root 'backup'
    [void](New-Item -ItemType Directory -Path $script:Run.Backup -Force)
    foreach ($source in $Path) {
        if (-not (Test-Path -LiteralPath $source)) { Write-WizardStatus "Backup skipped, not found: $source" -Level Warn; continue }
        $item = Get-Item -LiteralPath $source -ErrorAction Stop
        if ($item.PSProvider.Name -eq 'Registry') {
            $file = Join-Path $script:Run.Backup (($item.Name -replace '[\\/:*?"<>|]', '_') + '.reg')
            $result = Invoke-NativeProcess "$env:SystemRoot\System32\reg.exe" -ArgumentList 'export', $item.Name, $file, '/y' -TimeoutSeconds 120 -CaptureOutput
            if ($result.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $file)) { throw "Backup failed for $source (reg.exe exit $($result.ExitCode))." }
        }
        else { Copy-Item -LiteralPath $source -Destination $script:Run.Backup -Recurse -Force -ErrorAction Stop }
        Write-WizardLog "Backed up: $source"
    }
    $script:Run.Backup
}

<#
.SYNOPSIS
    Runs a program with a timeout; returns ExitCode and, with -CaptureOutput, Output.
.DESCRIPTION
    Use instead of Start-Process -Wait, which has no timeout and does not set an
    exit code. Pass absolute paths: the child starts in -WorkingDirectory, or in
    the current folder when that is on the file system. Each argument is passed
    separately, so spaces and quotes need no escaping.
#>
function Invoke-NativeProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [ValidateRange(1, 86400)][int]$TimeoutSeconds = 900,
        [switch]$CaptureOutput,
        [string]$WorkingDirectory = ''
    )
    $psi = [Diagnostics.ProcessStartInfo]::new($FilePath)
    $ArgumentList | ForEach-Object { $psi.ArgumentList.Add($_) }
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = [bool]$CaptureOutput
    $location = Get-Location
    $psi.WorkingDirectory = $WorkingDirectory ? $WorkingDirectory : ($location.Provider.Name -eq 'FileSystem' ? $location.ProviderPath : '')
    Write-WizardLog "Running: $FilePath (timeout $TimeoutSeconds s, in '$($psi.WorkingDirectory)')"
    $proc = [Diagnostics.Process]::Start($psi)
    $stdout = $CaptureOutput ? $proc.StandardOutput.ReadToEndAsync() : $null
    if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
        $proc.Kill($true)
        throw "$FilePath did not finish within $TimeoutSeconds s and was stopped."
    }
    $proc.WaitForExit()
    Write-WizardLog "Finished: $FilePath (exit $($proc.ExitCode))"
    [pscustomobject]@{ ExitCode = $proc.ExitCode; Output = $CaptureOutput ? $stdout.GetAwaiter().GetResult() : '' }
}

<#
.SYNOPSIS
    Returns a Windows optional feature's state ('Enabled', 'Disabled', ...) via dism.exe.
.DESCRIPTION
    The DISM cmdlets fail or hang in Store pwsh 7; dism.exe works from any host.
    Throws when dism fails or prints no state, so a failed query is never read as
    "not installed".
#>
function Get-OptionalFeatureState {
    [CmdletBinding()]
    param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9-]+$')][string]$Name)
    $result = Invoke-NativeProcess dism.exe -ArgumentList '/Online', '/English', '/Get-FeatureInfo', "/FeatureName:$Name" -TimeoutSeconds 300 -CaptureOutput
    if ($result.ExitCode -ne 0) { throw "dism /Get-FeatureInfo failed for $Name (exit $($result.ExitCode))." }
    $match = [regex]::Match($result.Output, '(?m)^State\s*:\s*(.+?)\s*$')
    if (-not $match.Success) { throw "dism printed no state for $Name." }
    $match.Groups[1].Value
}

<#
.SYNOPSIS
    Disables a Windows optional feature via dism.exe; returns $true when a restart is needed.
#>
function Disable-OptionalFeature {
    [CmdletBinding(SupportsShouldProcess)]
    [OutputType([bool])]
    param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9-]+$')][string]$Name)
    if (-not $PSCmdlet.ShouldProcess($Name, 'Disable optional feature')) { return $false }
    $result = Invoke-NativeProcess dism.exe -ArgumentList '/Online', '/English', '/Disable-Feature', "/FeatureName:$Name", '/NoRestart', '/Quiet' -TimeoutSeconds 1800
    if ($result.ExitCode -notin 0, 3010) { throw "dism /Disable-Feature failed for $Name (exit $($result.ExitCode))." }
    $result.ExitCode -eq 3010
}

<#
.SYNOPSIS
    Records software this run installed, so a failed run can uninstall it.
.DESCRIPTION
    Call it right after each install. When installing is the run's goal, a
    failed goal check does not uninstall; only an error that stops the run does.
#>
function Register-InstalledSoftware {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$UninstallCommand
    )
    Assert-RunStarted
    $script:Run.Installed.Add([pscustomobject]@{ Name = $Name; UninstallCommand = $UninstallCommand })
    Write-WizardLog "Registered install: $Name"
}

function Uninstall-RunSoftware {
    $hostPath = (Get-Process -Id $PID).Path
    foreach ($item in $script:Run.Installed) {
        try {
            $result = Invoke-NativeProcess $hostPath -ArgumentList '-NoProfile', '-Command', "$($item.UninstallCommand)`nexit `$LASTEXITCODE"
            if ($result.ExitCode -notin 0, 1641, 3010) { throw "exit $($result.ExitCode)" }
            Write-WizardLog "Uninstalled: $($item.Name)"
        }
        catch {
            $script:Run.Manual.Add("Uninstall $($item.Name) ($($_.Exception.Message))")
            Write-WizardStatus "Could not uninstall $($item.Name): $($_.Exception.Message)" -Level Warn
        }
    }
    $script:Run.Installed.Clear()
}

<#
.SYNOPSIS
    Runs one goal check and records pass or fail; never stops the other checks.
.DESCRIPTION
    Passes only when the block's last output is exactly $true, so it must prove
    the goal state ('Disabled'), not the absence of a bad one (-ne 'Enabled'),
    which a failed query also satisfies. Compute everything inside the block.
#>
function Test-WizardGoal {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)][string]$Name,
        [Parameter(Mandatory, Position = 1)][scriptblock]$Check
    )
    Assert-RunStarted
    $detail = ''
    try {
        $out = @(& $Check)
        $passed = $out.Count -gt 0 -and $out[-1] -is [bool] -and $out[-1]
    }
    catch {
        $passed = $false
        $detail = $_.Exception.Message
    }
    $script:Run.Checks.Add([pscustomobject]@{ Name = $Name; Passed = $passed; Detail = $detail })
    Write-WizardStatus ($passed ? "Check passed: $Name" : "Check FAILED: $Name $detail") -Level ($passed ? 'Ok' : 'Fail')
}

<#
.SYNOPSIS
    Records something a person must still do by hand; it is listed in the summary.
#>
function Add-ManualFollowUp {
    [CmdletBinding()]
    param([Parameter(Mandatory, Position = 0)][string]$Item)
    Assert-RunStarted
    $script:Run.Manual.Add($Item)
    Write-WizardLog "Manual follow-up: $Item"
}

<#
.SYNOPSIS
    Prints the summary and returns the exit code: 0 only when at least one check ran and all passed.
#>
function Complete-WizardRun {
    [CmdletBinding()]
    [OutputType([int])]
    param()
    Assert-RunStarted
    $failed = @($script:Run.Checks | Where-Object { -not $_.Passed })
    $ok = $script:Run.Checks.Count -gt 0 -and -not $failed
    if ($ok) { Write-WizardStatus "$($script:Run.Title): done, all $($script:Run.Checks.Count) checks passed." -Level Ok }
    elseif (-not $script:Run.Checks.Count) { Write-WizardStatus "$($script:Run.Title): finished, but no goal check ran; nothing is verified." -Level Fail }
    else { Write-WizardStatus "$($script:Run.Title): $($failed.Count) of $($script:Run.Checks.Count) checks failed." -Level Fail }
    if ($script:Run.Values.Count) { Write-WizardStatus "Values written: $($script:Run.Values.Keys -join ', ')" }
    if ($script:Run.Secrets.Count) { Write-WizardStatus "Secrets stored (names only): $($script:Run.Secrets -join ', ')" }
    foreach ($item in $script:Run.Manual) { Write-WizardStatus "Do by hand: $item" -Level Warn }
    if ($script:Run.Backup) { Write-WizardStatus "Backup: $($script:Run.Backup)" }
    Write-WizardStatus "Log: $($script:Run.Log)"
    $ok ? 0 : 1
}

<#
.SYNOPSIS
    Handles an error that stopped the run: logs it with its stack, uninstalls what the run installed, returns exit code 1.
#>
function Complete-WizardFailure {
    [CmdletBinding()]
    [OutputType([int])]
    param([Parameter(Mandatory, Position = 0)][System.Management.Automation.ErrorRecord]$ErrorRecord)
    Write-WizardLog "Run failed: $($ErrorRecord.Exception.Message)`n$($ErrorRecord.ScriptStackTrace)"
    Write-WizardStatus "Failed: $($ErrorRecord.Exception.Message)" -Level Fail
    if ($script:Run) {
        Uninstall-RunSoftware
        Write-WizardStatus "Log: $($script:Run.Log)"
    }
    1
}

Export-ModuleMember -Function Write-WizardLog, Write-WizardStatus, Start-WizardRun, Stop-WizardRun, Invoke-WizardStep,
    Assert-WizardPrerequisite, Wait-HumanAction, Read-PlainValue, Read-SecretValue, Get-ExistingValue, Write-PersistedValue,
    Close-BlockingProcess, Invoke-QuickBackup, Invoke-NativeProcess, Get-OptionalFeatureState, Disable-OptionalFeature,
    Register-InstalledSoftware, Test-WizardGoal, Add-ManualFollowUp, Complete-WizardRun, Complete-WizardFailure
