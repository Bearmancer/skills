#Requires -Version 7.0
<#
.SYNOPSIS
    One-shot admin wizard template for ps-wizard generated setups.

.DESCRIPTION
    Template library for single .ps1 wizards run under pwsh 7.x. Provides
    stage framing with progress counters, colored say/step output, an admin
    self-elevate-and-relaunch at start, a goal-sufficiency gate before stage 1,
    blocker detection with force-close, plain and secret prompts, transcript
    plus explicit log file on the Desktop, a single quick backup step,
    auto-uninstall of anything the wizard installed, and maximum tracing.

    Run with no parameters:
        pwsh -NoProfile -ExecutionPolicy Bypass -File template.ps1

    Generated wizards copy this file and fill the TODO stages inside
    Invoke-Wizard. There are no script parameters by design: the human just
    runs the file and answers prompts.

.NOTES
    No Enter-pauses for pacing. The only Read-Host pauses are the human-action
    gate in Wait-HumanAction and the final hold that keeps the elevated window
    open on the summary. Secret values are never written to the screen,
    transcript echo, or log file.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$VerbosePreference = 'Continue'
$DebugPreference = 'Continue'

$script:TotalStages = 0
$script:StageIndex = 0
$script:WrittenValues = @{}
$script:WrittenSecrets = @()
$script:Skipped = @()
$script:InstalledSoftware = @()
$script:DesktopPath = [Environment]::GetFolderPath('Desktop')
$script:WizardName = 'wizard'
if (-not [string]::IsNullOrEmpty($PSCommandPath)) {
    $script:WizardName = [System.IO.Path]::GetFileNameWithoutExtension($PSCommandPath)
}
$script:WizardRoot = Join-Path -Path $script:DesktopPath -ChildPath (Join-Path -Path 'ps-wizard' -ChildPath $script:WizardName)
$script:RunRoot = ''
$script:WizardOutputDir = ''
$script:LogFilePath = ''
$script:TranscriptPath = ''
$script:BackupPath = ''
$script:VerificationResults = [System.Collections.Generic.List[object]]::new()
$script:ExitCode = 0
$script:ConsoleInputHandle = [System.IntPtr]::Zero
$script:OriginalConsoleInputMode = [uint32]0
$script:RestoreConsoleInputMode = $false

# Write-Host is used only inside Write-Colored for colored human-facing
# say/step output. All diagnostic output uses Write-Verbose, Write-Debug,
# and Write-Warning. Never Write-Error: under $ErrorActionPreference = 'Stop'
# it is a terminating error, so in a catch block it skips every line after it.
function Write-Colored {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification = 'Colored human-facing wizard say/step output requires Write-Host; diagnostics use Write-Verbose, Write-Debug, and Write-Warning.')]
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [Parameter()]
        [ValidateSet('Cyan', 'Green', 'Yellow', 'DarkGray', 'White', 'Red')]
        [string]$Color = 'White'
    )
    Write-Host $Message -ForegroundColor $Color
}

<#
.SYNOPSIS
    Prints a plain instruction line.
#>
function Write-Say {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    Write-Colored -Message $Message -Color White
}

<#
.SYNOPSIS
    Prints a bulleted action line in the accent color.
#>
function Write-Step {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    Write-Colored -Message "- $Message" -Color Cyan
}

<#
.SYNOPSIS
    Prints a dim supplementary line.
#>
function Write-Note {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    Write-Colored -Message $Message -Color DarkGray
}

<#
.SYNOPSIS
    Prints a warning line.
#>
function Write-Warn {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    Write-Colored -Message "WARNING: $Message" -Color Yellow
}

<#
.SYNOPSIS
    Clears the screen when interactive; no-op when output is redirected.
#>
function Clear-StepScreen {
    [CmdletBinding()]
    param()
    if ([Environment]::UserInteractive -and (-not [Console]::IsOutputRedirected)) {
        Clear-Host
    }
}

<#
.SYNOPSIS
    Appends a timestamped line to the explicit Desktop log file.
.DESCRIPTION
    Never throws: the fatal handler logs through this function, so a log
    failure must not replace the error being reported.
#>
function Write-WizardLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    $line = "[$((Get-Date).ToString('s'))] $Message"
    if ($script:LogFilePath -eq '') {
        Write-Verbose $line
        return
    }
    try {
        Add-Content -LiteralPath $script:LogFilePath -Value $line -ErrorAction Stop
    }
    catch {
        Write-Warning "Could not write the wizard log: $($_.Exception.Message)"
    }
}

