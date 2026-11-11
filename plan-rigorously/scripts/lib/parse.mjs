// plan.md text -> model. Pure: no filesystem, no knowledge of any harness.
import { createHash } from 'node:crypto';

export const INTENT_KEYS = ['outcome', 'user', 'why now', 'success', 'constraint', 'out of scope'];
export const INTENT_LABELS = {
  outcome: 'Outcome',
  user: 'User',
  'why now': 'Why now',
  success: 'Success',
  constraint: 'Constraint',
  'out of scope': 'Out of scope',
};
const SEVERITIES = ['blocker', 'major', 'minor'];
const TASK_KEYS = ['covers', 'edits', 'creates', 'depends', 'verify', 'batch'];

export function normalizeText(text) {
  return String(text).replace(/\r\n?/g, '\n');
}

export const MAX_LINE = 2000;
export const MAX_BYTES = 300 * 1024;

export function hashText(text) {
  const clean = normalizeText(text)
    .split('\n')
    .map((l) => l.trimEnd())
    .join('\n')
    .trim();
  return createHash('sha256').update(clean).digest('hex');
}

const isFence = (line) => line.trimStart().startsWith('```');

/**
 * The one splitter behind the parser, the hashes and stripReview, so they can
 * never disagree about where a section starts. Frontmatter is skipped the same
 * way for all three; headings inside code fences are not headings.
 */
export function scan(text) {
  const lines = normalizeText(text).split('\n');
  const errors = [];
  const meta = {};
  let bodyStart = 0;
  if (lines[0] !== '---') {
    errors.push('The file must start with a frontmatter block (--- name: ... path: full|light ---).');
  } else {
    const end = lines.indexOf('---', 1);
    if (end === -1) {
      errors.push('The frontmatter block is not closed with a second --- line.');
      bodyStart = 1;
    } else {
      bodyStart = end + 1;
      for (const line of lines.slice(1, end)) {
        if (isFence(line)) {
          errors.push('The frontmatter block must not contain code fences.');
          continue;
        }
        const colon = line.indexOf(':');
        if (colon > 0 && /^[A-Za-z_-]+$/.test(line.slice(0, colon))) {
          meta[line.slice(0, colon)] = line.slice(colon + 1).trim().replace(/^["']|["']$/g, '');
        }
      }
    }
  }
  const sections = [];
  let current = null;
  let fence = false;
  for (let i = bodyStart; i < lines.length; i++) {
    const line = lines[i];
    if (isFence(line)) fence = !fence;
    if (!fence && line.startsWith('## ') && !line.startsWith('###')) {
      if (current) current.end = i;
      current = { title: line.slice(3).trim(), start: i, end: lines.length, lines: [] };
      sections.push(current);
    } else if (current) {
      current.lines.push(line.trimEnd());
    }
  }
  return { lines, errors, meta, sections };
}

function splitSubsections(lines) {
  const subs = {};
  let current = null;
  for (const line of lines) {
    if (line.startsWith('### ')) {
      current = line.slice(4).trim();
      subs[current] = [];
    } else if (current) {
      subs[current].push(line);
    }
  }
  return subs;
}

function splitList(value) {
  const v = (value ?? '').trim();
  if (v === '' || v === '-') return [];
  return v
    .split(',')
    .map((s) => s.trim().replace(/^`|`$/g, ''))
    .filter((s) => s && s !== '-');
}

function addUnique(map, kind, id, errors) {
  if (map.has(id)) {
    errors.push(`Duplicate id ${id}: each ${kind} id may appear only once.`);
    return false;
  }
  map.set(id, true);
  return true;
}

function parseIntent(lines) {
  const bullets = {};
  for (const line of lines) {
    const m = /^- ([A-Za-z ]+):\s*(.*)$/.exec(line);
    if (!m) continue;
    const key = m[1].toLowerCase();
    if (INTENT_KEYS.includes(key)) bullets[key] = m[2];
  }
  return bullets;
}

function parseQuestions(lines, errors) {
  const out = [];
  const seen = new Map();
  for (const line of lines) {
    if (!/^- Q-/.test(line)) continue;
    const m = /^- (Q-\d+)\s+\[([^\]]*)\]\s*(.*)$/.exec(line);
    if (!m) {
      errors.push(`Malformed question line: "${line.slice(0, 60)}". Use "- Q-n [open|answered|waiting Q-n] text".`);
      continue;
    }
    const [, id, statusRaw, text] = m;
    const status = statusRaw.trim();
    let kind;
    let waitsOn = null;
    if (status === 'open' || status === 'answered') kind = status;
    else {
      const w = /^waiting (Q-\d+)$/.exec(status);
      if (w) {
        kind = 'waiting';
        waitsOn = w[1];
      } else {
        errors.push(`Unknown status "[${status}]" on ${id}. Allowed: [open], [answered], [waiting Q-n].`);
        continue;
      }
    }
    if (addUnique(seen, 'question', id, errors)) out.push({ id, status: kind, waitsOn, text });
  }
  return out;
}

function parseBehaviours(lines, errors) {
  const out = [];
  const seen = new Map();
  for (const line of lines) {
    if (!/^- B-/.test(line)) continue;
    const m = /^- (B-\d+):\s*(.*)$/.exec(line);
    if (!m) {
      errors.push(`Malformed behaviour line: "${line.slice(0, 60)}". Use "- B-n: text".`);
      continue;
    }
    if (addUnique(seen, 'behaviour', m[1], errors)) out.push({ id: m[1], text: m[2] });
  }
  return out;
}

function parseCriteria(lines, errors) {
  const out = [];
  const seen = new Map();
  for (const line of lines) {
    if (!/^- AC-/.test(line)) continue;
    const m = /^- (AC-\d+)\s*(?:\(\s*Covers:\s*([^)]*)\))?\s*:\s*(.*)$/.exec(line);
    if (!m) {
      errors.push(`Malformed criterion line: "${line.slice(0, 60)}". Use "- AC-n (Covers: B-n): text".`);
      continue;
    }
    if (addUnique(seen, 'criterion', m[1], errors)) out.push({ id: m[1], covers: splitList(m[2]), text: m[3] });
  }
  return out;
}

