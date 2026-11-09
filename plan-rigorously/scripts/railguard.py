#!/usr/bin/env python3
"""railguard - gate and ledger engine for the plan-rigorously skill.

Python 3 standard library only. Five verbs:
  start   <slug> [--rebaseline]  create .rigor/, state, working-tree snapshot, codegraph init+sync
  check   <plan.yaml>            run every gate; --final requires all gates passed or skipped
  check   --pack                 self-check the skill pack (rules, gates, merge ledger)
  log     "<reason>" --kind K    append a hash-chained ledger event (and update state)
  render  <plan.yaml>            write markdown view from the YAML and record its hash
  publish <plan.yaml> [--yes]    GitHub issues through the gh CLI (dry run unless --yes)

On Windows use `python railguard.py ...`.
Exit codes: 0 ok, 1 gate failure, 2 refused (e.g. existing incomplete plan), 3 needs user decision.
"""
import argparse, datetime, glob, hashlib, json, math, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
REF = os.path.join(PACK, "references")
_LIM = None


def lim(path):
    """Read a number from references/limits.yaml, e.g. lim('planning.task.files')."""
    global _LIM
    if _LIM is None:
        _LIM = load(os.path.join(REF, "limits.yaml"))
    v = _LIM
    for k in path.split("."):
        v = v[k]
    return _bound(v)


_BOUNDS = ("exact", "min", "max")
UNITS = ("hours", "minutes", "seconds", "characters", "lines", "files", "share", "times")


def _bound(v):
    """A bound map {max: 3} or {max: 240, unit: minutes} reads as its number; {min:, max:} reads as both."""
    if isinstance(v, dict) and v and set(v) <= set(_BOUNDS) | {"unit"} and set(v) & set(_BOUNDS):
        ks = [k for k in _BOUNDS if k in v]
        return v[ks[0]] if len(ks) == 1 else {k: v[k] for k in ks}
    return v


# ------------------------------------------------------------------ YAML subset
def _strip_comment(s):
    out, q, i = [], None, 0
    while i < len(s):
        c = s[i]
        if q:
            out.append(c)
            if c == "\\" and q == '"' and i + 1 < len(s):
                out.append(s[i + 1]); i += 1
            elif c == q:
                q = None
        elif c in "\"'" and (i == 0 or s[i - 1] in " \t[{,:-"):
            q = c; out.append(c)
        elif c == "#" and (i == 0 or s[i - 1] in " \t"):
            break
        else:
            out.append(c)
        i += 1
    return "".join(out).rstrip()