<#
.SYNOPSIS
    Starts the transcript plus the explicit log file, both under the wizard's single Desktop root.
.DESCRIPTION
    Every run writes into one root, Desktop\ps-wizard\<script name>\<stamp>\, holding
    wizard.log, transcript.log, backup\ and output\. A file left by an earlier run can
    never satisfy this run's verification, and nothing lands loose on the Desktop.
#>
function Start-WizardLogging {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param()
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $script:RunRoot = Join-Path -Path $script:WizardRoot -ChildPath $stamp
    $script:LogFilePath = Join-Path -Path $script:RunRoot -ChildPath 'wizard.log'
    $script:TranscriptPath = Join-Path -Path $script:RunRoot -ChildPath 'transcript.log'
    $script:WizardOutputDir = Join-Path -Path $script:RunRoot -ChildPath 'output'
    [void](New-Item -Path $script:RunRoot -ItemType Directory -Force -ErrorAction Stop)
    [void](New-Item -Path $script:LogFilePath -ItemType File -ErrorAction Stop)
    [void](New-Item -Path $script:WizardOutputDir -ItemType Directory -Force -ErrorAction Stop)
    Start-Transcript -Path $script:TranscriptPath -ErrorAction Stop
    Write-WizardLog -Message 'Wizard started.'
    Write-Verbose "Run root: $script:RunRoot"
    Write-Verbose "Logging to transcript: $script:TranscriptPath"
    Write-Verbose "Logging to log file: $script:LogFilePath"
    Write-Debug "Wizard output directory: $($script:WizardOutputDir | ConvertTo-Json)"
}

<#
.SYNOPSIS
    Stops the transcript; safe to call when none is running.
#>
function Stop-WizardLogging {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param()
    # Runs in finally: any error here would mask the one that ended the wizard.
    try {
        Stop-Transcript -ErrorAction Stop
    }
    catch {
        Write-Verbose "Transcript not stopped: $($_.Exception.Message)"
    }
}

<#
.SYNOPSIS
    Returns $true when the current session is elevated.
#>
function Test-IsAdmin {
    [CmdletBinding()]
    param()
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object -TypeName Security.Principal.WindowsPrincipal -ArgumentList $identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

<#
.SYNOPSIS
    Relaunches this script elevated when not admin, then exits this copy.
.DESCRIPTION
    Relaunches with the exact pwsh executable already running: a bare 'pwsh'
    can resolve to another install (Store vs MSI) whose modules differ.
#>
function Assert-AdminAndRelaunch {
    [CmdletBinding()]
    param()
    Write-Verbose "Host: $((Get-Process -Id $PID).Path) $($PSVersionTable.PSVersion)"
    if (Test-IsAdmin) {
        Write-Verbose 'Running with administrator rights.'
        return
    }
    if ([string]::IsNullOrEmpty($PSCommandPath)) {
        throw 'Run this wizard with pwsh -File <path>; a dot-sourced or pasted copy cannot relaunch itself elevated.'
    }
    Write-Warn -Message 'Administrator rights are required. Relaunching elevated.'
    $startParams = @{
        FilePath     = (Get-Process -Id $PID).Path
        ArgumentList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath)
        Verb         = 'runas'
    }
    $elevated = Start-Process @startParams -Wait -PassThru
    exit $elevated.ExitCode
}

<#
.SYNOPSIS
    Stops the wizard before stage 1 when its goals cannot be met.
.DESCRIPTION
    Checks every required path exists and the Desktop drive has enough free
    space. Throws a terminating error naming the shortfall so Invoke-Wizard
    aborts before stage 1 instead of failing halfway.
#>
function Confirm-GoalSufficiency {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$RequiredPaths,
        [Parameter()]
        [ValidateRange(0, 1000)]
        [int]$MinimumFreeGB = 5
    )
    $missing = @(foreach ($req in $RequiredPaths) {
        if (-not (Test-Path -Path $req)) {
            Write-Output $req
        }
    })
    if ($missing.Count -gt 0) {
        throw "Goal-sufficiency gate failed. Missing required paths: $($missing -join ', ')"
    }
    $root = [System.IO.Path]::GetPathRoot($script:DesktopPath)
    if ($root -notmatch '^[A-Za-z]:') {
        Write-Warn -Message "The Desktop is not on a lettered drive ($root); free space was not checked."
        return
    }
    $drive = Get-PSDrive -Name $root.Substring(0, 1) -ErrorAction Stop
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    Write-Verbose "Desktop drive free space: $freeGB GB."
    if ($freeGB -lt $MinimumFreeGB) {
        throw "Goal-sufficiency gate failed. Only $freeGB GB free on $root; need at least $MinimumFreeGB GB."
    }
    Write-Verbose 'Goal-sufficiency gate passed.'
}

