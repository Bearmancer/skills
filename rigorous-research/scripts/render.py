import html
import re

from .footnotes import Notes

FONTS = (
    "Literata",
    "Source Serif 4",
    "Newsreader",
    "Crimson Pro",
    "EB Garamond",
    "Merriweather",
    "Lora",
    "Libre Baskerville",
    "Atkinson Hyperlegible",
    "Inter",
    "IBM Plex Sans",
    "Charter",
)
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
THEME_INIT = (
    "<script>try{var t=localStorage.getItem('theme');"
    "if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>"
)
STATUS_ORDER = ("true", "untrue", "interpretive", "not-found")


def esc(value):
    return html.escape(str(value), quote=True)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def safe_url(url):
    return url if re.match(r"https?://", url) else None


def _anchor(url, label, cls=""):
    safe = safe_url(url)
    if safe is None:
        return esc(label)
    extra = f' class="{cls}"' if cls else ""
    return f'<a{extra} href="{esc(safe)}">{esc(label)}</a>'


def _term_links(text, terms):
    if not terms:
        return esc(text)
    pattern = re.compile(
        r"(?<!\w)("
        + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
        + r")(?!\w)",
        re.I,
    )
    out, pos, seen = [], 0, set()
    for m in pattern.finditer(text):
        key = m.group(1).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(esc(text[pos : m.start()]))
        out.append(
            f'<a class="term" href="#term-{esc(terms[key])}">{esc(m.group(1))}</a>'
        )
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def inline(text, terms=None):
    out, pos = [], 0
    for m in LINK.finditer(text):
        out.append(_term_links(text[pos : m.start()], terms or {}))
        out.append(_term_links(m.group(1), terms or {}))
        pos = m.end()
    out.append(_term_links(text[pos:], terms or {}))
    return "".join(out)


def type_panel():
    fonts = "".join(
        f"<option{' selected' if f == 'Charter' else ''}>{esc(f)}</option>"
        for f in FONTS
    )
    sizes = "".join(
        f"<option{' selected' if s == 'M' else ''}>{s}</option>"
        for s in ("S", "M", "L", "XL")
    )
    return (
        '<span class="sep" aria-hidden="true"></span>'
        '<div class="type-panel"><span class="aa" aria-hidden="true">Aa</span>'
        f'<select aria-label="Font" data-font-select>{fonts}</select>'
        f'<select aria-label="Size" data-size-select>{sizes}</select>'
        '<button type="button" data-theme-toggle aria-label="Colour theme: auto. Activate to change." aria-pressed="false">Theme: auto</button>'
        "</div>"
    )


def _options(
    entries,
    base,
    current,
    placeholder=None,
):
    opts = [f'<option value="">{esc(placeholder)}</option>'] if placeholder else []
    for e in entries:
        sel = " selected" if current and e.get("id") == current else ""
        opts.append(
            f'<option value="{esc(base + e["href"])}"{sel}>{esc(e["label"])}</option>'
        )
    return "".join(opts)


def _topic_select(current, feed, base):
    cur = f' data-current="{esc(current)}"' if current else ""
    feed_attr = f' data-feed="{esc(feed)}"' if feed else ""
    return (
        '<label class="grp"><span class="lbl">Topic</span>'
        f'<select aria-label="Topic" data-topic{cur}{feed_attr} data-base="{esc(base)}"></select></label>'
    )


def bar_chapter(
    topic,
    topic_feed,
    base,
    current,
    chapters,
):
    cur = f' data-current="{esc(current)}"' if current else ""
    return (
        '<header class="A-bar"><div class="row">'
        f"{_topic_select(topic, topic_feed, base)}"
        f'<select aria-label="Chapter" data-index{cur}>{_options(chapters or [], "", current)}</select>'
        f"{type_panel()}</div></header>"
    )


def bar_answer(home_href, current=None):
    base = home_href.rsplit("index.html", 1)[0]
    return (
        '<header class="A-bar"><div class="row">'
        f"{_topic_select(current, None, base)}"
        f"{type_panel()}</div></header>"
    )


def bar_home(
    current_topic,
    feed,
    base,
    chapter_base=None,
):
    cur = f' data-current="{esc(current_topic)}"' if current_topic else ""
    feed_attr = f' data-feed="{esc(feed)}"' if feed else ""
    if chapter_base is None:
        chapter = '<select aria-label="Chapter" data-index data-placeholder="Select a chapter" data-follows-topic></select>'
    else:
        chapter = f'<select aria-label="Chapter" data-index data-placeholder="Select a chapter" data-base="{esc(chapter_base)}"></select>'
    return (
        '<header class="A-bar" data-state="home"><div class="row">'
        f'<label class="grp"><span class="lbl">Topic</span><select aria-label="Topic" data-topic{cur}{feed_attr} data-base="{esc(base)}" data-placeholder="Select a topic"></select></label>'
        f'<label class="grp"><span class="lbl">Chapter</span>{chapter}</label>'
        f"{type_panel()}</div></header>"
    )