def _scalar(t):
    t = t.strip()
    if t == "":
        return None
    if t[0] == '"':
        return json.loads(t)
    if t[0] == "'":
        return t[1:-1].replace("''", "'")
    if t[0] in "[{":
        return _flow(t, 0)[0]
    low = t.lower()
    if low in ("null", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    return t


def _flow_atom(s, i, stop):
    while s[i] == " ":
        i += 1
    if s[i] == '"':
        j = i + 1
        while s[j] != '"':
            j += 2 if s[j] == "\\" else 1
        return json.loads(s[i:j + 1]), j + 1
    if s[i] == "'":
        j = s.index("'", i + 1)
        return s[i + 1:j], j + 1
    j = i
    while j < len(s) and s[j] not in stop:
        j += 1
    tok = s[i:j].strip()
    return (tok if stop == ":" else _scalar(tok)), j


def _flow(s, i):
    while s[i] == " ":
        i += 1
    if s[i] == "[":
        i += 1
        out = []
        while True:
            while s[i] in " ,":
                i += 1
            if s[i] == "]":
                return out, i + 1
            v, i = _flow(s, i)
            out.append(v)
    if s[i] == "{":
        i += 1
        out = {}
        while True:
            while s[i] in " ,":
                i += 1
            if s[i] == "}":
                return out, i + 1
            k, i = _flow_atom(s, i, ":")
            while s[i] == " ":
                i += 1
            if s[i] != ":":
                raise ValueError("flow map key without colon: " + s)
            i += 1
            v, i = _flow(s, i)
            out[k] = v
    return _flow_atom(s, i, ",]}")


_KEY = re.compile(r'^(?:"[^"]*"|\'[^\']*\'|[^\s"\'\[\]{},#&*!|>%@`-][^:]*?|-[^\s:][^:]*?):(?:\s|$)')


def _is_key(rest):
    return bool(_KEY.match(rest))


def _split_kv(s):
    if s[0] in "\"'":
        q = s[0]
        j = s.index(q, 1)
        k = s[1:j] if q == "'" else json.loads(s[:j + 1])
        rest = s[j + 1:].lstrip()
        assert rest.startswith(":"), s
        return k, rest[1:].strip()
    m = re.match(r"^(.*?):(?:\s+(.*))?$", s)
    return m.group(1).strip(), (m.group(2) or "").strip()


def parse_yaml(text):
    lines = []
    for ln in text.splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        body = _strip_comment(ln)
        if not body.strip():
            continue
        lines.append([len(body) - len(body.lstrip(" ")), body.strip()])
    pos = [0]

    def is_item(t):
        return t.startswith("- ") or t == "-"

    def block(ind):
        return seq(ind) if is_item(lines[pos[0]][1]) else mp(ind)

    def seq(ind):
        out = []
        while pos[0] < len(lines) and lines[pos[0]][0] == ind and is_item(lines[pos[0]][1]):
            l = lines[pos[0]]
            rest = l[1][1:].lstrip(" ")
            off = ind + (len(l[1]) - len(rest))
            if rest == "":
                pos[0] += 1
                if pos[0] < len(lines) and lines[pos[0]][0] > ind:
                    out.append(block(lines[pos[0]][0]))
                else:
                    out.append(None)
            elif _is_key(rest):
                lines[pos[0]] = [off, rest]
                out.append(mp(off))
            else:
                out.append(_scalar(rest))
                pos[0] += 1
        return out

    def mp(ind):
        out = {}
        while pos[0] < len(lines) and lines[pos[0]][0] == ind and not is_item(lines[pos[0]][1]):
            k, v = _split_kv(lines[pos[0]][1])
            pos[0] += 1
            if v == "":
                nxt = lines[pos[0]] if pos[0] < len(lines) else None
                if nxt and (nxt[0] > ind or (nxt[0] == ind and is_item(nxt[1]))):
                    out[k] = block(nxt[0])
                else:
                    out[k] = None
            else:
                out[k] = _scalar(v)
        return out

    if not lines:
        return None
    result = block(lines[0][0])
    if pos[0] < len(lines):
        raise ValueError("unparsed content at: " + lines[pos[0]][1][:60])
    return result


_PLAIN = re.compile(r"^[A-Za-z0-9_./@][A-Za-z0-9_ ./@()+=,-]*$")


def _s(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return str(v)
    t = str(v)
    if (_PLAIN.match(t) and t.lower() not in ("null", "true", "false", "~") and not t.endswith(" ")
            and not re.fullmatch(r"-?\d+(\.\d+)?", t) and ", " not in t and not t.startswith("- ")):
        return t
    return json.dumps(t, ensure_ascii=False)


def dump_lines(o, ind=0):
    pad, out = " " * ind, []
    if isinstance(o, dict):
        if not o:
            return [pad + "{}"]
        for k, v in o.items():
            ks = _s(k)
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{ks}:")
                out += dump_lines(v, ind + 2)
            elif isinstance(v, dict):
                out.append(f"{pad}{ks}: {{}}")
            elif isinstance(v, list):
                out.append(f"{pad}{ks}: []")
            else:
                out.append(f"{pad}{ks}: {_s(v)}")
    elif isinstance(o, list):
        if not o:
            return [pad + "[]"]
        for v in o:
            if isinstance(v, dict) and v:
                sub = dump_lines(v, ind + 2)
                sub[0] = pad + "- " + sub[0].lstrip()
                out += sub
            elif isinstance(v, list) and v:
                out.append(pad + "-")
                out += dump_lines(v, ind + 2)
            elif isinstance(v, dict):
                out.append(pad + "- {}")
            elif isinstance(v, list):
                out.append(pad + "- []")
            else:
                out.append(f"{pad}- {_s(v)}")
    return out


def dump_yaml(o):
    return "\n".join(dump_lines(o)) + "\n"


def load(path):
    with open(path, encoding="utf-8") as f:
        return parse_yaml(f.read())


def save(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(dump_yaml(obj))
    os.replace(tmp, path)  # atomic: a reader never sees half a file


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def sha_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ paths, state, ledger
class Ctx:
    pass


def rig(root):
    return os.path.join(root, ".rigor")


def state_path(root):
    return os.path.join(rig(root), "state.yaml")


def ledger_path(root):
    return os.path.join(rig(root), "ledger.yaml")


def load_state(root):
    p = state_path(root)
    return load(p) if os.path.exists(p) else {}


def load_ledger(root):
    p = ledger_path(root)
    if not os.path.exists(p):
        return []
    d = load(p)
    return (d or {}).get("events") or []


EVENT_KINDS = ["decision", "question", "answer", "plan_change", "review_finding", "review_complete",
               "gate", "skip", "deviation", "tool_run", "note", "publish", "round"]
NEEDS_REASON = {"plan_change", "skip", "deviation", "review_finding", "decision"}
AUTH_RE = re.compile(r"^(user|system|proposal|rule:[\w.-]+|finding:[\w.-]+)$")
CONFIRM_SUBJECTS = ("intent_confirmed", "clarify_destination_signed", "clarify_chart_signed", "execute_authorized")
EXPLICIT_RE = re.compile(r"^(yes|no)\b", re.I)
HEDGE_RE = re.compile(r"\b(but|maybe|perhaps|not sure|unsure|if|unless|however|though|depends)\b", re.I)


def explicit_answer(text):
    """'yes' or 'no' as the first word with no hedge. Returns 'yes', 'no' or None."""
    t = (text or "").strip()
    m = EXPLICIT_RE.match(t)
    if not m or HEDGE_RE.search(t):
        return None
    return m.group(1).lower()


def _event_hash(ev):
    return sha({k: v for k, v in ev.items() if k != "hash"})


_LOCK_DEPTH = {}


class ledger_lock:
    """Re-entrant exclusive lock on .rigor/ledger.lock so parallel writers never lose events."""
    def __init__(self, root):
        self.path = os.path.join(rig(root), "ledger.lock")
        self.root = root

    def __enter__(self):
        d = _LOCK_DEPTH.get(self.path, 0)
        _LOCK_DEPTH[self.path] = d + 1
        if d == 0:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.f = open(self.path, "a+")
            try:
                import fcntl
                fcntl.flock(self.f, fcntl.LOCK_EX)
            except ImportError:
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_LOCK, 1)
        return self

    def __exit__(self, *e):
        _LOCK_DEPTH[self.path] -= 1
        if _LOCK_DEPTH[self.path] == 0:
            self.f.close()


def head_path(root):
    return os.path.join(rig(root), "ledger.head")


def ledger_add(root, kind, subject="", reason="", authority="system", before=None, after=None, extra=None):
    with ledger_lock(root):
        return _ledger_add(root, kind, subject, reason, authority, before, after, extra)


def _ledger_add(root, kind, subject, reason, authority, before, after, extra):
    events = load_ledger(root)
    ev = {"n": len(events) + 1, "ts": now(), "kind": kind, "subject": subject, "reason": reason,
          "authority": authority, "before": before, "after": after,
          "prev": events[-1]["hash"] if events else "genesis"}
    if extra:
        ev["extra"] = extra
    ev["hash"] = _event_hash(ev)
    events.append(ev)
    save(ledger_path(root), {"events": events})
    save(head_path(root), {"n": ev["n"], "hash": ev["hash"]})  # truncation of the ledger no longer verifies
    return ev


def verify_chain(events):
    prev = "genesis"
    for e in events:
        if e.get("prev") != prev or e.get("hash") != _event_hash(e):
            return False, f"chain broken at event {e.get('n')}"
        prev = e["hash"]
    return True, ""


# ------------------------------------------------------------------ plan helpers
def sid(x):
    return str(x)


def all_tasks(plan):
    out = []
    for ph in (plan.get("phases") or []):
        for t in (ph.get("tasks") or []):
            out.append((ph, t))
    return out


def plan_hash(plan):
    p = json.loads(json.dumps(plan))
    (p.get("meta") or {}).pop("status", None)
    (p.get("meta") or {}).pop("updated", None)
    return sha(p)


def task_hash(t):
    return sha(t)


SIZE_DUR = {k: v["duration"]["max"] for k, v in lim("planning.task_size").items()}


def cpm(plan):
    """Critical path method over task dependencies. Returns (rows, order_error)."""
    tasks = {sid(t["id"]): t for _, t in all_tasks(plan) if isinstance(t, dict) and "id" in t}
    dur = {i: SIZE_DUR.get(t.get("size"), 1) for i, t in tasks.items()}
    deps = {i: [sid(d) for d in (t.get("depends") or []) if sid(d) in tasks] for i, t in tasks.items()}
    order, seen, tmp = [], set(), set()
    cyc = [False]

    def visit(n):
        if n in seen:
            return
        if n in tmp:
            cyc[0] = True
            return
        tmp.add(n)
        for d in deps[n]:
            visit(d)
        tmp.discard(n)
        seen.add(n)
        order.append(n)

    for n in tasks:
        visit(n)
    if cyc[0]:
        return [], "cycle"
    es, ef = {}, {}
    for n in order:
        es[n] = max([ef[d] for d in deps[n]], default=0)
        ef[n] = es[n] + dur[n]
    end = max(ef.values(), default=0)
    succ = {n: [] for n in tasks}
    for n in tasks:
        for d in deps[n]:
            succ[d].append(n)
    lf, ls = {}, {}
    for n in reversed(order):
        lf[n] = min([ls[s] for s in succ[n]], default=end)
        ls[n] = lf[n] - dur[n]
    rows = [{"id": n, "dur": dur[n], "es": es[n], "ef": ef[n], "ls": ls[n], "lf": lf[n],
             "slack": round(ls[n] - es[n], 6), "critical": abs(ls[n] - es[n]) < 1e-9} for n in order]
    rows.sort(key=lambda r: (r["es"], 0 if r["critical"] else 1, r["id"]))
    return rows, None


def waves(rows):
    w = {}
    for r in rows:
        w.setdefault(r["es"], []).append(r["id"])
    return [w[k] for k in sorted(w)]


def spec_path_of(plan, plan_file):
    sp = (plan.get("meta") or {}).get("spec")
    if not sp:
        return None
    return sp if os.path.isabs(sp) else os.path.join(os.path.dirname(os.path.abspath(plan_file)), sp)


def strings_in(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings_in(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings_in(v)


# ------------------------------------------------------------------ rules
RULES = {}


def rule(name):
    def deco(fn):
        RULES[name] = fn
        return fn
    return deco


def E(msg):
    return ("error", msg)


def W(msg):
    return ("warn", msg)


def _tier(plan):
    try:
        return int((plan.get("meta") or {}).get("tier", 1))
    except (TypeError, ValueError):
        return 1


def planner_topology(plan):
    """Who plans: inline, or one planner subagent, by task and surface counts (planning.delegation)."""
    tasks = all_tasks(plan)
    n, sf = len(tasks), len({s for _, t in tasks for s in (t.get("surfaces") or [])})
    if n >= lim("planning.delegation.subagent.tasks") or sf >= lim("planning.delegation.subagent.surfaces"):
        return "subagent"
    return "inline" if n <= lim("planning.delegation.inline.tasks") and sf <= lim("planning.delegation.inline.surfaces") else "subagent"


def tier_floor(plan, pack=None):
    """Lowest tier the plan may claim: risk signals mean 2; more tasks or surfaces than tier 0 allows mean 1."""
    pack = pack or load_pack()
    if set(plan.get("risk_signals") or []) & set(pack["tiers"].get("risk_signals") or []):
        return 2
    tasks = all_tasks(plan)
    surfaces = {s for _, t in tasks for s in (t.get("surfaces") or [])}
    if len(tasks) > lim("planning.tier.t0.tasks") or len(surfaces) > lim("planning.tier.t0.surfaces"):
        return 1
    return 0


@rule("R_tier_floor")
def r_tier_floor(c):
    fl = tier_floor(c.plan, c.pack)
    return [E(f"meta.tier {_tier(c.plan)} is below the floor {fl} derived from risk signals and size")] if _tier(c.plan) < fl else []


@rule("R_meta")
def r_meta(c):
    m, out = c.plan.get("meta") or {}, []
    for k in ("slug", "status", "tier", "type", "spec"):
        if m.get(k) in (None, ""):
            out.append(E(f"meta.{k} missing"))
    if str(m.get("tier")) not in ("0", "1", "2"):
        out.append(E("meta.tier must be 0, 1 or 2"))
    if m.get("type") not in ("implementation", "design", "debug", "rollout", "eval", "pr-split"):
        out.append(E("meta.type must be implementation, design, debug, rollout, eval or pr-split"))
    return out


@rule("R_requirements_present")
def r_req(c):
    if c.spec is None:
        return [E("spec file not found (plan.meta.spec)")]
    out = []
    for k in ("problem", "solution", "success_criteria"):
        if not c.spec.get(k):
            out.append(E(f"spec.{k} missing"))
    if (c.spec.get("meta") or {}).get("slug") != (c.plan.get("meta") or {}).get("slug"):
        out.append(E("spec slug differs from plan slug"))
    return out


_URL = re.compile(r"https?://\S+")
_PATH = re.compile(r"(?<![\w:/.-])(?:\.{0,2}/)?(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,6}\b|[A-Za-z]:\\[\w\\.-]+")


@rule("R_requirements_clean")
def r_clean(c):
    if c.spec is None:
        return []
    spec = {k: v for k, v in c.spec.items() if k != "prototype_snippets"}
    out = []
    for s in strings_in(spec):
        if "```" in s:
            out.append(E("code fence in spec: " + s[:40]))
        t = _URL.sub("", s)
        for m in _PATH.finditer(t):
            if is_doc_path(m.group(0)):
                continue  # docs the spec asks execution to write (ADR, business facts, glossary)
            out.append(E("file path in spec (use an anchor): " + m.group(0)))
    return out


STORY = re.compile(r"^as an? .+,? i want .+,? so that .+", re.I)


@rule("R_user_stories")
def r_stories(c):
    need = lim("planning.user_stories.tier_%d" % c.tier)
    st = (c.spec or {}).get("user_stories") or []
    out = []
    if len(st) < need:
        out.append(E(f"{len(st)} user stories, tier {c.tier} needs {need}"))
    for s in st:
        if not STORY.match(str(s)):
            out.append(E("story not in As a X, I want Y, so that Z form: " + str(s)[:50]))
    return out


@rule("R_seams")
def r_seams(c):
    seams = (c.spec or {}).get("test_seams") or []
    out = []
    if not seams:
        out.append(E("no test seams"))
    for s in seams:
        if not s.get("confirmed"):
            out.append(E(f"seam {s.get('id')} not confirmed by the user"))
    if len(seams) > lim("planning.test_seams"):
        out.append(W(f"more than {lim('planning.test_seams')} seams; the ideal number is one"))
    return out


@rule("R_ideal_gaps")
def r_ideal(c):
    out = []
    ideal, gaps = c.plan.get("ideal_state") or [], c.plan.get("gaps")
    if not ideal:
        out.append(E("ideal_state empty"))
    for r in ideal:
        for k in ("id", "party", "property", "reason"):
            if not r.get(k):
                out.append(E(f"ideal_state row missing {k}"))
    if not gaps and not (c.plan.get("meta") or {}).get("no_gaps_reason"):
        out.append(E("gaps empty without meta.no_gaps_reason"))
    for g in gaps or []:
        for k in ("id", "text", "reason"):
            if not g.get(k):
                out.append(E(f"gap {g.get('id')} missing {k}"))
    return out


@rule("R_scope_conservation")
def r_scope(c):
    out = []
    gaps = {sid(g["id"]) for g in (c.plan.get("gaps") or []) if "id" in g}
    tasks = {sid(t["id"]): t for _, t in all_tasks(c.plan) if "id" in t}
    covered = set()
    for i, t in tasks.items():
        cov = [sid(x) for x in (t.get("covers") or [])]
        for x in cov:
            if x not in gaps:
                out.append(E(f"task {i} covers unknown gap {x}"))
        covered |= set(cov)
        if not cov:
            en = [sid(x) for x in (t.get("enables") or [])]
            if not en:
                out.append(E(f"task {i} covers no gap and enables nothing"))
            for x in en:
                if x not in tasks:
                    out.append(E(f"task {i} enables unknown task {x}"))
    for g in sorted(gaps - covered):
        out.append(E(f"gap {g} has no task"))
    return out


SCOPE_WORDS = re.compile(r"\b(mvp|v[12]|phase\s*2|later|future work|deferred|stretch|nice to have|for now|next release|post[- ]launch|initial version|basic version|interim|follow[- ]up release)\b", re.I)


@rule("R_scope_words")
def r_words(c):
    out = []
    for ph in c.plan.get("phases") or []:
        for s in [ph.get("title", "")]:
            if SCOPE_WORDS.search(str(s)):
                out.append(E(f"reduced-scope wording in phase title: {s}"))
        for t in ph.get("tasks") or []:
            for s in [t.get("title", "")] + list(t.get("acceptance") or []):
                m = SCOPE_WORDS.search(str(s))
                if m:
                    out.append(E(f"task {t.get('id')}: reduced-scope word '{m.group(0)}'"))
    return out


@rule("R_task_fields")
def r_fields(c):
    out, seen = [], set()
    full = c.tier >= 1
    for ph, t in all_tasks(c.plan):
        i = sid(t.get("id"))
        if i in seen:
            out.append(E(f"duplicate task id {i}"))
        seen.add(i)
        need = ["id", "title", "acceptance", "verify"] + (["size", "depends", "files", "interfaces"] if full else [])
        for k in need:
            v = t.get(k)
            if v is None or v == "" or (k in ("acceptance", "verify") and not v):
                out.append(E(f"task {i}: missing {k}"))
        if full and t.get("size") not in ("XS", "S", "M", "L", "XL"):
            out.append(E(f"task {i}: size must be XS, S or M"))
        if full and isinstance(t.get("interfaces"), dict):
            for k in ("consumes", "produces"):
                if k not in t["interfaces"]:
                    out.append(E(f"task {i}: interfaces.{k} missing"))
    if not seen:
        out.append(E("plan has no tasks"))
    return out


@rule("R_task_size")
def r_size(c):
    return [E(f"task {t.get('id')}: size {t.get('size')} must be split") for _, t in all_tasks(c.plan)
            if t.get("size") in ("L", "XL")]


@rule("R_task_files")
def r_files(c):
    out = []
    for _, t in all_tasks(c.plan):
        fs = t.get("files") or []
        i = t.get("id")
        if len(fs) > lim("planning.task.files"):
            out.append(E(f"task {i}: {len(fs)} files, max {lim('planning.task.files')}"))
        size_cap = (lim("planning.task_size").get(str(t.get("size"))) or {}).get("files")
        if size_cap is not None and len(fs) > _bound(size_cap):
            out.append(E(f"task {i}: size {t.get('size')} allows {_bound(size_cap)} file(s), has {len(fs)}; resize the task or split it"))
        for f in fs:
            p = str(f.get("path", ""))
            if not p or os.path.isabs(p) or ".." in p.replace("\\", "/").split("/"):
                out.append(E(f"task {i}: bad path {p!r}"))
            if f.get("op") not in ("create", "modify"):
                out.append(E(f"task {i}: file op must be create or modify ({p})"))
            if not f.get("verified_at"):
                out.append(E(f"task {i}: {p} missing verified_at"))
    return out


@rule("R_task_split_hints")
def r_split(c):
    out = []
    for _, t in all_tasks(c.plan):
        i = t.get("id")
        if len(t.get("acceptance") or []) > lim("planning.task.acceptance_bullets"):
            out.append(W(f"task {i}: more than {lim('planning.task.acceptance_bullets')} acceptance bullets"))
        if re.search(r"\band\b", str(t.get("title", "")), re.I):
            out.append(W(f"task {i}: title contains 'and'"))
        sf = t.get("surfaces") or []
        if len(sf) > lim("planning.task.surfaces"):
            out.append(W(f"task {i}: spans {len(sf)} surfaces, max {lim('planning.task.surfaces')}; consider splitting"))
    return out


@rule("R_task_surfaces")
def r_surfaces(c):
    """Every task names the surfaces it touches; execution counts the distinct names to choose inline or subagent."""
    out = []
    for _, t in all_tasks(c.plan):
        sf = t.get("surfaces")
        if not isinstance(sf, list) or not sf or not all(isinstance(x, str) and x.strip() for x in sf):
            out.append(E(f"task {t.get('id')}: surfaces must be a non-empty list of names"))
    return out


@rule("R_verify_paths")
def r_verify(c):
    out = []
    for _, t in all_tasks(c.plan):
        i, vs = t.get("id"), t.get("verify") or []
        kinds = {v.get("kind") for v in vs if isinstance(v, dict)}
        acc = len(t.get("acceptance") or [])
        for v in vs:
            if not isinstance(v, dict) or not v.get("run") or not v.get("expect"):
                out.append(E(f"task {i}: verify entry needs run and expect"))
                continue
            for p in v.get("proves") or []:
                if not isinstance(p, int) or p < 0 or p >= acc:
                    out.append(E(f"task {i}: verify proves index {p} out of range"))
        if t.get("size") in ("S", "M") and not {"happy", "failure"} <= kinds:
            out.append(E(f"task {i}: needs a happy and a failure verify"))
    return out


VAGUE = re.compile(r"\b(tbd|todo|handle edge cases|add appropriate|as needed|figure out|somehow|write tests for the above)\b|\betc\.?(\s|$)", re.I)


@rule("R_decision_complete")
def r_vague(c):
    out = []
    for _, t in all_tasks(c.plan):
        for s in strings_in({k: t.get(k) for k in ("title", "acceptance", "verify")}):
            m = VAGUE.search(s)
            if m:
                out.append(E(f"task {t.get('id')}: vague wording '{m.group(0).strip()}'"))
    return out


@rule("R_interfaces")
def r_iface(c):
    tasks = {sid(t["id"]): t for _, t in all_tasks(c.plan) if "id" in t}
    ext = set(map(str, c.plan.get("external_interfaces") or []))
    out = []

    def anc(i, acc):
        for d in tasks[i].get("depends") or []:
            d = sid(d)
            if d in tasks and d not in acc:
                acc.add(d)
                anc(d, acc)
        return acc

    for i, t in tasks.items():
        cons = (t.get("interfaces") or {}).get("consumes") or []
        if not cons:
            continue
        produced = set()
        for a in anc(i, set()):
            produced |= set(map(str, (tasks[a].get("interfaces") or {}).get("produces") or []))
        for n in cons:
            if str(n) not in produced and str(n) not in ext:
                out.append(E(f"task {i} consumes '{n}' that no dependency produces"))
    return out


@rule("R_constraints")
def r_constraints(c):
    return [] if c.plan.get("constraints") else [E("plan.constraints empty")]


@rule("R_review_focus")
def r_focus(c):
    rf = c.plan.get("review_focus") or []
    ids = {sid(t["id"]) for _, t in all_tasks(c.plan) if "id" in t}
    out = []
    rfl = lim("planning.review_focus")
    if not rfl["min"] <= len(rf) <= rfl["max"]:
        out.append(E(f"review_focus has {len(rf)} entries, need {rfl['min']} to {rfl['max']}"))
    for r in rf:
        if not r.get("text") or not r.get("expected") or sid(r.get("task")) not in ids:
            out.append(E("review_focus entry needs text, expected and an existing task"))
    return out


@rule("R_proportion")
def r_prop(c):
    if c.spec is None:
        return []
    a = len(json.dumps(c.spec))
    b = len(json.dumps(c.plan.get("phases") or []))
    return [W(f"plan phases are {b / max(a, 1):.1f}x the spec size; replace bodies with signatures")] if b > lim("planning.plan_size.spec_factor") * a + lim("planning.plan_size.spec_slack") else []


@rule("R_must_not")
def r_mustnot(c):
    return [] if c.plan.get("must_not_have") else [E("must_not_have empty")]


@rule("R_quality_ratio")
def r_ratio(c):
    out = []
    ev = c.plan.get("evidence_ledger") or []
    if ev:
        ok = sum(1 for e in ev if e.get("source"))
        if ok / len(ev) < lim("planning.evidence_facts.with_source"):
            out.append(E(f"only {ok}/{len(ev)} evidence facts cite a source (need {lim('planning.evidence_facts.with_source'):.0%})"))
    tot = proved = 0
    for _, t in all_tasks(c.plan):
        n = len(t.get("acceptance") or [])
        tot += n
        p = set()
        for v in t.get("verify") or []:
            if isinstance(v, dict):
                p |= {x for x in (v.get("proves") or []) if isinstance(x, int) and 0 <= x < n}
        proved += len(p)
    if tot and proved / tot < lim("planning.acceptance_bullets.proved"):
        out.append(E(f"only {proved}/{tot} acceptance bullets proved by a verify entry (need {lim('planning.acceptance_bullets.proved'):.0%})"))
    return out


@rule("R_files_exist")
def r_exist(c):
    if not c.repo or not os.path.isdir(c.repo):
        return [W("repo not found: file existence check skipped")]
    out = []
    created = {f.get("path") for _, t in all_tasks(c.plan) for f in t.get("files") or [] if f.get("op") == "create"}
    for _, t in all_tasks(c.plan):
        for f in t.get("files") or []:
            p = os.path.join(c.repo, str(f.get("path", "")))
            if f.get("op") == "modify" and not os.path.exists(p) and f.get("path") not in created:
                out.append(E(f"task {t.get('id')}: modify target missing {f.get('path')}"))
            if f.get("op") == "create" and not is_doc_path(f.get("path", "")) and not os.path.isdir(os.path.dirname(p)):
                out.append(E(f"task {t.get('id')}: parent missing for {f.get('path')}"))
    return out


@rule("R_anchors")
def r_anchors(c):
    out = []
    declared = {sid(a.get("id")) for a in ((c.spec or {}).get("anchors") or [])}
    resolved = {sid(a.get("id")): a for a in (c.plan.get("resolved_anchors") or [])}
    for _, t in all_tasks(c.plan):
        for a in t.get("anchors") or []:
            a = sid(a)
            if a not in declared:
                out.append(E(f"task {t.get('id')}: anchor {a} not declared in spec"))
            r = resolved.get(a)
            if not r or not r.get("path") or not r.get("commit") or not r.get("verified_at"):
                out.append(E(f"anchor {a} unresolved (needs path, commit, verified_at)"))
            elif r.get("stale"):
                out.append(E(f"anchor {a} is stale: re-run codegraph sync and resolve again"))
    return out


@rule("R_deps_valid")
def r_deps(c):
    out = []
    phase_of = {}
    for pi, (ph, t) in enumerate(all_tasks(c.plan)):
        pass
    for pi, ph in enumerate(c.plan.get("phases") or []):
        for t in ph.get("tasks") or []:
            phase_of[sid(t.get("id"))] = pi
    for ph, t in all_tasks(c.plan):
        i = sid(t.get("id"))
        for d in t.get("depends") or []:
            d = sid(d)
            if d not in phase_of:
                out.append(E(f"task {i}: unknown dependency {d}"))
            elif d == i:
                out.append(E(f"task {i}: depends on itself"))
            elif phase_of[d] > phase_of[i]:
                out.append(E(f"task {i}: depends on later-phase task {d}"))
    _, err = cpm(c.plan)
    if err:
        out.append(E("dependency cycle"))
    return out


@rule("R_checkpoints")
def r_check(c):
    out = []
    for ph in c.plan.get("phases") or []:
        ts = [sid(t.get("id")) for t in ph.get("tasks") or []]
        cps = ph.get("checkpoints") or []
        if not ts:
            out.append(E(f"phase {ph.get('id')} has no tasks"))
            continue
        idx = []
        for cp in cps:
            if sid(cp.get("after_task")) not in ts:
                out.append(E(f"checkpoint {cp.get('id')} after unknown task"))
                continue
            if not cp.get("verify"):
                out.append(E(f"checkpoint {cp.get('id')} has no verify"))
            idx.append(ts.index(sid(cp["after_task"])))
        if not idx or max(idx) != len(ts) - 1:
            out.append(E(f"phase {ph.get('id')} must end with a checkpoint"))
            continue
        prev = -1
        for k in sorted(idx):
            if k - prev > lim("planning.checkpoint.tasks_between"):
                out.append(E(f"phase {ph.get('id')}: more than {lim('planning.checkpoint.tasks_between')} tasks without a checkpoint"))
            prev = k
    return out


@rule("R_evidence_path")
def r_evpath(c):
    ep, out = c.plan.get("evidence_path") or {}, []
    ids = {sid(t["id"]) for _, t in all_tasks(c.plan) if "id" in t}
    if not ep.get("claims"):
        out.append(E("evidence_path.claims empty"))
    for cl in ep.get("claims") or []:
        if not cl.get("id") or not cl.get("text") or sid(cl.get("owner_task")) not in ids:
            out.append(E(f"claim {cl.get('id')}: needs id, text and an existing owner_task"))
    paths = ep.get("paths") or []
    if len(paths) < lim("planning.evidence_path.candidate_paths"):
        out.append(E(f"evidence_path needs at least {lim('planning.evidence_path.candidate_paths')} candidate paths"))
    if sum(1 for p in paths if p.get("chosen")) != 1:
        out.append(E("exactly one evidence path must be chosen"))
    if ep.get("test_strategy") not in ("tdd", "tests_after", "none"):
        out.append(E("test_strategy must be tdd, tests_after or none"))
    return out


@rule("R_evidence_budget")
def r_budget(c):
    cl = (c.plan.get("evidence_path") or {}).get("claims") or []
    ids = [sid(x.get("id")) for x in cl]
    return [E("claim ids are not unique")] if len(ids) != len(set(ids)) else []


@rule("R_affordance")
def r_aff(c):
    ids = {sid(t["id"]) for _, t in all_tasks(c.plan) if "id" in t}
    out = []
    for a in (c.plan.get("evidence_path") or {}).get("affordances") or []:
        if a.get("lifecycle") not in ("temporary", "durable") or sid(a.get("owner_task")) not in ids:
            out.append(E(f"affordance {a.get('name')}: needs lifecycle temporary|durable and an owner task"))
    return out


@rule("R_final_verification")
def r_final(c):
    fv = c.plan.get("final_verification") or []
    claims = {sid(x.get("id")) for x in (c.plan.get("evidence_path") or {}).get("claims") or []}
    out = []
    if not fv:
        out.append(E("final_verification empty"))
    done = set()
    for f in fv:
        v = f.get("verify") or {}
        if not f.get("id") or not f.get("text") or not v.get("run") or not v.get("expect"):
            out.append(E(f"final verification {f.get('id')}: needs id, text, verify.run, verify.expect"))
        done |= {sid(x) for x in f.get("proves_claims") or []}
    for x in sorted(claims - done):
        out.append(E(f"claim {x} not covered by any final_verification item"))
    return out


# ------------------------------------------------------------------ intent, fog, glossary, sediment, proposals, rounds
INTENT_FIELDS = ("outcome", "user", "why_now", "success", "constraint", "out_of_scope")


def _final_now(c):
    return bool(getattr(c, "final", False)) or (c.plan.get("meta") or {}).get("status") == "final"


def _sev_final(c):
    return E if _final_now(c) else W


def _last_event(c, kind=None, subject=None, authority=None):
    hit = None
    for e in c.ledger:
        if (kind is None or e.get("kind") == kind) and (subject is None or e.get("subject") == subject) and (authority is None or e.get("authority") == authority):
            hit = e
    return hit


def _plan_text(plan):
    out = []
    for _, t in all_tasks(plan):
        parts = [str(t.get("title", ""))] + [str(x) for x in t.get("acceptance") or []]
        parts += [str(f.get("path", "")) for f in t.get("files") or [] if isinstance(f, dict)]
        out.append((sid(t.get("id")), " ".join(parts)))
    return out


def _task_paths(plan):
    return [str(f.get("path", "")).replace("\\", "/") for _, t in all_tasks(plan) for f in t.get("files") or [] if isinstance(f, dict)]


def clarify_status(root):
    p = os.path.join(rig(root), "clarify", "clarify.yaml")
    return (load(p) or {}).get("status") if os.path.exists(p) else None


@rule("R_intent")
def r_intent(c):
    if c.spec is None:
        return []
    it = c.spec.get("intent") or {}
    out = [E(f"spec intent.{k} is empty") for k in INTENT_FIELDS if not str(it.get(k) or "").strip()]
    conf = _last_event(c, "answer", "intent_confirmed", "user")
    seeded = _last_event(c, "note", "clarify_closed")
    if not conf:
        out.append(_sev_final(c)("intent restate not confirmed: log the user's explicit yes (--kind answer --subject intent_confirmed --authority user)"))
    elif seeded and seeded["n"] > conf["n"]:
        out.append(_sev_final(c)("clarifying finished after the intent was confirmed; restate and confirm again"))
    elif not EXPLICIT_RE.match(str(conf.get("reason", "")).strip()) or str(conf.get("reason", "")).strip().lower().startswith("no"):
        out.append(_sev_final(c)("intent confirmation is not an explicit yes"))
    return out


@rule("R_fog")
def r_fog(c):
    if c.spec is None:
        return []
    nys = c.spec.get("not_yet_specified") or []
    if not isinstance(nys, list):
        return [E("spec not_yet_specified must be a list")]
    return [_sev_final(c)(f"not yet specified: {x}") for x in nys]


@rule("R_fog_test")
def r_fog_test(c):
    if c.spec is None:
        return []
    ft = c.spec.get("fog_test") or {}
    out = []
    for k in ("destination_one_sentence", "first_three_decisions"):
        if ft.get(k) not in (True, False):
            out.append(E(f"spec fog_test.{k} must be true or false"))
    if out:
        return out
    if not (ft["destination_one_sentence"] and ft["first_three_decisions"]):
        st = clarify_status(c.root)
        if st != "closed":
            out.append(E(f"fog test failed: finish clarifying first (clarify status: {st or 'not started'})"))
    return out


@rule("R_language")
def r_language(c):
    if c.spec is None:
        return []
    if not str((c.spec.get("meta") or {}).get("language") or "").strip():
        return [E("spec meta.language is not recorded: ask the user once in the front batch")]
    return []


@rule("R_out_of_scope")
def r_oos(c):
    out = []
    for o in (c.spec or {}).get("out_of_scope") or []:
        if not isinstance(o, dict):
            out.append(W(f"out_of_scope entry {o!r}: write it as id, text and terms so it can be checked"))
            continue
        oid = sid(o.get("id", "?"))
        terms = [str(t).lower() for t in o.get("terms") or []]
        if not o.get("text") or not terms:
            out.append(E(f"out_of_scope {oid}: needs text and terms"))
            continue
        if _last_event(c, "decision", f"scope_change:{oid}", "user"):
            continue
        for tid, txt in _plan_text(c.plan):
            hit = [t for t in terms if t in txt.lower()]
            if hit:
                out.append(E(f"task {tid} touches out-of-scope {oid} ({hit[0]}): ask the user, then log decision scope_change:{oid}"))
    return out


@rule("R_glossary_terms")
def r_gloss(c):
    g = (c.spec or {}).get("glossary") or {}
    out = []
    texts = [(f"task {i}", t) for i, t in _plan_text(c.plan)]
    for k in ("problem", "solution"):
        texts.append((f"spec {k}", str((c.spec or {}).get(k, ""))))
    for j, s_ in enumerate((c.spec or {}).get("user_stories") or []):
        texts.append((f"user story {j + 1}", str(s_)))
    for term, v in g.items():
        if isinstance(v, str):
            continue
        if not isinstance(v, dict) or not str(v.get("definition", "")).strip():
            out.append(E(f"glossary {term}: needs a definition"))
            continue
        for al in v.get("avoid") or []:
            pat = re.compile(r"\b" + re.escape(str(al)) + r"\b", re.I)
            for where, txt in texts:
                if pat.search(txt):
                    out.append(W(f"{where} uses '{al}'; the glossary prefers '{term}'"))
    return out


def _doc_draft(c, what, path, prefix):
    """Planning only plans the doc: a path and a plan task. Execution writes the file."""
    out = []
    path = str(path or "")
    if not path or not path.replace("\\", "/").startswith(prefix) or not is_doc_path(path):
        return [E(f"{what}: needs a file path under {prefix} (execution writes docs/, GLOSSARY.md, GLOSSARY-MAP.md)")]
    if path not in _task_paths(c.plan):
        out.append(E(f"{what}: no plan task writes {path}"))
    return out


@rule("R_adr_candidates")
def r_adr(c):
    out, cands = [], []
    for d in (c.spec or {}).get("decisions") or []:
        a = d.get("adr")
        if a is None:
            continue
        flags = [bool(a.get(k)) for k in ("hard_to_reverse", "surprising", "real_tradeoff")]
        if all(flags):
            cands.append(d.get("id"))
        elif any(flags):
            out.append(W(f"decision {d.get('id')}: an ADR needs all three tests; this one is not a candidate"))
    for d in (c.spec or {}).get("decisions") or []:
        a = d.get("adr")
        if a and all(bool(a.get(k)) for k in ("hard_to_reverse", "surprising", "real_tradeoff")):
            out += _doc_draft(c, f"decision {d.get('id')} ADR", a.get("file"), "docs/adr/")
    return out


@rule("R_business_facts")
def r_biz(c):
    facts = (c.spec or {}).get("business_facts") or []
    out = []
    for f in facts:
        out += _doc_draft(c, f"business fact {f.get('id')}", f.get("file"), "docs/business/")
    return out


@rule("R_glossary_promotion")
def r_gprom(c):
    if (c.spec or {}).get("promote_glossary") is True:
        return _doc_draft(c, "glossary promotion", "GLOSSARY.md", "GLOSSARY.md")
    return []


@rule("R_proposals_confirmed")
def r_props(c):
    out = []
    for e in c.ledger:
        if e.get("authority") == "proposal":
            ok = any(x["n"] > e["n"] and x.get("subject") == e.get("subject") and x.get("authority") == "user" and x.get("kind") in ("answer", "decision") and explicit_answer(x.get("reason")) == "yes" for x in c.ledger)
            if not ok:
                out.append(_sev_final(c)(f"event {e['n']} ({e.get('subject')}) is the agent's proposal and has no user confirmation"))
    return out


@rule("R_rounds")
def r_rounds_conv(c):
    rs = [e for e in c.ledger if e.get("kind") == "round"]
    n = lim("planning.question.stalled_rounds")
    tail = rs[-n:]
    if len(tail) < n:
        return []
    def resolved(e):
        m = re.search(r"resolved=(\d+)", str(e.get("reason", "")))
        return int(m.group(1)) if m else 0
    if any(resolved(e) for e in tail):
        return []
    back = _last_event(c, "answer", "step_back", "user")
    if back and back["n"] > tail[-1]["n"]:
        return []
    return [E(f"{n} question rounds in a row resolved nothing: stop, tell the user something foundational may be missing, and record their answer as --kind answer --subject step_back")]



CLARIFY_TYPES = ("research", "grilling")


def clarify_file(root):
    return os.path.join(rig(root), "clarify", "clarify.yaml")


def _signed(ledger, subject):
    e = None
    for x in ledger:
        if x.get("kind") == "answer" and x.get("subject") == subject and x.get("authority") == "user":
            e = x
    return bool(e and EXPLICIT_RE.match(str(e.get("reason", "")).strip()) and not str(e.get("reason", "")).strip().lower().startswith("no"))


@rule("R_clarify")
def r_clarify(c):
    p = clarify_file(c.root)
    if not os.path.exists(p):
        return []
    d = load(p) or {}
    out = []
    if d.get("status") not in ("charting", "open", "closed", "parked"):
        return [E("clarify status must be charting, open, closed or parked")]
    tickets = d.get("tickets") or []
    ids = [sid(t.get("id")) for t in tickets]
    if len(ids) != len(set(ids)):
        out.append(E("clarify: duplicate ticket ids"))
    if tickets and not _signed(c.ledger, "clarify_destination_signed"):
        out.append(E("clarify: tickets exist but the destination has no explicit user yes (clarify_destination_signed)"))
    if d.get("status") in ("open", "closed") and not _signed(c.ledger, "clarify_chart_signed"):
        out.append(E("clarify: chart has no explicit user yes (clarify_chart_signed)"))
    for t in tickets:
        i = sid(t.get("id"))
        if t.get("type") not in CLARIFY_TYPES:
            out.append(E(f"clarify {i}: type must be research or grilling"))
        if not str(t.get("question") or "").strip():
            out.append(E(f"clarify {i}: no question"))
        for b in t.get("blocked_on") or []:
            if sid(b) not in ids:
                out.append(E(f"clarify {i}: blocked_on unknown ticket {b}"))
        if t.get("status") == "closed":
            r = t.get("resolution") or {}
            if not str(r.get("gist") or "").strip():
                out.append(E(f"clarify {i}: closed without a one-line gist"))
            if t.get("type") == "grilling" and not any(x.get("kind") == "answer" and x.get("subject") == i and x.get("authority") == "user" for x in c.ledger):
                out.append(E(f"clarify {i}: closed without a user answer in the ledger"))
            if t.get("type") == "research" and not (r.get("restated") and r.get("sources") and r.get("unverified")):
                out.append(E(f"clarify {i}: a research record needs the restated question, sources and an Unverified section"))
    if d.get("status") == "closed":
        if any(t.get("status") != "closed" for t in tickets) or d.get("not_yet_specified"):
            out.append(E("clarify closed with open tickets or unspecified items"))
    if d.get("status") == "parked":
        out.append(E("clarify parked by the user: the effort cannot be planned until it is reopened"))
    return out


def drift(root):
    """Read mirrored issues back and compare to what was published. Returns (level, messages)."""
    st = load_state(root)
    items = {}
    pub = (st.get("publish") or {})
    repo = pub.get("repo")
    pdir = os.path.join(rig(root), "published")
    if repo and not pub.get("dry_run") and os.path.isdir(pdir):
        for f in os.listdir(pdir):
            if f.endswith(".md"):
                items[f[:-3]] = open(os.path.join(pdir, f), encoding="utf-8").read()
    mp = os.path.join(rig(root), "clarify", "mirror.yaml")
    if os.path.exists(mp):
        m = load(mp) or {}
        repo = repo or m.get("repo")
        for k, v in (m.get("issues") or {}).items():
            items[str(v.get("number"))] = v.get("body", "")
    if not items or not repo:
        return "none", []
    if shutil.which("gh") is None:
        return "none", ["gh not found: issue drift not checked"]
    worst, msgs = 0.0, []
    for num, old in sorted(items.items()):
        rc, out = run_cmd(["gh", "api", f"repos/{repo}/issues/{num}"])
        if rc != 0:
            msgs.append(f"issue {num}: could not be read, so it may be deleted or changed ({out[-lim('planning.engine.ledger_output_tail'):]})")
            worst = max(worst, lim("planning.drift.ask"))  # unreadable counts as an ask, never as unchanged
            continue
        try:
            new = json.loads(out).get("body") or ""
        except ValueError:
            msgs.append(f"issue {num}: unreadable reply from GitHub")
            worst = max(worst, lim("planning.drift.ask"))
            continue
        if new.strip() == old.strip():
            continue
        import difflib
        share = 1 - difflib.SequenceMatcher(None, old, new).ratio()
        worst = max(worst, share)
        msgs.append(f"issue {num} differs from what was published ({share:.0%} changed)")
    if not msgs or worst == 0:
        return "none", msgs
    level = "note" if worst <= lim("planning.drift.note_only") else "ask" if worst <= lim("planning.drift.ask") else "block"
    events = load_ledger(root)
    last = None
    for e in events:
        if e.get("kind") == "question" and e.get("subject") == "drift":
            last = e
    accepted = any(e.get("kind") == "decision" and e.get("subject") == "drift_accepted" and e.get("authority") == "user" and (last is None or e["n"] > last["n"]) for e in events)
    if level == "note":
        ledger_add(root, "note", "drift_noticed", "; ".join(msgs), "system")
    elif not accepted:
        ledger_add(root, "question", "drift", f"{level}: " + "; ".join(msgs), "system")
    return ("note" if level == "note" or accepted else level), msgs


@rule("R_questions")
def r_questions(c):
    out = []
    for q in c.plan.get("questions") or []:
        i = q.get("id")
        for k in ("id", "text", "why_not_discoverable", "status"):
            if not q.get(k):
                out.append(E(f"question {i}: missing {k}"))
        if q.get("blocking") not in (True, False):
            out.append(E(f"question {i}: blocking must be true or false"))
        ops = q.get("options") or []
        if len(ops) < lim("planning.question.options") or not any(isinstance(o, dict) and o.get("recommended") for o in ops):
            out.append(E(f"question {i}: needs 2+ options with one recommended"))
        if q.get("status") == "answered" and not q.get("answer"):
            out.append(E(f"question {i}: answered without answer"))
        if q.get("status") not in ("open", "answered"):
            out.append(E(f"question {i}: status must be open or answered"))
    return out


@rule("R_blocked")
def r_blocked(c):
    out = []
    qs = {sid(q.get("id")): q for q in c.plan.get("questions") or []}
    tasks = [t for _, t in all_tasks(c.plan)]
    blocked = 0
    for t in tasks:
        bo = [sid(x) for x in t.get("blocked_on") or []]
        for b in bo:
            if b not in qs:
                out.append(E(f"task {t.get('id')}: blocked_on unknown question {b}"))
            elif qs[b].get("status") == "answered":
                out.append(E(f"task {t.get('id')}: still blocked_on answered question {b}; replan it"))
        if bo:
            blocked += 1
    for q in qs.values():
        if q.get("status") == "open" and q.get("blocking") is True:
            out.append(E(f"blocking question {q.get('id')} is open: ask the user"))
    if tasks and blocked == len(tasks):
        out.append(E("every task is blocked: stop and ask"))
    opened = [q for q in qs.values() if q.get("status") == "open" and q.get("blocking") is False]
    if opened:
        out.append(W(f"{len(opened)} deferrable question(s) open: present the deferred block at the end"))
    return out


@rule("R_proposal_audit")
def r_audit(c):
    cfg = c.audit
    out = []
    ext_tools = set(cfg["tools"]) - set(cfg["internal_tools"])
    qs = {sid(q.get("id")): q for q in c.plan.get("questions") or []}
    for p in c.plan.get("proposals") or []:
        pid, a = p.get("id"), p.get("audit") or {}
        if p.get("kind") not in ("external", "internal"):
            out.append(E(f"proposal {pid}: kind must be external or internal"))
            continue
        if not a:
            out.append(E(f"proposal {pid}: not audited"))
            continue
        if a.get("auditor") != "subagent" or a.get("saw_planner_reasoning") is not False:
            out.append(E(f"proposal {pid}: audit must be by a subagent that did not see planner reasoning"))
        v = a.get("verdict")
        if v not in ("supported", "contradicted", "unverifiable"):
            out.append(E(f"proposal {pid}: verdict must be supported, contradicted or unverifiable"))
        if v == "unverifiable" and not any(pid in map(sid, q.get("blocks_proposals") or []) for q in qs.values()):
            out.append(E(f"proposal {pid}: unverifiable but no question lists it in blocks_proposals"))
        if v == "contradicted":
            out.append(E(f"proposal {pid}: contradicted; replace it and re-audit"))
        if v != "supported":
            continue
        ev = a.get("evidence") or []
        tools = set()
        primary = False
        for e in ev:
            t = e.get("tool")
            if t not in cfg["tools"]:
                out.append(E(f"proposal {pid}: unknown tool {t}"))
                continue
            f = os.path.join(rig(c.root), str(e.get("file", "")))
            need = 1 if p["kind"] == "internal" else lim("planning.audit.evidence")
            if not e.get("file") or not os.path.isfile(f) or os.path.getsize(f) < need:
                out.append(E(f"proposal {pid}: evidence file for {t} missing or under {need} bytes"))
                continue
            tools.add(t)
            primary = primary or bool(e.get("primary"))
        if p["kind"] == "external":
            if len(tools & ext_tools) < lim("planning.audit.external_tools"):
                out.append(E(f"proposal {pid}: needs {lim('planning.audit.external_tools')} different external tools, got {len(tools & ext_tools)}"))
            if not primary:
                out.append(E(f"proposal {pid}: no primary source"))
        elif not tools & set(cfg["internal_tools"]):
            out.append(E(f"proposal {pid}: internal claims need codegraph or code evidence"))
    status = {sid(p.get("id")): (p.get("audit") or {}).get("verdict") for p in c.plan.get("proposals") or []}
    for d in (c.spec or {}).get("decisions") or []:
        for pr in d.get("proposals") or []:
            if status.get(sid(pr)) != "supported":
                out.append(E(f"decision {d.get('id')} relies on unsupported proposal {pr}"))
    return out


@rule("R_tier2_sections")
def r_t2(c):
    t2, out = c.plan.get("tier2") or {}, []
    cs = t2.get("consensus_summary") or {}
    pr_min, pr_max = lim("planning.tier2.principles")["min"], lim("planning.tier2.principles")["max"]
    drivers, opts_min, scen = lim("planning.tier2.drivers"), lim("planning.tier2.options"), lim("planning.tier2.premortem_scenarios")
    if not pr_min <= len(cs.get("principles") or []) <= pr_max:
        out.append(E(f"consensus_summary.principles needs {pr_min} to {pr_max}"))
    if len(cs.get("drivers") or []) != drivers:
        out.append(E(f"consensus_summary.drivers needs exactly {drivers}"))
    if len(cs.get("options") or []) < opts_min and not cs.get("invalidation"):
        out.append(E(f"need {opts_min}+ options or an invalidation rationale"))
    pm = t2.get("premortem") or []
    if len(pm) != scen or any(not (x.get("scenario") and x.get("signal") and x.get("mitigation")) for x in pm):
        out.append(E(f"premortem needs {scen} scenarios, each with scenario, signal, mitigation"))
    tp = t2.get("test_plan") or {}
    for k in ("unit", "integration", "e2e", "observability"):
        if not tp.get(k):
            out.append(E(f"test_plan.{k} empty"))
    return out


def required_reviewers(plan, routing):
    risks = set(plan.get("risk_signals") or [])
    tier = _tier(plan)
    roles = []
    if tier >= 1:
        roles.append("critic")
    if tier == 2 or risks & {"interface_change", "module_boundary", "cross_cutting", "schema_change"}:
        roles.append("architect")
    if risks & {"schema_change", "data_migration", "destructive_or_irreversible"}:
        roles.append("data_lens")
    if "weak_verification" in risks:
        roles.append("verification_lens")
    return roles


def review_level(plan, state, routing):
    base = (state or {}).get("review_baseline")
    if not base:
        return "full", "no previous full review"
    rows, _ = cpm(plan)
    crit = {r["id"] for r in rows if r["critical"]} | set(map(str, base.get("critical") or []))
    cur = {sid(t["id"]): task_hash(t) for _, t in all_tasks(plan)}
    old = base.get("tasks") or {}
    changed = {i for i in set(cur) | set(old) if cur.get(i) != old.get(i)}
    if not changed and plan_hash(plan) == base.get("plan_hash"):
        return "none", "plan unchanged"
    if set(map(str, base.get("phases") or [])) != {sid(p.get("id")) for p in plan.get("phases") or []}:
        return "full", "phase added or removed"
    frac = len(changed) / max(len(cur), 1)
    th = {"lint_only": lim("planning.review.re_review.diff_only"), "targeted": lim("planning.review.re_review.touched_files")}
    if changed & crit:
        return "full", "critical-path task changed"
    if frac <= th["lint_only"]:
        return "lint_only", f"{len(changed)} task(s) changed"
    if frac <= th["targeted"]:
        return "targeted", f"{len(changed)} task(s) changed"
    return "full", f"{len(changed)} of {len(cur)} tasks changed"


@rule("R_reviews_done")
def r_reviews(c):
    status = (c.plan.get("meta") or {}).get("status")
    if status not in ("reviewed", "final") and not c.final:
        return [W("review pending (plan not yet marked reviewed)")]
    level, why = review_level(c.plan, c.state, c.routing)
    roles = required_reviewers(c.plan, c.routing)
    rv = (c.state or {}).get("reviews") or {}
    h = plan_hash(c.plan)
    out = []
    if level in ("none", "lint_only"):
        return []
    need = ["critic"] if level == "targeted" else roles
    for r in need:
        if (rv.get(r) or {}).get("plan_hash") != h:
            out.append(E(f"review level {level} ({why}): {r} has not approved the current plan hash"))
    return out


@rule("R_review_rounds")
def r_rounds(c):
    per = {}
    for e in c.ledger:
        if e.get("kind") == "review_complete":
            per.setdefault(e.get("subject"), set()).add(e.get("after"))
    mx = lim("planning.review.rounds_per_role")
    return [E(f"{r}: {len(h)} review rounds, max {mx}") for r, h in per.items() if len(h) > mx]


@rule("R_ledger_chain")
def r_chain(c):
    ok, why = verify_chain(c.ledger)
    out = [] if ok else [E(why)]
    hp = head_path(c.root)
    if os.path.exists(hp):
        h = load(hp) or {}
        last = c.ledger[-1] if c.ledger else {}
        if h.get("n") != last.get("n") or h.get("hash") != last.get("hash"):
            out.append(E(f"ledger head does not match ledger.head (events removed or replaced after #{h.get('n')})"))
    return out


@rule("R_ledger_reasons")
def r_lreasons(c):
    out = []
    for e in c.ledger:
        if e.get("kind") in NEEDS_REASON:
            if not e.get("reason"):
                out.append(E(f"event {e.get('n')} ({e.get('kind')}) has no reason"))
            if not AUTH_RE.match(str(e.get("authority", ""))):
                out.append(E(f"event {e.get('n')} has invalid authority {e.get('authority')!r}"))
    return out


def is_doc_path(p):
    p = str(p).replace("\\", "/").lstrip("./") if str(p).startswith("./") else str(p).replace("\\", "/")
    return p.startswith("docs/") or p in ("GLOSSARY.md", "GLOSSARY-MAP.md")


def snapshot(root):
    snap = {"kind": "walk"}
    if shutil.which("git") and os.path.isdir(os.path.join(root, ".git")):
        try:
            head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            por = subprocess.run(["git", "-C", root, "status", "--porcelain", "-uall"], capture_output=True, text=True).stdout.splitlines()
            por = sorted(l for l in por if ".rigor/" not in l and not l.endswith(".rigor"))
            diff = subprocess.run(["git", "-C", root, "diff", "HEAD", "--", ".", ":(exclude).rigor"], capture_output=True, text=True).stdout
            return {"kind": "git", "head": head, "porcelain": por, "diff_sha": sha_text(diff)}
        except Exception:
            pass
    files = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in (".git", ".rigor", "node_modules", "__pycache__")]
        for f in fn:
            p = os.path.join(dp, f)
            try:
                st = os.stat(p)
                files[os.path.relpath(p, root).replace("\\", "/")] = f"{st.st_size}:{st.st_mtime_ns}"
            except OSError:
                pass
            if len(files) > lim("planning.engine.snapshot_walk"):
                break
    snap["files_sha"] = sha(files)
    snap["files"] = files
    return snap


@rule("R_no_impl")
def r_noimpl(c):
    base = (c.state or {}).get("snapshot")
    if not base:
        return [E("no start snapshot: run railguard start")]
    cur = snapshot(c.root)
    if base.get("kind") != cur.get("kind"):
        return [W("snapshot kind changed; cannot compare")]
    out = []
    if cur["kind"] == "git":
        if base["head"] != cur["head"]:
            out.append(E("HEAD moved since start (a commit was made)"))
        add = set(cur["porcelain"]) - set(base["porcelain"])
        rem = set(base["porcelain"]) - set(cur["porcelain"])
        out += [E("changed outside .rigor: " + l) for l in sorted(add)]
        out += [E("reverted since start: " + l) for l in sorted(rem)]
        if base["diff_sha"] != cur["diff_sha"] and not add and not rem:
            out.append(E("tracked file content changed outside .rigor"))
    else:
        old = base.get("files") or {}
        for p in sorted(set(old) | set(cur["files"])):
            if old.get(p) != cur["files"].get(p):
                out.append(E("changed outside .rigor: " + p))
    return out


@rule("R_render_hash")
def r_render(c):
    rh = (c.state or {}).get("render_hash")
    status = (c.plan.get("meta") or {}).get("status")
    if not rh:
        return [E("not rendered: run railguard render")] if (status == "final" or c.final) else [W("not rendered yet")]
    md = render_md(c.plan, c.spec)
    return [] if sha_text(md) == rh else [E("rendered view is stale: run railguard render")]


@rule("R_published")
def r_pub(c):
    pub = (c.state or {}).get("publish")
    if pub and pub.get("parent") and not pub.get("dry_run"):
        return []
    g = ((c.state or {}).get("gates") or {}).get("G_publish") or {}
    return [] if g.get("status") == "skipped" else [W("not published to GitHub (run publish --yes, or skip with a reason)")]


# ------------------------------------------------------------------ render
def render_md(plan, spec):
    m = plan.get("meta") or {}
    L = []
    a = L.append
    a(f"# Plan: {m.get('slug')}")
    a("")
    a(f"status: {m.get('status')} | tier: {m.get('tier')} | type: {m.get('type')} | spec: {m.get('spec')}")
    a("")
    if spec:
        a("## Requirements")
        a(f"**Problem.** {spec.get('problem')}")
        a("")
        a(f"**Solution.** {spec.get('solution')}")
        a("")
        for k, t in (("success_criteria", "Success criteria"), ("user_stories", "User stories")):
            if spec.get(k):
                a(f"**{t}**")
                for i, s in enumerate(spec[k], 1):
                    a(f"{i}. {s}")
                a("")
        if spec.get("test_seams"):
            a("**Test seams:** " + "; ".join(f"{s.get('id')} {s.get('name')}" for s in spec["test_seams"]))
            a("")
        if spec.get("out_of_scope"):
            a("**Out of scope (user-authorized)**")
            for o in spec["out_of_scope"]:
                a(f"- {o.get('text')}")
            a("")
    if plan.get("ideal_state"):
        a("## Ideal state and gaps")
        a("| Party | Ideal property | Reason |")
        a("|---|---|---|")
        for r in plan["ideal_state"]:
            a(f"| {r.get('party')} | {r.get('property')} | {r.get('reason')} |")
        a("")
        a("| Gap | Description | Reason |")
        a("|---|---|---|")
        for g in plan.get("gaps") or []:
            a(f"| {g.get('id')} | {g.get('text')} | {g.get('reason')} |")
        a("")
    for k, t in (("constraints", "Global constraints"), ("definition_of_done", "Definition of done"), ("must_not_have", "Must not have")):
        if plan.get(k):
            a(f"## {t}")
            for x in plan[k]:
                a(f"- {x}")
            a("")
    if plan.get("proposals"):
        a("## Proposals and audit")
        a("| Id | Kind | Claim | Verdict | Tools |")
        a("|---|---|---|---|---|")
        for p in plan["proposals"]:
            au = p.get("audit") or {}
            tl = ", ".join(sorted({e.get("tool", "") for e in au.get("evidence") or []}))
            a(f"| {p.get('id')} | {p.get('kind')} | {p.get('claim')} | {au.get('verdict')} | {tl} |")
        a("")
    ep = plan.get("evidence_path")
    if ep:
        a("## Evidence path")
        a(f"Test strategy: {ep.get('test_strategy')}")
        for cl in ep.get("claims") or []:
            a(f"- Claim {cl.get('id')}: {cl.get('text')} (owner task {cl.get('owner_task')})")
        for p in ep.get("paths") or []:
            a(f"- Path {p.get('id')}{' (chosen)' if p.get('chosen') else ''}: {p.get('text')}; limits: {p.get('limits')}")
        for af in ep.get("affordances") or []:
            a(f"- Affordance {af.get('name')} ({af.get('lifecycle')}, task {af.get('owner_task')})")
        a("")
    rows, err = cpm(plan)
    rmap = {r["id"]: r for r in rows}
    a("## Phases")
    for ph in plan.get("phases") or []:
        a(f"### {ph.get('id')}: {ph.get('title')}")
        ts = sorted(ph.get("tasks") or [], key=lambda t: ((rmap.get(sid(t.get("id"))) or {}).get("es", 0), sid(t.get("id"))))
        cps = {sid(c.get("after_task")): c for c in ph.get("checkpoints") or []}
        for t in ph.get("tasks") or []:
            i = sid(t.get("id"))
            r = rmap.get(i, {})
            a(f"- [ ] {i}. {t.get('title')} (size {t.get('size')}, depends {t.get('depends') or 'none'}{', CRITICAL' if r.get('critical') else ''})")
            if t.get("blocked_on"):
                a(f"  - BLOCKED on question(s): {', '.join(map(str, t['blocked_on']))}")
            a(f"  - Covers: {t.get('covers') or t.get('enables')}")
            for f in t.get("files") or []:
                a(f"  - File: {f.get('path')} ({f.get('op')}, verified {f.get('verified_at')})")
            for an in t.get("anchors") or []:
                a(f"  - Anchor: {an}")
            it = t.get("interfaces") or {}
            a(f"  - Consumes: {it.get('consumes')}; Produces: {it.get('produces')}")
            for k, s in enumerate(t.get("acceptance") or []):
                a(f"  - Acceptance {k}: {s}")
            for v in t.get("verify") or []:
                a(f"  - Verify ({v.get('kind')}): `{v.get('run')}` expect {v.get('expect')}")
            if i in cps:
                cp = cps[i]
                a(f"- [ ] {cp.get('id')}. Checkpoint after task {i}")
                for v in cp.get("verify") or []:
                    a(f"  - Verify: {v}")
        a("")
    if rows:
        a("## Critical path order")
        a("| Task | Dur | ES | EF | LS | LF | Slack | Critical |")
        a("|---|---|---|---|---|---|---|---|")
        for r in rows:
            a(f"| {r['id']} | {r['dur']} | {r['es']} | {r['ef']} | {r['ls']} | {r['lf']} | {r['slack']} | {'yes' if r['critical'] else ''} |")
        a("")
        a("Waves (tasks that can run together): " + "; ".join("[" + ", ".join(w) + "]" for w in waves(rows)))
        a("")
    if plan.get("final_verification"):
        a("## Final verification")
        for f in plan["final_verification"]:
            a(f"- [ ] {f.get('id')}. {f.get('text')} - `{(f.get('verify') or {}).get('run')}` expect {(f.get('verify') or {}).get('expect')}")
        a("")
    if plan.get("review_focus"):
        a("## Review focus")
        for r in plan["review_focus"]:
            a(f"- {r.get('text')} -> expected: {r.get('expected')} (task {r.get('task')})")
        a("")
    if plan.get("risks"):
        a("## Risks")
        a("| Risk | Impact | Mitigation | Detection |")
        a("|---|---|---|---|")
        for r in plan["risks"]:
            a(f"| {r.get('risk')} | {r.get('impact')} | {r.get('mitigation')} | {r.get('detection')} |")
        a("")
    t2 = plan.get("tier2")
    if t2:
        a("## Tier 2")
        cs = t2.get("consensus_summary") or {}
        a("Principles: " + "; ".join(cs.get("principles") or []))
        a("Decision drivers: " + "; ".join(cs.get("drivers") or []))
        for o in cs.get("options") or []:
            a(f"- Option {o.get('name')}: pros {o.get('pros')}; cons {o.get('cons')}")
        for p in t2.get("premortem") or []:
            a(f"- Pre-mortem: {p.get('scenario')} | signal {p.get('signal')} | mitigation {p.get('mitigation')}")
        for k, v in (t2.get("test_plan") or {}).items():
            a(f"- Test plan {k}: {v}")
        a("")
    opens = [q for q in plan.get("questions") or [] if q.get("status") == "open"]
    a("## Deferred question block")
    if not opens:
        a("None open.")
    for q in opens:
        a(f"- {q.get('id')} ({'blocking' if q.get('blocking') else 'deferrable'}): {q.get('text')} blocks tasks {q.get('blocks')}")
        for o in q.get("options") or []:
            a(f"  - {o.get('label')}{' (recommended)' if o.get('recommended') else ''}")
    a("")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ pack config
def load_pack():
    p = {}
    for n in ("tiers", "gates", "routing", "lint-rules", "audit-tools", "questions", "pipeline"):
        p[n] = load(os.path.join(REF, n + ".yaml"))
    return p


def gate_map(pack):
    return {g["id"]: g for g in pack["gates"]["gates"]}


# ------------------------------------------------------------------ verbs
def run_cmd(cmd, cwd=None, timeout=None):
    timeout = timeout or lim("planning.engine.command_timeout")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, "not found: " + cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def incomplete_plans(root, slug):
    hits = []
    for p in glob.glob(os.path.join(rig(root), "plans", "*.plan.yaml")):
        try:
            d = load(p)
        except Exception:
            continue
        m = (d or {}).get("meta") or {}
        if m.get("slug") != slug and m.get("status") != "complete":
            hits.append(os.path.relpath(p, root))
    pats = ["tasks/plan.md", "tasks/todo.md", ".plans/*.md", "docs/**/plans/*.md"]
    for pat in pats:
        for p in glob.glob(os.path.join(root, pat), recursive=True):
            try:
                if re.search(r"^\s*- \[ \]", open(p, encoding="utf-8", errors="ignore").read(), re.M):
                    hits.append(os.path.relpath(p, root))
            except OSError:
                pass
    return hits


def cmd_start(a):
    root = os.path.abspath(a.root)
    hits = incomplete_plans(root, a.slug)
    if hits:
        print("REFUSED: existing incomplete plan(s) with unchecked tasks:")
        for h in hits:
            print("  -", h)
        print("Ask the user: finish the old plan, discard it explicitly, or choose another location. Nothing was written.")
        return 2
    os.makedirs(os.path.join(rig(root), "plans"), exist_ok=True)
    os.makedirs(os.path.join(rig(root), "evidence"), exist_ok=True)
    st = load_state(root)
    resumed = bool(st)
    if not st:
        st = {"slug": a.slug, "started": now(), "gates": {}, "reviews": {}, "execute_authorized": None,
              "snapshot": snapshot(root)}
        save(state_path(root), st)
        ledger_add(root, "note", "start", f"run started for {a.slug}", "system")
    else:
        print("resuming existing run", st.get("slug"))
        if a.rebaseline:
            st["snapshot"] = snapshot(root)
            save(state_path(root), st)
            ledger_add(root, "note", "rebaseline", a.rebaseline_reason or "working tree re-snapshotted on resume", "user" if a.rebaseline_reason else "system")
            print("snapshot re-taken (ledger note written)")
    st.setdefault("gates", {})["G_existing_plan"] = {"status": "passed", "reason": "no incomplete plan found", "authority": "system"}
    save(state_path(root), st)
    if not a.no_codegraph:
        home = os.path.abspath(os.path.expanduser("~"))
        if os.path.abspath(root) == home:
            ledger_add(root, "tool_run", "codegraph", "skipped: working directory is home", "system")
            print("codegraph: skipped (home directory)")
        else:
            for sub in ("init", "sync"):
                rc, out = run_cmd(["codegraph", sub], cwd=root)
                ledger_add(root, "tool_run", "codegraph " + sub, f"rc={rc} {out[-lim('planning.engine.ledger_output_tail'):]}", "system")
                print(f"codegraph {sub}: rc={rc}")
                if rc == 127 or (rc != 0 and "not found" in out.lower()):
                    print("WARNING: codegraph is not installed; internal claims need other code evidence and G_ground must say so in its reason")
                    break
            st = load_state(root)
            st["snapshot"] = snapshot(root)  # codegraph's own index files are not planning's edits
            save(state_path(root), st)
    print("started", a.slug, "(resumed)" if resumed else "", "- state:", os.path.relpath(state_path(root), root))
    return 0


def build_ctx(a, plan_file=None):
    c = Ctx()
    c.root = os.path.abspath(a.root)
    c.repo = os.path.abspath(getattr(a, "repo", None) or c.root)
    c.pack = load_pack()
    c.tiers, c.routing, c.audit = c.pack["tiers"], c.pack["routing"], c.pack["audit-tools"]
    c.state = load_state(c.root)
    c.ledger = load_ledger(c.root)
    c.final = getattr(a, "final", False)
    return c


def cmd_check(a):
    if a.pack:
        return check_pack()
    if not a.plan:
        print("usage: railguard check <plan.yaml> [--final] | railguard check --pack")
        return 2
    c = build_ctx(a)
    plan_file = a.plan
    c.plan = load(plan_file)
    sp = spec_path_of(c.plan, plan_file)
    c.spec = load(sp) if sp and os.path.exists(sp) else None
    c.tier = _tier(c.plan)
    gmap = gate_map(c.pack)
    lint = {r["id"]: r for r in c.pack["lint-rules"]["rules"]}
    skips = c.tiers["tiers"][str(c.tier)].get("skip") or {}
    results, errs = {}, 0
    for gid, g in gmap.items():
        if gid in skips:
            results[gid] = ("skipped", [f"skipped by tier {c.tier}: {skips[gid]}"], "rule:tiers")
            continue
        if g["kind"] == "manual":
            s = ((c.state.get("gates") or {}).get(gid) or {})
            if s.get("status") in ("passed", "skipped"):
                results[gid] = (s["status"], [s.get("reason", "")], s.get("authority", ""))
            else:
                results[gid] = ("pending", ["not yet recorded: railguard log --kind gate --subject %s --status passed" % gid], "")
            continue
        msgs, bad = [], 0
        for rid in g.get("rules") or []:
            if c.tier < int(lint[rid]["from_tier"]):
                continue
            for sev, m in RULES[rid](c):
                msgs.append(f"{sev.upper()} {rid}: {m}")
                if sev == "error":
                    bad += 1
        if bad == 0 and ((c.state.get("gates") or {}).get(gid) or {}).get("status") == "skipped":
            results[gid] = ("skipped", [(c.state["gates"][gid] or {}).get("reason", "")], (c.state["gates"][gid] or {}).get("authority", ""))
        else:
            results[gid] = ("passed" if bad == 0 else "failed", msgs, "rule")
        errs += bad
    changed = False
    st = load_state(c.root)
    if st:
        for gid, (status, msgs, auth) in results.items():
            old = ((st.get("gates") or {}).get(gid) or {}).get("status")
            if old != status and status in ("passed", "failed", "skipped"):
                st.setdefault("gates", {})[gid] = {"status": status, "reason": (msgs[0] if status == "skipped" and msgs else ""), "authority": auth}
                changed = True
                ledger_add(c.root, "gate", gid, f"{old} -> {status}", "rule:check")
        if changed:
            save(state_path(c.root), st)
    print(f"plan {a.plan}  tier {c.tier}  hash {plan_hash(c.plan)[:12]}")
    for gid, (status, msgs, auth) in results.items():
        print(f"{status.upper():8} {gid}")
        for m in msgs:
            print("           " + m)
    rows, err = cpm(c.plan)
    if rows:
        crit = [r["id"] for r in rows if r["critical"]]
        print("critical tasks:", ", ".join(crit), "| waves:", waves(rows))
    level, why = review_level(c.plan, c.state, c.routing)
    print("review required:", ", ".join(required_reviewers(c.plan, c.routing)) or "none", f"| level {level} ({why})")
    print("planner topology:", planner_topology(c.plan), "| tier floor:", tier_floor(c.plan, c.pack))
    opens = [q for q in c.plan.get("questions") or [] if q.get("status") == "open"]
    print(f"open questions: {len(opens)}")
    unfinished = [g for g, (s, _, _) in results.items() if s not in ("passed", "skipped")]
    if a.final and unfinished:
        print("FINAL CHECK FAILED; gates not passed or skipped:", ", ".join(unfinished))
        return 1
    return 1 if errs else 0


def check_pack():
    pack = load_pack()
    errs = []
    for fn in glob.glob(os.path.join(REF, "*.yaml")) + glob.glob(os.path.join(PACK, "assets", "*.yaml")) + glob.glob(os.path.join(os.path.dirname(PACK), "execute-rigorously", "references", "*.yaml")):
        try:
            load(fn)
        except Exception as e:
            errs.append(f"parse error {os.path.basename(fn)}: {e}")
    rules = {r["id"] for r in pack["lint-rules"]["rules"]}
    for r in rules - set(RULES):
        errs.append(f"rule {r} in lint-rules.yaml has no implementation")
    for r in set(RULES) - rules:
        errs.append(f"rule {r} implemented but missing from lint-rules.yaml")
    gids = {g["id"] for g in pack["gates"]["gates"]}
    for g in pack["gates"]["gates"]:
        for r in g.get("rules") or []:
            if r not in rules:
                errs.append(f"gate {g['id']} references unknown rule {r}")
    for r in pack["lint-rules"]["rules"]:
        if r["gate"] not in gids:
            errs.append(f"rule {r['id']} references unknown gate {r['gate']}")
    covered = {x for g in pack["gates"]["gates"] for x in (g.get("rules") or [])}
    for r in rules - covered:
        errs.append(f"rule {r} is not attached to any gate")
    for t in pack["tiers"]["tiers"].values():
        for g in t.get("skip") or {}:
            if g not in gids:
                errs.append(f"tier skip references unknown gate {g}")
    for st in pack["pipeline"]["stages"]:
        for g in st.get("gates") or []:
            if g not in gids:
                errs.append(f"stage {st['id']} references unknown gate {g}")
    import ast
    keys = set()
    scripts = [os.path.join(HERE, f) for f in ("railguard.py", "rigor_exec.py", "rigor_clarify.py")]
    for fn in scripts:
        keys |= set(re.findall(r"lim\(\s*f?[\"']([\w.%]+)[\"']", open(fn, encoding="utf-8").read()))
    # every leaf in limits.yaml must be read by code (directly or through its parent)
    def _leaves(o, path=""):
        if isinstance(o, dict) and not (set(o) & set(_BOUNDS)):
            for kk, vv in o.items():
                if kk not in ("purpose", "version"):
                    yield from _leaves(vv, f"{path}.{kk}" if path else str(kk))
        else:
            yield path
    for leaf in _leaves(load(os.path.join(REF, "limits.yaml"))):
        if not any(leaf == k or leaf.startswith(k + ".") or ("%" in k and leaf.startswith(k.split("%")[0])) for k in keys):
            errs.append(f"limit {leaf} is in limits.yaml but no code reads it")
    # no bare numeric literals in comparisons or timeouts inside the scripts
    for fn in scripts:
        for i, line in enumerate(open(fn, encoding="utf-8").read().splitlines(), 1):
            code = line.split("#")[0]
            if re.search(r"timeout=\d+|>= ?0\.\d+|<= ?0\.\d+|\[-\d{2,}:\]", code):
                errs.append(f"{os.path.basename(fn)}:{i}: number hardcoded in code, move it to limits.yaml: {code.strip()[:70]}")
    for k in sorted(keys):
        if "%" in k:
            continue
        try:
            v = lim(k)
            if not isinstance(v, (int, float, dict)):
                errs.append(f"limit {k} is not numeric")
        except (KeyError, TypeError):
            errs.append(f"limit {k} used in code but missing from limits.yaml")
    def _nums(o, path=""):
        if isinstance(o, dict):
            for kk, vv in o.items():
                if kk == "unit":
                    if vv not in UNITS:
                        yield path + ".unit=" + str(vv)
                else:
                    yield from _nums(vv, path + "." + str(kk))
        elif not isinstance(o, (int, float)) or isinstance(o, bool):
            yield path
    for pth in _nums(load(os.path.join(REF, "limits.yaml")), ""):
        if pth not in (".purpose", ".version"):
            errs.append(f"limits.yaml bad value: {pth}")
    ml_path = os.path.join(REF, "merge-ledger.yaml")
    summary = {}
    if os.path.exists(ml_path):
        ml = load(ml_path)
        ids = [r["id"] for r in ml["rows"]]
        if len(ids) != len(set(ids)):
            errs.append("duplicate ids in merge-ledger")
        sources = set(ml["sources"])
        cids = {c["id"] for c in ml.get("conflicts") or []}
        for r in ml["rows"]:
            d = r.get("disp")
            summary[d] = summary.get(d, 0) + 1
            if r.get("src") not in sources:
                errs.append(f"{r['id']}: unknown source {r.get('src')}")
            if d not in ("enforced", "merged", "skipped", "deferred"):
                errs.append(f"{r['id']}: bad disposition {d}")
                continue
            if d == "enforced":
                if r.get("by") not in ("script", "contract", "detective"):
                    errs.append(f"{r['id']}: enforced needs by script|contract|detective")
                if r.get("by") == "script" and r.get("ref") not in rules and r.get("ref") not in gids:
                    errs.append(f"{r['id']}: script ref {r.get('ref')} is not a rule or gate")
                if not r.get("ref"):
                    errs.append(f"{r['id']}: enforced needs ref")
            if d == "merged" and r.get("into") not in set(ids) | {"file"} and not r.get("into"):
                errs.append(f"{r['id']}: merged needs into")
            if d in ("skipped", "deferred") and not r.get("reason"):
                errs.append(f"{r['id']}: {d} needs reason")
            if d == "deferred" and r.get("to") not in ("execute-rigorously", "clarity-gate", "documents", "user"):
                errs.append(f"{r['id']}: deferred needs a valid to")
            if str(r.get("rel", "")).startswith("c:") and r["rel"][2:] not in cids:
                errs.append(f"{r['id']}: unknown conflict {r['rel']}")
        for cf in ml.get("conflicts") or []:
            for rid in cf.get("rows") or []:
                if rid not in ids:
                    errs.append(f"conflict {cf['id']} references unknown row {rid}")
            if not cf.get("resolution"):
                errs.append(f"conflict {cf['id']} has no resolution")
    else:
        errs.append("merge-ledger.yaml missing")
    import rigor_exec
    errs += rigor_exec.check_exec_pack()
    print("pack check:", "OK" if not errs else "FAILED")
    print("rules:", len(rules), "gates:", len(gids), "merge rows by disposition:", summary)
    for e in errs:
        print("  ERROR", e)
    return 1 if errs else 0


def cmd_log(a):
    root = os.path.abspath(a.root)
    if a.kind not in EVENT_KINDS:
        print("kind must be one of", EVENT_KINDS)
        return 2
    if a.kind in NEEDS_REASON and not a.reason:
        print("a reason is required for", a.kind)
        return 2
    if not AUTH_RE.match(a.authority):
        print("authority must be user, system, proposal, rule:<id> or finding:<id>")
        return 2
    if a.kind == "answer" and a.subject in CONFIRM_SUBJECTS:
        if a.authority != "user":
            print(f"REFUSED: {a.subject} can only be recorded with authority user (what the user actually answered).")
            return 2
        if explicit_answer(a.reason) is None:
            print(f"REFUSED: {a.subject} needs an explicit yes or no from the user, with no hedge. 'sounds good', 'sure', 'yes but', 'whatever you think' or silence do not count; re-ask with concrete options.")
            return 2
    if a.kind == "plan_change" and a.authority in ("system", "proposal"):
        print("REFUSED: a plan_change needs authority user, finding:<id> or rule:<id>")
        return 2
    if a.authority == "proposal" and a.kind not in ("answer", "decision"):
        print("authority proposal is only for answer or decision events")
        return 2
    st = load_state(root)
    before = after = None
    if a.plan:
        plan = load(a.plan)
        after = plan_hash(plan)
        before = st.get("last_plan_hash")
        st["last_plan_hash"] = after
    if a.kind == "gate":
        if not a.subject or a.status not in ("passed", "failed", "skipped"):
            print("gate events need --subject G_x --status passed|failed|skipped")
            return 2
        if a.status == "skipped":
            g = gate_map(load_pack()).get(a.subject) or {}
            if not a.reason or (a.authority != "user" and not a.authority.startswith("rule:")):
                print("a skipped gate needs a reason and authority user or rule:<id>")
                return 2
            if g and g.get("skippable") is False:
                print(f"REFUSED: {a.subject} is not skippable")
                return 2
            allowed = load_pack()["gates"].get("skip_authority") or []
            if a.authority not in allowed and not (a.authority.startswith("rule:") and "rule:*" in allowed):
                print(f"REFUSED: skip authority must be one of {allowed}")
                return 2
        st.setdefault("gates", {})[a.subject] = {"status": a.status, "reason": a.reason, "authority": a.authority}
    if a.kind == "review_complete":
        if not a.role or not a.plan:
            print("review_complete needs --role and --plan")
            return 2
        st.setdefault("reviews", {})[a.role] = {"plan_hash": after, "ts": now()}
        if a.set_baseline:
            rows, _ = cpm(plan)
            st["review_baseline"] = {"plan_hash": after, "tasks": {sid(t["id"]): task_hash(t) for _, t in all_tasks(plan)},
                                     "critical": [r["id"] for r in rows if r["critical"]],
                                     "phases": [sid(p.get("id")) for p in plan.get("phases") or []]}
    if a.kind == "answer" and a.subject == "execute_authorized":
        st["execute_authorized"] = explicit_answer(a.reason) == "yes"
    if a.kind == "review_complete":
        a.subject = a.role
    ev = ledger_add(root, a.kind, a.subject or "", a.reason or "", a.authority, before, after)
    if st:
        save(state_path(root), st)
    print(f"logged #{ev['n']} {a.kind} {a.subject or ''} {ev['hash'][:12]}")
    return 0


def cmd_render(a):
    c = build_ctx(a)
    plan = load(a.plan)
    sp = spec_path_of(plan, a.plan)
    spec = load(sp) if sp and os.path.exists(sp) else None
    md = render_md(plan, spec)
    slug = (plan.get("meta") or {}).get("slug", "plan")
    out = os.path.join(rig(c.root), "plans", f"{slug}.plan.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    st = load_state(c.root)
    if st is not None:
        st["render_hash"] = sha_text(md)
        st["render_plan_hash"] = plan_hash(plan)
        save(state_path(c.root), st)
    if getattr(a, "questionnaire", False):
        qs = [q for q in plan.get("questions") or [] if q.get("status") == "open"]
        lines = [f"# Questions for {slug}", "", "Please answer each question; the recommended option is marked.", ""]
        for q in qs:
            lines.append(f"## {q.get('id')}. {q.get('text')}")
            lines.append(f"_Why this cannot be found in the code: {q.get('why_not_discoverable')}_")
            for o in q.get("options") or []:
                if isinstance(o, dict):
                    lines.append(f"- [ ] {o.get('label')}{' (recommended)' if o.get('recommended') else ''}")
            lines += ["- [ ] Other: ", ""]
        qp = os.path.join(rig(c.root), "plans", f"{slug}.questions.md")
        with open(qp, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
        print("questionnaire", os.path.relpath(qp, c.root), f"({len(qs)} open)")
    if a.stdout:
        sys.stdout.write(md)
    print("rendered", os.path.relpath(out, c.root), "sha256", sha_text(md)[:16])
    return 0


def gh(args, dry, log):
    cmd = ["gh"] + args
    log.append("gh " + " ".join(args))
    if dry:
        return 0, ""
    return run_cmd(cmd)


def gh_json(method, path, payload, dry, log):
    """GitHub REST through `gh api` (works where the GraphQL-backed gh subcommands do not).
    Returns (rc, parsed JSON or None). A dry run records the call and returns (0, None)."""
    log.append(f"gh api -X {method} {path}")
    if dry:
        return 0, None
    cmd = ["gh", "api", "-X", method, path]
    tmp = None
    if payload is not None:
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        cmd += ["--input", tmp]
    try:
        rc, out = run_cmd(cmd)
    finally:
        if tmp:
            os.unlink(tmp)
    try:
        return rc, json.loads(out) if out.strip() else None
    except ValueError:
        return rc, None


def origin_repo(root):
    rc, url = run_cmd(["git", "-C", root, "config", "--get", "remote.origin.url"])
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?$", url or "")
    return f"{m.group(1)}/{m.group(2)}" if rc == 0 and m else None


def tokens(s):
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}


def cmd_publish(a):
    c = build_ctx(a)
    plan = load(a.plan)
    sp = spec_path_of(plan, a.plan)
    spec = load(sp) if sp and os.path.exists(sp) else None
    slug = plan["meta"]["slug"]
    dry = not a.yes
    log = []
    rc, url = run_cmd(["git", "-C", c.root, "config", "--get", "remote.origin.url"])
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?$", url or "")
    if rc != 0 or not m:
        print("no GitHub remote: record the skip with `railguard log \"no GitHub remote\" --kind gate --subject G_publish --status skipped --authority rule:publish`")
        return 0
    repo = f"{m.group(1)}/{m.group(2)}"
    title = f"plan: {slug}"
    if shutil.which("gh") is None and not dry:
        print("gh CLI not found")
        return 2
    existing = []
    if shutil.which("gh") is not None:  # read-only, so the dry run searches for duplicates too
        rc, listing = gh_json("GET", f"repos/{repo}/issues?state=open&per_page=100", None, False, log)
        if rc == 0 and isinstance(listing, list):
            mine = {n for n in ((c.state.get("publish") or {}).get("tasks") or {}).values() if n}
            existing = [e for e in listing if "pull_request" not in e and slug.lower() in e.get("title", "").lower()
                        and e.get("number") not in mine and not e.get("title", "").startswith(f"[{slug}] ")]
    else:
        log.append(f"gh api -X GET repos/{repo}/issues?state=open")
    parent = None
    for e in existing:
        if e["title"].strip().lower() == title.lower():
            parent = e
        elif len(tokens(e["title"]) & tokens(title)) / max(len(tokens(title)), 1) >= lim("planning.publish.duplicate_similarity"):
            print(f"NEEDS DECISION: open issue #{e['number']} '{e['title']}' looks like a duplicate of '{title}'")
            ledger_add(c.root, "question", "publish-duplicate", f"possible duplicate issue #{e['number']}", "system")
            return 3
    tmp = os.path.join(rig(c.root), "tmp")
    os.makedirs(tmp, exist_ok=True)
    body = render_md(plan, spec)
    bf = os.path.join(tmp, "parent.md")
    open(bf, "w", encoding="utf-8").write(body)
    reviewed = (c.state.get("reviews") or {}).get("critic") or c.state.get("review_baseline") or _tier(plan) == 0
    state_label = "triaged" if reviewed else "needs-review"
    labels = ["issue", "enhancement", state_label]
    if not dry and (c.state.get("publish") or {}).get("tasks"):
        lvl, dm = drift(c.root)
        if lvl in ("ask", "block"):
            print(f"REFUSED: published issues were changed outside the plan ({lvl}):")
            for x in dm:
                print("  ", x)
            print("record the user's decision with: railguard log \"<why>\" --kind decision --subject drift_accepted --authority user")
            return 1
    for lb in labels:
        gh_json("POST", f"repos/{repo}/labels", {"name": lb}, dry, log)  # 422 when it exists is fine
    st = load_state(c.root)
    pub = {"repo": repo, "dry_run": dry, "tasks": {}}
    if parent:
        pub["parent"] = parent["number"]
        gh_json("PATCH", f"repos/{repo}/issues/{parent['number']}", {"body": body, "labels": labels}, dry, log)
    else:
        rc, j = gh_json("POST", f"repos/{repo}/issues", {"title": title, "body": body, "labels": labels}, dry, log)
        pub["parent"] = (j or {}).get("number")
    rows, _ = cpm(plan)
    rmap = {r["id"]: r for r in rows}
    sub_lines = []
    for ph, t in all_tasks(plan):
        i = sid(t["id"])
        tb = os.path.join(tmp, f"task-{i}.md")
        lines = [f"Part of plan `{slug}` phase {ph.get('id')}. Size {t.get('size')}. Depends on {t.get('depends') or 'none'}.",
                 f"Critical path: {'yes' if rmap.get(i, {}).get('critical') else 'no'}", "", "Acceptance:"]
        lines += [f"- {x}" for x in t.get("acceptance") or []]
        lines += ["", "Verify:"] + [f"- `{v.get('run')}` expect {v.get('expect')}" for v in t.get("verify") or []]
        open(tb, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        known = ((c.state.get("publish") or {}).get("tasks") or {}).get(i)
        payload = {"title": f"[{slug}] task {i}: {t.get('title')}", "body": "\n".join(lines) + "\n", "labels": labels}
        if known:  # republish updates the recorded issue and never creates a second one
            rc, j = gh_json("PATCH", f"repos/{repo}/issues/{known}", payload, dry, log)
            j = j or {"number": known}
        else:
            rc, j = gh_json("POST", f"repos/{repo}/issues", payload, dry, log)
        num = (j or {}).get("number")
        pub["tasks"][i] = num
        if num and not dry:
            os.makedirs(os.path.join(rig(c.root), "published"), exist_ok=True)
            shutil.copyfile(tb, os.path.join(rig(c.root), "published", f"{num}.md"))
        sub_lines.append(f"- [ ] #{num if num else '<task ' + i + '>'} {t.get('title')}")
        if num and pub["parent"] and not dry and not known and (j or {}).get("id"):
            gh_json("POST", f"repos/{repo}/issues/{pub['parent']}/sub_issues", {"sub_issue_id": j["id"]}, dry, log)
    if pub["parent"] and not dry:
        open(bf, "a", encoding="utf-8").write("\n## Task issues\n" + "\n".join(sub_lines) + "\n")
        gh_json("PATCH", f"repos/{repo}/issues/{pub['parent']}", {"body": open(bf, encoding="utf-8").read()}, dry, log)
    if pub.get("parent") and not dry:
        os.makedirs(os.path.join(rig(c.root), "published"), exist_ok=True)
        shutil.copyfile(bf, os.path.join(rig(c.root), "published", f"{pub['parent']}.md"))
    if st is not None:
        st["publish"] = pub
        save(state_path(c.root), st)
    ledger_add(c.root, "publish", repo, ("dry run: " if dry else "published: ") + f"{len(pub['tasks'])} task issue(s)", "system")
    print(("DRY RUN (add --yes to execute)" if dry else "PUBLISHED"), "->", repo)
    for l in log:
        print("  ", l)
    return 0


def cmd_todo(a):
    """Planning progress as to-dos: stages, then phases and tasks when a plan exists."""
    c = build_ctx(a)
    gates = (c.state.get("gates") or {})
    print("status\tkind\tid\ttitle\tparent")
    for st in c.pack["pipeline"]["stages"]:
        gs = st.get("gates") or []
        done = bool(gs) and all(((gates.get(g) or {}).get("status") in ("passed", "skipped")) for g in gs)
        print("\t".join(["completed" if done else "pending", "stage", st["id"], st.get("does", "").split(". ")[0][:80], ""]))
    if a.plan and os.path.exists(a.plan):
        plan = load(a.plan)
        for ph in plan.get("phases") or []:
            print("\t".join(["pending", "phase", sid(ph.get("id")), str(ph.get("title") or ph.get("id")), ""]))
            for t in ph.get("tasks") or []:
                print("\t".join(["pending", "task", sid(t.get("id")), str(t.get("title")), sid(ph.get("id"))]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="railguard", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: current directory)")
    sub = ap.add_subparsers(dest="verb", required=True)
    s = sub.add_parser("start"); s.add_argument("slug"); s.add_argument("--no-codegraph", action="store_true"); s.add_argument("--rebaseline", action="store_true", help="resume: re-take the working-tree snapshot (use only after changes the user authorized)"); s.add_argument("--rebaseline-reason", default="")
    s = sub.add_parser("check"); s.add_argument("plan", nargs="?"); s.add_argument("--final", action="store_true"); s.add_argument("--pack", action="store_true"); s.add_argument("--repo")
    s = sub.add_parser("log"); s.add_argument("reason", nargs="?", default=""); s.add_argument("--kind", required=True); s.add_argument("--subject", default="")
    s.add_argument("--authority", default="system"); s.add_argument("--status"); s.add_argument("--plan"); s.add_argument("--role"); s.add_argument("--set-baseline", action="store_true")
    s = sub.add_parser("render"); s.add_argument("plan"); s.add_argument("--stdout", action="store_true"); s.add_argument("--questionnaire", action="store_true")
    import rigor_exec, rigor_clarify
    rigor_exec.add_parser(sub)
    rigor_clarify.add_parser(sub)
    s = sub.add_parser("publish"); s.add_argument("plan"); s.add_argument("--yes", action="store_true")
    s = sub.add_parser("todo"); s.add_argument("plan", nargs="?")
    a = ap.parse_args(argv)
    try:
        if a.verb == "exec":
            return rigor_exec.run(a)
        if a.verb == "clarify":
            return rigor_clarify.run(a)
        return {"start": cmd_start, "check": cmd_check, "log": cmd_log, "render": cmd_render, "publish": cmd_publish, "todo": cmd_todo}[a.verb](a)
    except FileNotFoundError as e:
        print(f"REFUSED: file not found: {e.filename}. Plans are given as a path such as .rigor/plans/<slug>.plan.yaml, not a slug.")
        return 2
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
