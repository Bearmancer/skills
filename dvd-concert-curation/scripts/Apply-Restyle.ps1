#Requires -Version 7
<#
Apply-Restyle.ps1 - executes phase1-mapping.json v3 (FINAL) on D:\DVDs.
applyOrder: 1 delete 6 trailers (old paths) -> 2 rename 17 folders -> 3 rename 83 files
-> 4 mkvpropedit segment+global TITLE (83) -> 5 tags.json sync (69 edits, title_file last)
-> 6 read-only surface verification (mkvmerge -J + mkvextract tags; never ffprobe).
STOP-DON'T-REPAIR: first failure halts; apply-log.json records every action result.
-PreflightOnly runs all read-only gates without touching D:\DVDs.
-VerifyOnly resumes step 6 after a halt (steps 1-5 must already be complete in apply-log.json).
All MKVToolNix stdout is captured via Process with explicit UTF-8 decoding (console code page
on this host is ibm437, which corrupts UTF-8 BOMs and accented titles if decoded natively).
#>
[CmdletBinding()]
param([switch]$PreflightOnly, [switch]$VerifyOnly)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { Write-Verbose 'Console output encoding unchanged (display only; tool capture uses explicit UTF-8).' }

$WorkDir     = 'C:\Users\Lance\AppData\Local\Temp\opencode\dvd-titles'
$MappingPath = Join-Path $WorkDir 'phase1-mapping.json'
$LogPath     = Join-Path $WorkDir 'apply-log.json'
$BackupDir   = Join-Path $WorkDir 'tags-backups'
$XmlDir      = Join-Path $WorkDir 'tags-xml'
$MkvToolDir  = 'C:\Program Files\MKVToolNix'
$Root        = 'D:\DVDs'
$MaxPathLen  = 240

$script:Log = [ordered]@{
    script         = 'Apply-Restyle.ps1'
    mappingFile    = $MappingPath
    mappingVersion = $null
    mappingSha256  = $null
    startedUtc     = (Get-Date).ToUniversalTime().ToString('o')
    finishedUtc    = $null
    status         = 'running'
    halt           = $null
    preflight      = [ordered]@{ pass = $false; checks = @() }
    trailersDeleted = @()
    foldersRenamed  = @()
    filesRenamed    = @()
    filesRetitled   = @()
    tagsBackups     = @()
    tagsEdits       = @()
    tagsWrites      = @()
    verification    = [ordered]@{
        files = @(); tagsHarmony = @(); census = @()
        passCount = 0; failCount = 0; maxPathLength = 0; maxPath = $null
    }
    counts = [ordered]@{}
}

function Save-ApplyLog {
    $json = $script:Log | ConvertTo-Json -Depth 30
    [System.IO.File]::WriteAllText($LogPath, $json, [System.Text.UTF8Encoding]::new($false))
}

function Stop-Apply {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '')]
    param([string]$Stage, [string]$Message, $Context = $null)
    $script:Log.status = 'halted'
    $script:Log.finishedUtc = (Get-Date).ToUniversalTime().ToString('o')
    $script:Log.halt = [ordered]@{ stage = $Stage; message = $Message; context = $Context; utc = (Get-Date).ToUniversalTime().ToString('o') }
    try { Save-ApplyLog } catch { Write-Host "LOG FLUSH FAILED: $_" -ForegroundColor Red }
    Write-Host "HALT [$Stage]: $Message" -ForegroundColor Red
    if ($null -ne $Context) { Write-Host ($Context | ConvertTo-Json -Depth 15) -ForegroundColor Red }
    exit 1
}

function Add-PreflightCheck {
    param([string]$Name, [bool]$Pass, $Detail = $null)
    $script:Log.preflight.checks += [ordered]@{ name = $Name; pass = $Pass; detail = $Detail }
    if ($Pass) { Write-Host "  ok  $Name" -ForegroundColor DarkGreen }
    else { Write-Host "  FAIL $Name - $Detail" -ForegroundColor Red }
}

function Invoke-Utf8Tool {
    param([string]$Exe, [string[]]$Arguments)
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $Exe
    foreach ($a in $Arguments) { [void]$psi.ArgumentList.Add($a) }
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $p = [System.Diagnostics.Process]::Start($psi)
    $stderrTask = $p.StandardError.ReadToEndAsync()
    $stdout = $p.StandardOutput.ReadToEnd()
    $p.WaitForExit()
    @{ ExitCode = $p.ExitCode; StdOut = $stdout; StdErr = $stderrTask.Result }
}

function Get-TagsProfile {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    $isUtf16 = ($bytes.Length -ge 2 -and (($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) -or ($bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF)))
    $text = [System.IO.File]::ReadAllText($Path)
    $eol = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $trailing = $text.EndsWith("`n")
    $indent = 2
    $m = [regex]::Match($text, '(?m)^( +)\S')
    if ($m.Success) { $indent = $m.Groups[1].Value.Length }
    [ordered]@{ HasBom = $hasBom; IsUtf16 = $isUtf16; Eol = $eol; TrailingNewline = $trailing; IndentSize = $indent; Text = $text }
}

function ConvertTo-TagsJsonText {
    param([System.Text.Json.Nodes.JsonNode]$Node, $Prof)
    $opts = [System.Text.Json.JsonSerializerOptions]::new()
    $opts.WriteIndented = $true
    $opts.IndentSize = $Prof.IndentSize
    $opts.NewLine = $Prof.Eol
    $opts.Encoder = [System.Text.Encodings.Web.JavaScriptEncoder]::UnsafeRelaxedJsonEscaping
    $text = [System.Text.Json.JsonSerializer]::Serialize($Node, $opts)
    if ($Prof.TrailingNewline) { $text += $Prof.Eol }
    $text
}

function Find-TitleIndex {
    param($Arr, [string]$TitleFile)
    if ($Arr -isnot [System.Text.Json.Nodes.JsonArray]) { throw 'title_file selector applied to non-array' }
    $hits = @()
    for ($i = 0; $i -lt $Arr.Count; $i++) {
        $tf = $Arr[$i]['title_file']
        if ($null -ne $tf -and $tf.GetValue[string]() -ceq $TitleFile) { $hits += $i }
    }
    if ($hits.Count -ne 1) { throw "title_file='$TitleFile' matched $($hits.Count) entries (need exactly 1)" }
    $hits[0]
}