<#
.SYNOPSIS
    Shows the opening frame and total step count.
.DESCRIPTION
    The only pause here is the human-action gate in Wait-HumanAction; there
    are no pacing pauses.
#>
function Show-Banner {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 64)]
        [int]$TotalStages
    )
    $script:TotalStages = $TotalStages
    $script:StageIndex = 0
    Clear-StepScreen
    Write-Colored -Message '================================' -Color Cyan
    Write-Colored -Message $Title -Color Cyan
    Write-Colored -Message '================================' -Color Cyan
    Write-Say -Message "This wizard has $TotalStages steps. You drive; the wizard tells you exactly what to do."
    Write-WizardLog -Message "Banner shown: $Title ($TotalStages steps)"
    Wait-HumanAction -Instruction 'Read the plan above, then continue.'
}

<#
.SYNOPSIS
    Opens a stage frame with a progress counter.
#>
function Invoke-Step {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )
    $script:StageIndex++
    Clear-StepScreen
    Write-Colored -Message "Step $($script:StageIndex) of $($script:TotalStages): $Name" -Color Cyan
    Write-WizardLog -Message "Stage $($script:StageIndex)/$($script:TotalStages) started: $Name"
}

<#
.SYNOPSIS
    Opens a URL, falling back to a manual step when it fails.
#>
function Open-Url {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )
    try {
        Start-Process -FilePath $Url -ErrorAction Stop
        Write-WizardLog -Message "Opened URL: $Url"
    }
    catch {
        Write-Warn -Message "Could not open a browser automatically. Open this URL by hand: $Url"
        Write-Verbose "Open-Url failed for: $Url"
    }
}

<#
.SYNOPSIS
    Turns off QuickEdit and mouse input for the wizard's lifetime.
.DESCRIPTION
    With QuickEdit on, a click after a GUI installer takes focus starts a
    selection that freezes the console until Space or Esc is pressed, so
    ENTER looks broken. The original mode is restored by
    Restore-WizardConsoleInput on every exit path.
#>
function Initialize-WizardConsoleInput {
    [CmdletBinding()]
    param()
    if ([Console]::IsInputRedirected) {
        return
    }
    try {
        if (-not ('WizardConsole.NativeMethods' -as [type])) {
            $signatures = @(
                '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern System.IntPtr GetStdHandle(int nStdHandle);'
                '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern bool GetConsoleMode(System.IntPtr hConsoleHandle, out uint lpMode);'
                '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern bool SetConsoleMode(System.IntPtr hConsoleHandle, uint dwMode);'
            )
            Add-Type -Namespace WizardConsole -Name NativeMethods -MemberDefinition ($signatures -join ' ') -ErrorAction Stop
        }
        $handle = [WizardConsole.NativeMethods]::GetStdHandle(-10)
        $mode = [uint32]0
        if (($handle -eq [System.IntPtr]::Zero) -or (-not [WizardConsole.NativeMethods]::GetConsoleMode($handle, [ref]$mode))) {
            Write-Verbose 'Console input mode is unavailable; left unchanged.'
            return
        }
        # Clear ENABLE_QUICK_EDIT_MODE (0x40) and ENABLE_MOUSE_INPUT (0x10);
        # set ENABLE_EXTENDED_FLAGS (0x80) so the QuickEdit change applies.
        $newMode = ($mode -band (-bnot [uint32]0x50)) -bor [uint32]0x80
        if (-not [WizardConsole.NativeMethods]::SetConsoleMode($handle, $newMode)) {
            throw "SetConsoleMode failed with Win32 error $([System.Runtime.InteropServices.Marshal]::GetLastWin32Error())."
        }
        $script:ConsoleInputHandle = $handle
        $script:OriginalConsoleInputMode = $mode
        $script:RestoreConsoleInputMode = $true
        Write-WizardLog -Message "Console QuickEdit and mouse input disabled (mode $mode -> $newMode)."
    }
    catch {
        Write-Warn -Message "Could not turn off console selection mode. If the window stops responding, press Esc. $($_.Exception.Message)"
    }
}

