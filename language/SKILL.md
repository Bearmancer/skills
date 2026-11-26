---
name: language
description: Synonyms, etymology and word origins, whether two words are related, archaic or anachronistic terms, and formal alternatives for words or verbal phrases/idioms. Use whenever the user asks for synonyms, "another word for", "terms for X", word origins, "where does X come from", "is X related to Y", "X == Y?", fancier/formal/older words, or a better way to say a phrase, even if they never say "thesaurus" or "etymology", and even when you think you know the answer, because popular word origins are often wrong. When nothing is specified, presume synonyms. Returns 20 terms in chronological order with etymologies as lineages, from fetched sources.
---

# Language

```
uv run "$HOME/.agents/skills/language/scripts/language.py" "<word or phrase>"
uv run "$HOME/.agents/skills/language/scripts/language.py" "<word>, <word>, ..."
```

One word or phrase prints it plus 20 synonyms; several comma-separated words print only those. Every row is an Etymonline entry, oldest first, so archaic words come first. Needs `httpx` (`uv pip install httpx`) and `EXA_API_KEY` in the environment; never print the key.

Choose what to show from the rows: the best matches for the sense asked, a lineage per etymology (oldest stage first), only relations both entries support. A row with no etymology is not evidence; look it up on Wiktionary and name it.
