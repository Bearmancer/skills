import html
import json
import re
from pathlib import Path

from . import render

ROOT = Path(__file__).resolve().parent.parent
THEME_FILES = ("lesson.css", "shell.js")
NOT_COURSES = {"assets", "answers", "work", "node_modules"}
H1 = re.compile(r"(?s)<h1[^>]*>(.*?)</h1>")
TAGS = re.compile(r"<[^>]+>")
LESSON_FILE = re.compile(r"^(\d+)-ch(\d+)-.+\.html$")


def lf(data):
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def write_text(path, text):
    data = lf(text.encode("utf-8"))
    if path.exists() and lf(path.read_bytes()) == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def sync_assets(site_root, assets_dir=None):
    src = assets_dir or ROOT / "assets"
    changed = []
    for name in THEME_FILES:
        dst = site_root / "assets" / name
        data = lf((src / name).read_bytes())
        if dst.exists() and lf(dst.read_bytes()) == data:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        changed.append(name)
    return changed


def lesson_filename(lesson):
    n = int(lesson["chapter"])
    return f"{n:02d}-ch{n}-{render.slug(lesson['title'])[:60].strip('-')}.html"


def lesson_path(site_root, lesson):
    return site_root / lesson["topic"] / "lessons" / lesson_filename(lesson)


def verify_path(site_root, topic, date):
    return site_root / "answers" / f"verify-{topic}-{date}.html"


def _h1(path):
    m = H1.search(path.read_text(encoding="utf-8", errors="replace"))
    return html.unescape(TAGS.sub("", m.group(1))).strip() if m else None


def _title_case(slug):
    return slug.replace("-", " ").title()


def _feed_js(entries):
    return "window.COURSE_INDEX = " + json.dumps(entries, ensure_ascii=True) + ";\n"


def _chapter_rows(topic_dir):
    rows = []
    for f in sorted((topic_dir / "lessons").glob("*.html")):
        m = LESSON_FILE.match(f.name)
        if m:
            rows.append((int(m.group(2)), _h1(f) or f.stem, f.name))
    return rows


def _chapters(topic_dir):
    return [
        {"id": f"ch{n}", "label": f"{n} · {name}", "href": href}
        for n, name, href in _chapter_rows(topic_dir)
    ]


KINDS = ("narrative", "explainer")
INDEX_EXTRAS = re.compile(r'<nav class="index-extras">.*?</nav>', re.S)


SINGLE_MODES = ("rules", "answer", "recommend")
SUBJECT_META = re.compile(r'<meta name="subject" content="([^"]*)">')


def _course_field(topic_dir, key):
    try:
        value = json.loads((topic_dir / "course.json").read_text(encoding="utf-8")).get(
            key
        )
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def read_course_kind(topic_dir):
    return _course_field(topic_dir, "kind")


def read_course_subject(topic_dir):
    return _course_field(topic_dir, "subject")


