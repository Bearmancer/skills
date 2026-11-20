#Requires -Version 7.0
<#
.SYNOPSIS
    Verifies a ps-wizard file against the skill's bar.
.DESCRIPTION
    One command for the checks a wizard author must not have to remember:
    the file parses, the analyzer is clean, there are no comments, the
    skeleton is intact, the step count matches, goal checks exist, and no
    known failure pattern appears. Prints one PASS/FAIL line per check and
    exits 1 when any check fails.
.PARAMETER Path
    The wizard to check.
.EXAMPLE
    pwsh -File verify-wizard.ps1 -Path C:\path\to\wizard.ps1
#>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Path)

$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()

function Add-Result {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    if ($Ok) { Write-Output "PASS $Name" }
    else {
        Write-Output "FAIL $Name :: $Detail"
        $script:failures.Add("$Name :: $Detail")
    }
}

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Output "FAIL file :: missing $Path"
    exit 1
}
$text = Get-Content -LiteralPath $Path -Raw
$lines = @($text -split "`r?`n")

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($text, [ref]$tokens, [ref]$parseErrors)
Add-Result 'parse' (@($parseErrors).Count -eq 0) (($parseErrors | ForEach-Object { "L$($_.Extent.StartLineNumber) $($_.Message)" }) -join '; ')

if (-not (Get-Command Invoke-ScriptAnalyzer -ErrorAction SilentlyContinue)) { Import-Module PSScriptAnalyzer }
$findings = @(Invoke-ScriptAnalyzer -Path $Path -Severity Warning, Error, ParseError)
Add-Result 'analyzer' ($findings.Count -eq 0) (($findings | ForEach-Object { "L$($_.Line) $($_.RuleName)" }) -join '; ')

$comments = @($tokens | Where-Object { $_.Kind -eq 'Comment' -and $_.Text -notmatch '^#Requires\s' })
Add-Result 'no-comments' ($comments.Count -eq 0) ("comment(s) at line(s) " + (($comments | ForEach-Object { $_.Extent.StartLineNumber }) -join ','))

Add-Result 'requires-pwsh7' ($text -match '#Requires\s+-Version\s+7') 'missing #Requires -Version 7.0'
Add-Result 'requires-admin' ($text -match '#Requires\s+-RunAsAdministrator') 'missing #Requires -RunAsAdministrator'
Add-Result 'module-import' ($text -match 'Import-Module\s+[^\r\n]*PsWizard\.psm1') 'missing Import-Module of PsWizard.psm1'

foreach ($call in 'Start-WizardRun', 'Complete-WizardRun', 'Complete-WizardFailure', 'Stop-WizardRun') {
    Add-Result "skeleton:$call" ($text -match [regex]::Escape($call)) "no $call call"
}
Add-Result 'skeleton:exit' ($text -match '(?m)^\s*exit\s+\$') 'no exit with the returned code'

$paramBlocks = @($ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParamBlockAst] -and $args[0].Parent -is [System.Management.Automation.Language.ScriptBlockAst] }, $true))
Add-Result 'no-param-block' ($paramBlocks.Count -eq 0) 'a wizard exposes no parameters'

$steps = [regex]::Match($text, 'Start-WizardRun[^\r\n]*-Steps\s+(\d+)')
$stepCalls = @([regex]::Matches($text, 'Invoke-WizardStep\s')).Count
if ($steps.Success) {
    Add-Result 'step-count' ([int]$steps.Groups[1].Value -eq $stepCalls) "-Steps says $($steps.Groups[1].Value), the file has $stepCalls Invoke-WizardStep calls"
}
else { Add-Result 'step-count' $false 'Start-WizardRun has no literal -Steps count' }

$goalCount = @([regex]::Matches($text, 'Test-WizardGoal\s')).Count
Add-Result 'goal-checks' ($goalCount -gt 0) 'no Test-WizardGoal call'

$patterns = [ordered]@{
    'Write-Error'           = 'Write-Error'
    'Select-Object -Unique' = 'Select-Object\s+-Unique'
    'SilentlyContinue'      = 'SilentlyContinue'
    'Start-Process -Wait'   = 'Start-Process[^|\r\n]*-Wait'
    'setx'                  = '\bsetx\b'
    'Remove-Item wildcard'  = 'Remove-Item[^\r\n]*(-Include|-Filter|\\\*)'
    'extra suppression'     = 'SuppressMessageAttribute'
    'negative state check'  = "-ne\s+'(Enabled|Disabled)'"
    'powershell 5.1'        = '\bpowershell\.exe\b|-UseWindowsPowerShell'
    'Confirm-Choice'        = '\bConfirm-Choice\b'
}
foreach ($name in $patterns.Keys) {
    $hitLines = @(for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match $patterns[$name]) { $i + 1 } })
    Add-Result "pattern:$name" ($hitLines.Count -eq 0) ("line(s) " + ($hitLines -join ','))
}

