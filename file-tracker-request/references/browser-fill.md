# Browser fill mechanics (RED and OPS)

Browse MCP recipe for the Gazelle form. Site references map fields; this maps the
browser. Everything here was learned from failures — each rule names its trap.

## Run order (the biggest loss was deferring the fill)

Research → payload JSON → **fill and read back immediately** → confirm → submit →
verify. Skill edits, retros, git and memory notes happen after the post, never
before. Do not ask about defaults, ratifying the skill, or anything else between
payload and fill.

## Payload JSON

Built only by `scripts/build_payload.py` (spec keys in its docstring); `make_bundle.py`
refuses a payload without its `tag_list`. Shape: `site` (`red`|`ops`), `type`,
`artists[{name,role}]`, `title`, `recordlabel`, `cataloguenumber`, `year`, `image`,
`tags` (comma-joined string), `tag_list`, `releasetype`, `formats[]`, `bitrates[]`,
`media[]`, `bounty{amount_box,unit,bytes}`, `description`. Log/cue/checksum are omitted
(unticked). The builder emits both sites from one spec: bitrate map (Lossless `8` RED,
`0` OPS) and `image_ops` for the rehosted cover.

`fill_request.js` lints the payload again before touching the form (tag shape,
`classical` present, ≤ 200 chars, no numeric or empty artist names) and sets `#tags`
last, because the genre dropdown rewrites it. Its readback returns the full artist
list and the final tag string.

## Isolated world

`eval` runs in an isolated context: DOM shared, page globals invisible
(`typeof AddArtistField`/`Calculate` → `undefined`). OPS handlers are jQuery-bound,
never globals. Run form code in the main world by injecting a script element:

```js
const s = document.createElement('script');
s.textContent = fillCode;      // plain IIFE string
document.head.appendChild(s);
```

`scripts/fill_request.js` is that body (async, yields every ~10 rows, branches on
`payload.site`, writes its readback to hidden `<pre id="__fill_result">`). The node
is `display:none`: `wait_for` on it times out; poll with eval instead:

```js
for (let i = 0; i < 80; i++) {
  r = await tools.browse.eval({tab, expression:
    `(async()=>{await new Promise(r=>setTimeout(r,500));const n=document.getElementById('__fill_result');return n?n.textContent:null})()`});
  if (r) break;
}
```

## Payload transport

1. `Start-Process -WindowStyle Hidden uv run scripts/serve_payload.py <payload.json> [port]`
   (default 8765, loopback, CORS `*`). A `background` shell wrapper dies on a
   connection abort and takes the listener with it — detach instead, verify with a
   local GET, kill the port when done.
2. Stash into the DOM from eval: `await fetch('http://127.0.0.1:8765/payload')` →
   hidden `<pre id="__payload">`. `fill_request.js` reads that node.
3. Never use synchronous XHR or a non-yielding loop on OPS: adding 100+ rows froze
   the tab past the 30 s eval limit ("tab is not responding" → reload it).

## One-call stage (tested live on both sites, 58-artist box)

`make_bundle.py payload.json bundle.json` → serve the bundle on its own port (one
server per site) → one `execute` per site:

```js
const t = await tools.browse.tabs({action:"new", url, keepVisible:true, group:"req"});
await tools.browse.wait_for({tab:t.tab, selector:"form#request_form #categories", timeout:25000});
await tools.browse.eval({tab:t.tab, expression:`(async()=>{
  const b = await (await fetch('http://127.0.0.1:${port}/payload')).json();
  const n = document.createElement('pre'); n.id='__payload'; n.style.display='none';
  n.textContent = JSON.stringify(b.payload); document.body.appendChild(n);
  const s = document.createElement('script'); s.textContent = b.code; document.head.appendChild(s);
})()`});
// poll #__fill_result as above; require ok:true, then confirm, then click #button
```

Keep the tab open between fill and submit (assert rows/amount/title again before the
click). Write helper scripts with `pathlib` — raw `open()` is blocked by the host's
python-pathlib-guard. Run every script as `uv run <file.py> <args>` with a PEP 723
header; the host's uv-run-script guard refuses the `uv run … python <file.py>` form.

## Browse API traps

- `eval` JSON-encodes its return: returning a `JSON.stringify` string comes back
  double-encoded (`'"none"'`) — return objects, never pre-stringified text.
- `navigate`/`fetch` with a null or quoted URL fail as `https://null` /
  `https://"https://…"`: assert the URL is a plain string first.
- Tabs auto-close after `idleMinutes` (default 10; set to `never` via
  `browse.settings({set:{idleMinutes:"never"}})`). A stored tab id can still be
  gone next turn — do open + stash + fill + readback in one `execute`; the fill is
  idempotent on a fresh form.
- Code Mode source is parsed as JS: regex literals with `/` inside template strings
  broke parsing — build selectors/URLs with plain strings.
- `browse.upload({tab, selector, files})` fills `input[type=file]` on any page.

## Site switches

| Concern | RED | OPS |
| --- | --- | --- |
| Add artist row | `AddArtistField()` (global) | `artist_add()` if defined, else click `#artist-add` |
| Bounty recompute | `Calculate()` on `change` | jQuery on `input` — fire native `input` on `#amount_box` and `#unit`; no global |
| Narrowing | uncheck "All" masters, check chosen subs | everything starts checked; set every sub to wanted state, fire `change` |
| Checksum box | `#needchecksum` | `#needcksum` |
| Min log score | text input | range; fire `input` + `change` |
| Extra field | `oclc` | `groupid` (empty for a new group) |
| Tags | free tags | official `#genre_tags` values only |
| Image | any HTTPS | Discogs URLs rejected server-side → rehost |

Fire `change` (bubbles) after every programmatic change. Set formats and media
before log/cue — on OPS the row vanishes unless FLAC **and** CD are checked. Log,
cue, checksum stay unticked.

## Image rehost (OPS; RED has built-in Rehost/Upload buttons)

1. Download the cover: `Invoke-WebRequest -Uri <url> -OutFile <tmp>.jpeg`.
2. New tab `https://postimages.org` → `browse.upload({tab, selector:"input[type='file']", files:<tmp>})`.
3. Read the `#direct` input value (`https://i.postimg.cc/…`) from the result page.
4. Verify 200 + `image/jpeg`, put it in the payload `image`, restart the payload
   server. A POST rejected for the image returns the form with values preserved:
   patch `input[name=image]` and resubmit instead of refilling.

## Completion criterion

The readback reports `ok:true`: zero `errs`, artist rows and role counts equal the
payload, `#amount` equals `bounty.bytes`, button enabled, formats/bitrates/media
exactly the payload's. A returned click or silent eval is not evidence.

## Verify after submit

- Inject the bundle's `verify` code on the view page (DOM only, isolated world is
  fine) and read `#__verify_result`: `ok:true` needs every payload tag and artist to
  appear as a rendered **link**, no extra tags, no numeric artist link, and the
  catalogue number on the page. Matching names against page text is not evidence —
  the description repeats them, which is how 11 rows named "1" passed on 2026-11-24.
- OPS: redirect to `requests.php?action=view&id=<id>`.
- RED: success redirects to `requests.php?action=view&id=<id>`; confirm the bounty on
  `requests.php?type=created` (title, bounty, age) — the view page's "Bounty: 0.00 MB"
  text belongs to the vote form, not the total.
- The user may submit RED themselves; verify the row either way.
