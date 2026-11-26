#!/usr/bin/env pwsh
# Run-Batch.ps1 - sequential batch runner + finalizer for the dvd-concert-curation merge driver.
# One child pwsh process per folder so driver exit codes cannot unwind this loop.
# Console + per-folder driver output teed to batch-console.log beside this script.
#
# Retro fixes folded in (2026-11-17):
#   - manifest pre-flight before every folder: a manifest being regenerated
#     concurrently once failed all 16 folders instantly (18-second sweep);
#   - driver hash stability check: detects the driver being edited mid-run;
#   - failed folders get exactly one retry after the sweep (the four 2026-11-17
#     failures were transient probe misses that a retry resolves);
#   - closing census proves the end state on the actual disk surface:
#     outputs exist, movement sources deleted, title-rip counts unchanged.
#   - exit-capture fix (2026-11-18, E8 owner addendum): Invoke-Folder's Tee-Object
#     pass-through polluted the function return value ($exits stored the log
#     strings plus the exit code, so -ne 0 marked passing folders failed);
#     tee output now goes to Out-Host and only the exit code is returned.
#
# Default folder list is derived from manifest.json; pass -Folders to run a subset.

[CmdletBinding()]
param(
    [string]$DriverPath = (Join-Path $PSScriptRoot 'Invoke-Merge.ps1'),
    [string]$ManifestPath = (Join-Path $PSScriptRoot 'manifest.json'),
    [string]$LogPath = (Join-Path $PSScriptRoot 'batch-console.log'),
    [string]$DvdsRoot = 'D:\DVDs',
    [string[]]$Folders = @()
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Read-Manifest {
    param([string]$Path)
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding Utf8
    $m = $raw | ConvertFrom-Json
    if ($null -eq $m.folders) { throw "manifest has no folders array: $Path" }
    return $m
}

function Invoke-Folder {
    param([string]$Name)
    "=== BEGIN $Name ===" | Tee-Object -FilePath $LogPath -Append | Out-Host
    & pwsh -NoProfile -File $DriverPath -Folder $Name *>&1 | Tee-Object -FilePath $LogPath -Append | Out-Host
    $code = $LASTEXITCODE
    "=== END $Name exit=$code ===" | Tee-Object -FilePath $LogPath -Append | Out-Host
    return $code
}

if (-not (Test-Path -LiteralPath $DriverPath)) { throw "driver not found: $DriverPath" }
$driverHash = (Get-FileHash -LiteralPath $DriverPath -Algorithm SHA256).Hash

$manifest = Read-Manifest -Path $ManifestPath
$manifestFolders = @($manifest.folders | ForEach-Object { $_.folder })
$folders = $(if ($Folders.Count -gt 0) { $Folders } else { $manifestFolders })

# Title-rip snapshot for the closing census.
$titlesBefore = @{}
foreach ($name in $folders) {
    $titlesBefore[$name] = @(Get-ChildItem -LiteralPath (Join-Path $DvdsRoot $name) -Filter 'title *.mkv' -File -ErrorAction SilentlyContinue).Count
}

"batch start $((Get-Date).ToUniversalTime().ToString('o')) | folders: $($folders.Count) | D free GB: $([math]::Round((Get-PSDrive D).Free/1GB,2))" | Tee-Object -FilePath $LogPath -Append
$exits = [ordered]@{}
foreach ($f in $folders) {
    # Pre-flight: manifest must parse and contain this folder.
    try {
        $manifest = Read-Manifest -Path $ManifestPath
        if ($manifestFolders -notcontains $f) {
            "SKIP $f (not in manifest)" | Tee-Object -FilePath $LogPath -Append
            $exits[$f] = 98
            continue
        }
    }
    catch {
        "FATAL: manifest pre-flight failed for $f : $($_.Exception.Message)" | Tee-Object -FilePath $LogPath -Append
        $exits[$f] = 99
        continue
    }
    $hashNow = (Get-FileHash -LiteralPath $DriverPath -Algorithm SHA256).Hash
    if ($hashNow -ne $driverHash) {
        "FATAL: driver changed on disk mid-run; stopping the sweep. Re-run Run-Batch after the edit settles." | Tee-Object -FilePath $LogPath -Append
        break
    }
    $exits[$f] = Invoke-Folder -Name $f
}

# One retry pass over failed folders.
$failed = @($exits.Keys | Where-Object { $exits[$_] -ne 0 })
if ($failed.Count -gt 0) {
    "retry pass: $($failed.Count) folder(s)" | Tee-Object -FilePath $LogPath -Append
    foreach ($f in $failed) { $exits[$f] = Invoke-Folder -Name $f }
}

# Closing census: prove the end state on the actual disk surface, for the folders this run covered.
$manifest = Read-Manifest -Path $ManifestPath
$outMissing = @()
$srcLeft = @()
$titleChanged = @()
$outCount = 0
$srcCount = 0
foreach ($f in @($manifest.folders)) {
    if ($folders -notcontains $f.folder) { continue }
    $fp = Join-Path $DvdsRoot $f.folder
    foreach ($o in @($f.outputs)) {
        $outCount++
        if (-not (Test-Path -LiteralPath (Join-Path $fp $o.outputName))) { $outMissing += "$($f.folder) :: $($o.outputName)" }
        foreach ($s in @($o.sources)) {
            $srcCount++
            if (Test-Path -LiteralPath (Join-Path $fp $s.file)) { $srcLeft += "$($f.folder) :: $($s.file)" }
        }
    }
    foreach ($sd in @($f.standalones)) {
        $outCount++
        if (-not (Test-Path -LiteralPath (Join-Path $fp $sd.outputName))) { $outMissing += "$($f.folder) :: $($sd.outputName)" }
        foreach ($s in @($sd.sources)) {
            $srcCount++
            if (Test-Path -LiteralPath (Join-Path $fp $s.file)) { $srcLeft += "$($f.folder) :: $($s.file)" }
        }
    }
    $tNow = @(Get-ChildItem -LiteralPath $fp -Filter 'title *.mkv' -File -ErrorAction SilentlyContinue).Count
    if ($tNow -ne $titlesBefore[$f.folder]) { $titleChanged += $f.folder }
}
"census: outputs $outCount, missing $(@($outMissing).Count); sources $srcCount, still present $(@($srcLeft).Count); title-rip count changed in $(@($titleChanged).Count) folder(s)" | Tee-Object -FilePath $LogPath -Append
foreach ($x in $outMissing) { "  MISSING OUT: $x" | Tee-Object -FilePath $LogPath -Append }
foreach ($x in $srcLeft) { "  SRC STILL PRESENT: $x" | Tee-Object -FilePath $LogPath -Append }
foreach ($x in $titleChanged) { "  TITLE RIPS CHANGED: $x" | Tee-Object -FilePath $LogPath -Append }

$passCount = @($exits.Keys | Where-Object { $exits[$_] -eq 0 }).Count
"batch done $((Get-Date).ToUniversalTime().ToString('o')) | folder pass: $passCount/$($folders.Count) | D free GB: $([math]::Round((Get-PSDrive D).Free/1GB,2))" | Tee-Object -FilePath $LogPath -Append
$exits.Keys | ForEach-Object { "exit $($exits[$_]): $_" } | Tee-Object -FilePath $LogPath -Append

if (($outMissing.Count -gt 0) -or ($srcLeft.Count -gt 0) -or ($titleChanged.Count -gt 0) -or ($passCount -lt $folders.Count)) { exit 1 }
exit 0
