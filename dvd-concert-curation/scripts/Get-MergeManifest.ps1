#!/usr/bin/env pwsh
# Get-MergeManifest.ps1 — merge manifest for the DVD split-works project (tags.json-primary).
# READ-ONLY on the DVDs root: only Get-ChildItem / Get-Content are used against it. No ffprobe.
# Emits manifest.json + manifest-review.md into -OutDir (default: this script's directory).
# Metadata precedence: owner research overrides > tags.json > filename parse > curated folder table.

[CmdletBinding()]
param(
    [string]$DvdsRoot = 'D:\DVDs',
    [string]$OutDir = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'

# --- Curated scope: 17 folders (SHOSTAKOVICH SOLTI handled separately).
# --- Soloist/conductor values are FALLBACK only, used when tags.json has no performers.
$folderSpecs = @(
    @{ name = 'Beethoven - Piano Concertos (Idil Biret, Antoni Wit)'; soloist = 'Idil Biret'; conductor = 'Antoni Wit' }
    @{ name = 'Beethoven {Solti-Perahia}'; soloist = 'Murray Perahia'; conductor = 'Georg Solti' }
    @{ name = 'Brahms 4; Ravel - La Valse (JPO, Markevitch)'; soloist = $null; conductor = 'Igor Markevitch' }
    @{ name = 'Cluytens at Moscow'; soloist = $null; conductor = 'André Cluytens' }
    @{ name = 'Maazel Beethoven Symphony No.6'; soloist = $null; conductor = 'Lorin Maazel' }
    @{ name = 'Mahler_9_Barenboim_dvd'; soloist = $null; conductor = 'Daniel Barenboim' }
    @{ name = 'MARKEVITCH Classic Archive 10'; soloist = $null; conductor = 'Igor Markevitch' }
    @{ name = 'Mozart - Concertos 2&3 Pianos'; soloist = $null; conductor = $null }
    @{ name = 'Rossini Mendelssohn'; soloist = $null; conductor = $null }
    @{ name = 'Solti in Concert'; soloist = $null; conductor = 'Georg Solti' }
    @{ name = 'Stravinsky - Le Sacre du Printemps; Sibelius - Symphony No.5 (Bernstein)'; soloist = $null; conductor = 'Leonard Bernstein' }
    @{ name = 'Tchaikovsky 6, Shostakovich - Forests (Svetlanov in Japan, DVD9)'; soloist = $null; conductor = 'Evgeny Svetlanov' }
    @{ name = 'Tchaikovsky 6; Moussorgsky - Pictures at the Excibition (NHK, Markevitch)'; soloist = $null; conductor = 'Igor Markevitch' }
    @{ name = 'Tchaikovsky Festival'; soloist = $null; conductor = $null }
    @{ name = 'Tchaikovsky_Gergiev'; soloist = $null; conductor = 'Valery Gergiev' }
    @{ name = 'Wagner Strauss'; soloist = $null; conductor = $null }
    @{ name = 'Yuri Temirkanov Conducts Rachmaninov & Rimsky-Korsakov [2013, Annecy Classic Festival, DVD9]'; soloist = $null; conductor = 'Yuri Temirkanov' }
)

# --- Owner research override (follow-up #2, 2026-11-16): MARKEVITCH title 04 Firebird chapters.
# --- Sources: medici.tv programme list for this exact BBC film + duration matching + NRC/Southbank reviews.
$researchOverrides = @{
    'MARKEVITCH Classic Archive 10' = @{
        '4|1'  = @{ chapterName = 'Fireworks'; confidence = 'medium' }
        '4|3'  = @{ chapterName = '1b. Prelude and Dance of the Firebird'; confidence = 'medium' }
        '4|4'  = @{ chapterName = '1c. Variations (Firebird)'; confidence = 'medium' }
        '4|5'  = @{ chapterName = '2. Pantomime I'; confidence = 'medium' }
        '4|6'  = @{ chapterName = '3. Pas de deux (Firebird and Ivan Tsarevich)'; confidence = 'medium' }
        '4|7'  = @{ chapterName = '4. Pantomime II'; confidence = 'medium' }
        '4|8'  = @{ chapterName = '5. Scherzo: Dance of the Princesses'; confidence = 'medium' }
        '4|9'  = @{ chapterName = '6. Pantomime III'; confidence = 'medium' }
        '4|10' = @{ chapterName = '7. Rondo: Khorovod'; confidence = 'medium' }
        '4|11' = @{ chapterName = '8. Infernal Dance'; confidence = 'medium' }
        '4|12' = @{ chapterName = '9. Lullaby (Firebird) / 10. Final Hymn'; confidence = 'medium'; chapterMergeInferred = $true; mergedSections = @(@{ number = '10'; name = 'Final Hymn' }) }
    }
}

# --- Artwork-sourced enrichments (follow-up #3, 2026-11-16).
$artworkVenue = @{
    'Cluytens at Moscow' = 'Grand Hall, Moscow Conservatory (live), 5 & 9 May 1959'
    'Tchaikovsky_Gergiev' = 'Salle Pleyel, Paris, 25-29 Jan 2010'
    'Maazel Beethoven Symphony No.6' = 'Beethovenhalle, Bonn, 1995'
    'Solti in Concert' = 'Gasteig Philharmonie, Munich, 1990'
    'Beethoven {Solti-Perahia}' = 'Barbican Centre, London, 1987'
}
$releaseIds = @{
    'MARKEVITCH Classic Archive 10' = 'EMI DVB 4901109'
    'Mozart - Concertos 2&3 Pianos' = 'Warner Classics 2564 61919-2'
    'Cluytens at Moscow' = 'Dreamlife/Nihon Monitor DLVC-1117'
    'Maazel Beethoven Symphony No.6' = 'Dreamlife DLVC-1042'
    'Mahler_9_Barenboim_dvd' = 'C Major/Unitel Classica 703708'
    'Tchaikovsky_Gergiev' = 'Mariinsky MAR0513'
    'Beethoven {Solti-Perahia}' = 'Arthaus Musik 100 148'
    'Solti in Concert' = 'Arthaus Musik 100 302'
    'Rossini Mendelssohn' = 'Sir Georg Solti: The Maestro, Decca 474 3203 / 074 3203 (4 DVDs, 2007)'
    'Tchaikovsky 6, Shostakovich - Forests (Svetlanov in Japan, DVD9)' = 'NHK Classical 09489AA'
    'Stravinsky - Le Sacre du Printemps; Sibelius - Symphony No.5 (Bernstein)' = 'ICA Classics ICAD5082'
    'Tchaikovsky Festival' = 'Arthaus 109318 (The Tchaikovsky Cycle)'
}

# --- Owner rulings 2026-11-16 (follow-up #5): Bizet group deleted from the project.
# --- Source files already removed by the owner; if any reappear they are surfaced, never merged.
$ownerDeletedGroups = @{
    'Cluytens at Moscow' = @('Bizet - Symphony No. 1 in C major')
}
$ownerStandaloneGroups = @{
    'Cluytens at Moscow' = @('Roussel - Bacchus et Ariane, Suite No. 2')
}
$ownerRulingNotes = @{
    'Cluytens at Moscow' = @(
        'Bizet Symphony No. 1 (2-movement film) deleted by owner as incomplete — content preserved in title 00.mkv.',
        'Roussel Bacchus et Ariane Suite No. 2 is a single-file work: standalone rename by owner ruling (no remux).',
        'Catalogue: our copy reads Dreamlife DLVC-1117; the same film was also issued by Nihon Monitor as DLVC-8045 (2006, 45 min).',
        'Year 1959 well-sourced: Moscow Conservatory sound-archive CD (SMC CD 0183/0033, CiNii BB24485186) documents Cluytens / Orchestre National de France live in the Grand Hall on 5 & 9 May 1959; CDJapan lists original release year 1959.'
    )
}
# --- GATE 1 owner ruling 2026-11-16: accented soloist spelling (tags.json source is ASCII).
$ownerSoloistSpelling = @{ 'Andras Schiff' = 'András Schiff' }

# --- Deep-research reconciliation (owner-adjudicated 2026-11-17): corrections over tags.json.
# --- Keys are filename group keys (composer - work as parsed from the rip names).
$ownerYearDateOverrides = @{
    'Rossini Mendelssohn' = @{
        'Mendelssohn-Bartholdy - Symphony No. 3 in A minor, Op. 56 Scottish' = @{ year = '1979'; date = '1979-10-24' }
        'Mendelssohn-Bartholdy - Violin Concerto in E minor, Op. 64' = @{ year = '1979'; date = '1979-10-24' }
        'Rossini - Il barbiere di Siviglia Overture' = @{ date = '1978-12-06' }
        'Rossini - L''italiana in Algeri Overture' = @{ date = '1978-12-06' }
        'Rossini - La scala di seta Overture' = @{ date = '1978-12-06' }
        'Rossini - Le siege de Corinthe Overture' = @{ date = '1978-12-06' }
        'Rossini - Semiramide Overture' = @{ date = '1978-12-06' }
        'Rossini - La gazza ladra Overture' = @{ date = '1978-12-06' }
        'Mendelssohn-Bartholdy - Symphony No. 4 in A major, Op. 90 Italian' = @{ date = '1976-06-02' }
    }
}
$ownerSoloistOverrides = @{
    'Tchaikovsky 6, Shostakovich - Forests (Svetlanov in Japan, DVD9)' = @{
        'Shostakovich - Song of the Forests, Op. 81' = @('Alexei Maslennikov', 'Alexander Vedernikov')
    }
}
# Canonical standalone-source inventory: original GATE-1-approved rip filenames for every
# rename-only output (works + Talk/Interview extras). The batch lane renames standalones
# mid-run before its folder-end record exists; this inventory keeps the manifest census
# complete at every disk state. Historical fact, not inference (verified against GATE 1).
$legacyRenamedSources = @{
    'Beethoven - Piano Concertos (Idil Biret, Antoni Wit)' = @(
        'T00-01 - Talk - Idil Biret interview - Idil Biret.mkv'
    )
    'Beethoven {Solti-Perahia}' = @(
        'T02-01 - Beethoven - Coriolan Overture, Op. 62 - London Symphony Orchestra - 1987.mkv'
    )
    'Brahms 4; Ravel - La Valse (JPO, Markevitch)' = @(
        '06 - Ravel - La valse, poeme choregraphique - Japan Philharmonic Symphony Orchestra - 1968.mkv'
    )
    'Cluytens at Moscow' = @(
        '07 - Roussel - Bacchus et Ariane, Suite No. 2 - Suite No. 2 (complete, single track) - Orchestre National de France - 1959.mkv'
    )
    'Mahler_9_Barenboim_dvd' = @(
        'T09-01 - Talk - The Mahler Project.mkv'
    )
    'MARKEVITCH Classic Archive 10' = @(
        'T00-01 - Wagner - Tannhauser, Overture - Orchestre National de l''ORTF - 1968.mkv'
    )
    'Rossini Mendelssohn' = @(
        '02 - Rossini - Il barbiere di Siviglia Overture - Chicago Symphony Orchestra - 1978.mkv'
        '03 - Rossini - L''italiana in Algeri Overture - Chicago Symphony Orchestra - 1978.mkv'
        '04 - Rossini - La scala di seta Overture - Chicago Symphony Orchestra - 1978.mkv'
        '05 - Rossini - Le siege de Corinthe Overture - Chicago Symphony Orchestra - 1978.mkv'
        '06 - Rossini - Semiramide Overture - Chicago Symphony Orchestra - 1978.mkv'
        '07 - Rossini - La gazza ladra Overture - Chicago Symphony Orchestra - 1978.mkv'
    )
    'Stravinsky - Le Sacre du Printemps; Sibelius - Symphony No.5 (Bernstein)' = @(
        'T01-01 - Bernstein on Sibelius''s Symphony No. 5 - Interview - 1966.mkv'
        'T02-01 - Bernstein on Stravinsky''s The Rite of Spring - Interview - 1966.mkv'
    )
    'Tchaikovsky Festival' = @(
        '01 - Tchaikovsky - 1812, Festival Overture in E-flat major, Op. 49 - Moscow Radio Symphony Orchestra - 1991.mkv'
    )
    'Tchaikovsky_Gergiev' = @(
        'T01-01 - Talk - Valery Gergiev interview.mkv'
    )
    'Wagner Strauss' = @(
        '02 - Wagner - The Flying Dutchman, Overture - Chicago Symphony Orchestra - 1976.mkv'
        '03 - Wagner - Tannhauser, Overture - Chicago Symphony Orchestra - 1976.mkv'
        '04 - Wagner - Die Meistersinger von Nurnberg, Prelude to Act I - Chicago Symphony Orchestra - 1976.mkv'
        '08 - Strauss - Till Eulenspiegels lustige Streiche, Op. 28 - Chicago Symphony Orchestra.mkv'
        '10 - Strauss - Tod und Verklarung (Death and Transfiguration), Op. 24 - Chicago Symphony Orchestra.mkv'
    )
    'Yuri Temirkanov Conducts Rachmaninov & Rimsky-Korsakov [2013, Annecy Classic Festival, DVD9]' = @(
        'T01-05 - Rachmaninoff - Etude-tableau in A minor, Op. 39 No. 2 - St. Petersburg Philharmonic Orchestra - 2013.mkv'
        'T01-06 - Rachmaninoff - Prelude in G-sharp minor, Op. 32 No. 12 - St. Petersburg Philharmonic Orchestra - 2013.mkv'
        'T01-16 - Elgar - Salut d''amour, Op. 12 - St. Petersburg Philharmonic Orchestra - 2013.mkv'
        'T01-18 - Verdi - La forza del destino, Overture - St. Petersburg Philharmonic Orchestra - 2013.mkv'
    )
}

$extraKeywords = @('talk', 'interview', 'applause', 'intro', 'encore')

function Get-NormalizedText {
    param([string]$Text)
    if (-not $Text) { return '' }
    $formD = $Text.Normalize([System.Text.NormalizationForm]::FormD)
    $sb = [System.Text.StringBuilder]::new()
    foreach ($ch in $formD.ToCharArray()) {
        if ([System.Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch) -ne [System.Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$sb.Append($ch)
        }
    }
    $ascii = $sb.ToString().ToLowerInvariant()
    return (($ascii -replace '[^a-z0-9]+', ' ').Trim())
}

function Get-ExtraKindFromName {
    param([string[]]$Pieces)
    if ($Pieces.Count -lt 2) { return $null }
    $targets = @($Pieces[1])
    if ($Pieces.Count -ge 3) { $targets += $Pieces[2] }
    $kinds = @()
    foreach ($t in $targets) {
        foreach ($k in $extraKeywords) { if ($t -like "*$k*") { $kinds += $k } }
    }
    if ($Pieces[1] -match '^Chapter\s+\d+$') { $kinds += 'chapter' }
    if ($kinds.Count -eq 0) { return $null }
    if ($kinds -contains 'talk') { return 'talk' }
    if ($kinds -contains 'interview') { return 'interview' }
    foreach ($k in @('applause', 'encore', 'intro', 'chapter')) {
        if ($kinds -contains $k) { return $k }
    }
    return $null
}

function Get-ExtraChapterName {
    param([string[]]$Pieces, [string]$Kind)
    if ($Pieces[1] -like "*$Kind*" -or ($Kind -eq 'chapter' -and $Pieces[1] -match '^Chapter\s+\d+$')) {
        return $Pieces[1]
    }
    if ($Pieces.Count -ge 3) { return $Pieces[2] }
    return $Pieces[1]
}

function Join-Segment {
    param([string[]]$Pieces, [int]$From, [int]$To)
    if ($To -lt $From) { return '' }
    return ($Pieces[$From..$To] -join ' - ')
}

function Get-PossessiveComposer {
    # Owner ruling 2026-11-17: surname possessive, first names dropped.
    # 'Ludwig van Beethoven' -> "Beethoven's"; 'Gioachino Rossini' -> "Rossini's".
    param([string]$Composer)
    $tokens = @($Composer -split '\s+' | Where-Object { $_ })
    if ($tokens.Count -eq 0) { return $Composer }
    return "$($tokens[-1])'s"
}

function Format-OutputName {
    param([string]$Composer, [string]$Work, [string[]]$Performers, $Year, [switch]$Standalone)
    # Possessive-surname style: "Surname's Work - Performers (Year)".
    # Two performers join with ' and '; three or more with ', ' (owner ruling 2026-11-17).
    $plist = @($Performers | Where-Object { $_ })
    $perf = $(if ($plist.Count -eq 2) { $plist -join ' and ' } else { $plist -join ', ' })
    if ($Standalone) {
        # Talks/interviews: the subject leads, the generic kind keyword drops
        # (song-parallel form "Subject - Person (Year)").
        $name = $Work
    }
    else {
        $name = "$(Get-PossessiveComposer -Composer $Composer) $Work"
    }
    if ($perf) { $name += " - $perf" }
    if ($Year) { $name += " ($Year)" }
    return "$name.mkv"
}

function Format-SanitizedName {
    param([string]$Name)
    # Owner ruling 2026-11-17 (Option A): Windows-illegal chars in filenames/titles only.
    # ASCII " -> paired curly quotes U+201C/U+201D; ASCII : -> U+A789 modifier-letter colon.
    $sb = [System.Text.StringBuilder]::new()
    $open = $true
    foreach ($ch in $Name.ToCharArray()) {
        if ($ch -eq '"') {
            if ($open) { [void]$sb.Append([char]0x201C) } else { [void]$sb.Append([char]0x201D) }
            $open = -not $open
        }
        elseif ($ch -eq ':') { [void]$sb.Append([char]0xA789) }
        else { [void]$sb.Append($ch) }
    }
    return $sb.ToString()
}

function Get-FittedOutputName {
    # D3 (owner-approved): deterministic shortening while full path > $MaxPathLength.
    # New-style core = "Surname's Work - Performers" (owner ruling 2026-11-17).
    # Order: opus/catalogue number -> orchestra -> truncate work text. The possessive
    # surname prefix and the year/.mkv tail are untouched.
    param([string]$Name, [string]$Directory, [string]$Orchestra, [int]$MaxPathLength = 240)
    $steps = [System.Collections.Generic.List[string]]::new()
    if ((Join-Path $Directory $Name).Length -le $MaxPathLength) { return @{ name = $Name; steps = @() } }
    $tail = ''
    $core = $Name
    if ($Name -match '^(.*)( \(\d{4}\)\.mkv)$') { $core = $Matches[1]; $tail = $Matches[2] }
    elseif ($Name.EndsWith('.mkv')) { $core = $Name.Substring(0, $Name.Length - 4); $tail = '.mkv' }
    else { throw "Cannot shorten output name without .mkv tail: $Name" }
    $parts = $core -split ' - ', 2
    $composerWork = $parts[0]
    $credits = $(if ($parts.Count -ge 2) { $parts[1] } else { '' })
    # Keep the possessive prefix separate so truncation never cuts the surname.
    $prefix = ''
    $work = $composerWork
    if ($composerWork -match "^(\S+'s)\s+(.*)$") { $prefix = $Matches[1] + ' '; $work = $Matches[2] }
    $opusRx = '\s*,?\s*\b(?:Op\.|K\.|KV|D\.|BWV|Hob\.|WoO|TrV|AV|Anh\.)\s*\d+(?:\s*(?:No\.|Nr\.)\s*\d+)?'
    $work2 = [regex]::Replace($work, $opusRx, '')
    if ($work2 -cne $work) {
        $steps.Add("opus/catalogue dropped: work '$work' -> '$work2'")
        $work = $work2
    }
    $name = ((@(($prefix + $work), $credits) | Where-Object { $_ }) -join ' - ') + $tail
    if ((Join-Path $Directory $name).Length -le $MaxPathLength) { return @{ name = $name; steps = $steps.ToArray() } }
    $credits2 = $credits
    if ($Orchestra -and $credits.IndexOf($Orchestra, [System.StringComparison]::Ordinal) -ge 0) {
        $credits2 = $credits.Replace(" and $Orchestra", '').Replace("$Orchestra and ", '').Replace(", $Orchestra", '').Replace("$Orchestra, ", '').Replace($Orchestra, '')
    }
    elseif ($credits.Contains(', ')) {
        $credits2 = $credits.Substring(0, $credits.LastIndexOf(', '))
    }
    elseif ($credits.Contains(' and ')) {
        $credits2 = $credits.Substring(0, $credits.LastIndexOf(' and '))
    }
    if ($credits2 -cne $credits) {
        $steps.Add("orchestra dropped: credits '$credits' -> '$credits2'")
        $credits = $credits2.Trim().TrimEnd(',').Trim()
    }
    $name = ((@(($prefix + $work), $credits) | Where-Object { $_ }) -join ' - ') + $tail
    if ((Join-Path $Directory $name).Length -le $MaxPathLength) { return @{ name = $name; steps = $steps.ToArray() } }
    $overhead = (Join-Path $Directory ($prefix + ' - ' + $credits + $tail)).Length + 3
    $budget = $MaxPathLength - $overhead
    if ($budget -lt 1) { throw "Output path cannot fit within $MaxPathLength chars even with empty work: $Name" }
    if ($work.Length -gt $budget) {
        $cut = $work.Substring(0, $budget)
        $sp = $cut.LastIndexOf(' ')
        if ($sp -gt 0) { $cut = $cut.Substring(0, $sp) }
        $steps.Add("work truncated: '$work' -> '$cut'")
        $work = $cut
    }
    $name = ((@(($prefix + $work), $credits) | Where-Object { $_ }) -join ' - ') + $tail
    if ((Join-Path $Directory $name).Length -gt $MaxPathLength) {
        throw "Output path still exceeds $MaxPathLength chars after all shortening steps: $name"
    }
    return @{ name = $name; steps = $steps.ToArray() }
}

function Get-ConfidenceRank {
    param($Confidence)
    switch ("$Confidence") {
        'high' { return 3 }
        'medium' { return 2 }
        'low' { return 1 }
        default { return 0 }
    }
}

function Get-ChapterLabel {
    param($MovementNumber, $Movement)
    $mn = "$MovementNumber".Trim()
    $mv = "$Movement".Trim()
    if ($mn -and $mv) {
        $sep = if ($mn.EndsWith('.')) { ' ' } else { '. ' }
        return "$mn$sep$mv"
    }
    if ($mv) { return $mv }
    return $null
}

function Format-TitleSource {
    param($Refs)
    $parts = @()
    $byTitle = @($Refs | Where-Object { $_.titleFile } | Group-Object titleFile | Sort-Object Name)
    foreach ($g in $byTitle) {
        $nums = @($g.Group | ForEach-Object { [int]$_.chapter } | Sort-Object -Unique)
        $runs = @()
        $i = 0
        while ($i -lt $nums.Count) {
            $j = $i
            while (($j + 1) -lt $nums.Count -and $nums[$j + 1] -eq ($nums[$j] + 1)) { $j++ }
            if ($j -gt $i) { $runs += "$($nums[$i])-$($nums[$j])" } else { $runs += "$($nums[$i])" }
            $i = $j + 1
        }
        $parts += "$($g.Name) ch $($runs -join ', ')"
    }
    return ($parts -join '; ')
}

if (-not (Test-Path -LiteralPath $DvdsRoot)) { throw "DVDs root not found: $DvdsRoot" }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

$manifestFolders = @()
$censusRows = @()
$grandMatched = 0; $grandAssigned = 0; $grandOutputs = 0; $grandStandalones = 0; $grandUnclassified = 0
$censusErrors = @()

foreach ($spec in $folderSpecs) {
    $folderName = $spec.name
    $dir = Join-Path $DvdsRoot $folderName
    Write-Host "=== $folderName ===" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $dir)) {
        $censusErrors += "Folder missing: $folderName"
        Write-Host '  MISSING FOLDER' -ForegroundColor Red
        continue
    }

    $matched = @(Get-ChildItem -LiteralPath $dir -File |
        Where-Object { $_.Extension -eq '.mkv' -and $_.BaseName -match '^(T\d{2}-\d{2}|\d{2}) - ' } |
        Sort-Object Name)
    # Census completeness: union disk files with recorded/historical source names. The batch
    # lane deletes merged sources and renames standalones mid-run; the plan of record must
    # stay complete at every disk state (runlog deletion/rename records + canonical inventory).
    $reconstructed = $false
    $runlogPathGen = Join-Path $PSScriptRoot 'runlog.json'
    $recoverNames = @()
    if (Test-Path -LiteralPath $runlogPathGen) {
        $sumRows = @(Get-Content -LiteralPath $runlogPathGen | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json } |
            Where-Object { $_.rowType -ceq 'folder-summary' -and $_.folder -ceq $folderName })
        $delRow = $sumRows | Where-Object { $_.deletedCount -gt 0 } | Select-Object -Last 1
        $renRow = $sumRows | Where-Object { @($_.sourcesRenamed).Count -gt 0 } | Select-Object -Last 1
        if ($null -ne $delRow) { $recoverNames += @($delRow.sourcesDeleted | ForEach-Object { $_.name }) }
        if ($null -ne $renRow) { $recoverNames += @($renRow.sourcesRenamed | ForEach-Object { $_.file }) }
    }
    if ($legacyRenamedSources.ContainsKey($folderName)) { $recoverNames += @($legacyRenamedSources[$folderName]) }
    $diskNames = @($matched | ForEach-Object { $_.Name })
    $extraNames = @($recoverNames | Select-Object -Unique | Where-Object { $diskNames -notcontains $_ })
    if ($extraNames.Count -gt 0) {
        $matched = @($matched + @($extraNames | ForEach-Object { [pscustomobject]@{ Name = $_; BaseName = [System.IO.Path]::GetFileNameWithoutExtension($_) } }) | Sort-Object Name)
        $reconstructed = $true
        Write-Host ("  census recovery: {0} source(s) reconstructed from records/inventory (already merged or renamed)" -f $extraNames.Count) -ForegroundColor Yellow
    }
    Write-Host ("  matched named mkv files: {0}" -f $matched.Count) -ForegroundColor Gray

    # --- tags.json: primary metadata source ---------------------------------
    $tagsPath = Join-Path $dir 'tags.json'
    $tags = $null
    if (Test-Path -LiteralPath $tagsPath) {
        $tags = Get-Content -LiteralPath $tagsPath -Raw | ConvertFrom-Json
    }
    else {
        Write-Host '  WARNING: tags.json missing — filename rules only' -ForegroundColor Yellow
    }
    $chapterIndex = @{}
    $titleEntries = @()
    if ($tags -and $tags.titles) {
        foreach ($t in $tags.titles) {
            $tt = $null
            if ($t.title_file -match '^title (\d+)\.mkv$') { $tt = [int]$Matches[1] }
            $titleEntries += [pscustomobject]@{ titleFile = $t.title_file; tt = $tt; chapters = @($t.chapters) }
            foreach ($c in $t.chapters) {
                if ($null -ne $tt) { $chapterIndex["$tt|$($c.chapter)"] = @{ chapter = $c; titleFile = $t.title_file } }
            }
        }
    }

    # --- Pass 1: filename parse (fallback metadata + join key) --------------
    $records = @()
    foreach ($f in $matched) {
        $pieces = @($f.BaseName -split ' - ')
        $tt = $null; $cc = $null
        if ($pieces[0] -match '^T(\d{2})-(\d{2})$') { $tt = [int]$Matches[1]; $cc = [int]$Matches[2] }
        elseif ($pieces[0] -match '^(\d{2})$') { $cc = [int]$Matches[1] }
        else {
            $records += [ordered]@{ file = $f.Name; pieces = $pieces; tt = $null; cc = $null; kind = 'unclassified'; reason = 'prefix does not match T\d\d-\d\d or \d\d' }
            continue
        }
        $r = [ordered]@{
            file = $f.Name; pieces = $pieces; tt = $tt; cc = $cc
            nameExtraKind = (Get-ExtraKindFromName -Pieces $pieces)
            kind = $null; tagsChapter = $null; titleFile = $null; tagsRef = $null
            tagsMismatch = $false; mismatchReason = $null
            effectiveConfidence = $null; researchResolved = $false; chapterMergeInferred = $false
            foldedInto = $null; foldSide = $null; sourceFlags = @()
        }
        $records += $r
    }

    # Orchestra candidates from well-formed filename parses (fallback only).
    $orchSet = @()
    foreach ($r in $records) {
        $p = $r.pieces; $n = $p.Count
        if ($n -ge 5 -and $p[$n - 1] -match '^\d{4}$') {
            $o = ($p[$n - 2] -replace '\s*-\s*$', '').Trim()
            if ($orchSet -notcontains $o) { $orchSet += $o }
        }
    }

    foreach ($r in $records) {
        if ($r.kind -eq 'unclassified') { continue }
        $p = $r.pieces; $n = $p.Count
        if ($n -ge 3) {
            $r.composer = $p[1]
            $r.work = $p[2]
            $r.groupKey = "$($p[1]) - $($p[2])"
        }
        $r.truncatedMovement = $false
        if ($n -lt 4) {
            if ($null -eq $r.nameExtraKind) {
                $r.kind = 'unclassified'; $r.reason = "only $n segments; cannot identify composer/work/orchestra"
                continue
            }
        }
        if ($n -ge 4) {
            $last = $p[$n - 1]
            if ($last -match '^\d{4}$') {
                $r.year = $last
                $r.orchestra = ($p[$n - 2] -replace '\s*-\s*$', '').Trim()
                if ($n -gt 5) { $r.movement = Join-Segment -Pieces $p -From 3 -To ($n - 3); $r.movementMissing = $false }
                else { $r.movement = ''; $r.movementMissing = $true }
            }
            else {
                $r.year = $null
                $r.sourceFlags += 'noYearInName'
                $lastTrim = ($last -replace '\s*-\s*$', '').Trim()
                $orchLike = ($orchSet -contains $lastTrim) -or
                    ($lastTrim.Length -ge 3 -and @($orchSet | Where-Object { $_.StartsWith($lastTrim) }).Count -gt 0) -or
                    ($lastTrim -match 'orchestr|orchestre|philharmon|symphony')
                if ($orchLike) {
                    $r.orchestra = $lastTrim
                    if ($lastTrim -ne $last) { $r.sourceFlags += 'trailingDashArtifact' }
                    if (@($orchSet | Where-Object { $_.Length -gt $lastTrim.Length -and $_.StartsWith($lastTrim) }).Count -gt 0) {
                        $r.sourceFlags += 'orchestraTruncated'
                    }
                    if ($n -gt 4) { $r.movement = Join-Segment -Pieces $p -From 3 -To ($n - 2); $r.movementMissing = ($r.movement -eq '') }
                    else { $r.movement = ''; $r.movementMissing = $true }
                }
                else {
                    $r.orchestra = $null
                    $r.movement = Join-Segment -Pieces $p -From 3 -To ($n - 1)
                    $r.movementMissing = ($r.movement -eq '')
                    $r.truncatedMovement = $true
                    $r.sourceFlags += 'movementTruncated'
                }
            }
        }
        else {
            $r.movement = ''; $r.movementMissing = $true; $r.orchestra = $null; $r.year = $null
        }
    }

    # --- Pass 2: join to tags.json chapters ----------------------------------
    foreach ($r in $records) {
        if ($r.kind -eq 'unclassified') { continue }
        $join = $null
        if ($null -ne $r.tt) {
            $key = "$($r.tt)|$($r.cc)"
            if ($chapterIndex.ContainsKey($key)) { $join = $chapterIndex[$key] }
            else { $r.tagsMismatch = $true; $r.mismatchReason = "no tags chapter for title $($r.tt) chapter $($r.cc)" }
        }
        else {
            $candidates = @($titleEntries | Where-Object { @($_.chapters | Where-Object { [int]$_.chapter -eq $r.cc }).Count -gt 0 })
            if ($candidates.Count -eq 1) {
                $ch = @($candidates[0].chapters | Where-Object { [int]$_.chapter -eq $r.cc })[0]
                $join = @{ chapter = $ch; titleFile = $candidates[0].titleFile }
            }
            elseif ($candidates.Count -gt 1) {
                $byContent = @($candidates | Where-Object {
                    $ch = @($_.chapters | Where-Object { [int]$_.chapter -eq $r.cc })[0]
                    ($ch.work) -and ((Get-NormalizedText $ch.work) -eq (Get-NormalizedText $r.work))
                })
                if ($byContent.Count -eq 1) {
                    $ch = @($byContent[0].chapters | Where-Object { [int]$_.chapter -eq $r.cc })[0]
                    $join = @{ chapter = $ch; titleFile = $byContent[0].titleFile }
                }
                else {
                    $r.tagsMismatch = $true; $r.mismatchReason = "bare chapter $($r.cc) ambiguous across $($candidates.Count) titles"
                }
            }
            else {
                $r.tagsMismatch = $true; $r.mismatchReason = "no tags chapter numbered $($r.cc) in any title"
            }
        }
        if ($join) {
            $r.tagsChapter = $join.chapter
            $r.titleFile = $join.titleFile
            $r.tagsRef = "$($join.titleFile) ch $($join.chapter.chapter)"
        }
    }

    # --- Pass 3: kind classification (tags kind primary, filename fallback) --
    foreach ($r in $records) {
        if ($r.kind -eq 'unclassified') { continue }
        if ($r.groupKey -and $ownerDeletedGroups.ContainsKey($folderName) -and $ownerDeletedGroups[$folderName] -contains $r.groupKey) {
            $r.kind = 'unclassified'
            $r.reason = 'deleted by owner ruling 2026-11-16 (Bizet Symphony No. 1, Cluytens) — source file should not exist; surface to owner'
            continue
        }
        $tk = $null
        if ($r.tagsChapter) { $tk = "$($r.tagsChapter.kind)".ToLowerInvariant() }
        if ($tk -in @('talk', 'interview')) { $r.kind = 'talk' }
        elseif ($tk -eq 'intro') { $r.kind = 'intro' }
        elseif ($tk -eq 'applause') { $r.kind = 'applause' }
        elseif ($tk -eq 'music' -or $null -eq $tk) {
            if ($r.nameExtraKind -and $r.nameExtraKind -ne 'talk' -and $r.nameExtraKind -ne 'interview') {
                $tagsWorkEmpty = (-not $r.tagsChapter) -or (-not "$($r.tagsChapter.work)".Trim())
                if ($tagsWorkEmpty -or $null -eq $tk) {
                    $r.kind = $r.nameExtraKind
                }
                else {
                    $r.kind = 'work'
                    $r.tagsMismatch = $true; $r.mismatchReason = "filename says extra ($($r.nameExtraKind)) but tags chapter names a work"
                }
            }
            else { $r.kind = 'work' }
        }
        else {
            # credits / trailer / unknown chapter joined by a named file
            if ($r.nameExtraKind) { $r.kind = $r.nameExtraKind } else { $r.kind = 'work' }
            $r.tagsMismatch = $true; $r.mismatchReason = "joined chapter kind '$tk' is not music"
        }

        # Work content validation: normalized work text + movement number must agree.
        if ($r.kind -eq 'work' -and $r.tagsChapter -and -not $r.tagsMismatch) {
            $tw = "$($r.tagsChapter.work)".Trim()
            if (-not $tw) {
                $r.tagsMismatch = $true; $r.mismatchReason = 'tags chapter has no work text'
            }
            elseif ((Get-NormalizedText $tw) -ne (Get-NormalizedText $r.work)) {
                $r.tagsMismatch = $true; $r.mismatchReason = "work differs: filename '$($r.work)' vs tags '$tw'"
            }
            else {
                $fnNum = $null
                if ($r.movement -match '^([0-9]+[a-z]?|[ivxlc]+)\.') { $fnNum = $Matches[1].ToLowerInvariant() }
                $tagNum = "$($r.tagsChapter.movement_number)".Trim().TrimEnd('.').ToLowerInvariant()
                if ($fnNum -and $tagNum -and $fnNum -ne $tagNum) {
                    $r.tagsMismatch = $true; $r.mismatchReason = "movement number differs: filename '$fnNum' vs tags '$tagNum'"
                }
            }
        }
    }

    # --- Pass 4: chapter names + effective confidence -------------------------
    foreach ($r in $records) {
        if ($r.kind -eq 'unclassified') { continue }
        $override = $null
        if ($null -ne $r.tt -and $researchOverrides.ContainsKey($folderName)) {
            $okey = "$($r.tt)|$($r.cc)"
            if ($researchOverrides[$folderName].ContainsKey($okey)) { $override = $researchOverrides[$folderName][$okey] }
        }
        if ($override) {
            $r.chapterName = $override.chapterName
            $r.movementMissing = $false
            $r.effectiveConfidence = $override.confidence
            $r.researchResolved = $true
            if ($override.chapterMergeInferred) { $r.chapterMergeInferred = $true }
            if ($override.mergedSections) { $r.researchMergedSections = $override.mergedSections }
            continue
        }
        if ($r.kind -eq 'work') {
            if ($r.tagsChapter -and -not $r.tagsMismatch) {
                $label = Get-ChapterLabel -MovementNumber $r.tagsChapter.movement_number -Movement $r.tagsChapter.movement
                if ($label) {
                    $r.chapterName = $label
                    $r.movementMissing = $false
                }
                else {
                    $fallbackWork = "$($r.tagsChapter.work)".Trim()
                    if (-not $fallbackWork) { $fallbackWork = $r.work }
                    $r.chapterName = '{0}. {1}' -f $r.cc, $fallbackWork
                    $r.movementMissing = $true
                }
                $r.effectiveConfidence = "$($r.tagsChapter.confidence)"
            }
            else {
                if ($r.movementMissing) { $r.chapterName = '{0}. {1}' -f $r.cc, $r.work }
                else { $r.chapterName = $r.movement }
            }
        }
        else {
            $r.chapterName = Get-ExtraChapterName -Pieces $r.pieces -Kind $r.kind
            $r.movementMissing = $false
            if ($r.tagsChapter) { $r.effectiveConfidence = "$($r.tagsChapter.confidence)" }
        }
    }

    # --- Work groups + extras folding -----------------------------------------
    $groups = [ordered]@{}
    foreach ($r in ($records | Where-Object { $_.kind -eq 'work' } | Sort-Object { $_.tt }, { $_.cc })) {
        if (-not $groups.Contains($r.groupKey)) { $groups[$r.groupKey] = @() }
        $groups[$r.groupKey] += $r
    }

    $standaloneExtras = @()
    foreach ($r in ($records | Where-Object { $_.kind -in @('applause', 'encore', 'intro', 'chapter') } | Sort-Object { $_.tt }, { $_.cc })) {
        $candidates = @($groups.Keys | ForEach-Object {
            $members = $groups[$_]
            $sameTitle = ($null -eq $r.tt) -or @($members | Where-Object { $_.tt -eq $r.tt }).Count -gt 0
            if ($sameTitle) {
                $ccs = @($members | ForEach-Object { $_.cc })
                [pscustomobject]@{ key = $_; min = ($ccs | Measure-Object -Minimum).Minimum; max = ($ccs | Measure-Object -Maximum).Maximum }
            }
        })
        $target = $null; $side = $null
        if ($r.kind -in @('applause', 'encore')) {
            $preceding = @($candidates | Where-Object { $_.max -lt $r.cc } | Sort-Object max -Descending)
            if ($preceding.Count -gt 0) { $target = $preceding[0].key; $side = 'trailing' }
        }
        else {
            $following = @($candidates | Where-Object { $_.min -gt $r.cc } | Sort-Object min)
            if ($following.Count -gt 0) { $target = $following[0].key; $side = 'leading' }
        }
        if ($target) {
            $r.foldedInto = $target
            $r.foldSide = $side
            $groups[$target] += $r
            Write-Host ("  fold {0} ({1}) -> {2} [{3}]" -f $r.file, $r.kind, $target, $side) -ForegroundColor DarkGray
        }
        else {
            $standaloneExtras += $r
            Write-Host ("  extra with no adjacent work, standalone: {0}" -f $r.file) -ForegroundColor Yellow
        }
    }

    # --- Build work outputs ----------------------------------------------------
    $folderFlags = @()
    if ($folderName -eq 'MARKEVITCH Classic Archive 10') { $folderFlags += 'orchestraVariesByWork' }
    if ($reconstructed) { $folderFlags += 'sourcesRemovedAfterVerifiedMerge' }
    $releaseId = $null
    if ($releaseIds.ContainsKey($folderName)) { $releaseId = $releaseIds[$folderName] }

    $outputs = @()
    $groupKeysOrdered = @($groups.Keys | Sort-Object {
        ($groups[$_] | Sort-Object { $_.tt }, { $_.cc } | Select-Object -First 1).tt
    }, {
        ($groups[$_] | Sort-Object { $_.tt }, { $_.cc } | Select-Object -First 1).cc
    })
    foreach ($key in $groupKeysOrdered) {
        $members = @($groups[$key])
        $workMembers = @($members | Where-Object { $_.kind -eq 'work' })
        $taggedWork = @($workMembers | Where-Object { $_.tagsChapter -and -not $_.tagsMismatch })
        $leading = @($members | Where-Object { $_.foldSide -eq 'leading' } | Sort-Object { $_.tt }, { $_.cc })
        $trailing = @($members | Where-Object { $_.foldSide -eq 'trailing' } | Sort-Object { $_.tt }, { $_.cc })
        $ordered = @($leading + ($workMembers | Sort-Object { $_.tt }, { $_.cc }) + $trailing)
        $outFlags = @()

        # Display composer/work: tags primary (must agree across the group).
        $displayComposer = $workMembers[0].composer
        $displayWork = $workMembers[0].work
        $dc = @($taggedWork | ForEach-Object { "$($_.tagsChapter.composer_display)".Trim() } | Where-Object { $_ } | Select-Object -Unique)
        $dw = @($taggedWork | ForEach-Object { "$($_.tagsChapter.work)".Trim() } | Where-Object { $_ } | Select-Object -Unique)
        if ($dc.Count -eq 1) { $displayComposer = $dc[0] }
        elseif ($dc.Count -gt 1) { $displayComposer = $dc[0]; $outFlags += 'inconsistentWorkTags' }
        if ($dw.Count -eq 1) { $displayWork = $dw[0] }
        elseif ($dw.Count -gt 1) { $displayWork = $dw[0]; $outFlags += 'inconsistentWorkTags' }

        # Performers from tags; curated table only as flagged fallback.
        $conds = @($taggedWork | ForEach-Object { "$($_.tagsChapter.conductor)".Trim() } | Where-Object { $_ } | Select-Object -Unique)
        $conductor = $null
        if ($conds.Count -ge 1) { $conductor = $conds[0] }
        if ($conds.Count -gt 1) { $outFlags += 'inconsistentPerformers' }
        if (-not $conductor) {
            $conductor = $spec.conductor
            if ($conductor) { $outFlags += 'performersFromCuratedTable' } else { $outFlags += 'unknownConductor' }
        }
        $soloists = @()
        foreach ($m in $taggedWork) {
            foreach ($s in @($m.tagsChapter.soloists)) {
                $sv = "$s".Trim()
                if ($ownerSoloistSpelling.ContainsKey($sv)) { $sv = $ownerSoloistSpelling[$sv] }
                if ($sv -and $soloists -notcontains $sv) { $soloists += $sv }
            }
        }
        if ($ownerSoloistOverrides.ContainsKey($folderName) -and $ownerSoloistOverrides[$folderName].ContainsKey($key)) {
            $soloists = @($ownerSoloistOverrides[$folderName][$key])
            $outFlags += 'ownerResearchCorrection'
        }
        $orchs = @($taggedWork | ForEach-Object { "$($_.tagsChapter.orchestra)".Trim() } | Where-Object { $_ } | Select-Object -Unique)
        # Curated soloist fallback only when tags carry NO performer data for the work;
        # empty soloists alongside conductor/orchestra is a complete orchestral credit.
        if ($soloists.Count -eq 0 -and $spec.soloist -and $conds.Count -eq 0 -and $orchs.Count -eq 0) {
            $soloists = @($spec.soloist)
            $outFlags += 'performersFromCuratedTable'
        }
        $orchestra = $null
        if ($orchs.Count -ge 1) { $orchestra = $orchs[0] }
        if ($orchs.Count -gt 1) { $outFlags += 'inconsistentPerformers' }
        if (-not $orchestra) {
            $fnOrchs = @($workMembers | Where-Object { $_.orchestra } | ForEach-Object { $_.orchestra } | Select-Object -Unique)
            if ($fnOrchs.Count -ge 1) {
                $byLen = @($fnOrchs | Sort-Object Length -Descending)
                $orchestra = $byLen[0]
                $outFlags += 'orchestraFromFilename'
                if (@($byLen | Where-Object { $byLen[0].StartsWith($_) }).Count -ne $byLen.Count) { $outFlags += 'inconsistentOrchestraOrYear' }
            }
        }
        $choirs = @($taggedWork | ForEach-Object { "$($_.tagsChapter.choir)".Trim() } | Where-Object { $_ } | Select-Object -Unique)
        $choir = ($choirs -join '; ')
        $years = @($taggedWork | ForEach-Object { "$($_.tagsChapter.performance_year)".Trim() } | Where-Object { $_ } | Select-Object -Unique)
        $year = $null
        if ($years.Count -eq 1) { $year = $years[0] }
        elseif ($years.Count -gt 1) { $year = $years[0]; $outFlags += 'inconsistentOrchestraOrYear' }
        else {
            $fnYears = @($workMembers | Where-Object { $_.year } | ForEach-Object { $_.year } | Select-Object -Unique)
            if ($fnYears.Count -ge 1) { $year = $fnYears[0]; $outFlags += 'yearFromFilename' }
            if ($fnYears.Count -gt 1) { $outFlags += 'inconsistentOrchestraOrYear' }
            if (-not $year) { $outFlags += 'missingYear' }
        }
        $venues = @($taggedWork | ForEach-Object { "$($_.tagsChapter.venue)".Trim() } | Where-Object { $_ } | Select-Object -Unique)
        $venue = ($venues -join '; ')
        if ($artworkVenue.ContainsKey($folderName)) { $venue = $artworkVenue[$folderName] }
        $dates = @($taggedWork | ForEach-Object { "$($_.tagsChapter.performance_date)".Trim() } | Where-Object { $_ } | Select-Object -Unique)
        $performanceDate = ($dates -join '; ')
        if ($ownerYearDateOverrides.ContainsKey($folderName) -and $ownerYearDateOverrides[$folderName].ContainsKey($key)) {
            $ov = $ownerYearDateOverrides[$folderName][$key]
            if ($ov.year) { $year = $ov.year }
            if ($ov.date) { $performanceDate = $ov.date }
            $outFlags += 'ownerResearchCorrection'
        }

        # Filename truncation artifacts (tags usually repair the content).
        if (@($workMembers | Where-Object { $_.sourceFlags -contains 'orchestraTruncated' -or $_.sourceFlags -contains 'trailingDashArtifact' -or $_.sourceFlags -contains 'movementTruncated' }).Count -gt 0) {
            $outFlags += 'truncatedSourceName'
        }
        if (@($ordered | Where-Object { $_.tagsMismatch }).Count -gt 0) { $outFlags += 'tagsMismatch' }
        if (@($ordered | Where-Object { $_.effectiveConfidence -eq 'low' }).Count -gt 0) { $outFlags += 'lowConfidence' }
        if (@($ordered | Where-Object { $_.chapterMergeInferred }).Count -gt 0) { $outFlags += 'chapterMergeInferred' }

        # Incompleteness: all work chapters numbered, but the set is not 1..N.
        $incomplete = $false
        $nums = @()
        $allNumbered = $workMembers.Count -gt 0
        foreach ($m in $workMembers) {
            $mn = $null
            if ($m.tagsChapter -and -not $m.tagsMismatch -and "$($m.tagsChapter.movement_number)".Trim() -match '^\d+$') {
                $mn = [int]"$($m.tagsChapter.movement_number)".Trim()
            }
            elseif ($m.movement -match '^(\d+)\.') { $mn = [int]$Matches[1] }
            if ($null -ne $mn) { $nums += $mn } else { $allNumbered = $false }
        }
        if ($allNumbered -and $nums.Count -gt 0) {
            $expected = @(1..$workMembers.Count)
            $actual = @($nums | Sort-Object -Unique)
            if (($actual -join ',') -ne ($expected -join ',')) { $incomplete = $true }
        }
        if ($incomplete) { $outFlags += 'incomplete' }
        $incompleteNote = $null

        # Folder-specific flags. Mahler venueAmbiguous RESOLVED by deep-research reconciliation 2026-11-17 (Philharmonie, Berlin).
        if ($folderName -eq 'Mozart - Concertos 2&3 Pianos' -and $displayWork -like '*K. 242*') { $outFlags += 'thirdPianistInferred' }

        $standalone = ($ordered.Count -eq 1 -and $ordered[0].movementMissing -and -not $ordered[0].foldedInto)
        if ($ownerStandaloneGroups.ContainsKey($folderName) -and $ownerStandaloneGroups[$folderName] -contains $key) {
            $standalone = $true
            $outFlags += 'standaloneByOwnerRuling'
        }

        # tagsConfidence: lowest among the output's chapters.
        $ranks = @($ordered | ForEach-Object { Get-ConfidenceRank $_.effectiveConfidence } | Where-Object { $_ -gt 0 })
        $tagsConfidence = $null
        if ($ranks.Count -gt 0) {
            $minRank = ($ranks | Measure-Object -Minimum).Minimum
            $tagsConfidence = switch ($minRank) { 3 { 'high' } 2 { 'medium' } 1 { 'low' } }
        }
        $titleSource = Format-TitleSource -Refs @($ordered | ForEach-Object { @{ titleFile = $_.titleFile; chapter = $(if ($_.tagsChapter) { $_.tagsChapter.chapter } else { $null }) } })

        # missingChapters (owner ruling 2026-11-17): complete movement set from tags.json
        # (all music/intro chapters of this work on its title, ripped or not) minus covered chapters.
        # Non-work bumper/credits/title-card chapters (empty work text) are NOT movements: excluded.
        $missingChapters = @()
        $coveredNums = @($ordered | Where-Object { $_.tagsChapter } | ForEach-Object { [int]$_.tagsChapter.chapter })
        $workNorm = Get-NormalizedText $workMembers[0].work
        $titleFiles = @($workMembers | Where-Object { $_.titleFile } | ForEach-Object { $_.titleFile } | Select-Object -Unique)
        foreach ($tf in $titleFiles) {
            $te = $titleEntries | Where-Object { $_.titleFile -ceq $tf } | Select-Object -First 1
            if ($null -eq $te) { continue }
            foreach ($c in $te.chapters) {
                $ck = "$($c.kind)".ToLowerInvariant()
                if ($ck -notin @('music', 'intro')) { continue }
                if ((Get-NormalizedText "$($c.work)") -ne $workNorm) { continue }
                if ($coveredNums -contains [int]$c.chapter) { continue }
                $mn = "$($c.movement_number)".Trim()
                $reason = $(if ($mn) { 'never ripped' } else { 'intro/title card' })
                $secs = $(if ($null -ne $c.PSObject.Properties['duration_seconds']) { $c.duration_seconds } else { $c.seconds })
                $missingChapters += [ordered]@{ number = $mn; name = "$($c.movement)".Trim(); seconds = $secs; reason = $reason }
            }
        }
        foreach ($m in $ordered) {
            if ($m.researchMergedSections) {
                foreach ($ms in $m.researchMergedSections) {
                    $missingChapters += [ordered]@{ number = $ms.number; name = $ms.name; seconds = $null; reason = 'merged into adjacent chapter' }
                }
            }
        }

        $sources = @()
        foreach ($m in $ordered) {
            $sources += [ordered]@{
                file = $m.file
                chapterName = $m.chapterName
                sort = @($m.tt, $m.cc)
                foldedExtra = ($m.kind -ne 'work')
                movementMissing = [bool]$m.movementMissing
                foldedInto = $(if ($m.foldedInto) { $m.foldedInto } else { $null })
                tagsConfidence = $(if ($m.effectiveConfidence) { $m.effectiveConfidence } else { $null })
                tagsRef = $m.tagsRef
                tagsMismatch = [bool]$m.tagsMismatch
                researchResolved = [bool]$m.researchResolved
                chapterMergeInferred = [bool]$m.chapterMergeInferred
                flags = @($m.sourceFlags)
            }
        }

        $perf = @($soloists + @($conductor) + @($orchestra)) | Where-Object { $_ } | Select-Object -Unique
        $outputName = Format-OutputName -Composer $displayComposer -Work $displayWork -Performers $perf -Year $year
        $outputName = Format-SanitizedName -Name $outputName
        $fit = Get-FittedOutputName -Name $outputName -Directory $dir -Orchestra "$orchestra" -MaxPathLength 240
        $outputName = $fit.name
        $nameShorteningSteps = @($fit.steps)
        if ($nameShorteningSteps.Count -gt 0) { $outFlags += 'nameShortened' }
        $out = [ordered]@{
            outputName = $outputName
            mkvTitle = [System.IO.Path]::GetFileNameWithoutExtension($outputName)
            standalone = [bool]$standalone
            incomplete = [bool]$incomplete
            composer = $displayComposer
            work = $displayWork
            conductor = $conductor
            soloists = @($soloists)
            orchestra = $orchestra
            choir = $(if ($choir) { $choir } else { $null })
            year = $year
            venue = $(if ($venue) { $venue } else { $null })
            performanceDate = $(if ($performanceDate) { $performanceDate } else { $null })
            tagsConfidence = $tagsConfidence
            titleSource = $(if ($titleSource) { $titleSource } else { $null })
            flags = @($outFlags | Select-Object -Unique)
            missingChapters = $missingChapters
            missingChaptersCount = $missingChapters.Count
            sources = $sources
        }
        if ($incompleteNote) { $out.incompleteNote = $incompleteNote }
        if ($nameShorteningSteps.Count -gt 0) { $out.nameShorteningSteps = $nameShorteningSteps }
        $outputs += $out
        $tag = if ($standalone) { 'standalone' } elseif ($incomplete) { 'INCOMPLETE' } else { 'merge' }
        Write-Host ("  [{0}] {1}  ({2} chapters)" -f $tag, $outputName, $sources.Count) -ForegroundColor Green
    }

    # --- Standalone extras (Talk/Interview, or unfoldered orphans) -------------
    $standalones = @()
    $talkRecords = @($records | Where-Object { $_.kind -in @('talk', 'interview') }) + $standaloneExtras
    foreach ($r in ($talkRecords | Sort-Object { $_.tt }, { $_.cc })) {
        $p = $r.pieces; $n = $p.Count
        $composer = $p[1]
        $work = $(if ($n -ge 3) { $p[2] } else { $p[1] })
        $sFlags = @('standaloneExtra')
        $soloists = @(); $conductor = $null; $orchestra = $null; $year = $null; $venue = $null
        $tc = $r.tagsChapter
        if ($tc -and -not $r.tagsMismatch) {
            foreach ($s in @($tc.soloists)) { $sv = "$s".Trim(); if ($ownerSoloistSpelling.ContainsKey($sv)) { $sv = $ownerSoloistSpelling[$sv] }; if ($sv -and $soloists -notcontains $sv) { $soloists += $sv } }
            $conductor = "$($tc.conductor)".Trim()
            $orchestra = "$($tc.orchestra)".Trim()
            $year = "$($tc.performance_year)".Trim()
            $venue = "$($tc.venue)".Trim()
        }
        if ($soloists.Count -eq 0 -and -not $conductor -and -not $orchestra) {
            if ($spec.soloist) { $soloists = @($spec.soloist) }
            if ($spec.conductor) { $conductor = $spec.conductor }
            if ($spec.soloist -or $spec.conductor) { $sFlags += 'performersFromCuratedTable' }
        }
        if (-not $year -and $p[$n - 1] -match '^\d{4}$') { $year = $p[$n - 1] }
        if (-not $year) { $sFlags += 'missingYear' }
        if ($r.tagsMismatch) { $sFlags += 'tagsMismatch' }
        if ($null -eq $r.foldedInto -and $r.kind -in @('applause', 'encore', 'intro', 'chapter')) { $sFlags += 'orphanNoAdjacentWork' }
        $perf = @($soloists + @($conductor) + @($orchestra)) | Where-Object { $_ } | Select-Object -Unique
        $outputName = Format-OutputName -Composer $composer -Work $work -Performers $perf -Year $year -Standalone
        $outputName = Format-SanitizedName -Name $outputName
        $fit = Get-FittedOutputName -Name $outputName -Directory $dir -Orchestra "$orchestra" -MaxPathLength 240
        $outputName = $fit.name
        $tagsConfidence = $(if ($r.effectiveConfidence) { $r.effectiveConfidence } else { $null })
        $titleSource = Format-TitleSource -Refs @(@{ titleFile = $r.titleFile; chapter = $(if ($tc) { $tc.chapter } else { $null }) })
        $standalones += [ordered]@{
            outputName = $outputName
            mkvTitle = [System.IO.Path]::GetFileNameWithoutExtension($outputName)
            standalone = $true
            incomplete = $false
            composer = $composer
            work = $work
            conductor = $(if ($conductor) { $conductor } else { $null })
            soloists = @($soloists)
            orchestra = $(if ($orchestra) { $orchestra } else { $null })
            choir = $null
            year = $(if ($year) { $year } else { $null })
            venue = $(if ($venue) { $venue } else { $null })
            performanceDate = $null
            tagsConfidence = $tagsConfidence
            titleSource = $(if ($titleSource) { $titleSource } else { $null })
            flags = @($sFlags)
            missingChapters = @()
            missingChaptersCount = 0
            sources = @([ordered]@{
                file = $r.file
                chapterName = $r.chapterName
                sort = @($r.tt, $r.cc)
                foldedExtra = $false
                movementMissing = $false
                foldedInto = $null
                tagsConfidence = $tagsConfidence
                tagsRef = $r.tagsRef
                tagsMismatch = [bool]$r.tagsMismatch
                researchResolved = [bool]$r.researchResolved
                chapterMergeInferred = $false
                flags = @($r.sourceFlags)
            })
        }
        Write-Host ("  [extra] {0}" -f $outputName) -ForegroundColor Yellow
    }

    # --- Unclassified -----------------------------------------------------------
    $unclassified = @()
    foreach ($r in ($records | Where-Object { $_.kind -eq 'unclassified' })) {
        $unclassified += [ordered]@{ file = $r.file; reason = $r.reason }
        Write-Host ("  UNCLASSIFIED: {0} — {1}" -f $r.file, $r.reason) -ForegroundColor Red
    }

    if (@($outputs | Where-Object { $_.flags -contains 'unknownConductor' -and $_.soloists.Count -eq 0 }).Count -gt 0) {
        $folderFlags += 'unknownPerformers'
    }

    # --- Census: every matched file exactly once --------------------------------
    $assigned = @()
    foreach ($o in $outputs) { foreach ($s in $o.sources) { $assigned += $s.file } }
    foreach ($o in $standalones) { foreach ($s in $o.sources) { $assigned += $s.file } }
    foreach ($u in $unclassified) { $assigned += $u.file }
    $dupes = @($assigned | Group-Object | Where-Object { $_.Count -gt 1 })
    $missingFiles = @($matched | Where-Object { $assigned -notcontains $_.Name })
    $extraFiles = @($assigned | Where-Object { $matched.Name -notcontains $_ })
    $ok = ($dupes.Count -eq 0 -and $missingFiles.Count -eq 0 -and $extraFiles.Count -eq 0)
    if (-not $ok) {
        $censusErrors += "Census mismatch in ${folderName}: dupes=$($dupes.Name -join ';') missing=$($missingFiles.Name -join ';') extra=$($extraFiles -join ';')"
        Write-Host '  CENSUS MISMATCH' -ForegroundColor Red
    }
    $censusRows += [pscustomobject]@{
        Folder = $folderName; Matched = $matched.Count; Assigned = $assigned.Count
        Outputs = $outputs.Count; Standalones = $standalones.Count; Unclassified = $unclassified.Count
        CensusOk = $ok
    }
    $grandMatched += $matched.Count; $grandAssigned += $assigned.Count
    $grandOutputs += $outputs.Count; $grandStandalones += $standalones.Count; $grandUnclassified += $unclassified.Count
    Write-Host ("  census: {0} matched = {1} assigned ({2} outputs, {3} standalones, {4} unclassified) OK={5}" -f $matched.Count, $assigned.Count, $outputs.Count, $standalones.Count, $unclassified.Count, $ok) -ForegroundColor $(if ($ok) { 'Green' } else { 'Red' })

    $manifestFolders += [ordered]@{
        folder = $folderName
        releaseId = $releaseId
        performers = [ordered]@{ soloist = $spec.soloist; conductor = $spec.conductor }
        flags = @($folderFlags)
        outputs = $outputs
        standalones = $standalones
        unclassified = $unclassified
    }
}

