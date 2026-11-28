import hashlib
import http.client
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections import namedtuple
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote, urlparse

from . import agents, keys, log_attempt, registry

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
BLOCKED_STATUS = (401, 403, 429, 503)
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")
TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".html", ".htm", ".vtt", ".srt")
MEDIA_SUFFIXES = (".mp3", ".wav", ".m4a", ".mp4", ".webm", ".mkv", ".ogg", ".flac")
MAX_BODY = 5_000_000


class FetchResult:
    def __init__(
        self,
        ok,
        text="",
        surface="",
        error=None,
        ocr_text="",
        visual=False,
        tried=None,
        duration=None,
        chapters=None,
        description=None,
    ):
        self.ok = ok
        self.text = text
        self.surface = surface
        self.error = error
        self.ocr_text = ocr_text
        self.visual = visual
        self.tried = tried if tried is not None else []
        self.duration = duration
        self.chapters = chapters
        self.description = description


HttpResponse = namedtuple(
    "HttpResponse", "status body content_type error", defaults=(b"", "", None)
)


def default_http_get(url, timeout=30.0):
    if urlparse(url).scheme not in ("http", "https"):
        return HttpResponse(0, error="UnsupportedScheme")
    req = urllib.request.Request(
        quote(url, safe=":/?#[]@!$&'()*+,;=%~"),
        headers={"User-Agent": UA, "Accept": "text/html,application/pdf,*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return HttpResponse(
                r.status, r.read(MAX_BODY), r.headers.get("Content-Type", "")
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        return HttpResponse(0, error=type(exc).__name__)


class _Text(HTMLParser):
    BLOCK: ClassVar[set[str]] = {
        "p",
        "div",
        "br",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "table",
        "ul",
        "ol",
        "dd",
        "dt",
    }
    SKIP: ClassVar[set[str]] = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw):
    parser = _Text()
    parser.feed(raw.decode("utf-8", errors="replace"))
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


TS = re.compile(r"(\d+):(\d+):(\d+)\.(\d+)")
VTT_TAG = re.compile(r"<[^>]*>")


def _clock(t):
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _video_info(out):
    for path in sorted(out.glob("*.info.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        return {
            "duration": data.get("duration"),
            "chapters": data.get("chapters") or None,
            "description": data.get("description") or None,
        }
    return {}


def vtt_to_text(raw):
    cues = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        lines = block.strip().splitlines()
        m = TS.match(lines[0]) if lines else None
        if not m:
            continue
        t = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000
        cues.append((t, " ".join(VTT_TAG.sub("", " ".join(lines[1:])).split())))
    out = []
    prev = []
    for t, text in cues:
        toks = text.split()
        if not toks:
            continue
        overlap = next(
            (
                j
                for j in range(min(len(toks), len(prev)), 0, -1)
                if prev[-j:] == toks[:j]
            ),
            0,
        )
        prev = toks
        if toks[overlap:]:
            out.append(f"[{_clock(t)}] {' '.join(toks[overlap:])}")
    return "\n".join(out)


def pages_text(text):
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    marked = [f"[p. {i}]\n{p.strip()}" for i, p in enumerate(pages, 1) if p.strip()]
    return "\n\n".join(marked), len(pages)


def is_video_url(url):
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS)


def is_local(source):
    return not re.match(r"https?://", source) and Path(source).expanduser().exists()


class LadderFetcher:
    def __init__(
        self,
        http_get=default_http_get,
        run_cmd=subprocess.run,
        min_chars=200,
        rate_limit_wait=5.0,
    ):
        self.http_get = http_get
        self.run_cmd = run_cmd
        self.min_chars = min_chars
        self.rate_limit_wait = rate_limit_wait

    def _step_id(self, ctx, label, url):
        # Stable across a resume, so a replayed fetch finds the agent's reply.
        return f"fetch.{label}.{hashlib.sha256(url.encode('utf-8')).hexdigest()[:10]}"

    def _cmd(self, args, timeout=600.0):
        return self.run_cmd(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )

    def _log(
        self,
        ctx,
        surface,
        route,
        url,
        status,
        error_class=None,
        content=None,
    ):
        try:
            rec = log_attempt.build_record(
                ctx.reg,
                claim="fetch",
                round_no=1,
                surface=surface,
                route=route,
                url=url,
                status=status,
                query_variant="fetch",
                error_class=error_class,
                content=content,
                now=ctx.clock() if ctx.clock else None,
            )
        except log_attempt.AttemptError:
            return
        ctx.ledger.append_attempt(rec)

    def read(self, source, ctx):
        if is_local(source):
            return self.read_local(Path(source).expanduser(), ctx)
        if is_video_url(source):
            return self.read_video(source, ctx)
        return self.read_url(source, ctx)

    def read_local(self, path, ctx):
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self.read_pdf(path, ctx, str(path))
        if suffix in MEDIA_SUFFIXES:
            return self.read_media_file(path, ctx, str(path))
        if suffix in TEXT_SUFFIXES or not suffix:
            raw = path.read_bytes()
            text = (
                vtt_to_text(raw.decode("utf-8", errors="replace"))
                if suffix == ".vtt"
                else (
                    html_to_text(raw)
                    if suffix in (".html", ".htm")
                    else raw.decode("utf-8", errors="replace")
                )
            )
            return FetchResult(
                bool(text.strip()),
                text,
                "local",
                None if text.strip() else "empty file",
            )
        return FetchResult(False, error=f"unsupported file type {suffix}")

    def read_pdf(self, path, ctx, url):
        ocr_cmd = registry.surfaces(ctx.reg)["ocr.read"].routes["cli"][0].split()
        proc = self._cmd([*ocr_cmd, str(path)])
        ocr_text = (proc.stdout or "").strip() if proc.returncode == 0 else ""
        self._log(ctx, "ocr.read", "cli", url, "ok" if len(ocr_text) > 8 else "empty")
        if not ocr_text:
            return FetchResult(
                False,
                error=(
                    f"ocr.read failed ({proc.returncode})"
                    if proc.returncode
                    else "ocr.read returned no text"
                ),
                tried=["ocr.read"],
            )
        text, _pages = pages_text(ocr_text)
        return FetchResult(
            True, text, "ocr.read", ocr_text=ocr_text, tried=["ocr.read"]
        )

    def read_media_file(self, path, ctx, url):
        try:
            text = ctx.runner.run(
                "media",
                f"{agents.step_prompt('media')}\n\n---\n\nThe attached file is the recording.",
                step="ingest.media.file",
                context={"files": [str(path)]},
            )
        except agents.Unanswerable as exc:
            return FetchResult(False, error=f"media ask unanswerable: {exc.reason}")
        reason = agents.unanswerable(text)
        if reason is not None:
            return FetchResult(False, error=f"media ask unanswerable: {reason}")
        text = text.strip()
        return FetchResult(
            bool(text),
            text,
            "media",
            None if text else "the media read returned nothing",
        )

    def read_video(self, url, ctx):
        # Subs and metadata are scratch under run/; the audio a media ask attaches
        # gets a stable name under run/media/ so its hash survives the process.
        media_dir = ctx.layout.media
        media_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=media_dir) as tmp:
            out = Path(tmp)
            proc = self._cmd(
                [
                    "yt-dlp",
                    "--no-warnings",
                    "--skip-download",
                    "--write-auto-subs",
                    "--write-subs",
                    "--sub-langs",
                    "en",
                    "--sub-format",
                    "vtt",
                    "--write-info-json",
                    "-o",
                    str(out / "subs.%(ext)s"),
                    url,
                ]
            )
            info = _video_info(out)
            vtts = sorted(out.glob("subs*.vtt"))
            if vtts:
                text = vtt_to_text(
                    vtts[0].read_text(encoding="utf-8", errors="replace")
                )
                if text.strip():
                    self._log(
                        ctx,
                        "ytdlp.transcript",
                        "local",
                        url,
                        "ok",
                        content=text.encode("utf-8"),
                    )
                    return FetchResult(
                        True,
                        text,
                        "ytdlp.transcript",
                        tried=["ytdlp.transcript"],
                        **info,
                    )
            code = "blocked" if "429" in (proc.stderr or "") else None
            self._log(
                ctx,
                "ytdlp.transcript",
                "local",
                url,
                "blocked" if code else "empty",
                error_class=code,
            )
            got = self._cmd(
                [
                    "yt-dlp",
                    "--no-warnings",
                    "-x",
                    "--audio-format",
                    "mp3",
                    "-o",
                    str(out / "audio.%(ext)s"),
                    url,
                ]
            )
            audio = sorted(out.glob("audio.*"))
            if got.returncode != 0 or not audio:
                return FetchResult(
                    False,
                    error=f"no captions and no audio ({(got.stderr or proc.stderr or '').strip()[:120]})",
                    tried=["ytdlp.transcript"],
                )
            stable = media_dir / f"{self._step_id(ctx, 'media', url)}{audio[0].suffix}"
            shutil.move(str(audio[0]), stable)
            res = self.read_media_file(stable, ctx, url)
            res.tried = ["ytdlp.transcript"]
            res.duration, res.chapters, res.description = (
                info.get("duration"),
                info.get("chapters"),
                info.get("description"),
            )
            return res

    def read_url(self, url, ctx, allow_mcp=True):
        reg = ctx.reg
        surfaces = registry.surfaces(reg)
        tried = []
        problems = []
        for sid in reg["fetch_ladder"]:
            surf = surfaces.get(sid)
            if (
                surf is None
                or not surf.wired
                or surf.id.startswith(("ytdlp.", "ocr."))
            ):
                continue
            if surf.pool and ctx.keys is not None:
                ctx.keys.guard(surf.server)
            res = self._try(sid, surf, url, ctx, allow_mcp=allow_mcp)
            tried.append(sid)
            if res.ok:
                res.tried = tried
                return res
            problems.append(f"{sid}: {res.error}")
        return FetchResult(
            False, error="; ".join(problems)[:300] or "no fetch surface", tried=tried
        )

    def _try(
        self,
        sid,
        surf,
        url,
        ctx,
        retried=False,
        allow_mcp=True,
    ):
        if sid == "direct.fetch":
            return self._direct(url, ctx)
        if sid == "wayback.fetch":
            if allow_mcp and surf.routes.get("mcp"):
                return self._agent(sid, surf, url, ctx, retried, allow_mcp=True)
            return self._wayback(url, ctx)
        return self._agent(sid, surf, url, ctx, retried, allow_mcp=allow_mcp)

    def _body_text(self, url, resp, ctx):
        if "pdf" in resp.content_type.lower() or url.lower().split("?")[0].endswith(
            ".pdf"
        ):
            with tempfile.TemporaryDirectory(dir=ctx.work_file("pdf").parent) as tmp:
                path = Path(tmp) / "doc.pdf"
                path.write_bytes(resp.body)
                ocr_cmd = registry.surfaces(ctx.reg)["ocr.read"].routes["cli"][0].split()
                proc = self._cmd([*ocr_cmd, str(path)])
                return pages_text(proc.stdout or "")[0] if proc.returncode == 0 else ""
        if "html" in resp.content_type.lower() or resp.body[
            :200
        ].lstrip().lower().startswith((b"<!doctype", b"<html")):
            return html_to_text(resp.body)
        return resp.body.decode("utf-8", errors="replace")

    def _direct(self, url, ctx):
        resp = self.http_get(url)
        if resp.error or resp.status == 0:
            self._log(ctx, "direct.fetch", "http", url, "error", "unknown")
            return FetchResult(False, error=resp.error or "no response")
        if resp.status >= 400:
            blocked = resp.status in BLOCKED_STATUS
            self._log(
                ctx,
                "direct.fetch",
                "http",
                url,
                "blocked" if blocked else "error",
                "blocked" if blocked else "unknown",
            )
            return FetchResult(False, error=f"HTTP {resp.status}")
        text = self._body_text(url, resp, ctx)
        if len(text.strip()) < self.min_chars:
            self._log(ctx, "direct.fetch", "http", url, "empty")
            return FetchResult(False, error="page has no readable text (script shell?)")
        self._log(ctx, "direct.fetch", "http", url, "ok", content=resp.body)
        return FetchResult(True, text, "direct.fetch")

    def _wayback(self, url, ctx, allow_mcp=True):
        meta = self.http_get(
            "https://archive.org/wayback/available?url=" + quote(url, safe="")
        )
        snap = None
        if meta.status == 200:
            try:
                snap = (
                    json.loads(meta.body.decode("utf-8")).get("archived_snapshots")
                    or {}
                ).get("closest")
            except ValueError:
                snap = None
        if not snap or not snap.get("available") or not snap.get("url"):
            self._log(ctx, "wayback.fetch", "http", url, "empty")
            return FetchResult(False, error="no archived snapshot")
        resp = self.http_get(snap["url"])
        text = self._body_text(url, resp, ctx) if resp.status == 200 else ""
        if len(text.strip()) < self.min_chars:
            self._log(
                ctx,
                "wayback.fetch",
                "http",
                url,
                "error" if resp.status != 200 else "empty",
            )
            return FetchResult(False, error="archived snapshot unreadable")
        self._log(ctx, "wayback.fetch", "http", url, "ok", content=resp.body)
        return FetchResult(True, text, "wayback.fetch")

    def _agent(self, sid, surf, url, ctx, retried, allow_mcp=True):
        routes = {
            kind: names
            for kind, names in surf.routes.items()
            if allow_mcp or kind != "mcp"
        }
        if not routes:
            return FetchResult(False, error="no non-MCP route on this surface")
        step = self._step_id(ctx, sid, url) + (".retry" if retried else "")
        # One drop file per URL, kept across a resume: the agent saves it before the run reads it.
        dest = ctx.drop_dir / f"{step}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        gen = (
            ctx.keys.generation(surf.pool) if surf.pool and ctx.keys is not None else 0
        )
        route_lines = "\n".join(
            f"- {kind}: "
            + ", ".join(
                registry.mcp_tool(surf.server, name) if kind == "mcp" else name
                for name in names
            )
            for kind, names in routes.items()
        )
        payload = (
            f"url: {url}\nsurface: {sid}\nroutes (try in this order; each later route is the fallback if an earlier one fails):\n"
            f"{route_lines}\nsave the page text to: {dest}\n"
        )
        try:
            data = agents.call(
                ctx.runner,
                "discovery",
                "fetch",
                payload,
                step,
                required=("ok",),
            )
        except agents.Unanswerable as exc:
            dest.unlink(missing_ok=True)
            self._log(ctx, sid, next(iter(routes)), url, "error", "unknown")
            return FetchResult(False, error=f"fetch ask unanswerable: {exc.reason}")
        route = (
            data.get("route")
            if data.get("route") in routes
            else next(iter(routes))
        )
        if data.get("ok") and dest.exists():
            text = dest.read_text(encoding="utf-8", errors="replace")
            dest.unlink(missing_ok=True)
            # A usable agent fetch settles the URL however short the text is;
            # the next surface is only tried when the ask failed (ADR 0015).
            if text.strip():
                self._log(ctx, sid, route, url, "ok", content=text.encode("utf-8"))
                return FetchResult(True, text, sid)
            self._log(ctx, sid, route, url, "empty")
            return FetchResult(False, error="surface returned no readable text")
        dest.unlink(missing_ok=True)
        err = data.get("error") or {}
        status, code = err.get("status"), err.get("code")
        cls = registry.classify_error(ctx.reg, surf.server, status, code)
        self._log(
            ctx,
            sid,
            route,
            url,
            "blocked" if cls == "blocked" else "error",
            cls if cls != "unknown" else "unknown",
        )
        decision = (
            ctx.keys.on_failure(
                surf.server, status=status, code=code, url=url, seen_generation=gen
            )
            if ctx.keys is not None
            else keys.NEXT_SURFACE
        )
        if decision == keys.RETRY and not retried:
            return self._agent(sid, surf, url, ctx, True, allow_mcp=allow_mcp)
        if decision == keys.RATE_LIMITED:
            ctx.sleep(self.rate_limit_wait)
        return FetchResult(False, error=f"{status or '-'} {code or 'failed'}")
