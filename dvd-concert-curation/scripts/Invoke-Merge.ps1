#!/usr/bin/env pwsh
# Invoke-Merge.ps1 — merge driver for the DVD split-works project (manifest-driven).
# Processes exactly one -Folder per invocation.
# Owner rulings 2026-11-17 (Gate 2):
#   D1: output names are sanitized at MANIFEST level per owner Option A (ASCII " -> paired curly
#       U+201C/U+201D, ASCII : -> U+A789) in outputName AND mkvTitle; name == title invariant holds.
#       Get-SafeFileName below is a fallback safety net (no-op on Option-A-sanitized manifests).
#   D2: resume semantics replace the old clobber refusal. An existing output is fully verified;
#       pass -> merge skipped; fail -> reported and the folder stops. Never silently overwritten.
#       (Implements the owner-approved mixed mode: existing passing outputs are verified-only.)
#   D3: full output paths > 240 chars auto-shortened deterministically: drop opus/catalogue,
#       then orchestra, then truncate work text at a word boundary; ' (Year).mkv' tail untouched.
#       Every shortened name is logged (runlog + console).
#   After ALL outputs of a folder pass full verification (chapters, duration, codecs, size,
#   full decode, title) AND title rips are unchanged AND sources are unmodified, the folder's
#   manifest-listed movement sources and folded extras are deleted. Nothing else is ever deleted
#   (title NN.mkv, tags.json, covers, VIDEO_TS are never touched). -NoDelete suppresses deletion.
# Writes: output MKVs inside the source folder; runlog.json + temp XML under this script's directory.
# Title rips (title *.mkv) are snapshotted before and compared after; any change fails the folder.
# Pass 1: mkvmerge append + --generate-chapters when-appending + --title.
# Pass 2: mkvextract chapters -> rewrite ONLY ChapterString values (timestamps untouched) -> mkvpropedit --chapters.
# Pass 3: mkvpropedit --edit info --set title=<mkvTitle> --tags all:<minimal XML>
#         (single global TITLE tag, TargetTypeValue 50) overwrites inherited rip TITLE tags. Also on renames.
# Verify: chapter count/names (standalone renames: chapters informational only); duration = video STREAM
#         duration, else format.duration with a subtitle assertion: no subtitle streams, or every
#         subtitle track duration within max(2 s, 1%) of format.duration (metric recorded);
#         Owner ruling 2026-11-19: when ffprobe exposes no video-stream duration (these DVD MKVs),
#         measure the VIDEO stream's own packet timestamps (max pts_time+duration_time, metric
#         'video-stream-packets') BEFORE any subtitle/format fallback — never subtitle duration;
#         standalone renames compare format.duration pre/post rename directly (subtitle streams kept,
#         metric 'format-duration-rename'); codecs vs first input; size +/-5%; full null decode of
#         video+audio (never subtitles); segment title via mkvinfo AND format tag title.
# Modes: default = merge (resume-aware, delete-after-verify); -VerifyOnly = verify existing outputs;
#        -TagsOnly = metadata-only pass 3 on existing outputs. Neither alternate mode deletes.
# Note: ffmpeg decode uses -i before -map/-f with trailing '-' output URL (the brief's literal order is invalid).

[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseDeclaredVarsMoreThanAssignments', '', Justification = 'lockStream holds the exclusive per-folder lock for the process lifetime; the OS releases it on exit.')]
[CmdletBinding()]
param(
    [string]$ManifestPath = (Join-Path $PSScriptRoot 'manifest.json'),
    [Parameter(Mandatory = $true)][string]$Folder,
    [switch]$VerifyOnly,
    [switch]$TagsOnly,
    [switch]$NoDelete,
    [string]$DvdsRoot = 'D:\DVDs'
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$mkvmerge = 'C:\Program Files\MKVToolNix\mkvmerge.exe'
$mkvpropedit = 'C:\Program Files\MKVToolNix\mkvpropedit.exe'
$mkvextract = 'C:\Program Files\MKVToolNix\mkvextract.exe'
$mkvinfo = 'C:\Program Files\MKVToolNix\mkvinfo.exe'
$ffprobe = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\ffprobe.exe'
$ffmpeg = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\ffmpeg.exe'
foreach ($t in @($mkvmerge, $mkvpropedit, $mkvextract, $mkvinfo, $ffprobe, $ffmpeg)) {
    if (-not (Test-Path -LiteralPath $t)) { throw "Required tool missing: $t" }
}

$runlogPath = Join-Path $PSScriptRoot 'runlog.json'
$tmpXmlPath = Join-Path $PSScriptRoot 'chapters-tmp.xml'
$tmpTagsPath = Join-Path $PSScriptRoot 'tags-tmp.xml'
$utf8 = [System.Text.UTF8Encoding]::new($false)
$modeLabel = $(if ($VerifyOnly) { 'verify-only' } elseif ($TagsOnly) { 'tags-only' } else { 'merge' })
$maxPathLength = 240

# Per-folder lock: a parallel lane was observed merging the same folder concurrently
# (Solti in Concert, 2026-11-17). One driver instance per folder; second instance exits clean.
# Exclusive-file lock (named kernel mutexes are denied in this shell context). The OS closes
# the handle on process exit, so a crashed holder releases the lock automatically.
$lockPath = Join-Path $PSScriptRoot ('lock-' + ($Folder -replace '[^A-Za-z0-9]', '_') + '.tmp')
$lockStream = $null
$lockOptions = [System.IO.FileStreamOptions]::new()
$lockOptions.Mode = [System.IO.FileMode]::OpenOrCreate
$lockOptions.Access = [System.IO.FileAccess]::ReadWrite
$lockOptions.Share = [System.IO.FileShare]::None
$lockOptions.Options = [System.IO.FileOptions]::DeleteOnClose
try {
    $lockStream = [System.IO.File]::Open($lockPath, $lockOptions)
}
catch [System.IO.IOException] {
    Write-Host "Another driver instance is already processing '$Folder'; exiting without changes." -ForegroundColor Yellow
    exit 1
}

function Get-ProbeJson {
    # Retry (retro 2026-11-17): a single ffprobe blip - a background scanner or
    # AV filter briefly holding the file - must not fail a whole folder. Three
    # attempts with linear backoff before the throw reaches the
    # stop-don't-repair handler. All four 2026-11-17 batch failures were
    # single-shot probe misses on files that verifiably existed minutes later.
    param([string]$Path, [string[]]$ProbeArgs)
    $text = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $text = & $ffprobe -v error @ProbeArgs -of json $Path 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) { break }
        if ($attempt -lt 3) { Start-Sleep -Seconds (5 * $attempt) }
    }
    if ($LASTEXITCODE -ne 0) { throw "ffprobe failed after $attempt attempts (exit $LASTEXITCODE) on $Path : $text" }
    return ($text | ConvertFrom-Json)
}

