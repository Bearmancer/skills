import re
import unicodedata
from functools import lru_cache
from urllib.parse import urlparse

from . import registry

DOMAINS_DIR = registry.ROOT / "references" / "domains"
CLASSICAL_WORDS = re.compile(
    r"\b(classical|symphon\w*|concert(?:o|os|i)|overtures?|tone poems?|string quartets?|(?-i:composers?)|orchestras?|orchestral|opera(?!\s+(?:browser|gx|mini)))\b",
    re.I,
)
POPULAR_WORDS = re.compile(
    r"\b(rock|pop|jazz|electronic|hip[- ]hop|albums?|bands?|discography|singles?)\b",
    re.I,
)
NO_ALIAS = {"vaughan williams"}
FULL_GIVEN = {"bach": ("johann", "sebastian")}
NAME_TOKEN = re.compile(r"[A-Z][a-z]+|(?:[A-Z]\.)+")
ERA_WORDS = re.compile(r"(?<!neo-)(?<!neo )\b(baroque|medieval)\b", re.I)


def domain_for(mode, prompt):
    if mode == "recommend" or CLASSICAL_WORDS.search(prompt):
        return "music/classical"
    if POPULAR_WORDS.search(prompt):
        return "music/popular"
    return "general"


def _read(rel):
    return (DOMAINS_DIR / rel).read_text(encoding="utf-8")


def prompt_block(domain):
    parts = [f"domain: {domain}"]
    files = [f"{domain}/sources.md", f"{domain}/exclusions.md"]
    if domain.startswith("music/"):
        files.insert(0, "music/rules.md")
    parts += [_read(rel).strip() for rel in files]
    parts.append(
        "Domain source order replaces the default preference order; domain bans always apply."
    )
    return "\n\n".join(parts)


def _fold(text):
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _unaccent(text):
    return _fold(text).lower()


@lru_cache(maxsize=1)
def banned_hosts():
    line = next(
        ln for ln in _read("music/rules.md").splitlines() if ln.startswith("- Domains,")
    )
    return tuple(re.findall(r"`([^`]+)`", line.split(":", 1)[1]))


def banned_host(url, domain):
    if not domain.startswith("music/"):
        return False
    host = re.sub(r"^www\.", "", (urlparse(url).hostname or "").lower())
    for pat in banned_hosts():
        if pat.endswith(".*"):
            if host.startswith(pat[:-1]):
                return True
        elif host == pat or host.endswith("." + pat):
            return True
    return False


@lru_cache(maxsize=1)
def _composer_aliases():
    text = (
        _read("music/classical/exclusions.md")
        .split("## Composer ban list", 1)[1]
        .split("##", 1)[0]
    )
    line = next(
        ln for ln in text.splitlines() if "," in ln and not ln.startswith("Unban")
    )
    out = {}
    for entry in line.rstrip(".").split(", "):
        name = _unaccent(re.sub(r"\(.*?\)", "", entry)).strip()
        name = re.sub(r"\s+(i|ii)$", "", name)
        qualifier = re.search(r"\((.*?)\)", entry)
        words = name.split()
        out.setdefault(
            name,
            _given_names(name, qualifier[1]) if qualifier and len(words) == 1 else None,
        )
        if len(words) == 2 and name not in NO_ALIAS:
            out.setdefault(words[-1], None)
    return tuple(out.items())


def _given_names(surname, qualifier):
    names = {w.lower() for w in re.findall(r"[A-Za-z]{2,}", qualifier)} | {
        *FULL_GIVEN.get(surname, ())
    }
    return frozenset(
        names
        | {
            c.lower()
            for c in re.findall(
                r"[A-Za-z]", "".join(re.findall(r"(?:[A-Za-z]\.)+", qualifier))
            )
        }
    )


def _namesake(hay, start, given):
    run = []
    for tok in reversed(hay[:start].split()):
        if not NAME_TOKEN.fullmatch(tok):
            break
        run.append(tok)
    return any(
        not (
            set(tok.lower().replace(".", "")) <= given
            if "." in tok
            else tok.lower() in given
        )
        for tok in run
    )


def banned_composer(text, prompt):
    hay, ask = _fold(text), _unaccent(prompt)
    for alias, given in _composer_aliases():
        if re.search(rf"\ballow\s+{re.escape(alias.split()[-1])}\b", ask):
            continue
        for m in re.finditer(rf"\b{re.escape(alias)}\b", hay, re.I):
            if given is None or not _namesake(hay, m.start(), given):
                return alias
    return None


def banned_era(text):
    m = ERA_WORDS.search(text)
    return m[1].lower() if m else None
