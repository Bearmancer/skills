# Etymology sources for Urdu / Hindustani words

No single dictionary is best for every word, because Hindustani vocabulary has layers.
Pick the source by the layer the word belongs to.

## The words this skill glosses are mostly Perso-Arabic: use these, in this order

1. **Platts, _A Dictionary of Urdu, Classical Hindi, and English_ (1884)**, searchable at DSAL,
   University of Chicago: https://dsal.uchicago.edu/dictionaries/platts/
   Gives an etymology in square brackets for each headword (letter codes such as A. Arabic,
   P. Persian, S. Sanskrit, H. Hindi, T. Turkish; check the key in its front matter). It is
   the most comprehensive Urdu-English dictionary and the standard reference for tracing
   Persian and Arabic words in Urdu. Weakness: it is from 1884, so its Sanskrit/Prakrit
   etymologies are dated (see the Indo-Aryan note below).
2. **`https://urdu.hawramani.com/<urdu-script>`** — Platts' text as a plain-GET page, carrying the
   **Origin** language tag (Arabic, Persian, Sanskrit, Hindi) on its own line. Reachable when DSAL
   is slow, and it is the fallback for confirming the origin language and the sense used in poetry.
3. **Steingass, _A Comprehensive Persian-English Dictionary_ (1892)**, also on DSAL.
   Use for Persian-origin words and for Arabic words as they were used in Persian.
4. **Lane's _Arabic-English Lexicon_** for the Arabic root and its core sense when you want
   to state the root.
5. **Urdu Lughat** (Urdu Dictionary Board): a large historical Urdu dictionary with
   etymological notes, useful when the three above disagree.
6. **Wiktionary**: handy for a fast cross-check, but user-edited; never the only source.

## Indo-Aryan (Sanskrit / Prakrit descended) words

Use **Turner, _A Comparative Dictionary of the Indo-Aryan Languages_ (CDIAL)**, also searchable
at DSAL, or **McGregor's Oxford Hindi-English Dictionary**, which relies on Turner. Learners
and scholars generally treat Platts as unreliable for this layer. Everyday native words are not
glossed by this skill, but a poetic Urdu word can still be Indic.

## Verification procedure

- Look the word up (Platts first) rather than relying on memory. Search the headword in Urdu
  script together with "Platts"; a Roman spelling only serves to find the script, never the lookup.
- Fastest verified lookup is a plain GET against the DSAL CGI, one call per headword, no MCP and
  no bot-block:
  `https://dsal.uchicago.edu/cgi-bin/app/platts_query.py?qs=<URDU-SCRIPT>&searchhws=yes&matchtype=exact`
  `qs` must be Urdu script, since roman spellings return no hit. Swap `platts_query.py` for
  `steingass_query.py` for the Persian layer. `https://urdu.hawramani.com/<urdu-script>` is a
  plain-GET Platts mirror carrying the same entry plus an Origin tag.
- A dictionary site whose entry loads by script returns boilerplate or a 500 to both plain GET and a
  static scraper. Two renderers work: ScrapeGraph MCP `scrape({url})`, which returns the rendered
  markdown with senses, the Origin language tag and the Platts block, Urdu and Devanagari intact; or
  the harness's own built-in browser tool, opening the entry URL and reading
  the page text. Prefer ScrapeGraph for one word, the built-in browser tool when credits are spent.
- For the fetch itself, follow the rigorous-research skill's chain of resources:
  the rigorous-research `SKILL.md`, section "Fast path: every web call".
  Pick the server by capability from its `references/fleet.md`, then walk the bot-block chain in
  order (Tavily -> Firecrawl -> Exa -> ScrapeGraph -> Apify -> AgentQL ->
  Bright Data -> Browserbase), stopping at the first fetch that actually holds the entry. ScrapeGraph
  speaks the remote endpoint `https://mcp.scrapegraphai.com/mcp` and is metered, so check `credits`
  before a batch. On a
  credit or auth failure, rotate that server's keys before leaving it. DSAL is
  bot-protected often enough that a single failed fetch means nothing: move down the chain.
- Cross-check the origin language across at least two sources when the word is unusual.
- Batch the lookups: one pass over all the words a song needs, hitting sources concurrently,
  beats one song-length argument per word. Confirm a word once, then reuse it across songs.
- Arabic words in Urdu normally arrived through Persian. Say "via Persian" only when a
  source says so or the word clearly has a Persian-specific form.
- If you cannot confirm the chain, give only what you can confirm (for example "Persian") and
  stop there. Never invent a root, a Middle Persian form or a "from X meaning Y" clause to
  make the line look complete.

## Style of the etymology clause

One clause: _source language + original form (ASCII) + core sense or root_.

- Arabic: `Arabic firaaq, from root f-r-q "to separate"`
- Persian: `Persian dasht "plain, wilderness"`
- Compound: `Persian-Arabic compound: shab (Persian "night") + hijr (Arabic "separation")`
- Turkic or others: `Turkish/Chagatai X "..."`

Write roots as plain letters with hyphens (f-r-q), dropping ain/hamza like the rest of the
output.