<#
.SYNOPSIS
    Restores the console input mode captured by Initialize-WizardConsoleInput.
#>
function Restore-WizardConsoleInput {
    [CmdletBinding()]
    param()
    if (-not $script:RestoreConsoleInputMode) {
        return
    }
    $script:RestoreConsoleInputMode = $false
    if (-not [WizardConsole.NativeMethods]::SetConsoleMode($script:ConsoleInputHandle, $script:OriginalConsoleInputMode)) {
        Write-Warn -Message 'Could not restore the original console input mode.'
    }
}

<#
.SYNOPSIS
    Discards keys typed while unattended stages ran.
.DESCRIPTION
    Read-Host consumes whatever is already buffered, so an ENTER pressed
    during an install would satisfy the next prompt before the human acts.
    Throws when input is redirected: Read-Host then returns at once and every
    gate would pass unattended.
#>
function Clear-PendingInput {
    [CmdletBinding()]
    param()
    if ([Console]::IsInputRedirected) {
        throw 'Console input is redirected; this wizard needs a person at the keyboard.'
    }
    while ([Console]::KeyAvailable) {
        [void][Console]::ReadKey($true)
    }
}

<#
.SYNOPSIS
    The only pause in a wizard: waits where the human must physically act.
#>
function Wait-HumanAction {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Instruction
    )
    Write-Step -Message $Instruction
    Write-WizardLog -Message "Waiting for human action: $Instruction"
    Clear-PendingInput
    [void](Read-Host -Prompt 'Only after completing the action above, press ENTER to continue')
    Write-WizardLog -Message 'Human action acknowledged.'
}

<#
.SYNOPSIS
    Yes/no gate that defaults to no.
#>
function Confirm-Choice {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt
    )
    Clear-PendingInput
    $answer = Read-Host -Prompt "$Prompt [y/N]"
    Write-WizardLog -Message "Choice '$Prompt' answered: $answer"
    if ($answer -eq 'y' -or $answer -eq 'Y') {
        return $true
    }
    return $false
}

<#
.SYNOPSIS
    Reads the currently persisted value for a re-run default.
.DESCRIPTION
    Returns the stored value or $null when there is none or it cannot be
    decoded. Never throws for a missing value. The File sink reads the
    KEY=VALUE lines that Write-PersistedValue writes.
#>
function Get-ExistingValue {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [ValidateSet('Environment', 'Registry', 'File')]
        [string]$Sink,
        [Parameter()]
        [string]$Path = ''
    )
    try {
        if ($Sink -eq 'Environment') {
            $machine = [Environment]::GetEnvironmentVariable($Key, 'Machine')
            if ($null -ne $machine) {
                return $machine
            }
            return [Environment]::GetEnvironmentVariable($Key, 'User')
        }
        if ($Sink -eq 'Registry') {
            $prop = Get-ItemProperty -Path $Path -Name $Key -ErrorAction Stop
            return $prop.$Key
        }
        $prefix = "$Key="
        foreach ($line in @(Get-Content -LiteralPath $Path -ErrorAction Stop)) {
            if ($line.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
                return $line.Substring($prefix.Length)
            }
        }
        return $null
    }
    catch {
        # Undecodable or missing values are normal on first run; the caller
        # treats $null as "no default". Logged at Verbose, never an error.
        Write-Verbose "No existing value for: $Key"
        return $null
    }
}

<#
.SYNOPSIS
    Prompts for a visible value with a re-run default. Never echoes it back.
#>
function Read-PlainValue {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt,
        [Parameter()]
        [string]$Current = ''
    )
    Clear-PendingInput
    if ($Current -ne '') {
        $value = Read-Host -Prompt "$Prompt (leave blank to keep current)"
    }
    else {
        $value = Read-Host -Prompt $Prompt
    }
    # The entered value is returned, never displayed or logged.
    if ([string]::IsNullOrWhiteSpace($value)) {
        if ($Current -ne '') {
            return $Current
        }
        throw "No input received for: $Prompt"
    }
    return $value
}

<#
.SYNOPSIS
    Prompts for a secret without echoing it. The value is never logged.