function Find-ChapterIndex {
    param($Arr, [int]$Chapter)
    if ($Arr -isnot [System.Text.Json.Nodes.JsonArray]) { throw 'chapter selector applied to non-array' }
    $hits = @()
    for ($i = 0; $i -lt $Arr.Count; $i++) {
        $c = $Arr[$i]['chapter']
        if ($null -ne $c -and $c.GetValue[int]() -eq $Chapter) { $hits += $i }
    }
    if ($hits.Count -ne 1) { throw "chapter=$Chapter matched $($hits.Count) entries (need exactly 1)" }
    $hits[0]
}

function Resolve-TagsSelector {
    param([System.Text.Json.Nodes.JsonNode]$RootNode, [string]$Selector)
    $parts = @(); $depth = 0; $cur = ''
    foreach ($ch in $Selector.ToCharArray()) {
        if ($ch -eq '[') { $depth++; $cur += $ch }
        elseif ($ch -eq ']') { $depth--; $cur += $ch }
        elseif ($ch -eq '.' -and $depth -eq 0) { $parts += $cur; $cur = '' }
        else { $cur += $ch }
    }
    if ($cur) { $parts += $cur }
    $steps = @()
    foreach ($p in $parts) {
        $m = [regex]::Match($p, '^([A-Za-z_][A-Za-z0-9_]*)(.*)$')
        if (-not $m.Success) { throw "bad selector part '$p' in '$Selector'" }
        $steps += @{ Kind = 'prop'; Name = $m.Groups[1].Value }
        $rest = $m.Groups[2].Value
        $bm = [regex]::Matches($rest, "\[title_file='([^']*)'\]|\[chapter=(\d+)\]|\[(\d+)\]")
        $consumed = ($bm | ForEach-Object { $_.Value }) -join ''
        if ($consumed -cne $rest) { throw "bad selector brackets '$rest' in '$Selector'" }
        foreach ($b in $bm) {
            if ($b.Groups[1].Success) { $steps += @{ Kind = 'title_file'; Value = $b.Groups[1].Value } }
            elseif ($b.Groups[2].Success) { $steps += @{ Kind = 'chapter'; Value = [int]$b.Groups[2].Value } }
            else { $steps += @{ Kind = 'index'; Value = [int]$b.Groups[3].Value } }
        }
    }
    if ($steps.Count -lt 1) { throw 'empty selector' }
    $node = $RootNode
    $pathParts = @()
    for ($i = 0; $i -lt $steps.Count - 1; $i++) {
        $s = $steps[$i]
        switch ($s.Kind) {
            'prop' {
                if ($node -isnot [System.Text.Json.Nodes.JsonObject] -or -not $node.ContainsKey($s.Name)) { throw "selector '$Selector': missing property '$($s.Name)'" }
                $node = $node[$s.Name]; $pathParts += $s.Name
            }
            'title_file' { $idx = Find-TitleIndex $node $s.Value; $node = $node[$idx]; $pathParts[-1] = "$($pathParts[-1])[$idx]" }
            'chapter'    { $idx = Find-ChapterIndex $node $s.Value; $node = $node[$idx]; $pathParts[-1] = "$($pathParts[-1])[$idx]" }
            'index'      { $node = $node[$s.Value]; $pathParts[-1] = "$($pathParts[-1])[$($s.Value)]" }
        }
    }
    $last = $steps[-1]
    $key = $null
    switch ($last.Kind) {
        'prop' {
            if ($node -isnot [System.Text.Json.Nodes.JsonObject] -or -not $node.ContainsKey($last.Name)) { throw "selector '$Selector': missing target property '$($last.Name)'" }
            $key = $last.Name
        }
        'index' {
            if ($node -isnot [System.Text.Json.Nodes.JsonArray] -or $last.Value -ge $node.Count) { throw "selector '$Selector': index $($last.Value) out of range" }
            $key = $last.Value
        }
        'title_file' { $key = Find-TitleIndex $node $last.Value }
        'chapter'    { $key = Find-ChapterIndex $node $last.Value }
    }
    $basePath = $pathParts -join '.'
    $leaf = if ($last.Kind -eq 'prop') { $key } else { "[$key]" }
    $resolvedPath = if ($basePath) { if ($last.Kind -eq 'prop') { "$basePath.$key" } else { "$basePath[$key]" } } else { $leaf }
    @{ Parent = $node; Key = $key; Path = $resolvedPath; Current = $node[$key] }
}

function Get-NodeAtPath {
    param([System.Text.Json.Nodes.JsonNode]$RootNode, [string]$Path)
    $n = $RootNode
    foreach ($seg in ($Path -split '\.')) {
        $pm = [regex]::Match($seg, '^([A-Za-z_][A-Za-z0-9_]*)((\[\d+\])*)$')
        if (-not $pm.Success) { throw "bad resolved path segment '$seg'" }
        $n = $n[$pm.Groups[1].Value]
        foreach ($im in [regex]::Matches($pm.Groups[2].Value, '\[(\d+)\]')) { $n = $n[[int]$im.Groups[1].Value] }
    }
    return ,$n
}

function Test-EditFromMatch {
    param($Resolved, $FromValue)
    $fromNode = [System.Text.Json.JsonSerializer]::SerializeToNode[object]($FromValue)
    [System.Text.Json.Nodes.JsonNode]::DeepEquals($Resolved.Current, $fromNode)
}

function Set-TagsValue {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '')]
    param($Resolved, $ToValue)
    $newNode = [System.Text.Json.JsonSerializer]::SerializeToNode[object]($ToValue)
    $Resolved.Parent[$Resolved.Key] = $newNode
}