function Get-FirstStream {
    param($Streams, [string]$Type)
    return @($Streams | Where-Object { $_.codec_type -ceq $Type })[0]
}

function Get-InvariantDouble {
    param($Value)
    if ($null -eq $Value -or "$Value" -eq '' -or "$Value" -ceq 'N/A') { return $null }
    return [double]::Parse("$Value", [System.Globalization.CultureInfo]::InvariantCulture)
}

function Get-VideoPacketDuration {
    # Owner ruling 2026-11-19: the video stream's OWN duration from its packet timestamps
    # (max pts_time + duration_time). ffprobe 9.x exposes no stream duration for these DVD
    # MKVs; this measures the video stream, never subtitle or format duration. Returns $null
    # on probe failure so the caller's existing fallback chain stays in charge.
    param([string]$Path)
    $text = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $text = & $ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,duration_time -of csv=p=0 $Path 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) { break }
        if ($attempt -lt 3) { Start-Sleep -Seconds (5 * $attempt) }
    }
    if ($LASTEXITCODE -ne 0) { return $null }
    $max = $null
    foreach ($line in ($text -split "`n")) {
        $t = $line.Trim()
        if (-not $t) { continue }
        $parts = $t -split ','
        $pts = Get-InvariantDouble $parts[0]
        if ($null -eq $pts) { continue }
        $dur = $(if ($parts.Count -ge 2) { Get-InvariantDouble $parts[1] } else { $null })
        $end = $pts + $(if ($null -ne $dur) { $dur } else { 0.0 })
        if ($null -eq $max -or $end -gt $max) { $max = $end }
    }
    if ($null -eq $max -or $max -le 0) { return $null }
    return $max
}

function Get-DurationMetric {
    param($Probe, [string]$Path)
    $v = Get-FirstStream -Streams $Probe.streams -Type 'video'
    $d = Get-InvariantDouble $v.duration
    if ($null -ne $d) { return @{ duration = $d; metric = 'video-stream'; ok = $true } }
    if ($Path) {
        $pd = Get-VideoPacketDuration -Path $Path
        if ($null -ne $pd) { return @{ duration = $pd; metric = 'video-stream-packets'; ok = $true } }
    }
    $fd = Get-InvariantDouble $Probe.format.duration
    if ($null -eq $fd) { return @{ duration = $null; metric = 'unavailable'; ok = $false } }
    $subs = @($Probe.streams | Where-Object { $_.codec_type -ceq 'subtitle' })
    if ($subs.Count -eq 0) { return @{ duration = $fd; metric = 'format-duration-no-subtitles'; ok = $true } }
    # Subtitle streams present: format.duration is usable only if every subtitle track spans
    # the same program (duration within max(2 s, 1%) of format.duration). A diverging subtitle
    # track could inflate the segment duration, so block in that case.
    $tol = [Math]::Max(2.0, 0.01 * $fd)
    foreach ($s in $subs) {
        $sd = Get-InvariantDouble $s.duration
        if ($null -eq $sd -or [Math]::Abs($sd - $fd) -gt $tol) {
            return @{ duration = $null; metric = 'blocked-subtitle-duration-diverges'; ok = $false }
        }
    }
    return @{ duration = $fd; metric = 'format-duration-subtitles-verified'; ok = $true }
}

function Get-SegmentTitle {
    param([string]$Path)
    $lines = & $mkvinfo $Path 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw "mkvinfo failed (exit $LASTEXITCODE) on $Path" }
    $line = $lines | Where-Object { $_ -match 'Title:' } | Select-Object -First 1
    if ($null -eq $line) { return '' }
    return ($line -replace '^.*?Title:\s*', '').Trim()
}

function Get-SafeFileName {
    # D1: clean characters illegal in Windows filenames. Title metadata is NOT touched.
    param([string]$Name)
    $s = $Name -replace '"', ''
    $s = $s -replace ':', ' -'
    $s = $s -replace '[/\\]', ' -'
    $s = $s -replace '[<>|?*]', ''
    $s = $s -replace '[\x00-\x1f]', ''
    $s = $s -replace ' {2,}', ' '
    return $s.TrimEnd('.', ' ')
}

