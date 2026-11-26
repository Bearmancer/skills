import asyncio
import os
import re
import sys

import httpx

DATE = r"(late Old English|Old English)|(?:(early|mid-|late) ?)?\b(\d{1,2})c\.|\b(1\d{3}|20\d\d)s?\b"


def dated(text):
    if not (m := re.search(DATE, text)):
        return 9999
    old, part, century, year = m.groups()
    if old:
        return 1050 if old.startswith("late") else 900
    if century:
        return (int(century) - 1) * 100 + {"early": 10, "late": 90}.get(part, 50)
    return int(year)


async def datamuse(c, **params):
    r = await c.get("https://api.datamuse.com/words", params={**params, "md": "p"})
    r.raise_for_status()
    return r.json()


async def main():
    terms = [t.strip().lower() for t in " ".join(sys.argv[1:]).split(",") if t.strip()]
    async with httpx.AsyncClient(timeout=60) as c:
        words, pos = terms, ""
        if len(terms) == 1:
            head, pool = await asyncio.gather(datamuse(c, sp=terms[0], max=1), datamuse(c, ml=terms[0], max=60))
            pos = next((t for t in head[0].get("tags", []) if t in ("n", "v", "adj", "adv")), "") if head and " " not in terms[0] else ""
            pool = [w["word"] for w in sorted(pool, key=lambda w: "syn" not in w.get("tags", [])) if (pos in w.get("tags", [])) or (not pos and (" " in w["word"] or " " not in terms[0]))]
            words = [terms[0], *[w for w in pool if w != terms[0]]]
        urls = {f"https://www.etymonline.com/word/{w.replace(' ', '%20')}": w for w in words}
        r = await c.post("https://api.exa.ai/contents", headers={"x-api-key": os.environ["EXA_API_KEY"]},
                         json={"urls": list(urls), "text": {"maxCharacters": 8000}, "maxAgeHours": -1})
        r.raise_for_status()
    found = {}
    for x in r.json()["results"]:
        word = urls.get(x["id"])
        parts = re.split(r"^## (.+?)\(([a-z]+)\.?[^)]*\)\s*$", x.get("text", ""), flags=re.M)
        body = next((b for h, p, b in zip(parts[1::3], parts[2::3], parts[3::3]) if h.strip().lower() == word and (not pos or p == pos)), "")
        if body:
            found[word] = " ".join(body.strip().split("\n\n")[0].split("Related:")[0].split())
    keep = [w for w in words if w in found][: len(terms) if len(terms) > 1 else 21]
    keep += [w for w in words if w not in found][: max(0, 21 - len(keep))] if len(terms) == 1 else [w for w in words if w not in found]
    for i, word in enumerate(sorted(keep, key=lambda w: dated(found.get(w, ""))), 1):
        print(f"{i}. {word} — {found.get(word, 'no etymology')}")


sys.stdout.reconfigure(encoding="utf-8")
asyncio.run(main())