# --- Systematic filename + metadata assertions (owner ruling 2026-11-17): hard fail on any hit.
$reservedNames = @('CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9')
$violations = @()
foreach ($mf in $manifestFolders) {
    foreach ($o in ($mf.outputs + $mf.standalones)) {
        $name = $o.outputName
        $stem = [System.IO.Path]::GetFileNameWithoutExtension($name)
        $full = Join-Path (Join-Path $DvdsRoot $mf.folder) $name
        if ($name -match '[<>:"/\\|?*\x00-\x1F]') { $violations += "illegal char in outputName: $name" }
        if ($o.mkvTitle -match '[<>:"/\\|?*\x00-\x1F]') { $violations += "illegal char in mkvTitle: $($o.mkvTitle)" }
        if ($stem.EndsWith('.') -or $stem.EndsWith(' ')) { $violations += "trailing dot/space in stem: $name" }
        if ($name.EndsWith('.') -or $name.EndsWith(' ')) { $violations += "trailing dot/space in name: $name" }
        $firstDot = $stem.Split('.')[0].ToUpperInvariant()
        if ($reservedNames -contains $stem.ToUpperInvariant() -or $reservedNames -contains $firstDot) { $violations += "reserved device name: $name" }
        if ($name -cne ($o.mkvTitle + '.mkv')) { $violations += "name != mkvTitle + .mkv: $name" }
        if ($full.Length -gt 240) { $violations += "full path > 240 ($($full.Length)): $full" }
        foreach ($s in $o.sources) {
            if ("$($s.chapterName)" -match '[\x00-\x1F]') { $violations += "control char in chapterName of $($s.file)" }
        }
    }
}
if ($violations.Count -gt 0) {
    foreach ($v in $violations) { Write-Host "MANIFEST ASSERTION FAILED: $v" -ForegroundColor Red }
    throw "Manifest filename/metadata assertions failed: $($violations.Count) violation(s)"
}
Write-Host 'Manifest assertions passed: illegal chars / control chars / trailing dot-space / reserved names / name==title / path<=240 / chapter metadata.' -ForegroundColor Green