function Get-FittedOutputName {
    # D3: deterministic shortening while full path > $MaxPathLength.
    # Order: opus/catalogue number -> orchestra -> truncate work text. Year/.mkv tail untouched.
    param([string]$Name, [string]$Directory, [string]$Orchestra, [int]$MaxPathLength = 240)
    $steps = [System.Collections.Generic.List[string]]::new()
    if ((Join-Path $Directory $Name).Length -le $MaxPathLength) { return @{ name = $Name; steps = @() } }
    $tail = ''
    $core = $Name
    if ($Name -match '^(.*)( \(\d{4}\)\.mkv)$') { $core = $Matches[1]; $tail = $Matches[2] }
    elseif ($Name.EndsWith('.mkv')) { $core = $Name.Substring(0, $Name.Length - 4); $tail = '.mkv' }
    else { throw "Cannot shorten output name without .mkv tail: $Name" }
    $parts = $core -split ' - ', 3
    if ($parts.Count -ne 3) {
        $budget = $MaxPathLength - (Join-Path $Directory 'x').Length - $tail.Length
        if ($budget -lt 1) { throw "Output path cannot fit within $MaxPathLength chars: $Name" }
        $cut = $core.Substring(0, [Math]::Min($budget, $core.Length))
        $sp = $cut.LastIndexOf(' ')
        if ($sp -gt 0) { $cut = $cut.Substring(0, $sp) }
        $steps.Add("unparsed name truncated: '$core' -> '$cut'")
        return @{ name = ($cut + $tail); steps = $steps.ToArray() }
    }
    $composer = $parts[0]
    $work = $parts[1]
    $credits = $parts[2]
    $opusRx = '\s*,?\s*\b(?:Op\.|K\.|KV|D\.|BWV|Hob\.|WoO|TrV|AV|Anh\.)\s*\d+(?:\s*(?:No\.|Nr\.)\s*\d+)?'
    $work2 = [regex]::Replace($work, $opusRx, '')
    if ($work2 -cne $work) {
        $steps.Add("opus/catalogue dropped: work '$work' -> '$work2'")
        $work = $work2
    }
    $name = (@($composer, $work, $credits) | Where-Object { $_ } | ForEach-Object { $_ }) -join ' - '
    $name = $name + $tail
    if ((Join-Path $Directory $name).Length -le $MaxPathLength) { return @{ name = $name; steps = $steps.ToArray() } }
    $credits2 = $credits
    if ($Orchestra -and $credits.IndexOf($Orchestra, [System.StringComparison]::Ordinal) -ge 0) {
        $credits2 = $credits.Replace(", $Orchestra", '').Replace("$Orchestra, ", '').Replace($Orchestra, '')
    }
    elseif ($credits.Contains(', ')) {
        $credits2 = $credits.Substring(0, $credits.LastIndexOf(', '))
    }
    if ($credits2 -cne $credits) {
        $steps.Add("orchestra dropped: credits '$credits' -> '$credits2'")
        $credits = $credits2
    }
    $name = (@($composer, $work, $credits) | Where-Object { $_ } | ForEach-Object { $_ }) -join ' - '
    $name = $name + $tail
    if ((Join-Path $Directory $name).Length -le $MaxPathLength) { return @{ name = $name; steps = $steps.ToArray() } }
    $overhead = (Join-Path $Directory ($composer + ' - ' + $credits + $tail)).Length + 3
    $budget = $MaxPathLength - $overhead
    if ($budget -lt 1) { throw "Output path cannot fit within $MaxPathLength chars even with empty work: $Name" }
    if ($work.Length -gt $budget) {
        $cut = $work.Substring(0, $budget)
        $sp = $cut.LastIndexOf(' ')
        if ($sp -gt 0) { $cut = $cut.Substring(0, $sp) }
        $steps.Add("work truncated: '$work' -> '$cut'")
        $work = $cut
    }
    $name = (@($composer, $work, $credits) | Where-Object { $_ } | ForEach-Object { $_ }) -join ' - '
    $name = $name + $tail
    if ((Join-Path $Directory $name).Length -gt $MaxPathLength) {
        throw "Output path still exceeds $MaxPathLength chars after all shortening steps: $name"
    }
    return @{ name = $name; steps = $steps.ToArray() }
}

function Get-InputMetric {
    # Probe live input files: duration metric sum, first-input codecs, byte sum.
    # -RenameOnly: same-file rename comparison; format.duration used directly (subtitle streams
    # are irrelevant because the file is not remuxed).
    param([string[]]$Paths, [switch]$RenameOnly)
    $info = @{ ok = $false; source = 'live'; sumDurSec = 0.0; metrics = @(); inVideo = $null; inAudio = $null; sumBytes = [long]0 }
    foreach ($p in $Paths) {
        if (-not (Test-Path -LiteralPath $p)) {
            # Transient-absence guard (retro 2026-11-17): a scanner, filter driver
            # or concurrent lane can make a present file read as missing for a
            # moment. Re-check once before reporting the probe as failed.
            Start-Sleep -Seconds 5
            if (-not (Test-Path -LiteralPath $p)) { return $info }
        }
    }
    $sum = 0.0
    $metrics = @()
    $bytes = [long]0
    for ($i = 0; $i -lt $Paths.Count; $i++) {
        $ij = Get-ProbeJson -Path $Paths[$i] -ProbeArgs @('-show_entries', 'stream=codec_type,codec_name,duration:format=duration')
        if ($i -eq 0) {
            $info.inVideo = "$( (Get-FirstStream -Streams $ij.streams -Type 'video').codec_name )"
            $info.inAudio = "$( (Get-FirstStream -Streams $ij.streams -Type 'audio').codec_name )"
        }
        if ($RenameOnly) {
            $fd = Get-InvariantDouble $ij.format.duration
            $im = @{ duration = $fd; metric = 'format-duration-rename'; ok = ($null -ne $fd) }
        }
        else {
            $im = Get-DurationMetric -Probe $ij -Path $Paths[$i]
        }
        $metrics += $im.metric
        if (-not $im.ok) { $info.metrics = $metrics; return $info }
        $sum += $im.duration
        $bytes += (Get-Item -LiteralPath $Paths[$i]).Length
    }
    $info.ok = $true
    $info.sumDurSec = $sum
    $info.metrics = $metrics
    $info.sumBytes = $bytes
    return $info
}

function Get-PriorRunlogRow {
    param([string]$FinalName, [string]$ManifestName)
    if (-not (Test-Path -LiteralPath $runlogPath)) { return $null }
    $rows = Get-Content -LiteralPath $runlogPath | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
    return @($rows | Where-Object {
        $_.rowType -ceq 'output' -and ($_.output -ceq $FinalName -or $_.output -ceq $ManifestName) -and
        $null -ne $_.checks -and $null -ne $_.checks.duration -and $null -ne $_.checks.duration.sumInputSec
    }) | Select-Object -Last 1
}