function Get-JsonDiffPath {
    param($A, $B, [string]$Path)
    $out = @()
    if ($null -eq $A -or $null -eq $B) {
        if (-not [System.Text.Json.Nodes.JsonNode]::DeepEquals($A, $B)) { $out += $Path }
        return $out
    }
    if ($A -is [System.Text.Json.Nodes.JsonObject] -and $B -is [System.Text.Json.Nodes.JsonObject]) {
        $keysA = @($A.AsObject() | ForEach-Object { $_.Key })
        $keysB = @($B.AsObject() | ForEach-Object { $_.Key })
        foreach ($k in @($keysA + $keysB | Select-Object -Unique)) {
            $childPath = if ($Path) { "$Path.$k" } else { $k }
            $av = $null
            if ($A.ContainsKey($k)) { $av = $A[$k] }
            $bv = $null
            if ($B.ContainsKey($k)) { $bv = $B[$k] }
            $out += Get-JsonDiffPath $av $bv $childPath
        }
    }
    elseif ($A -is [System.Text.Json.Nodes.JsonArray] -and $B -is [System.Text.Json.Nodes.JsonArray]) {
        if ($A.Count -ne $B.Count) { $out += $Path }
        else { for ($i = 0; $i -lt $A.Count; $i++) { $out += Get-JsonDiffPath $A[$i] $B[$i] "$Path[$i]" } }
    }
    else {
        if (-not [System.Text.Json.Nodes.JsonNode]::DeepEquals($A, $B)) { $out += $Path }
    }
    return $out
}

function ConvertTo-XmlEscaped {
    param([string]$s)
    $s.Replace('&', '&amp;').Replace('<', '&lt;').Replace('>', '&gt;').Replace('"', '&quot;').Replace("'", '&apos;')
}

function Get-MkvSegmentTitle {
    param([string]$FilePath)
    $r = Invoke-Utf8Tool (Join-Path $MkvToolDir 'mkvmerge.exe') @('-J', $FilePath)
    if ($r.ExitCode -ne 0) { throw "mkvmerge -J exit $($r.ExitCode): $($r.StdErr)" }
    $j = $r.StdOut | ConvertFrom-Json
    $j.container.properties.title
}

function Get-MkvGlobalTitle {
    param([string]$FilePath)
    $r = Invoke-Utf8Tool (Join-Path $MkvToolDir 'mkvextract.exe') @('tags', $FilePath)
    if ($r.ExitCode -ne 0) { throw "mkvextract tags exit $($r.ExitCode): $($r.StdErr)" }
    $tagsText = $r.StdOut
    $declIdx = $tagsText.IndexOf('<?xml')
    if ($declIdx -lt 0) { throw 'mkvextract tags output has no XML declaration' }
    $doc = [xml]$tagsText.Substring($declIdx)
    $found = @()
    foreach ($tag in $doc.Tags.Tag) {
        $targets = $tag.Targets
        $isGlobal = $true
        if ($null -ne $targets) {
            if ($targets.TargetType) { $isGlobal = $false }
            foreach ($uid in 'TrackUID','EditionUID','ChapterUID','AttachmentUID') { if ($targets.$uid) { $isGlobal = $false } }
            if ($targets.TargetTypeValue -and $targets.TargetTypeValue -ne '50') { $isGlobal = $false }
        }
        if ($isGlobal) {
            foreach ($simple in $tag.Simple) { if ($simple.Name -ceq 'TITLE') { $found += $simple.String } }
        }
    }
    if ($found.Count -ne 1) { throw "expected exactly 1 global TITLE tag, found $($found.Count)" }
    $found[0]
}

function Invoke-PostApplyVerification {
    Write-Host '=== STEP 6: post-apply verification (read-only surface) ===' -ForegroundColor Cyan
    $passCount = 0
    foreach ($r in $script:KeptRows) {
        $fileP = Join-Path (Join-Path $Root $r.newFolder) $r.newFile
        $entry = [ordered]@{ path = $fileP; expected = $r.newTitle; stem = $null; segmentTitle = $null; globalTitle = $null; pathLength = $fileP.Length; pass = $false; error = $null }
        try {
            if (-not (Test-Path -LiteralPath $fileP -PathType Leaf)) { throw 'file missing' }
            $entry.stem = [System.IO.Path]::GetFileNameWithoutExtension($fileP)
            if ($entry.stem -cne $r.newTitle) { throw 'stem != newTitle' }
            if ($fileP.Length -gt $MaxPathLen) { throw "path length $($fileP.Length) > $MaxPathLen" }
            $entry.segmentTitle = Get-MkvSegmentTitle $fileP
            if ($entry.segmentTitle -cne $r.newTitle) { throw "segment title mismatch: [$($entry.segmentTitle)]" }
            $entry.globalTitle = Get-MkvGlobalTitle $fileP
            if ($entry.globalTitle -cne $r.newTitle) { throw "global TITLE mismatch: [$($entry.globalTitle)]" }
            $entry.pass = $true
            $passCount++
            if ($fileP.Length -gt $script:Log.verification.maxPathLength) {
                $script:Log.verification.maxPathLength = $fileP.Length
                $script:Log.verification.maxPath = $fileP
            }
        } catch {
            $entry.error = $_.Exception.Message
            $script:Log.verification.files += $entry
            $script:Log.verification.failCount++
            Save-ApplyLog
            Stop-Apply 'verify-file' $_.Exception.Message $entry
        }
        $script:Log.verification.files += $entry
        Write-Host "  verified [$passCount/83] $($r.newTitle)" -ForegroundColor Green
    }
    $script:Log.verification.passCount = $passCount
    Save-ApplyLog

    foreach ($f in $script:FolderNames) {
        $plan = $script:FolderPlan[$f]
        $tagsP = Join-Path (Join-Path $Root $plan.NewFolder) 'tags.json'
        $backupP = Join-Path (Join-Path $BackupDir $f) 'tags.json'
        $cur = [System.Text.Json.Nodes.JsonNode]::Parse([System.IO.File]::ReadAllText($tagsP))
        $bak = [System.Text.Json.Nodes.JsonNode]::Parse([System.IO.File]::ReadAllText($backupP))
        $diffs = @(Get-JsonDiffPath $bak $cur '')
        $expected = @($plan.ResolvedEdits | ForEach-Object Path)
        $unexpected = @(Compare-Object $diffs $expected | Where-Object SideIndicator -eq '=>').Count
        $missing = @(Compare-Object $diffs $expected | Where-Object SideIndicator -eq '<=').Count
        $valuesOk = $true
        foreach ($re in $plan.ResolvedEdits) {
            $n = Get-NodeAtPath $cur $re.Path
            $toNode = [System.Text.Json.JsonSerializer]::SerializeToNode[object]($re.Edit.to)
            if (-not [System.Text.Json.Nodes.JsonNode]::DeepEquals($n, $toNode)) { $valuesOk = $false }
        }
        $trailerOk = $true
        foreach ($tf in $plan.TrailerCanon.Keys) {
            $tIdx = Find-TitleIndex $cur['titles'] $tf
            if ($cur['titles'][$tIdx].ToJsonString() -cne $plan.TrailerCanon[$tf]) { $trailerOk = $false }
        }
        $harmony = [ordered]@{ folder = $f; tagsPath = $tagsP; editsVerified = $expected.Count; diffPaths = $diffs; unexpectedDiffs = $unexpected; missingDiffs = $missing; editValuesMatch = $valuesOk; trailerEntriesUnchanged = $trailerOk; pass = ($unexpected -eq 0 -and $missing -eq 0 -and $valuesOk -and $trailerOk) }
        $script:Log.verification.tagsHarmony += $harmony
        Save-ApplyLog
        if (-not $harmony.pass) { Stop-Apply 'verify-tags-harmony' 'tags.json harmony failed' $harmony }
        Write-Host "  tags harmony $f - $($expected.Count) edits, 0 unexpected diffs" -ForegroundColor Green
    }

    $censusTotal = 0
    foreach ($f in $script:FolderNames) {
        $plan = $script:FolderPlan[$f]
        $dir = Join-Path $Root $plan.NewFolder
        $diskMkvs = @(Get-ChildItem -LiteralPath $dir -Filter '*.mkv' -File | ForEach-Object Name | Sort-Object)
        $expectedNames = @($plan.KeptRows | ForEach-Object newFile | Sort-Object)
        $cov = Compare-Object $diskMkvs $expectedNames
        $c = [ordered]@{ folder = $f; mkvCount = $diskMkvs.Count; expectedCount = $expectedNames.Count; pass = ($null -eq $cov) }
        $script:Log.verification.census += $c
        $censusTotal += $diskMkvs.Count
        if ($cov) { Save-ApplyLog; Stop-Apply 'verify-census' 'MKV census mismatch' @{ folder = $f; diff = $cov } }
    }
    foreach ($t in $script:Map.trailerDelete) {
        $plan = $script:FolderPlan[(Split-Path $t.folder -Leaf)]
        $p = Join-Path (Join-Path $Root $plan.NewFolder) $t.file
        if (Test-Path -LiteralPath $p) { Save-ApplyLog; Stop-Apply 'verify-census' 'trailer path present after apply' $p }
    }
    if ($censusTotal -ne 83) { Save-ApplyLog; Stop-Apply 'verify-census' "total MKV count $censusTotal != 83" }
    Save-ApplyLog
    $script:CensusTotal = $censusTotal
}

