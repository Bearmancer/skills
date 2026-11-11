#!/usr/bin/env node
// Adds or removes the plan-rigorously hook entries in a Claude Code settings file.
//   node install.mjs [--settings <path>] [--dry-run] [--uninstall]
import {
  copyFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync,
} from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HOOK_PATH = resolve(dirname(fileURLToPath(import.meta.url)), 'hook.mjs');

const EVENTS = [
  ['PreToolUse', 'Write|Edit|NotebookEdit|Bash|PowerShell|AskUserQuestion|Agent'],
  ['PostToolUse', 'Write|Edit|Bash|PowerShell|WebFetch|AskUserQuestion'],
  ['UserPromptSubmit', null],
  ['SessionStart', null],
];

const isOurs = (h) => {
  const first = Array.isArray(h?.args) ? String(h.args[0] ?? '') : '';
  return /(^|[\\/])plan-rigorously[\\/]scripts[\\/]hook\.mjs$/.test(first);
};

function desiredGroup(matcher, hookPath) {
  const group = matcher ? { matcher } : {};
  group.hooks = [{ type: 'command', command: 'node', args: [hookPath], timeout: 10 }];
  return group;
}

/** Returns the settings with our entries added (or removed); everything else is left as it was. */
export function applyHooks(settings, { uninstall = false, hookPath = HOOK_PATH } = {}) {
  const out = structuredClone(settings);
  if (out.hooks !== undefined && (typeof out.hooks !== 'object' || out.hooks === null || Array.isArray(out.hooks))) {
    throw new Error('"hooks" in the settings file is not an object; refusing to change it.');
  }
  for (const [event, matcher] of EVENTS) {
    const groups = out.hooks?.[event];
    if (groups !== undefined && !Array.isArray(groups)) throw new Error(`"hooks.${event}" is not a list; refusing to change it.`);
    const want = desiredGroup(matcher, hookPath);
    const kept = [];
    let removed = false;
    let exact = false;
    for (const group of groups ?? []) {
      const ours = (group.hooks ?? []).filter(isOurs);
      if (ours.length === 0) {
        kept.push(group);
        continue;
      }
      removed = true;
      if (!uninstall && !exact && ours.length === 1 && JSON.stringify(group) === JSON.stringify(want)) {
        exact = true;
        kept.push(group);
        continue;
      }
      const others = group.hooks.filter((h) => !isOurs(h));
      if (others.length) kept.push({ ...group, hooks: others });
    }
    if (!uninstall && !exact) kept.push(want);
    if (uninstall && !removed) continue;
    if (kept.length) {
      out.hooks ??= {};
      out.hooks[event] = kept;
    } else if (out.hooks) {
      delete out.hooks[event];
    }
  }
  if (uninstall && out.hooks && Object.keys(out.hooks).length === 0 && settings.hooks && Object.keys(settings.hooks).length > 0) {
    delete out.hooks;
  }
  return out;
}

export function runInstall({
  settingsPath, dryRun = false, uninstall = false, hookPath = HOOK_PATH,
}) {
  const exists = existsSync(settingsPath);
  let current = {};
  if (exists) {
    const text = readFileSync(settingsPath, 'utf8');
    try {
      current = text.trim() === '' ? {} : JSON.parse(text);
    } catch (err) {
      throw new Error(`${settingsPath} is not valid JSON (${err.message}); nothing was changed.`);
    }
    if (typeof current !== 'object' || current === null || Array.isArray(current)) {
      throw new Error(`${settingsPath} does not hold a JSON object; nothing was changed.`);
    }
  }
  const next = applyHooks(current, { uninstall, hookPath });
  const nextText = `${JSON.stringify(next, null, 2)}\n`;
  const changed = JSON.stringify(next) !== JSON.stringify(current) || (!exists && !uninstall);
  if (changed && !dryRun) {
    // the first backup is the user's original file, so it is never overwritten
    if (exists && !existsSync(`${settingsPath}.bak`)) copyFileSync(settingsPath, `${settingsPath}.bak`);
    mkdirSync(dirname(settingsPath), { recursive: true });
    const tmp = `${settingsPath}.${process.pid}.tmp`;
    writeFileSync(tmp, nextText);
    renameSync(tmp, settingsPath);
  }
  return { changed, text: nextText };
}

function main(argv) {
  const args = { settingsPath: join(homedir(), '.claude', 'settings.json'), dryRun: false, uninstall: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--settings') args.settingsPath = resolve(argv[++i] ?? '');
    else if (argv[i] === '--dry-run') args.dryRun = true;
    else if (argv[i] === '--uninstall') args.uninstall = true;
    else throw new Error(`Unknown option ${argv[i]}. Use --settings <path>, --dry-run, --uninstall.`);
  }
  const { changed, text } = runInstall(args);
  if (args.dryRun) {
    process.stdout.write(`${changed ? 'Would change' : 'No change to'} ${args.settingsPath}; resulting file:\n${text}`);
  } else if (changed) {
    process.stdout.write(`plan-rigorously hooks ${args.uninstall ? 'removed from' : 'installed in'} ${args.settingsPath}\n`);
  } else {
    process.stdout.write(`No change: hooks already ${args.uninstall ? 'absent from' : 'installed in'} ${args.settingsPath}\n`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    main(process.argv.slice(2));
  } catch (err) {
    process.stderr.write(`${err.message}\n`);
    process.exit(1);
  }
}
