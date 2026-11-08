#Requires -Version 7.0
<#
.SYNOPSIS
    Verifies a generated ps-wizard file against the skill's bar.

.DESCRIPTION
    One command for the checks a wizard author must not have to remember:
    the file parses, the analyzer is clean, the library above the STAGES
    marker still matches the template, the stage count matches -TotalStages,
    and no known failure pattern appears in the stage code.

    Prints one PASS/FAIL line per check and exits 1 when any check fails.

.PARAMETER Path
    The generated wizard to check.

.PARAMETER TemplatePath
    The template to compare the library section against. When omitted the
    library comparison is skipped and reported as SKIP.

.EXAMPLE
    pwsh -File verify-wizard.ps1 -Path C:\path\to\wizard.ps1 -TemplatePath C:\path\to\template.ps1
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter()]
    [string]$TemplatePath = ''
)

$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()
$marker = '===== STAGES ====='

function Add-Result {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    if ($Ok) {
        Write-Output "PASS $Name"
    }
    else {
        Write-Output "FAIL $Name :: $Detail"
        $script:failures.Add("$Name :: $Detail")
    }
}

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Output "FAIL file :: missing $Path"
    exit 1
}
$lines = @(Get-Content -LiteralPath $Path)

$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$parseErrors)
Add-Result -Name 'parse' -Ok (@($parseErrors).Count -eq 0) -Detail (($parseErrors | ForEach-Object { "L$($_.Extent.StartLineNumber) $($_.Message)" }) -join '; ')

if (-not (Get-Command Invoke-ScriptAnalyzer -ErrorAction SilentlyContinue)) {
    Import-Module PSScriptAnalyzer -ErrorAction Stop
}
$findings = @(Invoke-ScriptAnalyzer -Path $Path -Severity Warning, Error, ParseError)
Add-Result -Name 'analyzer' -Ok ($findings.Count -eq 0) -Detail (($findings | ForEach-Object { "L$($_.Line) $($_.RuleName)" }) -join '; ')

$markerIndex = 0
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match [regex]::Escape($marker)) {
        $markerIndex = $i
        break
    }
}
Add-Result -Name 'stages-marker' -Ok ($markerIndex -gt 0) -Detail 'the STAGES marker line is missing'