def _anchor_rel(href, label):
    return f'<a href="{esc(href)}">{esc(label)}</a>'


def page_shell(
    title,
    body,
    *,
    asset_prefix,
    bar,
    feed_src=None,
    head_extra="",
):
    feed = f'\t\t<script src="{esc(feed_src)}"></script>\n' if feed_src else ""
    return (
        '<!DOCTYPE html>\n<html lang="en" data-size="M">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{head_extra}{THEME_INIT}\n<title>{esc(title)}</title>\n"
        f'<link rel="stylesheet" href="{esc(asset_prefix)}assets/lesson.css">\n</head>\n<body>\n'
        f"{bar}\n{body}\n{feed}"
        f'\t\t<script src="{esc(asset_prefix)}assets/shell.js"></script>\n</body>\n</html>\n'
    )


def _sources(sources_doc):
    return {s["id"]: s for s in sources_doc.get("sources", [])}


def appendix(sources_doc, extra_html=""):
    rows = [s for s in sources_doc.get("sources", []) if s.get("kind") != "input"]
    read = [s for s in rows if s["status"] == "read"]
    failed = [s for s in rows if s["status"] == "failed"]
    read_items = (
        "".join(
            f'<li>{_anchor(s["url"], s["publisher"])} <span class="small">({esc(s["tier"])})</span></li>'
            for s in read
        )
        or "<li>none</li>"
    )
    fail_items = (
        "".join(
            f"<li>{esc(s['url'])}: {esc(s.get('fail_reason', ''))}</li>" for s in failed
        )
        or "<li>none</li>"
    )
    return (
        '<section class="appendix" aria-labelledby="appendix-h"><h2 id="appendix-h">Appendix</h2>'
        f'<h3>Sources read ({len(read)})</h3><ul class="sources-read">{read_items}</ul>'
        f'<h3>Sources failed to grab ({len(failed)})</h3><ul class="sources-failed">{fail_items}</ul>'
        f"{extra_html}</section>"
    )


class _Ctx:
    def __init__(
        self,
        claims_doc,
        sources_doc,
        terms=None,
    ):
        self.claims = {c["id"]: c for c in claims_doc.get("claims", [])}
        self.sources = _sources(sources_doc)
        self.terms = terms or {}
        self.skip_term = None
        self.notes = Notes(self.sources)

    def text(self, s):
        terms = {k: v for k, v in self.terms.items() if k != self.skip_term}
        return inline(s["text"], terms)

    def evidence_notes(self, claim_ids, stance):
        pairs = []
        for cid in claim_ids:
            for ev in self.claims.get(cid, {}).get("evidence", []):
                if (
                    ev["stance"] == stance
                    and (ev["source"], ev["locator"]) not in pairs
                ):
                    pairs.append((ev["source"], ev["locator"]))
        return pairs

    def span(self, s):
        pairs = self.evidence_notes(s["claims"], "supports")
        sups = self.notes.cite_all(pairs)
        evidence = ' data-evidence="1"' if pairs else ""
        return f'<span class="s" id="{esc(s["id"])}" data-claims="{esc(" ".join(s["claims"]))}"{evidence}>{self.text(s)}</span>{sups}'

    def positions(self, s):
        out = []
        for cid in s["claims"]:
            for p in self.claims.get(cid, {}).get("positions", []):
                holders = (
                    f'<p class="holders">Held by: {esc(", ".join(p["holders"]))}</p>'
                    if p.get("holders")
                    else ""
                )
                srcs = self.notes.cite_all([(sid, "") for sid in p["sources"]])
                out.append(
                    f'<div class="position"><p>{inline(p["text"])}</p>{holders}<p class="srcs">Sources:{srcs}</p></div>'
                )
        return "".join(out)

    def contradicting(self, s):
        pairs = self.evidence_notes(s["claims"], "contradicts")
        if not pairs:
            return ""
        return f'<p class="srcs">Contradicting sources:{self.notes.cite_all(pairs)}</p>'

    def sentence(self, s):
        block = s.get("block", "plain")
        if block == "debate":
            return (
                f'<aside class="debate" data-claims="{esc(" ".join(s["claims"]))}">'
                '<span class="box-title">Debate <span class="pill st-interpretive">interpretive</span></span>'
                f"<p>{self.span(s)}</p>{self.positions(s)}</aside>"
            )
        if block == "errata":
            return (
                f'<aside class="errata" data-claims="{esc(" ".join(s["claims"]))}">'
                '<span class="box-title">Errata <span class="pill st-untrue">untrue</span></span>'
                f"<p>{self.span(s)}</p>{self.contradicting(s)}</aside>"
            )
        return self.span(s)

    def para(self, s):
        out = self.sentence(s)
        return out if out.startswith("<aside") else f"<p>{out}</p>"

    def paras(self, sentences):
        return "".join(self.para(s) for s in sentences)

    def errata_box(self, sentences):
        if not sentences:
            return ""
        items = "".join(
            f"<li>{self.span(s)}{self.contradicting(s)}</li>" for s in sentences
        )
        return f'<aside class="errata" id="errata"><span class="box-title">Errata <span class="pill st-untrue">untrue</span></span><ul>{items}</ul></aside>'