def read_subjects_last(site_root):
    try:
        data = json.loads((site_root / "site.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("subjects_last")
    if not isinstance(raw, list):
        return []
    return [s for s in raw if isinstance(s, str)]


def read_page_subject(path):
    m = SUBJECT_META.search(path.read_text(encoding="utf-8", errors="replace"))
    return html.unescape(m.group(1)) if m else None


def existing_subjects(site_root):
    return sorted({r["subject"] for r in index_rows(site_root) if r["subject"]})


def write_topic_index(
    site_root,
    topic,
    topic_title=None,
    kind=None,
    subject=None,
):
    topic_dir = site_root / topic
    index = topic_dir / "index.html"
    title = (
        topic_title or (_h1(index) if index.exists() else None) or _title_case(topic)
    )
    kind = kind or read_course_kind(topic_dir) or "explainer"
    if kind not in KINDS:
        raise ValueError(f"course kind must be one of {KINDS}, got {kind!r}")
    subject = subject or read_course_subject(topic_dir)
    declared = {"kind": kind, **({"subject": subject} if subject else {})}
    write_text(topic_dir / "course.json", json.dumps(declared) + "\n")
    write_text(topic_dir / "assets" / "course-index.js", _feed_js(_chapters(topic_dir)))
    rows = "".join(
        f'<tr id="ch{n}"><td>{n}</td><td><a href="lessons/{render.esc(href)}">{render.esc(name)}</a></td></tr>'
        for n, name, href in _chapter_rows(topic_dir)
    )
    previous = index.read_text(encoding="utf-8") if index.exists() else ""
    extras = "".join(INDEX_EXTRAS.findall(previous))
    body = f'<h1>{render.esc(title)}</h1>\n<table class="hub-table numbered"><tr><th>#</th><th>Title</th></tr>{rows}</table>{extras}'
    page = render.page_shell(
        title,
        body,
        asset_prefix="../",
        bar=render.bar_home(
            topic, "../assets/course-index.js", "../", chapter_base="lessons/"
        ),
        feed_src="assets/course-index.js",
        head_extra=f'<meta name="course-kind" content="{kind}">\n',
    )
    write_text(index, page)
    return index


def write_lesson(
    site_root,
    lesson,
    claims_doc,
    sources_doc,
    *,
    topic_title=None,
    kind=None,
):
    path = lesson_path(site_root, lesson)
    topic_title = (
        topic_title
        or _existing_title(site_root, lesson["topic"])
        or _title_case(lesson["topic"])
    )
    nav = [("Index", "../index.html")]
    page = render.render_lesson(
        lesson,
        claims_doc,
        sources_doc,
        asset_prefix="../../",
        topics_feed="../assets/course-index.js",
        nav=nav,
    )
    write_text(path, page)
    write_topic_index(
        site_root, lesson["topic"], topic_title, kind, lesson.get("subject")
    )
    regenerate_index(site_root)
    return path


def _existing_title(site_root, topic):
    index = site_root / topic / "index.html"
    return _h1(index) if index.exists() else None


def single_path(site_root, mode, topic):
    return site_root / "answers" / f"{mode}-{topic}.html"


def write_single(
    site_root,
    lesson,
    claims_doc,
    sources_doc,
):
    path = single_path(site_root, lesson["mode"], lesson["topic"])
    page = render.render_lesson(
        lesson,
        claims_doc,
        sources_doc,
        asset_prefix="../",
        topics_feed="../assets/course-index.js",
        nav=[("Home", "../index.html")],
        bar=render.bar_answer("../index.html", f"{lesson['mode']}-{lesson['topic']}"),
    )
    write_text(path, page)
    regenerate_index(site_root)
    return path


def write_verify(
    site_root,
    claims_doc,
    sources_doc,
    meta,
):
    topic = meta.get("slug") or render.slug(meta["title"])
    path = verify_path(site_root, topic, meta["date"])
    write_text(
        path, render.render_verify(claims_doc, sources_doc, meta, asset_prefix="../")
    )
    return path


def index_rows(site_root):
    rows = []
    for d in sorted(site_root.iterdir(), key=lambda p: p.name):
        if not d.is_dir() or d.name.startswith((".", "_")) or d.name in NOT_COURSES:
            continue
        if (d / "index.html").exists() and (d / "lessons").is_dir():
            title = _h1(d / "index.html") or _title_case(d.name)
            count = len(_chapters(d))
            rows.append(
                {
                    "id": d.name,
                    "title": title,
                    "type": "Course",
                    "subject": read_course_subject(d) or "",
                    "count": str(count),
                    "href": f"{d.name}/index.html",
                }
            )
    answers = site_root / "answers"
    if answers.is_dir():
        for kind, prefix in (
            ("Rules", "rules-"),
            ("Answer", "answer-"),
            ("Picks", "recommend-"),
            ("Verdict", "verdict-"),
        ):
            for f in sorted(answers.glob(f"{prefix}*.html")):
                title = _h1(f) or _title_case(f.stem[len(prefix) :])
                rows.append(
                    {
                        "id": f.stem,
                        "title": title,
                        "type": kind,
                        "subject": read_page_subject(f) or "",
                        "count": "1",
                        "href": f"answers/{f.name}",
                    }
                )
    return rows


def _course_feed(site_root, row):
    entry = {
        "id": row["id"],
        "label": row["title"],
        "href": row["href"],
    }
    if row["type"] != "Course":
        return entry
    chapters = _chapters(site_root / row["id"])
    if len(chapters) > 1:
        entry["chapters"] = [
            {**c, "href": f"{row['id']}/lessons/{c['href']}"} for c in chapters
        ]
    return entry


def regenerate_index(site_root):
    rows = index_rows(site_root)
    courses = [r for r in rows if r["type"] == "Course"]
    subjects_last = read_subjects_last(site_root)
    pinned = set(subjects_last)
    order = {s: i for i, s in enumerate(subjects_last)}
    courses = [r for r in courses if r["subject"] not in pinned] + sorted(
        (r for r in courses if r["subject"] in pinned),
        key=lambda r: order[r["subject"]],
    )
    write_text(
        site_root / "assets" / "course-index.js",
        _feed_js(
            [
                _course_feed(site_root, r)
                for r in courses + [r for r in rows if r["type"] != "Course"]
            ]
        ),
    )
    sections = []
    present = {r["subject"] or "Other" for r in rows}
    subjects = [s for s in sorted(present) if s not in pinned] + [
        s for s in subjects_last if s in present
    ]
    for subject in subjects:
        items = sorted(
            (r for r in rows if (r["subject"] or "Other") == subject),
            key=lambda r: r["title"].casefold(),
        )
        table = "".join(
            f'<tr><td>{n}</td><td><a href="{render.esc(r["href"])}">{render.esc(r["title"])}</a></td></tr>'
            for n, r in enumerate(items, 1)
        )
        sections.append(
            f'<h2 class="subject-heading">{render.esc(subject)}</h2>\n'
            f'<table class="hub-table numbered"><tr><th>#</th><th>Topic</th></tr>{table}</table>'
        )
    body = "<h1>Index</h1>\n" + "\n".join(sections)
    page = render.page_shell(
        "Index",
        body,
        asset_prefix="",
        bar=render.bar_home(None, None, ""),
        feed_src="assets/course-index.js",
    )
    path = site_root / "index.html"
    write_text(path, page)
    return path
