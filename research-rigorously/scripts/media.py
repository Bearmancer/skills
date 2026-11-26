import re


LONG_MEDIA_SECONDS = 30 * 60
OUTLINE_STEP_SECONDS = 300
OUTLINE_LINE_CHARS = 160
DESCRIPTION_LINE = re.compile(
    r"^\s*[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*[-\u2013\u2014:.)]?\s*(\S.*)$"
)
MARKER = re.compile(r"^\[(?:(\d+):)?(\d{1,2}):(\d{2})\]")
STAMP = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})")


def _seconds(m):
    return int(m[1] or 0) * 3600 + int(m[2]) * 60 + int(m[3])


def stamp(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def clock(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def duration_seconds(text, metadata=None):
    if metadata:
        return float(metadata)
    times = [_seconds(m) for line in text.splitlines() if (m := MARKER.match(line))]
    return float(max(times, default=0))


def is_long(seconds):
    return seconds > LONG_MEDIA_SECONDS


def chapters_from_description(description):
    found = []
    for line in (description or "").splitlines():
        m = DESCRIPTION_LINE.match(line)
        if m:
            t = _seconds(STAMP.fullmatch(m[1]))
            if not found or t > found[-1]["start_time"]:
                found.append({"title": m[2].strip(), "start_time": t})
    return found if len(found) >= 2 else []


def plan(duration, chapters):
    items = sorted(chapters or [], key=lambda c: float(c.get("start_time") or 0))
    out = []
    for i, ch in enumerate(items):
        nxt = float(items[i + 1]["start_time"]) if i + 1 < len(items) else duration
        end = (
            min(int(float(ch.get("end_time") or nxt)), int(duration))
            if duration
            else int(float(ch.get("end_time") or nxt))
        )
        start = int(float(ch.get("start_time") or 0))
        if end > start:
            out.append(
                {
                    "n": len(out) + 1,
                    "title": " ".join(str(ch.get("title") or "").split())
                    or f"Chapter {len(out) + 1}",
                    "start": start,
                    "end": end,
                }
            )
    return out if len(out) >= 2 else []


def from_decision(duration, items):
    picked = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("start", "")).strip().strip("[]")
        m = STAMP.fullmatch(raw)
        t = _seconds(m) if m else int(raw) if raw.isdigit() else None
        if (
            t is not None
            and t < duration
            and (not picked or t > picked[-1]["start_time"])
        ):
            picked.append({"title": item.get("title"), "start_time": t})
    return plan(duration, picked)


def outline(text):
    out, last = [], -OUTLINE_STEP_SECONDS
    for line in text.splitlines():
        m = MARKER.match(line)
        if m and _seconds(m) - last >= OUTLINE_STEP_SECONDS:
            last = _seconds(m)
            out.append(line[:OUTLINE_LINE_CHARS])
    return "\n".join(out)


def slice_text(text, start, end):
    keep = []
    inside = False
    for line in text.splitlines():
        m = MARKER.match(line)
        if m:
            inside = start <= _seconds(m) < end
        if inside:
            keep.append(line)
    return "\n".join(keep)