function Invoke-MetadataPass {
    param([string]$Path, [string]$Title)
    $xml = @(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Tags>'
        '  <Tag>'
        '    <Targets>'
        '      <TargetTypeValue>50</TargetTypeValue>'
        '    </Targets>'
        '    <Simple>'
        '      <Name>TITLE</Name>'
        ('      <String>' + [System.Security.SecurityElement]::Escape($Title) + '</String>')
        '    </Simple>'
        '  </Tag>'
        '</Tags>'
    ) -join "`n"
    [System.IO.File]::WriteAllText($tmpTagsPath, $xml, $utf8)
    try {
        $out = & $mkvpropedit $Path --edit info --set "title=$Title" --tags "all:$tmpTagsPath" 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
        $warn = @($out | Where-Object { $_ -match 'Warning:|Error:' })
        return @{ exit = $code; warnings = $warn; output = ($out -join "`n") }
    }
    finally {
        if (Test-Path -LiteralPath $tmpTagsPath) { Remove-Item -LiteralPath $tmpTagsPath -Force -Confirm:$false }
    }
}

function Add-RunLogRow {
    param($Row)
    [System.IO.File]::AppendAllText($runlogPath, (($Row | ConvertTo-Json -Depth 10 -Compress) + "`n"), $utf8)
}

function Invoke-OutputVerification {
    # Full spec verification of one output. Returns checks + pass + row fields.
    param(
        [string]$OutPath,
        $Entry,
        [hashtable]$InputInfo,
        [switch]$StandaloneRename
    )
    $expectedNames = @($Entry.sources | ForEach-Object { $_.chapterName })
    $cj = Get-ProbeJson -Path $OutPath -ProbeArgs @('-show_chapters')
    $chaps = @($cj.chapters)
    $actualNames = @($chaps | ForEach-Object { "$($_.tags.title)" })
    if ($StandaloneRename) {
        # Rename-only outputs keep their authored chapters; count/names are informational.
        $chapPass = $true
        $namesMatch = $null
        $chapCheck = [ordered]@{ standaloneRename = $true; expected = $null; actual = $chaps.Count; namesMatch = $null; pass = $true }
    }
    else {
        $namesMatch = ($actualNames.Count -eq $expectedNames.Count)
        if ($namesMatch) {
            for ($i = 0; $i -lt $expectedNames.Count; $i++) {
                if ($actualNames[$i] -cne $expectedNames[$i]) { $namesMatch = $false; break }
            }
        }
        $chapPass = ($chaps.Count -eq $expectedNames.Count) -and $namesMatch
        $chapCheck = [ordered]@{ expected = $expectedNames.Count; actual = $chaps.Count; namesMatch = $namesMatch; pass = $chapPass }
    }

    $sj = Get-ProbeJson -Path $OutPath -ProbeArgs @('-show_entries', 'stream=codec_type,codec_name,duration:format=duration')
    $vOut = Get-FirstStream -Streams $sj.streams -Type 'video'
    $aOut = Get-FirstStream -Streams $sj.streams -Type 'audio'
    if ($StandaloneRename) {
        $fd = Get-InvariantDouble $sj.format.duration
        $outMetric = @{ duration = $fd; metric = 'format-duration-rename'; ok = ($null -ne $fd) }
    }
    else {
        $outMetric = Get-DurationMetric -Probe $sj -Path $OutPath
    }
    $tol = [Math]::Max(2.0, 0.01 * $InputInfo.sumDurSec)
    $durDelta = $null
    $durPass = $false
    if ($InputInfo.ok -and $outMetric.ok) {
        $durDelta = $outMetric.duration - $InputInfo.sumDurSec
        $durPass = ([Math]::Abs($durDelta) -le $tol)
    }
    $durationDeltaSec = $(if ($null -ne $durDelta) { [Math]::Round($durDelta, 3) } else { $null })
    $codecPass = ($null -ne $vOut -and $null -ne $aOut -and $InputInfo.ok -and
        "$($vOut.codec_name)" -ceq $InputInfo.inVideo -and "$($aOut.codec_name)" -ceq $InputInfo.inAudio)
    $sizeOut = (Get-Item -LiteralPath $OutPath).Length
    $sizePct = $null
    $sizePass = $false
    if ($InputInfo.ok -and $InputInfo.sumBytes -gt 0) {
        $sizePct = ($sizeOut - $InputInfo.sumBytes) / $InputInfo.sumBytes * 100.0
        $sizePass = ([Math]::Abs($sizePct) -le 5.0)
    }

    Write-Host '  full decode: ffmpeg -v error -xerror -i OUT -map 0:v -map 0:a -f null -' -ForegroundColor Gray
    $decOut = & $ffmpeg -v error -xerror -i $OutPath -map 0:v -map 0:a -f null - 2>&1 | ForEach-Object { "$_" }
    $decodeExit = $LASTEXITCODE
    $decodePass = ($decodeExit -eq 0)
    $decodeErrors = @($decOut | Where-Object { $_ -match '\S' })

    $segmentTitle = Get-SegmentTitle -Path $OutPath
    $tj = Get-ProbeJson -Path $OutPath -ProbeArgs @('-show_entries', 'format_tags=title')
    $titleActual = "$($tj.format.tags.title)"
    $segmentMatch = ($segmentTitle -ceq $Entry.mkvTitle)
    $tagMatch = ($titleActual -ceq $Entry.mkvTitle)
    $titlePass = ($segmentMatch -and $tagMatch)

    $checks = [ordered]@{
        chapters = $chapCheck
        duration = [ordered]@{ metric = $outMetric.metric; inputSource = $InputInfo.source; inputMetrics = $InputInfo.metrics; sumInputSec = [Math]::Round($InputInfo.sumDurSec, 3); outputSec = $(if ($outMetric.ok) { [Math]::Round($outMetric.duration, 3) } else { $null }); deltaSec = $durationDeltaSec; toleranceSec = [Math]::Round($tol, 3); pass = $durPass }
        codecs = [ordered]@{ inVideo = $InputInfo.inVideo; outVideo = "$($vOut.codec_name)"; inAudio = $InputInfo.inAudio; outAudio = "$($aOut.codec_name)"; pass = $codecPass }
        size = [ordered]@{ sumInputBytes = $InputInfo.sumBytes; outputBytes = $sizeOut; deltaPct = $(if ($null -ne $sizePct) { [Math]::Round($sizePct, 4) } else { $null }); pass = $sizePass }
        decode = [ordered]@{ exit = $decodeExit; errors = $decodeErrors; pass = $decodePass }
        titleMetadata = [ordered]@{ expected = $Entry.mkvTitle; segmentTitle = $segmentTitle; formatTagTitle = $titleActual; segmentMatch = $segmentMatch; tagMatch = $tagMatch; pass = $titlePass }
    }
    $pass = ($chapPass -and $durPass -and $codecPass -and $sizePass -and $decodePass -and $titlePass)

    $cc = $(if ($chapPass) { 'Green' } else { 'Red' })
    Write-Host ("  chapters: {0}/{1} namesMatch={2}" -f $chaps.Count, $(if ($StandaloneRename) { 'n/a (rename)' } else { $expectedNames.Count }), $namesMatch) -ForegroundColor $cc
    $dc = $(if ($durPass) { 'Green' } else { 'Red' })
    Write-Host ("  duration [{0}|{1}]: in={2:N3}s out={3}s delta={4}s tol={5:N3}s" -f $outMetric.metric, $InputInfo.source, $InputInfo.sumDurSec, $(if ($outMetric.ok) { $outMetric.duration } else { 'N/A' }), $durationDeltaSec, $tol) -ForegroundColor $dc
    $kc = $(if ($codecPass) { 'Green' } else { 'Red' })
    Write-Host ("  codecs: video {0}->{1} audio {2}->{3}" -f $InputInfo.inVideo, "$($vOut.codec_name)", $InputInfo.inAudio, "$($aOut.codec_name)") -ForegroundColor $kc
    $sc = $(if ($sizePass) { 'Green' } else { 'Red' })
    Write-Host ("  size: in={0} out={1} delta={2:N4}%" -f $InputInfo.sumBytes, $sizeOut, $sizePct) -ForegroundColor $sc
    $ec = $(if ($decodePass) { 'Green' } else { 'Red' })
    Write-Host ("  decode: exit={0}" -f $decodeExit) -ForegroundColor $ec
    $tc = $(if ($titlePass) { 'Green' } else { 'Red' })
    Write-Host ("  title: segmentMatch={0} tagMatch={1}" -f $segmentMatch, $tagMatch) -ForegroundColor $tc

    return @{
        checks = $checks
        pass = $pass
        chapterNames = $actualNames
        durationDeltaSec = $durationDeltaSec
        sizeDeltaPct = $(if ($null -ne $sizePct) { [Math]::Round($sizePct, 4) } else { $null })
        decodeExit = $decodeExit
    }
}