#>
function Read-SecretValue {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt,
        [Parameter()]
        [string]$Name = ''
    )
    Clear-PendingInput
    $secure = Read-Host -Prompt "$Prompt (leave blank to keep current)" -AsSecureString
    # Secret values are never displayed, never written to the log, and only
    # their names are recorded for the summary.
    if (($null -eq $secure) -or ($secure.Length -eq 0)) {
        if ($Name -ne '') {
            return $null
        }
        throw "No input received for: $Prompt"
    }
    if ($Name -ne '') {
        $script:WrittenSecrets = @($script:WrittenSecrets) + $Name
    }
    return $secure
}

<#
.SYNOPSIS
    Persists one value to the declared sink with idempotent upsert semantics.
.DESCRIPTION
    Records KEY to sink in WrittenValues for the summary. The value itself is
    never logged. Destructive overwrites honor ShouldProcess (-WhatIf/-Confirm).
    The File sink persists KEY=VALUE lines (upsert by KEY= prefix match),
    which Get-ExistingValue -Sink File reads back.
#>
function Write-PersistedValue {
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [ValidateSet('Environment', 'Registry', 'File')]
        [string]$Sink,
        [Parameter()]
        [string]$Path = ''
    )
    if ($PSCmdlet.ShouldProcess($Key, "Write $Sink value")) {
        try {
            if ($Sink -eq 'Environment') {
                [Environment]::SetEnvironmentVariable($Key, $Value, 'User')
            }
            elseif ($Sink -eq 'Registry') {
                Set-ItemProperty -Path $Path -Name $Key -Value $Value -ErrorAction Stop
            }
            else {
                $lines = @()
                if (Test-Path -Path $Path) {
                    $lines = @(Get-Content -Path $Path -ErrorAction Stop)
                }
                $updated = $false
                $out = @(foreach ($line in $lines) {
                    if ($line -like "$Key=*") {
                        $updated = $true
                        Write-Output "$Key=$Value"
                    }
                    else {
                        Write-Output $line
                    }
                })
                if (-not $updated) {
                    $out = $out + "$Key=$Value"
                }
                Set-Content -Path $Path -Value $out -ErrorAction Stop
            }
            $script:WrittenValues[$Key] = $Sink
            Write-WizardLog -Message "Persisted value: $Key -> $Sink"
        }
        catch [System.UnauthorizedAccessException] {
            $script:Skipped = @($script:Skipped) + $Key
            Write-Warn -Message "Access denied persisting: $Key"
            Write-WizardLog -Message "Access denied persisting: $Key"
        }
        catch {
            Write-WizardLog -Message "Unexpected error persisting ${Key}: $($_.Exception.Message)"
            throw
        }
    }
}

<#
.SYNOPSIS
    Lists the blocking processes that are currently running.
#>
function Find-BlockingProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$ProcessNames
    )
    # Get-Process -Name reports "not running" as an error; filtering the full
    # list keeps a real query failure terminating.
    $all = @(Get-Process -ErrorAction Stop)
    foreach ($name in $ProcessNames) {
        foreach ($proc in @($all | Where-Object { $_.ProcessName -eq $name })) {
            Write-Output $proc
        }
    }
}

<#
.SYNOPSIS
    Force-closes blocking processes with Stop-Process.
.DESCRIPTION
    Lists the running blockers and asks once before closing them, because a
    force-close loses unsaved work. Pass -NoUnsavedWork only for processes
    that hold no user data (updaters, tray agents, services). The confirmation
    is an explicit Confirm-Choice, not ShouldProcess: never set
    $ConfirmPreference = 'None' to silence prompts, it disables this guard.
#>
function Close-BlockingProcess {
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$ProcessNames,
        [Parameter()]
        [switch]$NoUnsavedWork
    )
    $running = @(Find-BlockingProcess -ProcessNames $ProcessNames)
    if ($running.Count -eq 0) {
        Write-Verbose 'No blocking processes running.'
        return
    }
    foreach ($proc in $running) {
        Write-Say -Message "Running: $($proc.ProcessName) ($($proc.Id))"
    }
    if (-not $NoUnsavedWork) {
        $ok = Confirm-Choice -Prompt 'Force-close the listed apps and lose unsaved work'
        if (-not $ok) {
            throw 'Blocker close declined; cannot continue.'
        }
    }
    foreach ($proc in $running) {
        if ($PSCmdlet.ShouldProcess($proc.ProcessName, 'Stop-Process')) {
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            Write-WizardLog -Message "Stopped blocking process: $($proc.ProcessName) ($($proc.Id))"
        }
    }
}

