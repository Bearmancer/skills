---
name: language
description: Synonyms, etymology and word origins, whether two words are related, archaic or anachronistic terms, and formal alternatives for words or verbal phrases/idioms. Use whenever the user asks for synonyms, "another word for", "terms for X", word origins, "where does X come from", "is X related to Y", "X == Y?", fancier/formal/older words, or a better way to say a phrase, even if they never say "thesaurus" or "etymology", and even when you think you know the answer, because popular word origins are often wrong. When nothing is specified, presume synonyms. Returns 20 terms in chronological order with etymologies as lineages, from fetched sources.
---

# Language

Pass the ask verbatim. No flags.

```
uv run "$HOME/.agents/skills/language/scripts/language.py" "<the user's ask>"
```

Needs `httpx` installed once: `uv pip install httpx`.

- Synonym asks (the default) print up to 40 candidates, oldest first by first English attestation.
- Pick the part of speech by writing the word as `to urge` (verb) or `a request` (noun) when the user's context makes it clear.
- Asks containing "etymology", "origin", "root", "come from", "derivation" or "cognate" print one entry per word. Separate words with commas. For "is X related to Y", send `etymology of X, Y`.
- "archaic", "anachronistic", "obsolete" and "old-fashioned" mean archaic in time: only words with a Wiktionary sense labelled archaic or obsolete, with those senses printed under each word.
- Needs `EXA_API_KEY` in the environment. Never print it.

## Answer

1. From the candidates, keep the best 20 in the requested sense. Drop loose associates. For archaic asks, keep a word only if a printed old sense matches the requested meaning. Return fewer than 20 rather than pad.
2. Keep the printed chronological order. Undated entries go last.
3. Write each etymology as one lineage, oldest first, using only stages in the printed text:

   `ponder (mid-14c.): PIE *(s)pen- "draw, stretch, spin" → Latin pendere "hang, weigh" → pondus "weight" → ponderare "ponder" → Old French ponderer → English ponder`

4. Name Wiktionary for entries marked `[Wiktionary]`, and strip its template markup. For a row with no etymology, give the word alone and say none was found.

## Accuracy

- Say two words are related only when both entries show the shared root.
- Answer about the exact word typed. Do not swap in a lookalike.
- Spellings are shared by unrelated words. If an etymology's meaning does not fit the sense you are listing, say no etymology was found for that sense.
- If Etymonline and Wiktionary disagree, report both.
- A hedge in the source ("said to be", "perhaps") stays a hedge.
- Do not fetch etymonline.com directly: Cloudflare returns 403. The script reads it through Exa.