def _cell(ctx, cell, head):
    inner = esc(cell) if isinstance(cell, str) else ctx.sentence(cell)
    return f'<th scope="row">{inner}</th>' if head else f"<td>{inner}</td>"


def _node(ctx, node):
    if "outcome" in node:
        return f'<span class="outcome">{ctx.sentence(node["outcome"])}</span>'
    branches = "".join(
        f'<li><span class="branch">{esc(b["label"])}</span>{_node(ctx, b["node"])}</li>'
        for b in node["branches"]
    )
    return f'<span class="q">{esc(node["question"])}</span><ul>{branches}</ul>'


def _layers(nodes, edges):
    layer = {n["id"]: 0 for n in nodes}
    for _ in range(len(nodes)):
        moved = False
        for e in edges:
            if layer[e["to"]] < layer[e["from"]] + 1 and layer[e["from"]] + 1 < len(
                nodes
            ):
                layer[e["to"]] = layer[e["from"]] + 1
                moved = True
        if not moved:
            break
    return layer


def _wrap(label, width=18):
    lines, cur = [], ""
    for word in label.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    lines.append(cur)
    return lines[:3]


def diagram_svg(nodes, edges, title):
    w, h, gx, gy, pad = 150, 52, 70, 26, 14
    layer = _layers(nodes, edges)
    rows = {}
    pos = {}
    for n in nodes:
        l = layer[n["id"]]
        r = rows.get(l, 0)
        rows[l] = r + 1
        pos[n["id"]] = (pad + l * (w + gx), pad + r * (h + gy))
    width = pad * 2 + (max(layer.values()) + 1) * w + max(layer.values()) * gx
    height = pad * 2 + max(rows.values()) * h + (max(rows.values()) - 1) * gy + 30
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="dg-title dg-desc">',
        f'<title id="dg-title">{esc(title)}</title>',
        '<desc id="dg-desc">'
        + esc(
            "; ".join(
                f"{_label(nodes, e['from'])} to {_label(nodes, e['to'])}"
                + (f" ({e['label']})" if e.get("label") else "")
                for e in edges
            )
        )
        + "</desc>",
        '<defs><marker id="dg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="arrow" d="M0 0L10 5L0 10z"/></marker></defs>',
    ]
    for e in edges:
        x1, y1 = pos[e["from"]]
        x2, y2 = pos[e["to"]]
        if layer[e["to"]] > layer[e["from"]]:
            sx, sy, ex, ey = x1 + w, y1 + h / 2, x2, y2 + h / 2
            d = f"M{sx} {sy}L{ex - 2} {ey}"
            lx, ly = (sx + ex) / 2, (sy + ey) / 2 - 5
        else:
            sx, sy, ex, ey = x1 + w / 2, y1 + h, x2 + w / 2, y2 + h
            drop = max(sy, ey) + 22
            d = f"M{sx} {sy}C{sx} {drop} {ex} {drop} {ex} {ey + 2}"
            lx, ly = (sx + ex) / 2, drop - 4
        parts.append(f'<path class="edge" d="{d}" marker-end="url(#dg-arrow)"/>')
        if e.get("label"):
            parts.append(
                f'<text class="elabel" x="{lx:.0f}" y="{ly:.0f}" text-anchor="middle">{esc(e["label"])}</text>'
            )
    for n in nodes:
        x, y = pos[n["id"]]
        lines = _wrap(n["label"])
        parts.append(
            f'<rect class="node" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>'
        )
        top = y + h / 2 - (len(lines) - 1) * 8 + 4
        for i, line in enumerate(lines):
            parts.append(
                f'<text x="{x + w / 2}" y="{top + i * 16:.0f}" text-anchor="middle">{esc(line)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _label(nodes, nid):
    return next(n["label"] for n in nodes if n["id"] == nid)


def render_body(lesson, ctx):
    layout, b = lesson["layout"], lesson["body"]
    match layout:
        case "concept":
            return "".join(
                f"<h2>{esc(s['heading'])}</h2>{ctx.paras(s['sentences'])}"
                for s in b["sections"]
            )
        case "glossary":
            out = []
            for e in b["entries"]:
                ctx.skip_term = e["term"].lower()
                out.append(
                    f'<dt id="term-{esc(slug(e["term"]))}">{esc(e["term"])}</dt><dd>{ctx.paras(e["sentences"])}</dd>'
                )
            ctx.skip_term = None
            return f'<dl class="glossary">{"".join(out)}</dl>'
        case "qa":
            return (
                '<dl class="qa">'
                + "".join(
                    f"<dt>{esc(i['question'])}</dt><dd>{ctx.paras(i['answer'])}</dd>"
                    for i in b["items"]
                )
                + "</dl>"
            )
        case "table":
            head = "".join(f'<th scope="col">{esc(c)}</th>' for c in b["columns"])
            rows = []
            for r in b["rows"]:
                cells = r["cells"]
                first_label = isinstance(cells[0], str)
                tds = "".join(
                    _cell(ctx, c, first_label and i == 0) for i, c in enumerate(cells)
                )
                rows.append(f"<tr>{tds}</tr>")
            return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        case "decision-tree":
            return f'<ul class="tree"><li>{_node(ctx, b["root"])}</li></ul>'
        case "steps":
            return (
                '<ol class="steps">'
                + "".join(f"<li>{ctx.sentence(s)}</li>" for s in b["steps"])
                + "</ol>"
            )
        case "timeline":
            return (
                '<ul class="tl">'
                + "".join(
                    f"<li><time>{esc(e['when'])}</time><div>{ctx.sentence(e['sentence'])}</div></li>"
                    for e in b["events"]
                )
                + "</ul>"
            )
        case "cause-effect":
            parts = []
            for i, s in enumerate(b["chain"]):
                if i:
                    parts.append('<span class="a" aria-hidden="true">&rarr;</span>')
                parts.append(
                    f'<span class="n" role="listitem">{ctx.sentence(s)}</span>'
                )
            return f'<div class="chain" role="list">{"".join(parts)}</div>'
        case "cheat-sheet":
            return (
                '<div class="cheat">'
                + "".join(
                    f"<div><b>{esc(c['label'])}</b>{ctx.sentence(c['sentence'])}</div>"
                    for c in b["cells"]
                )
                + "</div>"
            )
        case "diagram":
            return f'<figure class="diagram">{diagram_svg(b["nodes"], b["edges"], lesson["title"])}<figcaption>{ctx.sentence(b["caption"])}</figcaption></figure>'
        case _:
            raise ValueError(f"unknown layout {layout}")


def _glossary_terms(lesson):
    if lesson["layout"] != "glossary":
        return {}
    return {e["term"].lower(): slug(e["term"]) for e in lesson["body"]["entries"]}


def render_lesson(
    lesson,
    claims_doc,
    sources_doc,
    *,
    asset_prefix,
    chapters=None,
    topics_feed=None,
    nav=None,
    bar=None,
):
    ctx = _Ctx(claims_doc, sources_doc, _glossary_terms(lesson))
    mode, layout = lesson["mode"], lesson["layout"]
    current = f"ch{lesson['chapter']}" if lesson.get("chapter") else None
    head = f'<meta name="rigorous-research-mode" content="{esc(mode)}">\n<meta name="rigorous-research-layout" content="{esc(layout)}">\n'
    if lesson.get("subject"):
        head += f'<meta name="subject" content="{esc(lesson["subject"])}">\n'
    footer = ""
    if nav:
        footer = (
            '<footer class="lesson-footer"><nav>'
            + "".join(_anchor_rel(href, label) for label, href in nav)
            + "</nav></footer>"
        )
    answer = ctx.span(lesson["answer"])
    layout_html = render_body(lesson, ctx)
    extra = "".join(
        f"<details><summary>{esc(x['heading'])}</summary>{ctx.paras(x['sentences'])}</details>"
        for x in lesson.get("extra", [])
    )
    errata = ctx.errata_box(
        [{"block": "errata", **s} for s in lesson.get("errata", [])]
    )
    body = (
        f"<h1>{esc(lesson['title'])}</h1>\n"
        f'<p class="answer">{answer}</p>\n'
        f'<section class="layout layout-{esc(layout)}">{layout_html}</section>\n'
        f"{extra}{errata}\n"
        f"{ctx.notes.render()}\n{appendix(sources_doc)}\n{footer}"
    )
    the_bar = (
        bar
        if bar is not None
        else bar_chapter(
            lesson["topic"],
            asset_prefix + "assets/course-index.js",
            asset_prefix,
            current,
            chapters,
        )
    )
    return page_shell(
        lesson["title"],
        body,
        asset_prefix=asset_prefix,
        bar=the_bar,
        feed_src=topics_feed,
        head_extra=head,
    )


def _count(claims_doc):
    counts = {s: 0 for s in STATUS_ORDER}
    for c in claims_doc.get("claims", []):
        if c["status"] in counts:
            counts[c["status"]] += 1
    return counts


def render_verify(
    claims_doc,
    sources_doc,
    meta,
    *,
    asset_prefix,
):
    ctx = _Ctx(claims_doc, sources_doc)
    counts = _count(claims_doc)
    checked = len(claims_doc.get("claims", []))
    stats = [
        ("checked", checked),
        ("true (not listed)", counts["true"]),
        ("untrue", counts["untrue"]),
        ("interpretive", counts["interpretive"]),
        ("not-found", counts["not-found"]),
        ("skipped opinions and predictions", int(meta.get("skipped", 0))),
    ]
    header = (
        '<ul class="counts">'
        + "".join(f"<li><b>{n}</b>{esc(label)}</li>" for label, n in stats)
        + "</ul>"
    )
    cards = []
    for c in sorted(claims_doc.get("claims", []), key=lambda c: int(c["id"][1:])):
        if c["status"] not in ("untrue", "interpretive"):
            continue
        cards.append(_card(ctx, c))
    listing = (
        f'<ul class="cards">{"".join(cards)}</ul>'
        if cards
        else "<p>No untrue or interpretive claims.</p>"
    )
    nf = [c for c in claims_doc.get("claims", []) if c["status"] == "not-found"]
    nf_html = ""
    if nf:
        nf_html = (
            '<h3>Claims not found</h3><ul class="claims-not-found">'
            + "".join(
                f'<li>{esc(c["text"])} <span class="small">{esc(", ".join(c.get("anchors", [])))}</span></li>'
                for c in nf
            )
            + "</ul>"
        )
    body = (
        f"<h1>{esc(meta['title'])}</h1>\n"
        f'<p class="surtitle">{esc(meta.get("date", ""))} &middot; {esc(meta.get("input_ref", ""))}</p>\n'
        f"{header}\n{listing}\n{ctx.notes.render()}\n{appendix(sources_doc, nf_html)}"
    )
    return page_shell(
        meta["title"],
        body,
        asset_prefix=asset_prefix,
        bar=bar_answer(asset_prefix + "index.html"),
        feed_src=asset_prefix + "assets/course-index.js",
        head_extra='<meta name="robots" content="noindex">\n',
    )


def _card(ctx, c):
    status = c["status"]
    where = (
        f' <span class="loc">{esc(", ".join(c["anchors"]))}</span>'
        if c.get("anchors")
        else ""
    )
    evidence = "".join(
        f'<p class="ev">{esc(ctx.sources.get(ev["source"], {}).get("publisher", ev["source"]))} <span class="loc">{esc(ev["locator"])}</span> '
        f'<span class="small">{esc(ev["stance"])}</span> <q>{esc(ev["quote"])}</q>{ctx.notes.cite(ev["source"], ev["locator"])}</p>'
        for ev in c.get("evidence", [])
    )
    positions = ""
    for p in c.get("positions", []):
        holders = (
            f'<p class="holders">Held by: {esc(", ".join(p["holders"]))}</p>'
            if p.get("holders")
            else ""
        )
        srcs = ctx.notes.cite_all([(sid, "") for sid in p["sources"]])
        positions += f'<div class="position"><p>{inline(p["text"])}</p>{holders}<p class="srcs">Sources:{srcs}</p></div>'
    return (
        f'<li class="card" id="{esc(c["id"])}"><div class="claim-head"><span class="pill st-{esc(status)}">{esc(status)}</span>{where}</div>'
        f'<p class="claim-text">{esc(c["text"])}</p>{evidence}{positions}</li>'
    )