function parseProof(raw) {
  const text = raw.trim();
  let m = /^doc:\s*(https?:\/\/\S+)(?:\s+"([^"]*)")?/.exec(text);
  if (m) return { kind: 'doc', url: m[1], quote: m[2] ?? '' };
  m = /^code:\s*(.+):(\d+)$/.exec(text);
  if (m) return { kind: 'code', path: m[1].trim(), line: Number(m[2]) };
  m = /^cmd:\s*(.+)$/.exec(text);
  if (m) {
    const cmd = /^`(.*)`$/.exec(m[1]);
    return { kind: 'cmd', command: cmd ? cmd[1] : m[1] };
  }
  return { kind: 'unknown', raw: text };
}

function parseClaims(lines, errors) {
  const out = [];
  const seen = new Map();
  for (const line of lines) {
    if (!/^- C-/.test(line)) continue;
    const m = /^- (C-\d+):\s*(.*)$/.exec(line);
    if (!m) {
      errors.push(`Malformed claim line: "${line.slice(0, 60)}". Use "- C-n: text -- doc|code|cmd: ...".`);
      continue;
    }
    const split = / -- (?=(?:doc|code|cmd):)/.exec(m[2]);
    const text = split ? m[2].slice(0, split.index) : m[2];
    const proof = split ? parseProof(m[2].slice(split.index + 4)) : null;
    if (addUnique(seen, 'claim', m[1], errors)) out.push({ id: m[1], text, proof });
  }
  return out;
}

function parseTasks(lines, errors) {
  const out = [];
  const seen = new Map();
  let current = null;
  for (const line of lines) {
    if (/^- \[/.test(line)) {
      current = null;
      const m = /^- \[( |x|X)\]\s+(T-\d+):\s*(.*)$/.exec(line);
      if (!m) {
        errors.push(`Malformed task line: "${line.slice(0, 60)}". Use "- [ ] T-n: title".`);
        continue;
      }
      if (!addUnique(seen, 'task', m[2], errors)) continue;
      current = {
        id: m[2], title: m[3], done: m[1] !== ' ',
        covers: [], edits: [], creates: [], depends: [], verify: '', batch: '',
      };
      out.push(current);
      continue;
    }
    const sub = /^\s+- ([A-Za-z]+):\s*(.*)$/.exec(line);
    if (!sub || !current) continue;
    const key = sub[1].toLowerCase();
    if (!TASK_KEYS.includes(key)) continue;
    if (key === 'verify') {
      const v = sub[2].replace(/^`(.*)`$/, '$1').trim();
      current.verify = v === '-' ? '' : v;
    } else if (key === 'batch') current.batch = sub[2].trim() === '-' ? '' : sub[2].trim();
    else current[key] = splitList(sub[2]);
  }
  return out;
}

function parseReview(lines, errors) {
  const findings = [];
  const seen = new Map();
  let noFindings = false;
  for (const line of lines) {
    if (/^- No findings/i.test(line)) {
      noFindings = true;
      continue;
    }
    if (!/^- F-/.test(line)) continue;
    const m = /^- (F-\d+)\s+\[([^\]]*)\]\s*(.*)$/.exec(line);
    if (!m) {
      errors.push(`Malformed finding line: "${line.slice(0, 60)}". Use "- F-n [blocker|major|minor] \\"quote\\" -- text -> disposition".`);
      continue;
    }
    const severity = m[2].trim();
    if (!SEVERITIES.includes(severity)) {
      errors.push(`Unknown severity "[${severity}]" on ${m[1]}. Allowed: [blocker], [major], [minor].`);
      continue;
    }
    let text = m[3];
    let disposition = null;
    const arrow = text.lastIndexOf(' -> ');
    if (arrow !== -1) {
      const tail = text.slice(arrow + 4).trim();
      const d = /^(fixed|rejected: .+|user: .+)$/.exec(tail);
      if (d) {
        text = text.slice(0, arrow);
        disposition = {
          kind: tail.startsWith('fixed') ? 'fixed' : tail.startsWith('rejected') ? 'rejected' : 'user',
          detail: tail,
        };
      }
    }
    if (addUnique(seen, 'finding', m[1], errors)) findings.push({ id: m[1], severity, text, disposition });
  }
  return { findings, noFindings };
}