function Complete-ApplyLog {
    $script:Log.counts = [ordered]@{
        trailersDeleted = $script:Log.trailersDeleted.Count
        foldersRenamed  = $script:Log.foldersRenamed.Count
        filesRenamed    = $script:Log.filesRenamed.Count
        filesRetitled   = $script:Log.filesRetitled.Count
        tagsEditsApplied = $script:Log.tagsEdits.Count
        tagsEditsVerified = @($script:Log.tagsEdits | Where-Object verified).Count
        filesVerifiedPass = $script:Log.verification.passCount
        filesVerifiedFail = $script:Log.verification.failCount
        maxPathLength = $script:Log.verification.maxPathLength
        mkvCensusTotal = $script:CensusTotal
    }
    $script:Log.status = 'completed'
    $script:Log.finishedUtc = (Get-Date).ToUniversalTime().ToString('o')
    Save-ApplyLog
    Write-Host '=== APPLY COMPLETE ===' -ForegroundColor Green
    Write-Host ("trailers deleted: {0}/6 | folders renamed: {1}/17 | files renamed: {2}/83 | retitled: {3}/83 | tags edits: {4}/69 | verified: {5}/83 | max path: {6}" -f $script:Log.counts.trailersDeleted, $script:Log.counts.foldersRenamed, $script:Log.counts.filesRenamed, $script:Log.counts.filesRetitled, $script:Log.counts.tagsEditsApplied, $script:Log.counts.filesVerifiedPass, $script:Log.counts.maxPathLength) -ForegroundColor Green
}

