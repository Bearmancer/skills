# Browser fill mechanics (RED and OPS)

Browse MCP recipe for the Gazelle form. Site references map fields; this maps the
browser. Everything here was learned from failures — each rule names its trap.

## Run order (the biggest loss was deferring the fill)

Research → payload JSON → **fill and read back immediately** → confirm → submit →
verify. Skill edits, retros, git and memory notes happen after the post, never
before. Do not ask about defaults, ratifying the skill, or anything else between
payload and fill.

## Payload JSON

`site` (`red`|`ops`), `type`, `artists[{name,role}]`, `title`, `recordlabel`,
`cataloguenumber`, `oclc` (RED) / `groupid` (OPS), `year`, `image`, `tags`,
`releasetype`, `formats[]`, `bitrates[]`, `media[]`, `needlog/needcue/needchecksum/
needcksum` (omit = unticked), `bounty{amount_box,unit,bytes}`, `description`.

One payload per site — derive the OPS one from the RED one: `site`, official-only
tags, bitrate map (Lossless is `8` on RED, `0` on OPS), rehosted `image`.

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

1. `Start-Process -WindowStyle Hidden uv run --no-project python scripts/serve_payload.py <payload.json> [port]`
   (default 8765, loopback, CORS `*`). A `background` shell wrapper dies on a
   connection abort and takes the listener with it — detach instead, verify with a
   local GET, kill the port when done.
2. Stash into the DOM from eval: `await fetch('http://127.0.0.1:8765/payload')` →
   hidden `<pre id="__payload">`. `fill_request.js` reads that node.
3. Never use synchronous XHR or a non-yielding loop on OPS: adding 100+ rows froze
   the tab past the 30 s eval limit ("tab is not responding" → reload it).

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

- OPS: redirect to `requests.php?action=view&id=<id>`.
- RED: `requests.php?type=created` lists the new row (title, bounty, "10 mins ago");
  anchors there did not match `a[href*="requests.php?id="]` — match by text.
- The user may submit RED themselves; verify the row either way.
