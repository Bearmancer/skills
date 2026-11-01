# /// script
# requires-python = ">=3.12"
# ///
"""URL audit gate: every cited URL must resolve to real content before a page publishes.

Flags: OK, BROKEN (dead, redirect-to-root, soft 404, network error), JS? (script shell with no text), BLOCKED
(401/403/429/503). BLOCKED and JS? may be re-checked by a second fetcher (`recheck`), which upgrades them to OK when it
returns the page; BGG answers 403 to bots, so its links need that second surface.

  uv run <skill dir>/scripts/urlaudit.py <url>... | -f file.md      exit 1 when any URL is not OK
"""

import argparse
import re
import sys
import urllib.error
import urllib.request
from collections import namedtuple
from pathlib import Path
from urllib.parse import quote, urlparse

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
URL_RE = re.compile(r"https?://[^\s<>()\[\]\"'`|]+")
SOFT_404 = re.compile(
    rb"page not found|404 not found|doesn.t exist|no longer available", re.I
)
PLACEHOLDER = re.compile(
    r"…|\.\.\.|XXXX|<|\{|/example\b|example\.(com|org)|://mcp\.|/mcp(\?|$)|localhost|127\.0\.0\.1"
)
JS_SHELL = re.compile(
    rb"enable javascript|requires javascript|<noscript>|id=\"(root|app|__next)\"", re.I
)
BLOCKED_CODES = (401, 403, 429, 503)
MAX_BODY = 300_000


class Fetched(namedtuple("Fetched", "code final body error", defaults=(b"", None))):
    pass


class UrlResult(namedtuple("UrlResult", "url code flag final")):
    @property
    def ok(self):
        return self.flag.startswith("OK")


def default_fetch(url, timeout=20.0):
    req = urllib.request.Request(
        quote(url, safe=":/?#[]@!$&'()*+,;=%~"),
        headers={"User-Agent": UA, "Accept": "text/html,*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return Fetched(r.status, r.geturl(), r.read(MAX_BODY))
    except urllib.error.HTTPError as exc:
        return Fetched(exc.code, url)
    except Exception as exc:
        return Fetched(0, url, error=type(exc).__name__)


def classify(url, got):
    if got.error:
        return UrlResult(url, 0, f"BROKEN({got.error})", url)
    if got.code >= 400 or got.code == 0:
        return UrlResult(
            url, got.code, "BLOCKED" if got.code in BLOCKED_CODES else "BROKEN", url
        )
    if urlparse(url).path.strip("/") and not urlparse(got.final).path.strip("/"):
        return UrlResult(url, got.code, "BROKEN(redirect-to-root)", got.final)
    if SOFT_404.search(got.body[:20_000]):
        return UrlResult(url, got.code, "BROKEN(soft-404)", got.final)
    text = re.sub(
        rb"<script.*?</script>|<style.*?</style>|<[^>]+>", b" ", got.body, flags=re.S
    )
    if JS_SHELL.search(got.body) and len(text.split()) < 150:
        return UrlResult(url, got.code, "JS?", got.final)
    return UrlResult(url, got.code, "OK", got.final)


def extract_urls(text):
    urls = list(dict.fromkeys(u.rstrip(".,;:") for u in URL_RE.findall(text)))
    return [u for u in urls if urlparse(u).netloc and not PLACEHOLDER.search(u)]


def audit(
    urls,
    fetch=default_fetch,
    recheck=None,
):
    results = []
    for url in dict.fromkeys(urls):
        res = classify(url, fetch(url))
        if res.flag in ("BLOCKED", "JS?") and recheck is not None and recheck(url):
            res = UrlResult(url, res.code, "OK(recheck)", res.final)
        results.append(res)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("urls", nargs="*")
    ap.add_argument("-f", dest="file", help="extract every http(s) URL from this file")
    args = ap.parse_args(argv)
    urls = args.urls
    if args.file:
        with Path(args.file).open(encoding="utf-8") as fh:
            urls = extract_urls(fh.read())
    bad = 0
    for res in audit(urls):
        bad += not res.ok
        print(
            f"{res.code} {res.flag} {res.final} <- {res.url}"
            if res.final != res.url
            else f"{res.code} {res.flag} {res.url}"
        )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
