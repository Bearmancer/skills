#Requires -Version 7.0
<#
.SYNOPSIS
    Smoke test: launches a generated no-input wizard through the .ps1 open verb and asserts its wizard.log reports completion.
#>
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$base = "$desktop\ps-wizard"
$wizard = "$env:TEMP\ps-wizard-smoke-wizard.ps1"
$body = @'
#Requires -Version 7.0
#Requires -RunAsAdministrator
Import-Module "$HOME\.agents\skills\ps-wizard\PsWizard.psm1" -Force
$code = Start-WizardRun -Title 'Smoke wizard' -Steps 2
try {
    Assert-WizardPrerequisite -Path @('C:\Windows\System32')
    Invoke-WizardStep 'Write'
    Test-WizardGoal 'run is live' { $true }
    Invoke-WizardStep 'Verify'
    $code = Complete-WizardRun
}
catch { $code = Complete-WizardFailure $_ }
finally { Stop-WizardRun }
Write-WizardLog "SMR smoke finished with exit code $code"
exit $code
'@
[IO.File]::WriteAllText($wizard, $body)

$marker = 'SMR smoke finished with exit code 0'
$runDir = ''
$found = $false
$deadline = (Get-Date).AddSeconds(40)
do {
    $dirs = @([IO.Directory]::EnumerateFiles($base, '*wizard.log', 'AllDirectories') |
        Where-Object { [IO.File]::ReadAllText($_) -match $marker } |
        ForEach-Object { [IO.Path]::GetDirectoryName($_) })
    if ($dirs.Count -gt 0) { $runDir = $dirs[0]; $found = $true }
    if (-not $found) { Start-Sleep -Milliseconds 500 }
} while (-not $found -and ((Get-Date) -lt $deadline))

$pass = $found
if ($pass) { Write-Output "PASS smoke-launch :: the open verb launched the wizard; wizard.log contains '$marker'" } else { Write-Output "FAIL smoke-launch :: no wizard.log with '$marker' under $base" }
Get-CimInstance Win32_Process | ? { $_.CommandLine -match 'ps-wizard-smoke-wizard' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if ($runDir) { Remove-Item -Recurse -Force -LiteralPath $runDir -ErrorAction SilentlyContinue }
Remove-Item -Force -LiteralPath $wizard -ErrorAction SilentlyContinue
exit $pass ? 0 : 1
