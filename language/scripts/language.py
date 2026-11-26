import asyncio
import os
import re
import sys
from itertools import batched

import httpx

N = 40
ORIGIN = r"\b(etymolog\w*|origins?|roots?|come[s]? from|derivation|cognates?)\b"
ARCHAIC = r"\b(archaic|anachronistic|obsolete|old[- ]fashioned)\b"
STYLE = r"\b(formal|fancier|obscure|older|old)\b"
LEAD = r"^.*?\b(?:synonyms?|words?|terms?|alternatives?|way to say|phrases?)\b(?:\s+(?:for|of|to))?\s+"
FILLER = r"\b(what|is|are|the|of|for|from|where|does|do|find|give|me|a|an|word|words|term|terms|synonyms?)\b"
DATE = r"(late Old English|Old English)|(?:(early|mid-|late) ?)?\b(\d{1,2})c\.|\b(1\d{3}|20\d\d)s?\b"


def parse(ask):
    ask = ask.lower().strip(" ?.!")
    if re.search(ORIGIN, ask):
        rest = re.sub(ORIGIN, " ", ask)
        parts = [re.sub(rf"^(?:\s*{FILLER})+\s*", "", p.strip()) for p in re.split(r",|==|/|\band\b", rest)]
        return "origin", False, [" ".join(p.split()) for p in parts if p.split()]
    archaic = bool(re.search(ARCHAIC, ask))
    term = re.sub(f"{ARCHAIC}|{STYLE}", " ", re.sub(LEAD, "", ask))
    term = re.sub(r"^(?:\s*(?:and|or)\b)+", "", " ".join(term.split())).strip("\"' ")
    return "synonym", archaic, [term]


def dated(text):
    if not (m := re.search(DATE, text)):
        return 9999, "undated"
    old, part, century, year = m.groups()
    if old:
        return 1050 if old.startswith("late") else 900, old
    if century:
        return (int(century) - 1) * 100 + {"early": 10, "late": 90}.get(part, 50), m[0]
    return int(year), m[0]


async def datamuse(c, **params):
    r = await c.get("https://api.datamuse.com/words", params={**params, "md": "fp"})
    r.raise_for_status()
    return r.json()


async def wiki_api(c, **params):
    for wait in (1, 3, 8, None):
        r = await c.get("https://en.wiktionary.org/w/api.php", headers={"User-Agent": "language-skill/1.0 (python-httpx)"},
                        params={"action": "query", "format": "json", "formatversion": 2, **params})
        if r.status_code != 429 or wait is None:
            break
        await asyncio.sleep(max(wait, int(r.headers.get("retry-after", 0))))
    r.raise_for_status()
    return r.json()["query"]


async def archaic_recall(c, term):
    syns = [w["word"] for w in await datamuse(c, rel_syn=term, max=20) if " " not in w["word"]]
    words, titles = [term, *syns[:5]], []
    for word in words:
        query = rf'insource:"{word}" insource:/\{{lb\|en\|[^}}]*(archaic|obsolete)[^}}]*\}}[^\n]*[\[ |]{word}[\]s |.,;}}]/'
        hits = await wiki_api(c, list="search", srsearch=query, srlimit=60, srnamespace=0)
        titles += [h["title"] for h in hits["search"]]
    wiki = await wiktionary(c, [w for w in dict.fromkeys(titles) if w.lower() != term])
    senses = {}
    for title, section in wiki.items():
        if matched := [(i, s) for s in old_senses(section) for i, w in enumerate(words) if re.search(rf"\b{re.escape(w)}", s, re.I)]:
            senses[title] = list(dict.fromkeys(s for _, s in sorted(matched, key=lambda m: m[0])))
    pool = sorted(senses, key=lambda w: not any(re.search(rf"\b{re.escape(term)}", s, re.I) for s in senses[w]))
    return pool, wiki, senses


