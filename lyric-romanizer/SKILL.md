---
name: lyric-romanizer
description: "Use when the user pastes non-English song lyrics (Urdu, Hindi, Punjabi, Persian, Arabic, Korean, Japanese, Chinese, Russian) or a ghazal, qawwali or film song, or asks to romanize, transliterate, translate or dedupe a song. Outputs a deduplicated study sheet."
---

# Lyric Romanizer

For each unique line: the Romanized original, the native-script line (colored), an English translation, and for Hindustani lyrics, glosses of uncommon words. Repeats are dropped; each line appears once.

## Workflow

1. **Dedupe the original script.** Write the pasted lyrics to a file in the approved temp directory, then run `uv run scripts/dedupe_lyrics.py <absolute-path-to-song.txt>` from the skill dir. Use an absolute path; a relative one resolves against the working directory and usually misfires. Stdin is the fallback. The script keeps the first occurrence of each line, matching through punctuation, case, Urdu vowel marks, Devanagari nukta, Latin accents and a trailing "(x2)", and removes section labels like `[Chorus]`. Dedupe before romanizing, so spelling variants collapse while the text is in one script. Dedupe within one song only: a line shared by two songs belongs in both. Drop credits and metadata (writer, singer, album).
2. **Romanize** each line not already in Latin script, reading only that language's section of `references/romanization.md`. Pronunciation leads: write what is sung, using doubled vowels, digraphs and the Hindustani capital-letter convention, not accents. Latin input stays as written, except scholarly diacritics, which convert to this scheme.
3. **Second dedupe pass.** Drop the later of any Romanized lines that now match. This is judgment, not another script run.
4. **Translate** each line into natural English faithful to meaning and register: idioms by sense, poetic imagery kept, one English line per lyric line. English words inside the lyric stay as they are.
5. **Gloss** uncommon Hindustani words (below).
6. **Emit** in order of first appearance, in the format below, then delete the temp file.

## Output format

Each unique line is one block: the Romanized line in Markdown italics (`*...*`), sentence case (capitalize the first letter of each line), ending `<br>`; the native-script line in a colored `<span>` (`style="color:#b45309"`), ending `<br>`; the translation; any gloss lines; a blank line before the next block.

```
*Romanized original line*<br>
<span style="color:#b45309">मूल लिपि पंक्ति</span><br>
English translation
**word** - definition
Etym: one-line etymology.

*Next romanized line*<br>
<span style="color:#b45309">...</span><br>
English translation
```

The native-script line uses the song's writing system: Devanagari for Hindi, Urdu script for Urdu. Latin-script Hindustani is still Hindi, so it gets a Devanagari line. Another Latin-script language gets a native line only when its script is known, and none otherwise. Use the exact color `#b45309`. Apart from that span, the sheet is plain Markdown: no code fence, title, headings, commentary or recap.

## Glossing uncommon Hindustani words

Gloss a word an ordinary Hindi-Urdu speaker would not use in daily talk: literary, poetic or Persian/Arabic-heavy vocabulary (firaaq, wasl, hijr, saaqi, dasht, sabaa). Everyday words stay unglossed even when Perso-Arabic (dil, pyaar, ishq, zindagi, khwaab, yaad, raat, waqt, intezaar, mohabbat, jaan, aankh, dost, duniya). Test: would a casual speaker use it over chai? If yes, skip it.

- Hindustani only (Urdu, Hindi, Braj/Bhojpuri registers); skip other languages unless asked.
- One line per word, its etymology on the next: `**word** - definition` then `Etym: ...`. About 25 words across both lines. Give the sense the song uses, not the dictionary entry.
- Gloss each word once, at its first appearance; repeats count as duplicates.
- An izafat compound (shab-e-hijr) gets one entry covering its parts.
- The etymology is one clause on its own line: source language, original form, core sense or root. `references/etymology-sources.md` has the style and worked examples.

Etymology comes from a source. `references/etymology-sources.md` maps dictionaries to layers: Platts and Steingass for Perso-Arabic, Turner's CDIAL for Indic.

## Fetch chain

Direct hits beat MCP. Use one `execute` call with `Promise.all` over all shortlisted words. Platts, Steingass and CDIAL share `dsal.uchicago.edu`, so a printed etymology needs a second host: hawramani.com, rekhtadictionary.com, or ScrapeGraph-rendered Rekhta.

1. **Platts by GET** (no bot-block, one round trip): `https://dsal.uchicago.edu/cgi-bin/app/platts_query.py?qs=<URDU-SCRIPT>&searchhws=yes&matchtype=exact`. `qs` must be word script (Urdu, Devanagari, never roman): query the Urdu-script and Devanagari headwords in parallel, since either may hit where the other misses. Get the script from the song's source or a plain-GET lyric page; romanize from attested script.
2. **Persian layer, same shape**: `.../cgi-bin/app/steingass_query.py?qs=<headword>&searchhws=yes&matchtype=exact`.
3. **Fallback mirror, plain GET**: `https://urdu.hawramani.com/<urdu-script>` (Platts text plus Origin tag); `https://www.rekhtadictionary.com/meaning-of-<roman>` and `https://www.rekhtadictionary.com/search?wref=rweb&keyword=<urdu-script>` (senses, Origin language, verse examples, no JS needed).
4. **JS-gated pages**: ScrapeGraph MCP `scrape({url})` renders them (senses, Origin tag, Platts block with Urdu and Devanagari intact). The built-in browser also works: open the entry and read its text. Plain GET and static scrapers return only boilerplate. `hamariweb.com` and `smule.com` sit behind a JS challenge; `gaana.com` and WordPress lyric pages do not.
5. **All fail**: walk rigorous-research "Fast path: every web call" (server pick: `references/fleet.md`), only for the failed words. ScrapeGraph is the remote endpoint `https://mcp.scrapegraphai.com/mcp` on a metered free plan.
6. **Credit or auth failure**: rotate that server's key per rigorous-research "Key rotation: single home" before leaving it.
7. **Chain exhausted**: print the origin language marked unverified (`Etym: <language> (unverified)`), so the failed fetch shows. A confident wrong etymology costs more than a bare language tag.

## Speed

Cut round trips, not accuracy: shortlist uncommon words, fetch them in one parallel batch, emit as soon as it lands.

## Example (invented lines, Urdu input)

Input lines (after dedupe): شامِ فراق میں دل اکیلا ہے / دشت میں پیاسا ہوں، ساقی کہاں ہے

```
*Shaam-e-firaaq mein dil akela hai*<br>
<span style="color:#b45309">شامِ فراق میں دل اکیلا ہے</span><br>
In the evening of separation, the heart is alone.
**firaaq** - separation, parting from a loved one
Etym: Arabic firaaq, from root f-r-q "to separate".

*Dasht mein pyaasa hoon, saaqi kahaan hai*<br>
<span style="color:#b45309">دشت میں پیاسا ہوں، ساقی کہاں ہے</span><br>
I am thirsty in the wilderness - where is the cup-bearer?
**dasht** - wilderness, desert, open plain
Etym: Persian dasht "plain, wilderness".
**saaqi** - cup-bearer, the one who serves wine
Etym: Arabic saaqi, "one who gives drink", from root s-q-y.
```
