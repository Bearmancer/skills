import html
import re
from html.parser import HTMLParser

VOID = {"meta", "link", "br", "hr", "img", "input", "source", "wbr"}
BACK = "&#8617;"
NOTE_ID = re.compile(r"^fn-(\d+)$")


def esc(value):
    return html.escape(str(value), quote=True)


def safe_url(url):
    return url if re.match(r"https?://", url) else None


class Notes:
    def __init__(self, sources):
        self.sources = sources
        self.keys = []
        self.uses = {}

    def cite(self, sid, locator=""):
        if sid not in self.sources:
            return ""
        key = (sid, locator)
        if key not in self.uses:
            self.keys.append(key)
            self.uses[key] = 0
        self.uses[key] += 1
        n, k = self.keys.index(key) + 1, self.uses[key]
        ref = f"fnref-{n}" if k == 1 else f"fnref-{n}-{k}"
        return f'<sup class="fn"><a href="#fn-{n}" id="{ref}">{n}</a></sup>'

    def cite_all(self, pairs):
        return "".join(self.cite(sid, loc) for sid, loc in pairs)

    def render(self):
        if not self.keys:
            return ""
        items = []
        for n, (sid, loc) in enumerate(self.keys, 1):
            s = self.sources[sid]
            where = f", {esc(loc)}" if loc else ""
            url = safe_url(s["url"])
            link = (
                f' <a href="{esc(url)}">{esc(url)}</a>' if url else f" {esc(s['url'])}"
            )
            backs = "".join(
                f'<a class="back" href="#fnref-{n}{"" if k == 1 else f"-{k}"}" aria-label="Back to text">{BACK}</a>'
                for k in range(1, self.uses[(sid, loc)] + 1)
            )
            items.append(
                f'<li id="fn-{n}" data-source="{esc(sid)}">{esc(s["publisher"])}{where}.{link} {backs}</li>'
            )
        return f'<section class="notes" aria-labelledby="notes-h"><h2 id="notes-h">Notes</h2><ol class="footnotes">{"".join(items)}</ol></section>'


REFERENCE_ATTRS = ("href", "src", "srcset", "action", "data")
EXTERNAL_REF = re.compile(r"^\s*(https?:)?//", re.I)
URL_TEXT = re.compile(r"https?://|(?<![:\w/])//[a-z0-9-]+\.[a-z0-9.-]+", re.I)


class _Scan(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.external = []
        self.sups = []
        self.notes = []
        self.backs = {}
        self.note = 0
        self.awaiting = None
        self.unmarked = []
        self.feed(text)
        self._missing()

    def _in(self, idx):
        return any(frame[idx] for frame in self.stack)

    def _missing(self):
        if self.awaiting is not None:
            self.unmarked.append(self.awaiting)
            self.awaiting = None

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        classes = a.get("class", "").split()
        protected = (
            (tag == "ol" and "footnotes" in classes)
            or (tag == "section" and "appendix" in classes)
            or (tag == "p" and "surtitle" in classes)
        )
        sup = tag == "sup" and "fn" in classes
        if not sup:
            self._missing()
        else:
            self.awaiting = None
        if tag == "li" and self._in(1) and NOTE_ID.match(a.get("id", "")):
            self.note = int(NOTE_ID.match(a["id"])[1])
            self.notes.append((self.note, a.get("data-source", "")))
            self.backs[self.note] = []
        if not self._in(1):
            self.external += [
                v
                for k, v in a.items()
                if k in REFERENCE_ATTRS and EXTERNAL_REF.match(v)
            ]
        if tag == "a":
            href = a.get("href", "")
            if self._in(2) or (href.startswith("#fn-") and not self._in(1)):
                self.sups.append((href, a.get("id", "")))
            elif self._in(1) and href.startswith("#fnref-") and self.note:
                self.backs[self.note].append(href[1:])
        if tag not in VOID:
            evidence = (
                (a.get("id") or "(no id)")
                if tag == "span" and "data-evidence" in a
                else None
            )
            self.stack.append((tag, protected, sup, evidence))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if self.stack[i][3] and i == len(self.stack) - 1:
                    self.awaiting = self.stack[i][3]
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.awaiting is not None and data.strip():
            self._missing()
        if not self._in(1) and not any(f[0] in ("script", "style") for f in self.stack):
            self.external += [m.group(0) for m in URL_TEXT.finditer(data)]


def problems(text, source_ids):
    scan = _Scan(text)
    out = [
        f"external link outside the footnotes and appendix: {u}" for u in scan.external
    ]
    out += [
        f"evidence-bearing sentence {sid} has no superscript" for sid in scan.unmarked
    ]
    note_nums = [n for n, _ in scan.notes]
    sup_ids = {i for _, i in scan.sups}
    if note_nums != list(range(1, len(note_nums) + 1)):
        out.append(f"notes are not numbered in sequence from 1: {note_nums}")
    for href, _ in scan.sups:
        m = NOTE_ID.match(href.lstrip("#"))
        if not href.startswith("#") or not m or int(m[1]) not in note_nums:
            out.append(
                f"superscript links to {href.lstrip('#')} but the page has no note with that id"
            )
    cited = {
        int(m[1]) for href, _ in scan.sups if (m := NOTE_ID.match(href.lstrip("#")))
    }
    first = [
        int(m[1]) for href, _ in scan.sups if (m := NOTE_ID.match(href.lstrip("#")))
    ]
    seen = []
    for n in first:
        if n not in seen:
            seen.append(n)
    if seen != sorted(seen):
        out.append(f"superscripts are not numbered in order of first use: {seen}")
    for n, sid in scan.notes:
        if n not in cited:
            out.append(f"note fn-{n} has no superscript")
        if not scan.backs.get(n):
            out.append(f"note fn-{n} has no back-link")
        for target in scan.backs.get(n, []):
            if target not in sup_ids:
                out.append(
                    f"note fn-{n} back-link {target} has no matching superscript"
                )
        if sid not in source_ids:
            out.append(
                f"note fn-{n} names source {sid or '(none)'}, which is not a sources.yaml row"
            )
    return out