if ($markerIndex -gt 0) {
    $library = @($lines[0..($markerIndex - 1)])
    $stageLines = @($lines[$markerIndex..($lines.Count - 1)])

    if ($TemplatePath -ne '') {
        if (-not (Test-Path -LiteralPath $TemplatePath)) {
            Add-Result -Name 'library-identity' -Ok $false -Detail "template missing: $TemplatePath"
        }
        else {
            $templateLines = @(Get-Content -LiteralPath $TemplatePath)
            $templateMarker = 0
            for ($i = 0; $i -lt $templateLines.Count; $i++) {
                if ($templateLines[$i] -match [regex]::Escape($marker)) {
                    $templateMarker = $i
                    break
                }
            }
            $templateLibrary = @($templateLines[0..($templateMarker - 1)])
            $diff = @(Compare-Object -ReferenceObject $templateLibrary -DifferenceObject $library -SyncWindow 10)
            Add-Result -Name 'library-identity' -Ok ($diff.Count -eq 0) -Detail "$($diff.Count) line(s) differ from the template above the marker"
        }
    }
    else {
        Write-Output 'SKIP library-identity :: no -TemplatePath given'
    }

    $stageText = $stageLines -join "`n"
    $stepCount = @($stageLines | Where-Object { $_ -match '^\s*Invoke-Step -Name' }).Count
    $bannerMatch = [regex]::Match($stageText, 'Show-Banner\s+-Title\s+''[^'']+''\s+-TotalStages\s+(\d+)')
    if ($bannerMatch.Success) {
        $declared = [int]$bannerMatch.Groups[1].Value
        Add-Result -Name 'stage-count' -Ok ($stepCount -eq $declared) -Detail "-TotalStages says $declared, the file has $stepCount Invoke-Step calls"
    }
    else {
        Add-Result -Name 'stage-count' -Ok $false -Detail 'no Show-Banner ... -TotalStages <n> call in the stage code'
    }

    $goalCount = @($stageLines | Where-Object { $_ -match '^\s*Test-WizardGoal -Name' }).Count
    Add-Result -Name 'goal-checks' -Ok ($goalCount -gt 0) -Detail 'no Test-WizardGoal in the stage code'

    $patterns = [ordered]@{
        'Write-Error'                 = 'Write-Error'
        'Select-Object -Unique'       = 'Select-Object\s+-Unique'
        'SilentlyContinue'            = 'SilentlyContinue'
        'Start-Process -Wait'         = 'Start-Process[^|]*-Wait'
        'setx'                        = '\bsetx\b'
        'Remove-Item wildcard'        = 'Remove-Item[^\r\n]*(-Include|-Filter|\\\*)'
        'stage param() block'         = '^param\s*\('
        'extra suppression'           = 'SuppressMessageAttribute'
        'negative state check'        = "-ne\s+'(Enabled|Disabled)'"
    }
    foreach ($name in $patterns.Keys) {
        $hitLines = @()
        for ($i = 0; $i -lt $stageLines.Count; $i++) {
            if ($stageLines[$i] -match $patterns[$name]) {
                $hitLines += ($i + $markerIndex + 1)
            }
        }
        Add-Result -Name "pattern:$name" -Ok ($hitLines.Count -eq 0) -Detail ("stage line(s) " + ($hitLines -join ','))
    }

    $launchLines = @()
    $relativeLaunches = @()
    $bunxLaunches = @()
    for ($i = 0; $i -lt $stageLines.Count; $i++) {
        $line = $stageLines[$i]
        if ($line -notmatch 'Invoke-NativeProcess') {
            continue
        }
        $launchLines += ($i + $markerIndex + 1)
        $filePathMatch = [regex]::Match($line, 'Invoke-NativeProcess\s+-FilePath\s+(\S+)')
        if ($filePathMatch.Success) {
            $expression = $filePathMatch.Groups[1].Value
            if ($expression -match "^'[^A-Z]") {
                $relativeLaunches += ($i + $markerIndex + 1)
            }
        }
        if ($line -match '\.bunx') {
            $bunxLaunches += ($i + $markerIndex + 1)
        }
    }
    Add-Result -Name 'launch:absolute-literal' -Ok ($relativeLaunches.Count -eq 0) -Detail ("non-drive literal FilePath at line(s) " + ($relativeLaunches -join ',') + '; pass a resolved variable instead')
    Add-Result -Name 'launch:no-bunx' -Ok ($bunxLaunches.Count -eq 0) -Detail ("a .bunx launcher at line(s) " + ($bunxLaunches -join ',') + '; start the .exe')
    Write-Output "INFO native launches in stage code: $($launchLines.Count)"

    $secretWrites = @()
    for ($i = 0; $i -lt $stageLines.Count; $i++) {
        if ($stageLines[$i] -match 'Write-(Say|Note|Host|Warn|Step)\s+.*\$(?:\w*(?:Token|Secret|Password|ApiKey)\w*)') {
            $secretWrites += ($i + $markerIndex + 1)
        }
    }
    Add-Result -Name 'secret:not-echoed' -Ok ($secretWrites.Count -eq 0) -Detail ("a secret-named variable reaches human output at line(s) " + ($secretWrites -join ','))

    $gateCount = @($stageLines | Where-Object { $_ -match '^\s*Wait-HumanAction' }).Count
    Write-Output "INFO human-action gates in stage code: $gateCount (each must sit inside a branch that prints manual instructions)"
}

if ($failures.Count -gt 0) {
    Write-Output "RESULT $($failures.Count) check(s) failed"
    exit 1
}
Write-Output 'RESULT all checks passed'
exit 0