# ============================= MAIN =============================
try {
    $map = Get-Content -Raw -Encoding utf8 $MappingPath | ConvertFrom-Json
    $script:Map = $map
    $script:KeptRows = @($map.rows | Where-Object { $_.action -eq 'rename-retitle' })
    $script:FolderNames = @($map.rows | ForEach-Object { $_.oldFolder } | Select-Object -Unique)

    if ($VerifyOnly) {
        Write-Host '=== VERIFY-ONLY RESUME (steps 1-5 already applied) ===' -ForegroundColor Cyan
        if (-not (Test-Path -LiteralPath $LogPath)) { Stop-Apply 'verify-only-gate' 'apply-log.json missing' }
        $script:Log = Get-Content -Raw -Encoding utf8 $LogPath | ConvertFrom-Json
        $gateFails = @()
        if (@($script:Log.trailersDeleted).Count -ne 6 -or @($script:Log.trailersDeleted | Where-Object verifiedAbsent).Count -ne 6) { $gateFails += 'trailersDeleted not 6/6 verified' }
        if (@($script:Log.foldersRenamed).Count -ne 17 -or @($script:Log.foldersRenamed | Where-Object verified).Count -ne 17) { $gateFails += 'foldersRenamed not 17/17 verified' }
        if (@($script:Log.filesRenamed).Count -ne 83 -or @($script:Log.filesRenamed | Where-Object verified).Count -ne 83) { $gateFails += 'filesRenamed not 83/83 verified' }
        if (@($script:Log.filesRetitled).Count -ne 83 -or @($script:Log.filesRetitled | Where-Object ok).Count -ne 83) { $gateFails += 'filesRetitled not 83/83 ok' }
        if (@($script:Log.tagsEdits).Count -ne 69 -or @($script:Log.tagsEdits | Where-Object verified).Count -ne 69) { $gateFails += 'tagsEdits not 69/69 verified' }
        if (@($script:Log.tagsBackups).Count -ne 17 -or @($script:Log.tagsBackups | Where-Object verified).Count -ne 17) { $gateFails += 'tagsBackups not 17/17 verified' }
        foreach ($f in $script:FolderNames) {
            $newFolder = ($map.rows | Where-Object { $_.oldFolder -ceq $f } | Select-Object -First 1).newFolder
            if (-not (Test-Path -LiteralPath (Join-Path $Root $newFolder) -PathType Container)) { $gateFails += "new folder missing: $newFolder" }
            if (-not (Test-Path -LiteralPath (Join-Path (Join-Path $BackupDir $f) 'tags.json') -PathType Leaf)) { $gateFails += "backup missing: $f" }
        }
        foreach ($t in $map.trailerDelete) {
            if (Test-Path -LiteralPath (Join-Path $t.folder $t.file)) { $gateFails += "trailer still present at old path: $(Join-Path $t.folder $t.file)" }
        }
        if ($gateFails.Count -gt 0) { Stop-Apply 'verify-only-gate' 'prior apply state incomplete' $gateFails }

        $script:FolderPlan = [ordered]@{}
        foreach ($f in $script:FolderNames) {
            $newFolder = ($map.rows | Where-Object { $_.oldFolder -ceq $f } | Select-Object -First 1).newFolder
            $fKept = @($script:KeptRows | Where-Object { $_.oldFolder -ceq $f })
            $resolved = @($script:Log.tagsEdits | Where-Object { $_.folder -ceq $f } | ForEach-Object { [ordered]@{ Edit = [ordered]@{ to = $_.to }; Path = $_.resolvedPath } })
            $trailerCanon = @{}
            $bakNode = [System.Text.Json.Nodes.JsonNode]::Parse([System.IO.File]::ReadAllText((Join-Path (Join-Path $BackupDir $f) 'tags.json')))
            foreach ($td in @($map.trailerDelete | Where-Object { $_.folder -ceq (Join-Path $Root $f) })) {
                $tIdx = Find-TitleIndex $bakNode['titles'] $td.file
                $trailerCanon[$td.file] = $bakNode['titles'][$tIdx].ToJsonString()
            }
            $script:FolderPlan[$f] = [ordered]@{ OldFolder = $f; NewFolder = $newFolder; KeptRows = $fKept; ResolvedEdits = $resolved; TrailerCanon = $trailerCanon }
        }
        $script:Log | Add-Member -NotePropertyName previousHalt -NotePropertyValue $script:Log.halt -Force
        $hist = @()
        if ($script:Log.PSObject.Properties['haltHistory']) { $hist = @($script:Log.haltHistory) }
        if ($script:Log.halt) { $hist += $script:Log.halt }
        $script:Log | Add-Member -NotePropertyName haltHistory -NotePropertyValue $hist -Force
        $script:Log.halt = $null
        $script:Log | Add-Member -NotePropertyName resumeNote -NotePropertyValue ([ordered]@{ utc = (Get-Date).ToUniversalTime().ToString('o'); mode = 'VerifyOnly'; reason = 'step 6 halted on mkvextract stdout BOM decoded under ibm437 console code page; tool capture switched to explicit UTF-8 Process decoding; steps 1-5 unchanged, step 6 re-run in full' }) -Force
        $script:Log.verification = [ordered]@{ files = @(); tagsHarmony = @(); census = @(); passCount = 0; failCount = 0; maxPathLength = 0; maxPath = $null }
        $script:Log.status = 'running'
        Save-ApplyLog
        Invoke-PostApplyVerification
        Complete-ApplyLog
        exit 0
    }

    Write-Host '=== PREFLIGHT (read-only) ===' -ForegroundColor Cyan
    $script:Log.mappingVersion = $map.version
    $script:Log.mappingSha256 = (Get-FileHash -LiteralPath $MappingPath -Algorithm SHA256).Hash

    Add-PreflightCheck 'mapping-version-3' ($map.version -eq 3) "version=$($map.version)"
    Add-PreflightCheck 'mapping-validation-allPass' ($map.validation.allPass -eq $true)

    $keptRows = $script:KeptRows
    $deleteRows = @($map.rows | Where-Object { $_.action -eq 'delete' })
    $workCount = @($map.rows | Where-Object { $_.kind -eq 'work' }).Count
    $standaloneCount = @($map.rows | Where-Object { $_.kind -eq 'standalone' }).Count
    $ripCount = @($map.rows | Where-Object { $_.kind -eq 'title-rip' }).Count
    $keptRipCount = @($keptRows | Where-Object { $_.kind -eq 'title-rip' }).Count
    Add-PreflightCheck 'row-counts-89-6-83' ($map.rows.Count -eq 89 -and $deleteRows.Count -eq 6 -and $keptRows.Count -eq 83) "rows=$($map.rows.Count) delete=$($deleteRows.Count) kept=$($keptRows.Count)"
    Add-PreflightCheck 'kind-counts-58-5-26-20' ($workCount -eq 58 -and $standaloneCount -eq 5 -and $ripCount -eq 26 -and $keptRipCount -eq 20) "work=$workCount standalone=$standaloneCount rip=$ripCount keptRip=$keptRipCount"

    $tdSet = @($map.trailerDelete | ForEach-Object { "$($_.folder)|$($_.file)" } | Sort-Object)
    $drSet = @($deleteRows | ForEach-Object { "$($_.folder)|$($_.oldFile)" } | Sort-Object)
    $tdMatch = ($tdSet.Count -eq 6) -and (-not (Compare-Object $tdSet $drSet))
    Add-PreflightCheck 'trailerDelete-matches-delete-rows' $tdMatch "trailerDelete=$($tdSet.Count)"

    $folderNames = $script:FolderNames
    $tsFolders = @($map.tagsSync | ForEach-Object { Split-Path $_.folder -Leaf })
    $editTotal = ($map.tagsSync | ForEach-Object { $_.edits.Count } | Measure-Object -Sum).Sum
    $allFinal = @($map.tagsSync | ForEach-Object { $_.edits } | Where-Object { $_.status -cne 'final' }).Count -eq 0
    $noPending = @($map.tagsSync | ForEach-Object { $_.pendingEdits }).Count -eq 0 -and @($map.pendingResearch).Count -eq 0
    $folderSetsMatch = -not (Compare-Object ($folderNames | Sort-Object) ($tsFolders | Sort-Object))
    Add-PreflightCheck 'folders-17-tagsSync-69-all-final' ($folderNames.Count -eq 17 -and $tsFolders.Count -eq 17 -and $editTotal -eq 69 -and $allFinal -and $noPending -and $folderSetsMatch) "folders=$($folderNames.Count) edits=$editTotal allFinal=$allFinal noPending=$noPending setsMatch=$folderSetsMatch"

    $icaRow = $keptRows | Where-Object { $_.oldFolder -ceq 'Stravinsky - Le Sacre du Printemps; Sibelius - Symphony No.5 (Bernstein)' -and $_.oldFile -ceq 'title 03.mkv' }
    Add-PreflightCheck 'ICA-intro-KEPT' ($null -ne $icaRow -and $icaRow.newFile -ceq 'Introduction to ICA Classics.mkv')

    foreach ($tool in 'mkvpropedit.exe','mkvmerge.exe','mkvextract.exe') {
        Add-PreflightCheck "tool-$tool" (Test-Path -LiteralPath (Join-Path $MkvToolDir $tool))
    }

    $badChars = '[<>:"/\\|?*\x00-\x1F]'
    $rowInvariantFails = @()
    foreach ($r in $keptRows) {
        $full = Join-Path (Join-Path $Root $r.newFolder) $r.newFile
        if ($r.newFile -cne ($r.newTitle + '.mkv')) { $rowInvariantFails += "name!=title+.mkv: $($r.oldFolder)|$($r.oldFile)" }
        if ($full.Length -gt $MaxPathLen) { $rowInvariantFails += "path>$MaxPathLen ($($full.Length)): $full" }
        if ($r.newFile -match $badChars -or $r.newFolder -match $badChars) { $rowInvariantFails += "forbidden chars: $($r.newFolder)|$($r.newFile)" }
        if ($r.newFile.EndsWith('.') -or $r.newFile.EndsWith(' ')) { $rowInvariantFails += "trailing dot/space: $($r.newFile)" }
    }
    Add-PreflightCheck 'kept-row-invariants (name==title+.mkv, path<=240, chars)' ($rowInvariantFails.Count -eq 0) ($rowInvariantFails -join '; ')

    $script:FolderPlan = [ordered]@{}
    $diskFails = @()
    foreach ($f in $folderNames) {
        $oldDir = Join-Path $Root $f
        $newFolder = ($map.rows | Where-Object { $_.oldFolder -ceq $f } | Select-Object -First 1).newFolder
        $newDir = Join-Path $Root $newFolder
        $fRows = @($map.rows | Where-Object { $_.oldFolder -ceq $f })
        $fKept = @($keptRows | Where-Object { $_.oldFolder -ceq $f })
        $plan = [ordered]@{ OldFolder = $f; NewFolder = $newFolder; KeptRows = $fKept; TagsProfile = $null; ResolvedEdits = @(); TrailerCanon = @{} }
        if (-not (Test-Path -LiteralPath $oldDir -PathType Container)) { $diskFails += "missing old folder: $oldDir" }
        if (Test-Path -LiteralPath $newDir) { $diskFails += "new folder already exists: $newDir" }
        $tagsPath = Join-Path $oldDir 'tags.json'
        if (-not (Test-Path -LiteralPath $tagsPath -PathType Leaf)) { $diskFails += "missing tags.json: $tagsPath" }
        else {
            $diskMkvs = @(Get-ChildItem -LiteralPath $oldDir -Filter '*.mkv' -File | ForEach-Object Name | Sort-Object)
            $rowMkvs = @($fRows | ForEach-Object oldFile | Sort-Object)
            $cov = Compare-Object $diskMkvs $rowMkvs
            if ($cov) { $diskFails += "disk/rows MKV mismatch in ${f}: $(($cov | ForEach-Object { "$($_.SideIndicator)$($_.InputObject)" }) -join ', ')" }
            $newNames = @($fKept | ForEach-Object newFile)
            if (@($newNames | Select-Object -Unique).Count -ne $newNames.Count) { $diskFails += "duplicate newFile in $f" }
            $oldSet = @($fRows | ForEach-Object oldFile)
            foreach ($n in $newNames) {
                if ($oldSet -contains $n) { $diskFails += "rename-chain collision in ${f}: $n" }
                if (Test-Path -LiteralPath (Join-Path $oldDir $n)) { $diskFails += "newFile already on disk in ${f}: $n" }
            }
            try {
                $tp = Get-TagsProfile $tagsPath
                if ($tp.IsUtf16) { throw 'utf16 encoding not supported' }
                $node = [System.Text.Json.Nodes.JsonNode]::Parse($tp.Text)
                $rt = ConvertTo-TagsJsonText $node $tp
                $norm = { param($s) $s.Replace("`r`n", "`n").TrimEnd("`n") }
                if ((& $norm $rt) -cne (& $norm $tp.Text)) { throw 'System.Text.Json round-trip not byte-identical (would reformat file)' }
                $plan.TagsProfile = $tp
                $ts = $map.tagsSync | Where-Object { $_.folder -ceq (Join-Path $Root $f) }
                if (-not $ts) { throw 'no tagsSync entry for folder' }
                if ($ts.newFolder -cne $newFolder) { throw 'tagsSync.newFolder != row newFolder' }
                foreach ($e in $ts.edits) {
                    $resolved = Resolve-TagsSelector $node $e.field
                    if (-not (Test-EditFromMatch $resolved $e.from)) {
                        throw "edit from-mismatch: $($e.field) expected [$($e.from | ConvertTo-Json -Compress)]"
                    }
                    if ($e.field -ceq 'disc') {
                        if ($e.from -cne $f -or $e.to -cne $newFolder) { throw 'disc edit inconsistent with folder rename' }
                    }
                    if ($e.field -match "^titles\[title_file='([^']*)'\]\.title_file$") {
                        $origTf = $Matches[1]
                        $row = $fKept | Where-Object { $_.oldFile -ceq $origTf }
                        if (-not $row -or $row.newFile -cne $e.to) { throw "title_file edit inconsistent with row: $($e.field)" }
                    }
                    $plan.ResolvedEdits += [ordered]@{ Edit = $e; Path = $resolved.Path }
                }
                foreach ($td in @($map.trailerDelete | Where-Object { $_.folder -ceq (Join-Path $Root $f) })) {
                    $tIdx = Find-TitleIndex $node['titles'] $td.file
                    $plan.TrailerCanon[$td.file] = $node['titles'][$tIdx].ToJsonString()
                }
            } catch {
                $diskFails += "tags preflight ${f}: $($_.Exception.Message)"
            }
        }
        foreach ($td in @($map.trailerDelete | Where-Object { $_.folder -ceq (Join-Path $Root $f) })) {
            if (-not (Test-Path -LiteralPath (Join-Path $oldDir $td.file) -PathType Leaf)) { $diskFails += "trailer missing: $(Join-Path $oldDir $td.file)" }
        }
        $script:FolderPlan[$f] = $plan
    }
    Add-PreflightCheck 'disk-state + tags-profiles + 69-selector-from-matches' ($diskFails.Count -eq 0) ($diskFails -join '; ')

    $failedChecks = @($script:Log.preflight.checks | Where-Object { -not $_.pass })
    if ($failedChecks.Count -gt 0) {
        $script:Log.preflight.pass = $false
        Stop-Apply 'preflight' "$($failedChecks.Count) preflight check(s) failed - NOTHING on D:\DVDs was changed" $failedChecks
    }
    $script:Log.preflight.pass = $true
    Write-Host "PREFLIGHT PASS - $($script:Log.preflight.checks.Count) checks" -ForegroundColor Green
    if ($PreflightOnly) {
        $script:Log.status = 'preflight-pass'
        $script:Log.finishedUtc = (Get-Date).ToUniversalTime().ToString('o')
        Save-ApplyLog
        Write-Host 'PreflightOnly: exiting without changes.' -ForegroundColor Cyan
        exit 0
    }

    # ============================= STEP 1: DELETE TRAILERS =============================
    Write-Host '=== STEP 1: delete 6 trailer rips (old paths) ===' -ForegroundColor Cyan
    foreach ($t in $map.trailerDelete) {
        $p = Join-Path $t.folder $t.file
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { Stop-Apply 'delete-trailer' 'trailer missing before delete' $p }
        try { Remove-Item -LiteralPath $p -Force } catch { Stop-Apply 'delete-trailer' $_.Exception.Message $p }
        $gone = -not (Test-Path -LiteralPath $p)
        $script:Log.trailersDeleted += [ordered]@{ path = $p; deleted = $gone; verifiedAbsent = $gone }
        Save-ApplyLog
        if (-not $gone) { Stop-Apply 'delete-trailer' 'file still present after Remove-Item' $p }
        Write-Host "  deleted $p" -ForegroundColor Green
    }

    # ============================= STEP 2: RENAME FOLDERS =============================
    Write-Host '=== STEP 2: rename 17 folders ===' -ForegroundColor Cyan
    foreach ($f in $folderNames) {
        $plan = $script:FolderPlan[$f]
        $oldDir = Join-Path $Root $f
        $newDir = Join-Path $Root $plan.NewFolder
        try { Rename-Item -LiteralPath $oldDir -NewName $plan.NewFolder } catch { Stop-Apply 'rename-folder' $_.Exception.Message @{ old = $oldDir; new = $newDir } }
        $ok = (Test-Path -LiteralPath $newDir -PathType Container) -and (-not (Test-Path -LiteralPath $oldDir))
        $script:Log.foldersRenamed += [ordered]@{ oldPath = $oldDir; newPath = $newDir; verified = $ok }
        Save-ApplyLog
        if (-not $ok) { Stop-Apply 'rename-folder' 'rename did not land' @{ old = $oldDir; new = $newDir } }
        Write-Host "  $f -> $($plan.NewFolder)" -ForegroundColor Green
    }

    # ============================= STEP 3: RENAME FILES =============================
    Write-Host '=== STEP 3: rename 83 kept files ===' -ForegroundColor Cyan
    foreach ($r in $keptRows) {
        $dir = Join-Path $Root $r.newFolder
        $oldP = Join-Path $dir $r.oldFile
        $newP = Join-Path $dir $r.newFile
        if (-not (Test-Path -LiteralPath $oldP -PathType Leaf)) { Stop-Apply 'rename-file' 'old file missing before rename' $oldP }
        try { Rename-Item -LiteralPath $oldP -NewName $r.newFile } catch { Stop-Apply 'rename-file' $_.Exception.Message @{ old = $oldP; new = $newP } }
        $ok = (Test-Path -LiteralPath $newP -PathType Leaf) -and (-not (Test-Path -LiteralPath $oldP))
        $script:Log.filesRenamed += [ordered]@{ oldPath = $oldP; newPath = $newP; verified = $ok }
        Save-ApplyLog
        if (-not $ok) { Stop-Apply 'rename-file' 'rename did not land' @{ old = $oldP; new = $newP } }
        Write-Host "  $($r.oldFile) -> $($r.newFile)" -ForegroundColor Green
    }

    # ============================= STEP 4: RETITLE (mkvpropedit) =============================
    Write-Host '=== STEP 4: retitle 83 files (segment + global TITLE) ===' -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $XmlDir)) { New-Item -ItemType Directory -Path $XmlDir | Out-Null }
    $i = 0
    foreach ($r in $keptRows) {
        $fileP = Join-Path (Join-Path $Root $r.newFolder) $r.newFile
        $safeStem = $r.newTitle -replace '[<>:"/\\|?*\x00-\x1F]', '_'
        $xmlP = Join-Path $XmlDir ('{0:D3} - {1}.xml' -f $i, $safeStem)
        if ($xmlP.Length -gt $MaxPathLen) { Stop-Apply 'retitle' "tags XML path too long ($($xmlP.Length))" $xmlP }
        $xml = @"
<?xml version="1.0" encoding="UTF-8"?>
<Tags>
  <Tag>
    <Targets>
      <TargetTypeValue>50</TargetTypeValue>
    </Targets>
    <Simple>
      <Name>TITLE</Name>
      <String>$(ConvertTo-XmlEscaped $r.newTitle)</String>
      <TagLanguageIETF>und</TagLanguageIETF>
    </Simple>
  </Tag>
</Tags>
"@
        [System.IO.File]::WriteAllText($xmlP, $xml, [System.Text.UTF8Encoding]::new($false))
        $sizeBefore = (Get-Item -LiteralPath $fileP).Length
        $propArgs = @($fileP, '--edit', 'info', '--set', "title=$($r.newTitle)", '--tags', "all:$xmlP")
        $res = Invoke-Utf8Tool (Join-Path $MkvToolDir 'mkvpropedit.exe') $propArgs
        $ec = $res.ExitCode
        $sizeAfter = (Get-Item -LiteralPath $fileP).Length
        $entry = [ordered]@{ index = $i; path = $fileP; newTitle = $r.newTitle; tagsXml = $xmlP; exitCode = $ec; output = ($res.StdOut + $res.StdErr).Trim(); sizeBefore = $sizeBefore; sizeAfter = $sizeAfter; ok = ($ec -eq 0) }
        $script:Log.filesRetitled += $entry
        Save-ApplyLog
        if ($ec -ne 0) { Stop-Apply 'retitle' "mkvpropedit exit $ec" $entry }
        Write-Host "  [$($i+1)/83] $($r.newTitle)" -ForegroundColor Green
        $i++
    }

    # ============================= STEP 5: TAGS.JSON SYNC =============================
    Write-Host '=== STEP 5: tags.json sync (69 edits, 17 folders; title_file last) ===' -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }
    foreach ($f in $folderNames) {
        $plan = $script:FolderPlan[$f]
        $src = Join-Path (Join-Path $Root $plan.NewFolder) 'tags.json'
        $bDir = Join-Path $BackupDir $f
        if (-not (Test-Path -LiteralPath $bDir)) { New-Item -ItemType Directory -Path $bDir | Out-Null }
        $dst = Join-Path $bDir 'tags.json'
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $h1 = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
        $h2 = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
        $script:Log.tagsBackups += [ordered]@{ original = $src; backup = $dst; sha256 = $h1; verified = ($h1 -ceq $h2) }
        Save-ApplyLog
        if ($h1 -cne $h2) { Stop-Apply 'tags-backup' 'backup hash mismatch' @{ original = $src; backup = $dst } }
        Write-Host "  backed up $src" -ForegroundColor Green
    }
    foreach ($f in $folderNames) {
        $plan = $script:FolderPlan[$f]
        $tagsP = Join-Path (Join-Path $Root $plan.NewFolder) 'tags.json'
        $text = [System.IO.File]::ReadAllText($tagsP)
        $node = [System.Text.Json.Nodes.JsonNode]::Parse($text)
        $nonTf = @($plan.ResolvedEdits | Where-Object { $_.Edit.field -notmatch '\.title_file$' })
        $tfEdits = @($plan.ResolvedEdits | Where-Object { $_.Edit.field -match '\.title_file$' })
        $appliedPaths = @()
        foreach ($re in @($nonTf + $tfEdits)) {
            $e = $re.Edit
            $resolved = Resolve-TagsSelector $node $e.field
            if ($resolved.Path -cne $re.Path) { Stop-Apply 'tags-sync' 'selector resolved differently than preflight' @{ folder = $f; field = $e.field; preflight = $re.Path; now = $resolved.Path } }
            if (-not (Test-EditFromMatch $resolved $e.from)) { Stop-Apply 'tags-sync' 'from-value mismatch at apply time' @{ folder = $f; field = $e.field; from = $e.from } }
            Set-TagsValue $resolved $e.to
            $appliedPaths += $resolved.Path
            $script:Log.tagsEdits += [ordered]@{ folder = $f; tagsPath = $tagsP; field = $e.field; resolvedPath = $resolved.Path; from = $e.from; to = $e.to; applied = $true; verified = $false }
        }
        $newText = ConvertTo-TagsJsonText $node $plan.TagsProfile
        [System.IO.File]::WriteAllText($tagsP, $newText, [System.Text.UTF8Encoding]::new($plan.TagsProfile.HasBom))
        $reread = [System.Text.Json.Nodes.JsonNode]::Parse([System.IO.File]::ReadAllText($tagsP))
        $editOk = $true
        $idx = 0
        foreach ($re in $plan.ResolvedEdits) {
            $n = Get-NodeAtPath $reread $re.Path
            $toNode = [System.Text.Json.JsonSerializer]::SerializeToNode[object]($re.Edit.to)
            $ok = [System.Text.Json.Nodes.JsonNode]::DeepEquals($n, $toNode)
            $script:Log.tagsEdits[-(@($plan.ResolvedEdits).Count - $idx)].verified = $ok
            if (-not $ok) { $editOk = $false }
            $idx++
        }
        $trailerOk = $true
        foreach ($tf in $plan.TrailerCanon.Keys) {
            $tIdx = Find-TitleIndex $reread['titles'] $tf
            if ($reread['titles'][$tIdx].ToJsonString() -cne $plan.TrailerCanon[$tf]) { $trailerOk = $false }
        }
        $script:Log.tagsWrites += [ordered]@{ folder = $f; tagsPath = $tagsP; editsApplied = $appliedPaths.Count; allEditsVerified = $editOk; trailerEntriesUnchanged = $trailerOk; sha256After = (Get-FileHash -LiteralPath $tagsP -Algorithm SHA256).Hash }
        Save-ApplyLog
        if (-not $editOk) { Stop-Apply 'tags-sync' 'post-write edit verification failed' @{ folder = $f; tagsPath = $tagsP } }
        if (-not $trailerOk) { Stop-Apply 'tags-sync' 'trailer title entry changed (must stay unchanged)' @{ folder = $f; tagsPath = $tagsP } }
        Write-Host "  $f - $($appliedPaths.Count) edits applied + verified" -ForegroundColor Green
    }

    # ============================= STEP 6 + FINALIZE =============================
    Invoke-PostApplyVerification
    Complete-ApplyLog
}
catch {
    Stop-Apply 'unexpected' $_.Exception.Message @{ stack = $_.ScriptStackTrace }
}