def plain(sense):
    sense = re.sub(r"\{\{(?:lb|label|senseid|defdate)\|[^{}]*\}\}", "", sense.lstrip("# "))
    sense = re.sub(r"\{\{[^{}|]*\|(?:en\|)?([^{}|]*)[^{}]*\}\}", r"\1", sense)
    return " ".join(re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", sense).split())


async def recall(c, term, forced):
    head, pool = await asyncio.gather(datamuse(c, sp=term, max=1), datamuse(c, ml=term, max=100))
    pos = forced or next((t for t in head[0].get("tags", []) if t in ("n", "v", "adj", "adv")), "") if head else forced
    if " " in term:
        pos = ""
        pool = [w for w in pool if " " in w["word"] or "syn" in w.get("tags", [])]
    pool = [w for w in pool if w["word"] != term and (not pos or pos in w.get("tags", []))]
    return [w["word"] for w in sorted(pool, key=lambda w: "syn" not in w.get("tags", []))], pos


async def etymonline(c, words, pos):
    if not words:
        return {}, set()
    urls = {f"https://www.etymonline.com/word/{w.replace(' ', '%20')}": w for w in words}
    r = await c.post("https://api.exa.ai/contents", headers={"x-api-key": os.environ["EXA_API_KEY"]},
                     json={"urls": list(urls), "text": {"maxCharacters": 8000}, "maxAgeHours": -1})
    r.raise_for_status()
    found, mismatch = {}, set()
    for x in r.json()["results"]:
        if not (word := urls.get(x["id"])):
            continue
        parts = re.split(r"^## (.+?)\(([a-z]+)\.?[^)]*\)\s*$", x.get("text", ""), flags=re.M)
        sections = [(p, b) for h, p, b in zip(parts[1::3], parts[2::3], parts[3::3]) if h.strip().lower() == word.lower()]
        want = pos.get(word, "") if isinstance(pos, dict) else pos
        body = next((b for p, b in sections if not want or p == want), None)
        if body is None:
            if sections:
                mismatch.add(word)
            continue
        first = body.strip().split("\n\n")[0]
        first = re.sub(r"\s*\(see [^()]*(?:\([^()]*\))?[^()]*\)|(?:[;,]|(?<=\"))\s*(?:for which )?see [^.;()]*(?:\([a-z0-9., ]+\))?|\s*Related:.*", "", first, flags=re.S)
        found[word] = " ".join(first.split())
    return found, mismatch


async def wiktionary(c, words):
    pages = [await wiki_api(c, prop="revisions", titles="|".join(b), rvslots="main", rvprop="content") for b in batched(words, 50)]
    out = {}
    for page in (p for group in pages for p in group["pages"] if "revisions" in p):
        text = page["revisions"][0]["slots"]["main"]["content"]
        if m := re.search(r"^==English==$(.*?)(?=^==[^=]|\Z)", text, re.M | re.S):
            out[page["title"]] = re.sub(r"<ref[^>]*/>|<ref.*?</ref>|<!--.*?-->", "", m[1], flags=re.S)
    return out


def template(m):
    p = [x for x in m[1].split("|") if "=" not in x or x.startswith("t=")]
    kind, rest = p[0], p[1:]
    if kind in ("der", "bor", "inh", "bor+", "der+", "inh+", "cog", "m", "l", "mention", "link") and len(rest) > 1:
        word = rest[2 if kind in ("der", "bor", "inh", "bor+", "der+", "inh+") and len(rest) > 2 else 1]
        return word.removeprefix("*") and word or ""
    if kind in ("af", "affix", "suffix", "prefix", "compound") and len(rest) > 1:
        return " + ".join(x for x in rest[1:] if x)
    return ""


def wiki_origin(section):
    found = re.findall(r"^===+Etymology(?: \d+)?===+\s*$(.*?)(?=^==|\Z)", section, re.M | re.S)
    text = next((t for t in found if t.strip()), "")
    for _ in range(3):
        text = re.sub(r"\{\{([^{}]*)\}\}", template, text)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text).replace("''", "")
    return " ".join(text.split())[:600]


def old_senses(section):
    return re.findall(r"^#+ .*\{\{(?:lb|label)\|en\|[^}]*\b(?:archaic|obsolete)\b[^}]*\}\}.*$", section, re.M)


async def lookup(c, words, pos, wiki):
    found, mismatch = await etymonline(c, words, pos)
    rest = [w for w in words if w not in found and w not in mismatch]
    wiki = wiki or (await wiktionary(c, rest) if rest else {})
    for w in rest:
        if w in wiki and (text := wiki_origin(wiki[w])):
            found[w] = f"[Wiktionary] {text}"
    return found, mismatch


async def main():
    mode, archaic, terms = parse(" ".join(sys.argv[1:]))
    if not terms or not terms[0]:
        sys.exit("no term found in ask")
    wiki, found, keep = {}, {}, []
    forced = ""
    if mode == "synonym" and (m := re.fullmatch(r"(to|a|an) (\S+)", terms[0])):
        forced, terms = "v" if m[1] == "to" else "n", [m[2]]
    async with httpx.AsyncClient(timeout=60) as c:
        if mode == "origin":
            keep = terms
            found, _ = await lookup(c, terms, "", {})
        else:
            if archaic:
                (pool, wiki, senses), phrase = await archaic_recall(c, terms[0]), True
                pos = {w: "v" if plain(s[0]).startswith("To ") else "" for w, s in senses.items()}
            else:
                (pool, pos), phrase = await recall(c, terms[0], forced), " " in terms[0]
            for batch in batched(pool, N):
                got, mismatch = await lookup(c, list(batch), pos, wiki)
                found |= got
                keep += [w for w in batch if (archaic or w not in mismatch) and (phrase or w in got)]
                if len(keep) >= N:
                    break
            keep = keep[:N]
    rows = sorted(((*dated("" if found.get(w, "").startswith("[Wiktionary]") else found.get(w, "")), w) for w in keep), key=lambda r: r[0])
    for i, (_, label, word) in enumerate(rows, 1):
        print(f"{i}. {word} [{label}] — {found.get(word, 'no etymology on Etymonline or Wiktionary')}")
        if archaic:
            for sense in senses[word][:3]:
                print(f"   old sense: {plain(sense)[:200]}")


sys.stdout.reconfigure(encoding="utf-8")
asyncio.run(main())