$manifest = [ordered]@{ folders = $manifestFolders }
$json = $manifest | ConvertTo-Json -Depth 12
$manifestPath = Join-Path $OutDir 'manifest.json'
[System.IO.File]::WriteAllText($manifestPath, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "Manifest written: $manifestPath" -ForegroundColor Cyan

# --- Human-readable review -----------------------------------------------------
$lines = @()
$lines += '# DVD merge manifest — owner review gate'
$lines += ''
$lines += ("Generated {0} by Get-MergeManifest.ps1 from ``{1}`` (read-only; filenames + tags.json only, no media probing)." -f (Get-Date -Format 'yyyy-MM-dd HH:mm'), $DvdsRoot)
$lines += ''
$lines += ("Totals: {0} named files matched, {1} assigned; {2} work outputs, {3} standalone extras, {4} unclassified." -f $grandMatched, $grandAssigned, $grandOutputs, $grandStandalones, $grandUnclassified)
$lines += ''
$lines += '## Conventions'
$lines += '- Metadata precedence: owner research overrides (Firebird, follow-up #2) > tags.json > filename parse > curated folder table (fallback only, flagged).'
$lines += '- Output naming: `Composer - Work - Soloists, Conductor, Orchestra (Year).mkv`, no track numbering. Composer/Work use tags.json display forms (full names, accented titles). MKV Title = filename minus extension.'
$lines += '- Filename sanitization (owner ruling 2026-11-17, Option A): in outputName AND mkvTitle only, ASCII double quotes become paired curly quotes (U+201C/U+201D) and ASCII colon becomes U+A789 modifier-letter colon. Chapter names and metadata fields keep tags forms. The name == mkvTitle + .mkv invariant holds on sanitized values.'
$lines += '- Systematic filename assertion (owner ruling 2026-11-17): every outputName/standalone name/mkvTitle is scanned for NTFS-illegal chars (<>:"/\|?*), control chars, trailing dots/spaces, and reserved device names (CON/PRN/AUX/NUL/COM1-9/LPT1-9); any hit fails the manifest build. Full paths must be <= 240 chars: overlong names are deterministically shortened (D3: drop opus/catalogue, then orchestra, then truncate work; year tail untouched) and flagged nameShortened with steps recorded. Chapter names are metadata: asserted control-char-free, never sanitized.'
$lines += '- missingChapters (owner ruling 2026-11-17): per output, the work''s complete movement set from tags.json (all music/intro chapters of that work on its title, ripped or not) minus the chapters present in the merged file. Reasons: never ripped / intro/title card / not on film / merged into adjacent chapter. Bumper/credits/title-card chapters with no work text are not movements and are never listed. Tags movement_number is kept verbatim so numbering gaps remain visible. Firebird: ch 2 (1a. Introduction, 17 s) never ripped; section 10 Final Hymn merged into the final chapter (chapterMergeInferred).'
$lines += '- Completed folders: where a prior verified run already removed the movement sources (Gate-2 delete-after-verify), the manifest reconstructs the folder from the runlog deletion record (flag sourcesRemovedAfterVerifiedMerge) so the plan of record and census stay complete. tags.json schema note: chapter durations are read from seconds (legacy duration_seconds also supported).'
$lines += '- Soloists joined with ", "; a conductor who is also a soloist (Mozart K.242, Solti at the third piano) is listed once. Choir is metadata-only (not in the filename, per the unchanged naming format).'
$lines += '- Curated soloist fallback applies only when tags.json has no performers at all for a work; empty soloists with conductor/orchestra present = orchestral work, no soloist added (e.g. Coriolan, Beethoven 7).'
$lines += '- `outputs` = work groups (merges, plus single-file groups needing chapter naming). `standalone: true` = rename-only single-movement work. `standalones` = Talk/Interview extras (never merged).'
$lines += '- Chapter names: tags movement_number + movement ("1. Allegro", "I. Allegro", "1b. Prelude..."); movement only as-is; neither → fallback "<cc>. <work>" with movementMissing.'
$lines += '- Join: T<tt>-<cc> → title <tt>.mkv chapter <cc>; bare NN → the titles[] entry containing chapter NN (verified by chapter number, not position). Mismatches keep filename rules and flag tagsMismatch.'
$lines += '- Extras fold by tags kind: Applause/Encore → trailing chapters of preceding work; Intro/Chapter-NN orphan → leading chapter of following work; Talk/Interview standalone.'
$lines += '- MARKEVITCH title 04: chapter 2 (17 s Introduction) was never ripped — expected, not flagged. Chapters 1, 3-12 carry the research-resolved names (medici.tv programme + duration matching + NRC/Southbank reviews), confidence medium. Chapter 12 combines Lullaby + Final Hymn (chapterMergeInferred).'
$lines += '- Artwork lane (follow-up #3) corroborated all performers; venue refinements applied. Mahler venue ambiguity RESOLVED 2026-11-17: Philharmonie, Berlin (flag dropped).'
$lines += '- Deep-research reconciliation (Firecrawl sweep 2026-11-17, owner-adjudicated against tags.json + artwork): performers/venues independently verified across all 17 folders; corrections applied = Rossini Scottish/Violin Concerto years 1980->1979 (1979-10-24, Decca 074 3203 booklet track-level) and Svetlanov Song of the Forests vocal soloists (Maslennikov/Vedernikov, NHK catalogue). See reconciliation section below.'
$lines += '- Owner rulings 2026-11-16 (follow-ups #4/#5): Cluytens Bizet Symphony No. 1 deleted from the project (sources already removed; content preserved in title 00.mkv); Cluytens 1959 well-sourced (yearLowConfidence dropped); Roussel Suite No. 2 = standalone rename.'
$lines += ''
$idx = 0
foreach ($mf in $manifestFolders) {
    $idx++
    $lines += "## $idx. $($mf.folder)"
    $lines += ''
    $rid = $(if ($mf.releaseId) { $mf.releaseId } else { 'no catalogue number found (artwork lane)' })
    $lines += "Release ID: $rid"
    if ($mf.flags.Count -gt 0) { $lines += "Folder flags: $($mf.flags -join ', ')" }
    if ($ownerRulingNotes.ContainsKey($mf.folder)) {
        foreach ($note in $ownerRulingNotes[$mf.folder]) { $lines += "Owner ruling / note: $note" }
    }
    $lines += ''
    foreach ($o in $mf.outputs) {
        $kind = $(if ($o.standalone) { 'RENAME ONLY (single movement)' } else { 'MERGE' })
        $lines += "### $kind — $($o.outputName)"
        $meta = @()
        if ($o.incomplete) {
            $note = $(if ($o.PSObject.Properties['incompleteNote'] -and $o.incompleteNote) { $o.incompleteNote } else { 'movement set incomplete' })
            $meta += "INCOMPLETE: $note"
        }
        if ($o.flags.Count -gt 0) { $meta += "flags: $($o.flags -join ', ')" }
        if ($meta.Count -gt 0) { $lines += ($meta -join ' | ') }
        $detail = @()
        if ($o.venue) { $detail += "venue: $($o.venue)" }
        if ($o.performanceDate) { $detail += "date: $($o.performanceDate)" }
        if ($o.choir) { $detail += "choir: $($o.choir)" }
        if ($o.tagsConfidence) { $detail += "tagsConfidence: $($o.tagsConfidence)" }
        if ($o.titleSource) { $detail += "titleSource: $($o.titleSource)" }
        if ($detail.Count -gt 0) { $lines += ($detail -join ' | ') }
        $n = 0
        foreach ($s in $o.sources) {
            $n++
            $note = @()
            if ($s.foldedExtra) { $note += "folded extra -> $($s.foldedInto)" }
            if ($s.movementMissing) { $note += 'fallback chapter name' }
            if ($s.researchResolved) { $note += 'research-resolved' }
            if ($s.chapterMergeInferred) { $note += 'CHAPTER MERGE INFERRED (Lullaby flows into Final Hymn; no separate disc chapter)' }
            if ($s.tagsMismatch) { $note += 'TAGS MISMATCH' }
            if ($s.tagsConfidence -eq 'low') { $note += 'low confidence' }
            if ($s.flags.Count -gt 0) { $note += ($s.flags -join ', ') }
            $suffix = $(if ($note.Count -gt 0) { '  [' + ($note -join '; ') + ']' } else { '' })
            $ref = $(if ($s.tagsRef) { " ($($s.tagsRef))" } else { '' })
            $lines += ("  {0}. {1}  <-  {2}{3}{4}" -f $n, $s.chapterName, $s.file, $ref, $suffix)
        }
        if ($o.missingChapters.Count -gt 0) {
            $lines += '  Absent from merged file (complete movement set per tags.json):'
            foreach ($mc in $o.missingChapters) {
                $num = $(if ($mc.number) { "$($mc.number). " } else { '' })
                $sec = $(if ($null -ne $mc.seconds) { "$($mc.seconds)s" } else { 'duration n/a' })
                $lines += ("    - {0}{1} ({2}) — {3}" -f $num, $mc.name, $sec, $mc.reason)
            }
        }
        $lines += ''
    }
    if ($mf.standalones.Count -gt 0) {
        $lines += '### Standalone extras (rename only, no merge)'
        foreach ($o in $mf.standalones) {
            $lines += "- $($o.outputName)  <-  $($o.sources[0].file)   [flags: $($o.flags -join ', ')]"
        }
        $lines += ''
    }
    if ($mf.unclassified.Count -gt 0) {
        $lines += '### UNCLASSIFIED (needs owner decision)'
        foreach ($u in $mf.unclassified) { $lines += "- $($u.file) — $($u.reason)" }
        $lines += ''
    }
    else {
        $lines += 'Unclassified: none.'
        $lines += ''
    }
}
$lines += '## Deep-research reconciliation (Firecrawl sweep 2026-11-17, owner-adjudicated)'
$lines += ''
$lines += 'CONFIRMED, no change: Solti-Perahia (Arthaus 100 148, Barbican 1987); Mahler 9 performers (Barenboim / Staatskapelle Berlin); Mozart performers — K.365 = Barenboim + Schiff, K.242 = + Solti at the third piano (the research agent''s contrary K.365 claim came from a different Barenboim CD release — REJECTED; tags.json back-cover evidence stands); Solti in Concert (programme + BRSO 1990); Bernstein (Rite / Sibelius, LSO 1966); Tchaikovsky Festival (Fedoseyev / Tretyakov / Moscow Radio SO, 1991, Alte Oper Frankfurt — release "The Tchaikovsky Cycle", Arthaus 109318); Gergiev (Salle Pleyel, Jan 2010); Wagner Strauss (Lucia Popp, Oct 1977); Temirkanov (pianist Denis Matsuev); Firebird section list independently re-confirmed — caveat: the physical booklet''s exact 12-chapter labels were never transcribed publicly, so chapterMergeInferred is KEPT on the final chapter.'
$lines += ''
$lines += 'CORRECTIONS APPLIED:'
$lines += '- Rossini Mendelssohn: Symphony No. 3 "Scottish" and Violin Concerto years 1980 -> 1979, performanceDate 1979-10-24 (Decca 074 3203 booklet track-level transcription; tags.json CiNii-based 1980 was less specific). Rossini overtures confirmed 1978-12-06; Italian confirmed 1976-06-02 (dates added). Release ID: Sir Georg Solti: The Maestro, Decca 474 3203 / 074 3203 (4 DVDs, 2007).'
$lines += '- Svetlanov in Japan: Song of the Forests vocal soloists added — Alexei Maslennikov (tenor), Alexander Vedernikov (bass) — per NHK catalogue (nhk-ep.com h09489AA). Venue NHK Hall, Tokyo and date 1978-10-21 confirmed. Release ID: NHK Classical 09489AA.'
$lines += '- Mahler 9: venueAmbiguous RESOLVED — Philharmonie, Berlin (Naxos/EuroArts/MusicWeb catalogue + review), 2009-04-05; flag dropped, year 2009 unchanged.'
$lines += '- Bernstein: venue Fairfield Halls, Croydon and date 1966-11-27 confirmed; release ID ICA Classics ICAD5082 added.'
$lines += ''
$lines += '## Performer gaps and inferences (owner attention)'
$lines += ''
$gapFound = $false
foreach ($mf in $manifestFolders) {
    foreach ($o in ($mf.outputs + $mf.standalones)) {
        if ($o.flags -contains 'unknownConductor') { $lines += "- UNKNOWN CONDUCTOR: $($o.outputName)"; $gapFound = $true }
        if ($o.flags -contains 'performersFromCuratedTable') { $lines += "- Curated-table fallback used (tags empty): $($o.outputName)"; $gapFound = $true }
        if ($o.flags -contains 'thirdPianistInferred') { $lines += "- INFERENCE: $($o.outputName) — Solti as third pianist is not printed on the artwork; kept from tags.json as a flagged inference."; $gapFound = $true }
        if ($o.flags -contains 'inconsistentPerformers') { $lines += "- PERFORMER CONFLICT across chapters: $($o.outputName)"; $gapFound = $true }
    }
}
if (-not $gapFound) { $lines += 'None.' }
$lines += ''
$lines += 'Spelling: GATE 1 owner ruling applied — "András Schiff" (accented) in both Mozart outputs; tags.json source value was ASCII "Andras Schiff".'
$lines += ''
$lines += 'Talk extras: Biret interview carries tags soloist Idil Biret only (no conductor). Mahler/Gergiev/Bernstein talk items have empty tags performers, so the curated folder conductor was applied as a flagged fallback — confirm or drop at the gate.'
$lines += ''
$reviewPath = Join-Path $OutDir 'manifest-review.md'
[System.IO.File]::WriteAllText($reviewPath, ($lines -join "`n"), [System.Text.UTF8Encoding]::new($false))
Write-Host "Review written: $reviewPath" -ForegroundColor Cyan

# --- Exit summary -----------------------------------------------------------------
Write-Host ''
Write-Host '=== CENSUS ===' -ForegroundColor Cyan
$censusRows | Format-Table -AutoSize | Out-String | Write-Host
Write-Host ("TOTAL matched={0} assigned={1} outputs={2} standalones={3} unclassified={4}" -f $grandMatched, $grandAssigned, $grandOutputs, $grandStandalones, $grandUnclassified) -ForegroundColor Cyan
if ($censusErrors.Count -gt 0) {
    foreach ($e in $censusErrors) { Write-Host "ERROR: $e" -ForegroundColor Red }
    exit 1
}
if ($grandUnclassified -gt 0) {
    Write-Host 'WARNING: unclassified entries present — see manifest and review.' -ForegroundColor Yellow
}
Write-Host 'Census passed: every matched file assigned exactly once.' -ForegroundColor Green
exit 0
