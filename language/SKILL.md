---
name: language
description: Synonyms, etymology and word origins, whether two words are related, archaic or anachronistic terms, and formal alternatives for words or verbal phrases/idioms. Use whenever the user asks for synonyms, "another word for", "terms for X", word origins, "where does X come from", "is X related to Y", "X == Y?", fancier/formal/older words, or a better way to say a phrase, even if they never say "thesaurus" or "etymology", and even when you think you know the answer, because popular word origins are often wrong. When nothing is specified, presume synonyms. Returns 20 terms in chronological order with etymologies as lineages, from fetched sources.
---

# Language

```
uv run "$HOME/.agents/skills/language/scripts/language.py" "<word or phrase>"
uv run "$HOME/.agents/skills/language/scripts/language.py" "<word>, <word>, ..."
```

One word prints it plus 40 Datamuse candidates (`ml`: related by meaning; tags give part of speech, `syn` and frequency). Several comma-separated words print only those. Each line is the opening of the Etymonline page (all parts of speech run together), or "no Etymonline entry". Needs `httpx` (`uv pip install httpx`) and `EXA_API_KEY` in the environment; never print the key.

You do the judging: pick the 20 that fit the sense and part of speech asked, order them oldest first by first attestation (archaic words come first), write each etymology as a lineage, and say two words are related only when both entries show the shared root. Take nothing from memory; for a missing entry read Wiktionary and name it.

## Anti-patterns

- **Trusting the script's order.** It sorts by the first date it finds, which may belong to another part of speech or sense. Check each date against the sense asked, then re-sort.
- **Mistaking age for obscurity.** `like`, `want` and `hope` are Old English and common. For "obscure" or "archaic", drop high-frequency words (the `f:` tag) and prefer entries marked archaic or obsolete.
- **Padding to 20.** Datamuse returns loose associates (`strongly`, `demanding` for "urge"). Drop them; return fewer.
- **Wrong part of speech.** Entries run all senses together. Use the tags to keep verbs with verbs, and cite the matching section.
- **Stating relatedness from sound or spelling.** `salary`/`salt` needs both entries showing the shared root. `perpend` is not `prepend`. Answer for the exact word typed.
- **Filling gaps from memory.** "no Etymonline entry" is not evidence. Read Wiktionary, name it, and report disagreements between sources.
- **Dumping raw text.** Condense each entry to one lineage, oldest stage first, with no `{{...}}` markup, cross-references or "Related:" tails.
- **Fetching etymonline.com directly.** Cloudflare returns 403. The script reads it through Exa.