$installCalls = @([regex]::Matches($text, '(?i)\b(winget\s+install|Install-Module|Install-Package|npm\s+i(nstall)?\s+-g|bun\s+(add|install)\s+-g)\b')).Count
$registerCalls = @([regex]::Matches($text, 'Register-InstalledSoftware\s')).Count
if ($installCalls -gt 0) {
    Add-Result 'installs-registered' ($registerCalls -ge $installCalls) "$installCalls install command(s), $registerCalls Register-InstalledSoftware call(s)"
}
else { Write-Output 'SKIP installs-registered :: no install commands found' }

$writes = @([regex]::Matches($text, 'Write-PersistedValue\s|Remove-Item\s')).Count
if ($writes -gt 0) {
    Add-Result 'backup-present' ($text -match 'Invoke-QuickBackup\s') 'the wizard writes or deletes but never backs up'
}
else { Write-Output 'SKIP backup-present :: no writes or deletes found' }

$closeCalls = @([regex]::Matches($text, 'Close-BlockingProcess[^\r\n]*'))
$unconsented = @($closeCalls | Where-Object { $_.Value -notmatch '-NoUnsavedWork|-AllowUnsavedWorkLoss' })
if ($closeCalls.Count -gt 0) {
    Add-Result 'blocker-consent' ($unconsented.Count -eq 0) 'Close-BlockingProcess without -NoUnsavedWork or -AllowUnsavedWorkLoss'
}
else { Write-Output 'SKIP blocker-consent :: no Close-BlockingProcess call' }

$relativeLaunches = @()
$bunxLaunches = @()
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -notmatch 'Invoke-NativeProcess') { continue }
    $m = [regex]::Match($lines[$i], 'Invoke-NativeProcess\s+(?:-FilePath\s+)?(\S+)')
    if ($m.Success -and $m.Groups[1].Value -match "^'(?![A-Za-z]:)") { $relativeLaunches += ($i + 1) }
    if ($lines[$i] -match '\.bunx') { $bunxLaunches += ($i + 1) }
}
Add-Result 'launch:absolute-literal' ($relativeLaunches.Count -eq 0) ("non-drive literal launch path at line(s) " + ($relativeLaunches -join ',') + '; pass a resolved variable instead')
Add-Result 'launch:no-bunx' ($bunxLaunches.Count -eq 0) ("a .bunx launcher at line(s) " + ($bunxLaunches -join ',') + '; start the .exe')

$secretEcho = @(for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match 'Write-(WizardStatus|WizardLog|Host|Verbose|Warning|Output)\s[^\r\n]*\$(?:\w*(?:Token|Secret|Password|ApiKey)\w*)') { $i + 1 }
})
Add-Result 'secret:not-echoed' ($secretEcho.Count -eq 0) ("a secret-named variable reaches output at line(s) " + ($secretEcho -join ','))

$pathMap = @{}
foreach ($line in $lines) {
    $m = [regex]::Match($line, "\`$(\w+)\s*=\s*'([A-Za-z]:\\[^']*)'")
    if ($m.Success) { $pathMap[$m.Groups[1].Value] = $m.Groups[2].Value }
}
$required = [System.Collections.Generic.List[string]]::new()
foreach ($m in [regex]::Matches($text, 'Assert-WizardPrerequisite[^\r\n]*-Path\s+@\(([^)]*)\)')) {
    foreach ($token in ($m.Groups[1].Value -split ',')) {
        $t = $token.Trim()
        if ($t -match "^'([A-Za-z]:\\[^']*)'$") { $required.Add($Matches[1]) }
        elseif ($t -match '^\$(?:script:)?(\w+)$' -and $pathMap.ContainsKey($Matches[1])) { $required.Add($pathMap[$Matches[1]]) }
    }
}
$missingPaths = @($required | Sort-Object -Unique | Where-Object { -not (Test-Path -LiteralPath $_) })
Add-Result 'path:required-exist' ($missingPaths.Count -eq 0) ("missing literal path(s): " + ($missingPaths -join ' | '))
Write-Output "INFO required literal paths checked: $(@($required | Sort-Object -Unique).Count)"

if ($failures.Count -gt 0) {
    Write-Output "RESULT $($failures.Count) check(s) failed"
    exit 1
}
Write-Output 'RESULT all checks passed'
exit 0