<#
.SYNOPSIS
    Copies the given paths to this run's backup folder.
.DESCRIPTION
    The single quick backup step of a wizard. It writes into the current run
    root, so every run's artifacts stay in one Desktop folder. Missing sources
    are warned about and skipped, never fatal.
#>
function Invoke-QuickBackup {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Paths
    )
    if ([string]::IsNullOrEmpty($script:RunRoot)) {
        throw 'The run root is not set; Start-WizardLogging runs before any backup.'
    }
    $dest = Join-Path -Path $script:RunRoot -ChildPath 'backup'
    [void](New-Item -Path $dest -ItemType Directory -Force -ErrorAction Stop)
    foreach ($source in $Paths) {
        if (Test-Path -Path $source) {
            Copy-Item -Path $source -Destination $dest -Recurse -Force -ErrorAction Stop
            Write-WizardLog -Message "Backed up: $source"
        }
        else {
            Write-Warn -Message "Backup source missing, skipped: $source"
        }
    }
    $script:BackupPath = $dest
    Write-Verbose "Backup complete: $dest"
    return $dest
}

<#
.SYNOPSIS
    Runs a native program with a timeout and returns its exit code.
.DESCRIPTION
    Start-Process -Wait has no timeout (a hidden installer prompt blocks the
    wizard forever) and does not set $LASTEXITCODE. Arguments go through
    ProcessStartInfo.ArgumentList, so each one is quoted correctly even with
    spaces or quotes. -CaptureOutput returns stdout in .Output.
#>
function Invoke-NativeProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter()]
        [string[]]$ArgumentList = @(),
        [Parameter()]
        [ValidateRange(1, 86400)]
        [int]$TimeoutSeconds = 900,
        [Parameter()]
        [switch]$CaptureOutput,
        [Parameter()]
        [string]$WorkingDirectory = ''
    )
    $psi = [System.Diagnostics.ProcessStartInfo]::new($FilePath)
    foreach ($arg in $ArgumentList) {
        $psi.ArgumentList.Add($arg)
    }
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = [bool]$CaptureOutput
    $resolvedWorkingDirectory = $WorkingDirectory
    if (-not $resolvedWorkingDirectory) {
        $currentLocation = Get-Location
        if ($currentLocation.Provider.Name -eq 'FileSystem') {
            $resolvedWorkingDirectory = $currentLocation.ProviderPath
        }
    }
    if ($resolvedWorkingDirectory) {
        $psi.WorkingDirectory = $resolvedWorkingDirectory
    }
    Write-WizardLog -Message "Working directory: $(if ($resolvedWorkingDirectory) { $resolvedWorkingDirectory } else { 'inherited from host' })"
    Write-WizardLog -Message "Running: $FilePath (timeout $TimeoutSeconds s)"
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = if ($CaptureOutput) { $proc.StandardOutput.ReadToEndAsync() } else { $null }
    if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
        $proc.Kill($true)
        throw "$FilePath did not exit within $TimeoutSeconds s and was stopped."
    }
    $proc.WaitForExit()
    Write-WizardLog -Message "Finished: $FilePath (exit $($proc.ExitCode))"
    return [pscustomobject]@{
        ExitCode = $proc.ExitCode
        Output   = if ($CaptureOutput) { $stdout.GetAwaiter().GetResult() } else { '' }
    }
}

<#
.SYNOPSIS
    Returns an optional feature's state ('Enabled', 'Disabled', ...) via dism.exe.
.DESCRIPTION
    The DISM cmdlets (Get-WindowsOptionalFeature) fail in the Store (MSIX)
    pwsh 7.6.9 with "Class not registered" or hang; dism.exe answers from any
    host. Throws when dism fails or prints no state, so a failed query is
    never read as "not installed".
#>
function Get-OptionalFeatureState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Za-z0-9-]+$')]
        [string]$Name
    )
    $result = Invoke-NativeProcess -FilePath 'dism.exe' -ArgumentList @('/Online', '/English', '/Get-FeatureInfo', "/FeatureName:$Name") -TimeoutSeconds 300 -CaptureOutput
    if ($result.ExitCode -ne 0) {
        throw "dism /Get-FeatureInfo failed for $Name (exit $($result.ExitCode))."
    }
    $match = [regex]::Match($result.Output, '(?m)^State\s*:\s*(.+?)\s*$')
    if (-not $match.Success) {
        throw "dism printed no state for $Name."
    }
    return $match.Groups[1].Value
}