if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Manifest not found: $ManifestPath" }
$manifest = [System.IO.File]::ReadAllText($ManifestPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$entry = @($manifest.folders | Where-Object { $_.folder -ceq $Folder })
if ($entry.Count -ne 1) { throw "Folder not found in manifest (exact name required): $Folder" }
$entry = $entry[0]
$dir = Join-Path $DvdsRoot $Folder
if (-not (Test-Path -LiteralPath $dir)) { throw "Source folder not found: $dir" }
$workList = @($entry.outputs) + @($entry.standalones)
if ($workList.Count -eq 0) { throw "No outputs for folder: $Folder" }

Write-Host "=== $Folder ===" -ForegroundColor Cyan
Write-Host ("mode: {0} | outputs: {1} | manifest: {2}" -f $modeLabel, $workList.Count, $ManifestPath) -ForegroundColor Gray

# --- Preflight: name fitting (D1/D3), existence/resume plan, source availability ----
foreach ($o in $workList) {
    $safe = Get-SafeFileName -Name $o.outputName
    $fit = Get-FittedOutputName -Name $safe -Directory $dir -Orchestra "$($o.orchestra)" -MaxPathLength $maxPathLength
    $o | Add-Member -NotePropertyName 'finalName' -NotePropertyValue $fit.name -Force
    $o | Add-Member -NotePropertyName 'sanitizedFrom' -NotePropertyValue $(if ($safe -cne $o.outputName) { $o.outputName } else { $null }) -Force
    $o | Add-Member -NotePropertyName 'shorteningSteps' -NotePropertyValue $fit.steps -Force
    if ($safe -cne $o.outputName) {
        Write-Host ("  NAME SANITIZED: '{0}' -> '{1}'" -f $o.outputName, $safe) -ForegroundColor Yellow
    }
    foreach ($st in $fit.steps) { Write-Host ("  NAME SHORTENED: {0} (final: '{1}')" -f $st, $fit.name) -ForegroundColor Yellow }
    $full = Join-Path $dir $fit.name
    $o | Add-Member -NotePropertyName 'existsAlready' -NotePropertyValue (Test-Path -LiteralPath $full) -Force
    if ($VerifyOnly -or $TagsOnly) {
        if (-not $o.existsAlready) { throw "Output missing for ${Folder}: $full" }
    }
    elseif (-not $o.existsAlready) {
        foreach ($s in $o.sources) {
            if (-not (Test-Path -LiteralPath (Join-Path $dir $s.file))) { throw "Source file missing for new output $($fit.name): $($s.file)" }
        }
    }
}
$srcNames = @($workList | ForEach-Object { $_.sources } | ForEach-Object { $_.file } | Select-Object -Unique)
$finalNames = @($workList | ForEach-Object { $_.finalName })
$preMissing = @($srcNames | Where-Object { -not (Test-Path -LiteralPath (Join-Path $dir $_)) })
$estimateBytes = [long]0
foreach ($o in $workList) {
    if ($o.existsAlready) { $estimateBytes += (Get-Item -LiteralPath (Join-Path $dir $o.finalName)).Length }
    else { $estimateBytes += ($o.sources | ForEach-Object { (Get-Item -LiteralPath (Join-Path $dir $_.file)).Length } | Measure-Object -Sum).Sum }
}
$spaceGuard = [ordered]@{ required = $null; free = $null; pass = $true }
if ($modeLabel -ceq 'merge') {
    $driveName = $DvdsRoot.Substring(0, 1)
    $free = (Get-PSDrive -Name $driveName).Free
    $need = 1.2 * $estimateBytes + 2GB
    $spaceGuard = [ordered]@{ requiredBytes = [long]$need; freeBytes = [long]$free; pass = ($free -gt $need) }
    Write-Host ("space guard: free {0:N2} GB > required {1:N2} GB = {2}" -f ($free / 1GB), ($need / 1GB), $spaceGuard.pass) -ForegroundColor $(if ($spaceGuard.pass) { 'Green' } else { 'Red' })
    if (-not $spaceGuard.pass) {
        Add-RunLogRow -Row ([ordered]@{ timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); rowType = 'folder-summary'; folder = $Folder; mode = $modeLabel; spaceGuard = $spaceGuard; pass = $false; error = 'space guard failed' })
        exit 1
    }
}
$titleSnap = @(Get-ChildItem -LiteralPath $dir -File -Filter 'title *.mkv' | ForEach-Object { @{ name = $_.Name; lwt = $_.LastWriteTimeUtc; len = $_.Length } })
$srcSnap = @{}
foreach ($s in $srcNames) {
    if ($preMissing -contains $s) { continue }
    $i = Get-Item -LiteralPath (Join-Path $dir $s)
    $srcSnap[$s] = @{ lwt = $i.LastWriteTimeUtc; len = $i.Length }
}
Write-Host ("title rips snapshotted: {0} | sources present: {1} | sources pre-missing: {2}" -f $titleSnap.Count, $srcSnap.Count, $preMissing.Count) -ForegroundColor Gray

