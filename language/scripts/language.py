import asyncio
import os
import sys

import httpx


async def main():
    terms = [t.strip().lower() for t in " ".join(sys.argv[1:]).split(",") if t.strip()]
    async with httpx.AsyncClient(timeout=60) as c:
        tags = {t: [] for t in terms}
        if len(terms) == 1:
            r = await c.get("https://api.datamuse.com/words", params={"ml": terms[0], "max": 40, "md": "pf"})
            tags |= {w["word"]: w.get("tags", []) for w in r.json() if w["word"] != terms[0]}
        urls = {f"https://www.etymonline.com/word/{w.replace(' ', '%20')}": w for w in tags}
        r = await c.post("https://api.exa.ai/contents", headers={"x-api-key": os.environ["EXA_API_KEY"]},
                         json={"urls": list(urls), "text": {"maxCharacters": 700}, "maxAgeHours": -1})
        r.raise_for_status()
    text = {urls[x["id"]]: " ".join(x.get("text", "").split()) for x in r.json()["results"] if x["id"] in urls}
    for word, t in tags.items():
        print(f"{word} {t} | {text.get(word) or 'no Etymonline entry'}")


sys.stdout.reconfigure(encoding="utf-8")
asyncio.run(main())