<#
.SYNOPSIS
    Disables an optional feature via dism.exe; returns $true when a reboot is needed.
#>
function Disable-OptionalFeature {
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Za-z0-9-]+$')]
        [string]$Name
    )
    if (-not $PSCmdlet.ShouldProcess($Name, 'Disable Windows optional feature')) {
        return $false
    }
    $result = Invoke-NativeProcess -FilePath 'dism.exe' -ArgumentList @('/Online', '/English', '/Disable-Feature', "/FeatureName:$Name", '/NoRestart', '/Quiet') -TimeoutSeconds 1800
    if ($result.ExitCode -eq 3010) {
        return $true
    }
    if ($result.ExitCode -ne 0) {
        throw "dism /Disable-Feature failed for $Name (exit $($result.ExitCode))."
    }
    return $false
}

<#
.SYNOPSIS
    Records software this wizard installed so it can be removed later.
.DESCRIPTION
    Call it right after every install a stage performs; Uninstall-WizardSoftware
    only removes what was registered here.
#>
function Register-InstalledSoftware {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$UninstallCommand
    )
    $script:InstalledSoftware = @($script:InstalledSoftware) + @{ Name = $Name; UninstallCommand = $UninstallCommand }
    Write-WizardLog -Message "Registered installed software: $Name"
}

<#
.SYNOPSIS
    Auto-uninstalls everything the wizard installed, oldest first (install order).
.DESCRIPTION
    Runs from the fatal handler, so it never throws: a failed or timed-out
    uninstall is warned about, logged, and left for the human, and the
    remaining items still run.
#>
function Uninstall-WizardSoftware {
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
    param()
    $count = $script:InstalledSoftware.Count
    Write-Verbose "Uninstalling $count package(s) installed by this wizard."
    $hostPath = (Get-Process -Id $PID).Path
    foreach ($item in $script:InstalledSoftware) {
        if ($PSCmdlet.ShouldProcess($item.Name, 'Uninstall')) {
            try {
                # pwsh -Command maps a failing native command to exit 1; pass the
                # real code through so MSI 3010/1641 (reboot needed) count as done.
                $command = "$($item.UninstallCommand)`nexit `$LASTEXITCODE"
                $result = Invoke-NativeProcess -FilePath $hostPath -ArgumentList @('-NoProfile', '-Command', $command)
                if ($result.ExitCode -notin @(0, 1641, 3010)) {
                    throw "exit $($result.ExitCode)"
                }
                Write-WizardLog -Message "Uninstalled: $($item.Name)"
            }
            catch {
                $script:Skipped = @($script:Skipped) + "Uninstall $($item.Name)"
                Write-Warn -Message "Failed to uninstall $($item.Name): $($_.Exception.Message)"
                Write-WizardLog -Message "Failed to uninstall $($item.Name): $($_.Exception.Message)"
            }
        }
    }
    $script:InstalledSoftware = @()
}

<#
.SYNOPSIS
    Runs one goal check and records its result; never aborts the others.
.DESCRIPTION
    The check passes only when its scriptblock's last output is exactly $true,
    so it must prove the goal state (feature 'Disabled'), not the absence of
    the bad state (anything but 'Enabled', which a failed or empty query also
    satisfies). An exception fails this check and the next one still runs.
#>
function Test-WizardGoal {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Check
    )
    $detail = ''
    try {
        $output = @(& $Check)
        $passed = ($output.Count -gt 0) -and ($output[-1] -is [bool]) -and $output[-1]
    }
    catch {
        $passed = $false
        $detail = $_.Exception.Message
    }
    $script:VerificationResults.Add([pscustomobject]@{ Name = $Name; Passed = $passed; Detail = $detail })
    Write-WizardLog -Message "Check $(if ($passed) { 'passed' } else { 'FAILED' }): $Name $detail"
}

<#
.SYNOPSIS
    Returns $true only when at least one check ran and every check passed.
#>
function Test-WizardSucceeded {
    [CmdletBinding()]
    param()
    $failed = @($script:VerificationResults | Where-Object { -not $_.Passed })
    return ($script:VerificationResults.Count -gt 0) -and ($failed.Count -eq 0)
}

<#
.SYNOPSIS
    Prints the closing frame with check results, counts and manual follow-ups.