# --- Per-output processing -------------------------------------------------------
$folderFailed = $false
$renamedActual = @{}
foreach ($o in $workList) {
    $outPath = Join-Path $dir $o.finalName
    $srcPaths = @($o.sources | ForEach-Object { Join-Path $dir $_.file })
    $expectedNames = @($o.sources | ForEach-Object { $_.chapterName })
    $row = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        rowType = 'output'
        folder = $Folder
        output = $o.finalName
        mode = $modeLabel
        standalone = [bool]$o.standalone
        resumed = $false
        sourcesCount = $o.sources.Count
        missingChaptersCount = @($o.missingChapters).Count
        mkvmergeExit = $null
        warnings = @()
        chaptersPropeditExit = $null
        mkvpropeditExit = $null
        chapterNames = @()
        durationDeltaSec = $null
        sizeDeltaPct = $null
        decodeExit = $null
        checks = $null
        pass = $false
        error = $null
    }
    if ($o.finalName -cne $o.outputName) {
        $row.manifestOutputName = $o.outputName
        $row.nameSanitizedFrom = $o.sanitizedFrom
        $row.nameShorteningSteps = $o.shorteningSteps
    }
    Write-Host "--- $($o.finalName)" -ForegroundColor Cyan
    if (@($o.missingChapters).Count -gt 0) {
        Write-Host ("  missingChapters: {0} (see manifest for numbers/names/reasons)" -f @($o.missingChapters).Count) -ForegroundColor Yellow
    }
    try {
        if ($TagsOnly) {
            Write-Host '  tags-only: mkvpropedit --edit info --set title + --tags all (metadata only, no remux)' -ForegroundColor Gray
            $meta = Invoke-MetadataPass -Path $outPath -Title $o.mkvTitle
            $row.mkvpropeditExit = $meta.exit
            $row.warnings = @($meta.warnings)
            $row.metadataOutput = $meta.output
            if ($meta.exit -ge 2) { throw "mkvpropedit (title/tags) failed with exit $($meta.exit)" }
            $row.pass = $true
            Add-RunLogRow -Row $row
            Write-Host '  TAGS PASS APPLIED' -ForegroundColor Green
            continue
        }

        $inputInfo = $null
        $skipBuild = $false
        if ($o.existsAlready -and -not $VerifyOnly) {
            # D2 resume: verify the existing output; never overwrite.
            Write-Host '  existing output found: resume-verify (merge skipped if it passes)' -ForegroundColor Gray
            $row.resumed = $true
            $inputInfo = Get-InputMetric -Paths $srcPaths -RenameOnly:([bool]$o.standalone)
            if (-not $inputInfo.ok) {
                if ($o.standalone) {
                    $inputInfo = Get-InputMetric -Paths @($outPath) -RenameOnly
                    $inputInfo.source = 'self-reference (rename-only, sources already renamed)'
                }
                else {
                    $prior = Get-PriorRunlogRow -FinalName $o.finalName -ManifestName $o.outputName
                    if ($null -ne $prior) {
                        $inputInfo = @{
                            ok = $true; source = 'runlog-fallback'; sumDurSec = [double]$prior.checks.duration.sumInputSec
                            metrics = @($prior.checks.duration.inputMetrics); inVideo = "$($prior.checks.codecs.inVideo)"
                            inAudio = "$($prior.checks.codecs.inAudio)"; sumBytes = [long]$prior.checks.size.sumInputBytes
                        }
                    }
                }
            }
            if (-not $inputInfo.ok) { throw "Existing output cannot be verified: input metrics unavailable (sources missing, no usable runlog row)" }
            $skipBuild = $true
        }
        elseif ($o.existsAlready -and $VerifyOnly) {
            $inputInfo = Get-InputMetric -Paths $srcPaths -RenameOnly:([bool]$o.standalone)
            if (-not $inputInfo.ok) {
                if ($o.standalone) {
                    $inputInfo = Get-InputMetric -Paths @($outPath) -RenameOnly
                    $inputInfo.source = 'self-reference (rename-only)'
                }
                else {
                    $prior = Get-PriorRunlogRow -FinalName $o.finalName -ManifestName $o.outputName
                    if ($null -ne $prior) {
                        $inputInfo = @{
                            ok = $true; source = 'runlog-fallback'; sumDurSec = [double]$prior.checks.duration.sumInputSec
                            metrics = @($prior.checks.duration.inputMetrics); inVideo = "$($prior.checks.codecs.inVideo)"
                            inAudio = "$($prior.checks.codecs.inAudio)"; sumBytes = [long]$prior.checks.size.sumInputBytes
                        }
                    }
                }
            }
            if (-not $inputInfo.ok) { throw "Cannot verify: input metrics unavailable (sources missing, no usable runlog row)" }
            $skipBuild = $true
        }

        if (-not $skipBuild) {
            if ($o.standalone) {
                $inputInfo = Get-InputMetric -Paths $srcPaths -RenameOnly:([bool]$o.standalone)
                if (-not $inputInfo.ok) { throw "Standalone source probe failed: $($srcPaths[0])" }
                $inputInfo.source = 'pre-rename'
                Write-Host '  rename-only: Rename-Item + mkvpropedit title/global-TITLE' -ForegroundColor Gray
                Rename-Item -LiteralPath $srcPaths[0] -NewName $o.finalName -Confirm:$false
                $renamedActual[$o.sources[0].file] = $o.finalName
                $meta = Invoke-MetadataPass -Path $outPath -Title $o.mkvTitle
                $row.mkvpropeditExit = $meta.exit
                $row.warnings = @($meta.warnings)
                if ($meta.exit -ge 2) { throw "mkvpropedit (title/tags) failed with exit $($meta.exit)" }
            }
            else {
                # Live per-output space re-check (concurrent lanes write to D:).
                $driveName = $DvdsRoot.Substring(0, 1)
                $freeNow = (Get-PSDrive -Name $driveName).Free
                $outNeed = 1.2 * ($o.sources | ForEach-Object { (Get-Item -LiteralPath (Join-Path $dir $_.file)).Length } | Measure-Object -Sum).Sum + 1GB
                if ($freeNow -le $outNeed) { throw "per-output space guard failed: free $([math]::Round($freeNow/1GB,2)) GB <= needed $([math]::Round($outNeed/1GB,2)) GB" }
                $inputInfo = Get-InputMetric -Paths $srcPaths -RenameOnly:([bool]$o.standalone)
                if (-not $inputInfo.ok) { throw "Input duration metrics unavailable for merge (subtitle stream or probe failure)" }
                $mergeArgs = @('-o', $outPath, '--title', $o.mkvTitle, '--generate-chapters', 'when-appending')
                for ($i = 0; $i -lt $srcPaths.Count; $i++) {
                    $mergeArgs += $srcPaths[$i]
                    if ($i -lt ($srcPaths.Count - 1)) { $mergeArgs += '+' }
                }
                Write-Host ("  pass 1: mkvmerge append ({0} files)" -f $srcPaths.Count) -ForegroundColor Gray
                $mergeOut = & $mkvmerge @mergeArgs 2>&1 | ForEach-Object { "$_" }
                $row.mkvmergeExit = $LASTEXITCODE
                $row.warnings = @($mergeOut | Where-Object { $_ -match 'Warning:|Error:' })
                $row.mergeOutput = ($mergeOut -join "`n")
                if ($LASTEXITCODE -ge 2) { throw "mkvmerge failed with exit $LASTEXITCODE" }
                foreach ($w in $row.warnings) { Write-Host "  $w" -ForegroundColor Yellow }
                Write-Host '  pass 2: mkvextract chapters -> ChapterString rewrite -> mkvpropedit' -ForegroundColor Gray
                $xmlText = (& $mkvextract chapters $outPath 2>&1 | ForEach-Object { "$_" }) -join "`n"
                if ($LASTEXITCODE -ge 2) { throw "mkvextract chapters failed with exit $LASTEXITCODE" }
                $rx = [regex]::new('<ChapterString>.*?</ChapterString>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
                $found = $rx.Matches($xmlText)
                if ($found.Count -ne $expectedNames.Count) { throw "extracted chapter count $($found.Count) != manifest $($expectedNames.Count)" }
                $sb = [System.Text.StringBuilder]::new()
                $pos = 0
                for ($i = 0; $i -lt $found.Count; $i++) {
                    $m = $found[$i]
                    [void]$sb.Append($xmlText.Substring($pos, $m.Index - $pos))
                    [void]$sb.Append('<ChapterString>')
                    [void]$sb.Append([System.Security.SecurityElement]::Escape($expectedNames[$i]))
                    [void]$sb.Append('</ChapterString>')
                    $pos = $m.Index + $m.Length
                }
                [void]$sb.Append($xmlText.Substring($pos))
                [System.IO.File]::WriteAllText($tmpXmlPath, $sb.ToString(), $utf8)
                try {
                    $peOut = & $mkvpropedit $outPath --chapters $tmpXmlPath 2>&1 | ForEach-Object { "$_" }
                    $row.chaptersPropeditExit = $LASTEXITCODE
                    $row.warnings = @($row.warnings + @($peOut | Where-Object { $_ -match 'Warning:|Error:' }))
                    if ($LASTEXITCODE -ge 2) { throw "mkvpropedit (chapters) failed with exit $LASTEXITCODE" }
                }
                finally {
                    if (Test-Path -LiteralPath $tmpXmlPath) { Remove-Item -LiteralPath $tmpXmlPath -Force -Confirm:$false }
                }
                Write-Host '  pass 3: mkvpropedit title + global TITLE tag overwrite' -ForegroundColor Gray
                $meta = Invoke-MetadataPass -Path $outPath -Title $o.mkvTitle
                $row.mkvpropeditExit = $meta.exit
                $row.warnings = @($row.warnings + @($meta.warnings))
                if ($meta.exit -ge 2) { throw "mkvpropedit (title/tags) failed with exit $($meta.exit)" }
            }
        }

        $v = Invoke-OutputVerification -OutPath $outPath -Entry $o -InputInfo $inputInfo -StandaloneRename:([bool]$o.standalone)
        $row.checks = $v.checks
        $row.chapterNames = $v.chapterNames
        $row.durationDeltaSec = $v.durationDeltaSec
        $row.sizeDeltaPct = $v.sizeDeltaPct
        $row.decodeExit = $v.decodeExit
        $row.pass = $v.pass
        if ($row.pass) {
            if ($row.resumed) { Write-Host '  RESUME VERIFY PASS (merge skipped)' -ForegroundColor Green }
            else { Write-Host '  OUTPUT PASS' -ForegroundColor Green }
        }
        else {
            Write-Host '  OUTPUT FAIL' -ForegroundColor Red
            $folderFailed = $true
            if ($row.resumed) { $row.error = 'existing output failed resume verification; folder stopped, output left untouched' }
        }
    }
    catch {
        $row.error = "$_"
        $row.pass = $false
        Write-Host "  FAILED: $_" -ForegroundColor Red
        $folderFailed = $true
    }
    Add-RunLogRow -Row $row
    if ($folderFailed) {
        Write-Host 'Folder stopped at first failure; no repairs attempted; all sources kept.' -ForegroundColor Red
        break
    }
}