/** The plan text with every `## Review` section removed. */
export function stripReview(text) {
  const { lines, sections } = scan(text);
  const drop = new Set();
  for (const sec of sections) {
    if (sec.title === 'Review') for (let i = sec.start; i < sec.end; i++) drop.add(i);
  }
  return lines.filter((_, i) => !drop.has(i)).join('\n');
}

function normalizeCheckboxes(text) {
  return text.replace(/^(\s*- )\[[xX]\](\s+T-\d+:)/gm, '$1[ ]$2');
}

export function planHashText(text) {
  return hashText(normalizeCheckboxes(stripReview(text)));
}

/** An oversized plan is refused without being parsed (no regex ever sees the long line). */
function rejected(text, message) {
  const zero = hashText('');
  return {
    ok: false,
    errors: [message],
    plan: {
      name: '', path: '', files: [], intent: {}, questions: [], behaviours: [], criteria: [], claims: [], tasks: [],
      review: { findings: [], noFindings: false, present: false },
      hashes: { intent: zero, spec: zero, plan: zero },
      text: '',
    },
  };
}

/**
 * Parse a plan. Always returns a best-effort model; `ok` is false when the
 * file must be rejected (bad frontmatter, duplicate ids, unknown status words).
 */
export function parsePlan(rawText) {
  const text = normalizeText(rawText);
  if (text.length > MAX_BYTES) return rejected(text, `The plan is larger than ${MAX_BYTES / 1024} KB; shorten it.`);
  const longLine = text.split('\n').findIndex((l) => l.length > MAX_LINE);
  if (longLine !== -1) return rejected(text, `Line ${longLine + 1} is longer than ${MAX_LINE} characters; break it up.`);

  const { errors, meta, sections } = scan(text);

  const name = meta.name ?? '';
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(name)) {
    errors.push('Frontmatter `name` is missing or not kebab-case (lowercase words joined by hyphens).');
  }
  const path = meta.path ?? '';
  if (path !== 'full' && path !== 'light') {
    errors.push('Frontmatter `path` must be `full` or `light`.');
  }

  const byTitle = new Map();
  for (const s of sections) {
    if (byTitle.has(s.title)) errors.push(`The section "## ${s.title}" appears twice.`);
    else byTitle.set(s.title, s.lines);
  }
  const lines = (title) => byTitle.get(title) ?? [];

  const specLines = lines('Spec');
  const subs = splitSubsections(specLines);
  const behaviourLines = subs.Behaviours ?? [];
  const criteriaLines = subs.Criteria ?? [];

  const review = parseReview(lines('Review'), errors);
  const files = lines('Files')
    .map((l) => /^\s*[-*]\s+(.*)$/.exec(l))
    .filter(Boolean)
    .map((m) => m[1].replace(/^`|`$/g, ''));

  const plan = {
    name,
    path,
    files,
    intent: parseIntent(lines('Intent')),
    questions: parseQuestions(lines('Questions'), errors),
    behaviours: parseBehaviours(behaviourLines, errors),
    criteria: parseCriteria(criteriaLines, errors),
    claims: parseClaims(lines('Claims'), errors),
    tasks: parseTasks(lines('Tasks'), errors),
    review: { ...review, present: byTitle.has('Review') },
    hashes: {
      intent: hashText(lines('Intent').join('\n')),
      spec: hashText(behaviourLines.join('\n') + '\n' + criteriaLines.join('\n')),
      plan: planHashText(text),
    },
    text,
  };
  return { ok: errors.length === 0, errors, plan };
}