#>
function Show-Summary {
    [CmdletBinding()]
    param()
    Clear-StepScreen
    if (Test-WizardSucceeded) {
        Write-Colored -Message 'Setup complete.' -Color Green
    }
    elseif ($script:VerificationResults.Count -eq 0) {
        Write-Colored -Message 'Setup finished, but no goal check ran; nothing is verified.' -Color Red
    }
    else {
        Write-Colored -Message 'Setup finished with failures:' -Color Red
        foreach ($result in @($script:VerificationResults | Where-Object { -not $_.Passed })) {
            Write-Say -Message "Failed: $($result.Name) $($result.Detail)"
        }
    }
    Write-Say -Message "Persisted $($script:WrittenValues.Count) value(s)."
    if ($script:WrittenSecrets.Count -gt 0) {
        Write-Say -Message "Stored $($script:WrittenSecrets.Count) secret(s) (names only, values never logged)."
    }
    if ($script:Skipped.Count -gt 0) {
        Write-Warn -Message 'These steps need you to act by hand:'
        foreach ($item in $script:Skipped) {
            Write-Say -Message "By hand: $item"
        }
    }
    if ($script:RunRoot -ne '') {
        Write-Say -Message "Everything from this run: $script:RunRoot"
    }
    if ($script:BackupPath -ne '') {
        Write-Say -Message "Backup kept at: $script:BackupPath"
    }
    Write-Say -Message "Full log: $($script:LogFilePath)"
    Write-Say -Message "Console transcript: $($script:TranscriptPath)"
    Write-WizardLog -Message 'Wizard finished.'
}

# ===== STAGES =====
# Everything above is the shared library; generated wizards edit only below.

<#
.SYNOPSIS
    Runs the wizard stages. Generated wizards fill the TODO stages.
#>
function Invoke-Wizard {
    [CmdletBinding()]
    param()
    Assert-AdminAndRelaunch
    Start-WizardLogging
    try {
        Initialize-WizardConsoleInput
        # Goal-sufficiency gate runs before stage 1.
        Confirm-GoalSufficiency -RequiredPaths @($script:DesktopPath)
        Show-Banner -Title 'Example Admin Wizard' -TotalStages 3

        Invoke-Step -Name 'Quick backup'
        # TODO: list the real paths this wizard is about to change.
        [void](Invoke-QuickBackup -Paths @($script:WizardOutputDir))

        Invoke-Step -Name 'Configure values'
        # TODO: close the apps that block this wizard's task.
        # Close-BlockingProcess -ProcessNames @('ExampleApp')
        # TODO: prompt, persist, and open any pages the task needs.
        # $current = Get-ExistingValue -Key 'ExampleSetting' -Sink 'Environment'
        # $value = Read-PlainValue -Prompt 'Example setting' -Current $current
        # Write-PersistedValue -Key 'ExampleSetting' -Value $value -Sink 'Environment'
        # $secret = Read-SecretValue -Prompt 'Example token' -Name 'ExampleToken'
        # TODO: register anything installed so it auto-uninstalls on failure.
        # Register-InstalledSoftware -Name 'ExampleApp' -UninstallCommand 'winget uninstall --id Example.App'
        Write-Note -Message 'Stage 2 is a placeholder until the generated wizard fills it in.'

        Invoke-Step -Name 'Verify and finish'
        # TODO: replace with one Test-WizardGoal per goal, each proving the goal
        # state. This placeholder fails so an unfilled wizard never reports success.
        Test-WizardGoal -Name 'Placeholder: no real goal check written' -Check { $false }
        Show-Summary
        if (-not (Test-WizardSucceeded)) {
            $script:ExitCode = 1
        }
    }
    catch {
        # Log first, through helpers that never throw, then clean up.
        Write-WizardLog -Message "Wizard failed: $($_.Exception.Message)`n$($_.ScriptStackTrace)"
        Write-Colored -Message "Wizard failed: $($_.Exception.Message)" -Color Red
        Write-Say -Message "Full log: $($script:LogFilePath)"
        Uninstall-WizardSoftware
        throw
    }
    finally {
        # The elevated window closes when the script ends; hold it so the
        # summary or the failure stays readable.
        if (-not [Console]::IsInputRedirected) {
            Clear-PendingInput
            [void](Read-Host -Prompt 'Press ENTER to close this window')
        }
        Restore-WizardConsoleInput
        Stop-WizardLogging
    }
}

Invoke-Wizard
exit $script:ExitCode