# --- Post-folder integrity: title rips + source state ---------------------------
$titleNow = @(Get-ChildItem -LiteralPath $dir -File -Filter 'title *.mkv')
$titleOk = ($titleNow.Count -eq $titleSnap.Count)
$titleEvidence = @()
foreach ($s in $titleSnap) {
    $cur = $titleNow | Where-Object { $_.Name -ceq $s.name }
    $ok = ($null -ne $cur -and $cur.LastWriteTimeUtc -eq $s.lwt -and $cur.Length -eq $s.len)
    if (-not $ok) { $titleOk = $false }
    $titleEvidence += [ordered]@{
        name = $s.name
        beforeUtc = $s.lwt.ToString('o')
        afterUtc = $(if ($cur) { $cur.LastWriteTimeUtc.ToString('o') } else { 'MISSING' })
        unchanged = $ok
    }
}
# Only standalones actually renamed THIS run map source->output; a standalone that failed
# before its rename keeps its source file, which the normal snapshot check below covers.
# Standalones renamed in earlier runs have their source in $preMissing (already gone).
$unexpectedMissing = @()
$changed = @()
foreach ($s in $srcNames) {
    if ($renamedActual.ContainsKey($s)) {
        if (-not (Test-Path -LiteralPath (Join-Path $dir $renamedActual[$s]))) { $unexpectedMissing += $s }
        continue
    }
    if ($preMissing -contains $s) {
        if (Test-Path -LiteralPath (Join-Path $dir $s)) { $changed += $s }
        continue
    }
    $p = Join-Path $dir $s
    if (-not (Test-Path -LiteralPath $p)) {
        # Transient-absence guard (retro 2026-11-17): re-check once before
        # declaring a source unexpectedly missing; a momentary filter-driver
        # or scanner blip is not evidence of loss.
        Start-Sleep -Seconds 5
        if (-not (Test-Path -LiteralPath $p)) { $unexpectedMissing += $s; continue }
    }
    $cur = Get-Item -LiteralPath $p
    if ($cur.Length -ne $srcSnap[$s].len -or $cur.LastWriteTimeUtc -ne $srcSnap[$s].lwt) { $changed += $s }
}
$sourcesOk = ($unexpectedMissing.Count -eq 0 -and $changed.Count -eq 0)
Write-Host ("title rips unchanged: {0} ({1} tracked)" -f $titleOk, $titleSnap.Count) -ForegroundColor $(if ($titleOk) { 'Green' } else { 'Red' })
foreach ($t in $titleEvidence) { Write-Host ("  {0}: {1} -> {2} unchanged={3}" -f $t.name, $t.beforeUtc, $t.afterUtc, $t.unchanged) -ForegroundColor Gray }
Write-Host ("sources unmodified during run: {0}" -f $sourcesOk) -ForegroundColor $(if ($sourcesOk) { 'Green' } else { 'Red' })
if ($unexpectedMissing.Count -gt 0) { Write-Host ("  UNEXPECTEDLY MISSING: {0}" -f ($unexpectedMissing -join '; ')) -ForegroundColor Red }
if ($changed.Count -gt 0) { Write-Host ("  CHANGED: {0}" -f ($changed -join '; ')) -ForegroundColor Red }

# --- Delete-after-verify (merge mode only; manifest-listed sources only) ---------
$allPass = (-not $folderFailed) -and $titleOk -and $sourcesOk
$deleted = @()
$deletedBytes = [long]0
$deletionSkipped = @()
if ($allPass -and $modeLabel -ceq 'merge' -and -not $NoDelete) {
    foreach ($s in $srcNames) {
        if ($renamedActual.ContainsKey($s)) { continue }
        if ($preMissing -contains $s) { continue }
        if ($s -match '^title \d+\.mkv$' -or $s -ceq 'tags.json' -or $finalNames -contains $s) {
            $deletionSkipped += $s
            continue
        }
        $p = Join-Path $dir $s
        if (-not (Test-Path -LiteralPath $p)) { continue }
        $len = (Get-Item -LiteralPath $p).Length
        Remove-Item -LiteralPath $p -Force -Confirm:$false
        $deleted += [ordered]@{ name = $s; bytes = $len }
        $deletedBytes += $len
        Write-Host ("  DELETED source: {0} ({1:N0} bytes)" -f $s, $len) -ForegroundColor Gray
    }
    Write-Host ("sources deleted after verify: {0} files, {1:N2} GB" -f $deleted.Count, ($deletedBytes / 1GB)) -ForegroundColor Green
}
elseif ($allPass -and $modeLabel -ceq 'merge' -and $NoDelete) {
    Write-Host 'sources kept: -NoDelete specified' -ForegroundColor Yellow
}
elseif (-not $allPass) {
    Write-Host 'sources kept: folder did not pass full verification' -ForegroundColor Yellow
}

Add-RunLogRow -Row ([ordered]@{
    timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    rowType = 'folder-summary'
    folder = $Folder
    mode = $modeLabel
    outputs = $workList.Count
    spaceGuard = $spaceGuard
    titleRips = $titleEvidence
    sourcesPreMissing = $preMissing
    sourcesRenamed = @($renamedActual.Keys | ForEach-Object { [ordered]@{ file = $_; finalName = $renamedActual[$_] } })
    sourcesDeleted = $deleted
    deletedCount = $deleted.Count
    deletedBytes = $deletedBytes
    deletionSkipped = $deletionSkipped
    sourcesChanged = $changed
    sourcesUnexpectedlyMissing = $unexpectedMissing
    pass = $allPass
})
if ($allPass) { Write-Host "FOLDER PASS: $Folder" -ForegroundColor Green; exit 0 }
Write-Host "FOLDER FAIL: $Folder" -ForegroundColor Red
exit 1
