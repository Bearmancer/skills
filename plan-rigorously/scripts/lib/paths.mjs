// Pure path helpers shared by the core. Plan files are written by a model, so
// declared paths may use either separator; real paths follow the platform.

export const IS_WIN = process.platform === 'win32';

export function foldCase(p) {
  return IS_WIN ? p.toLowerCase() : p;
}

/** Forward slashes, no leading "./", no doubled slashes. */
export function normRel(p) {
  return String(p)
    .trim()
    .replace(/\\/g, '/')
    .replace(/^(\.\/)+/, '')
    .replace(/\/{2,}/g, '/');
}

/** Relative and not escaping the repo root. */
export function isSafeRel(p) {
  if (!p) return false;
  if (/^([\\/]|[A-Za-z]:|~)/.test(p)) return false;
  return !normRel(p).split('/').includes('..');
}

export function samePath(a, b) {
  return foldCase(normRel(a)) === foldCase(normRel(b));
}

/** Only `*` and `?` are wildcards; `[ ] { }` are ordinary characters (src/pages/[id].tsx). */
export function hasGlob(p) {
  return /[*?]/.test(p);
}

/**
 * A Creates pattern may use wildcards in the final file-name segment only, never `**`; a wildcard
 * name must not start with a dot and needs a letter or digit, so `*` and `.*` cannot cover dotfiles.
 */
export function creatableGlobOk(p) {
  const segs = normRel(p).split('/');
  const last = segs.pop();
  if (segs.some(hasGlob) || last.includes('**')) return false;
  return !hasGlob(last) || (!last.startsWith('.') && /[A-Za-z0-9]/.test(last));
}

/** Glob with `*`, `**` and `?` only. */
export function globToRegExp(glob) {
  const g = normRel(glob);
  let out = '';
  for (let i = 0; i < g.length; i++) {
    const c = g[i];
    if (c === '*') {
      if (g[i + 1] === '*') {
        if (g[i + 2] === '/') {
          out += '(?:.*/)?';
          i += 2;
        } else {
          out += '.*';
          i += 1;
        }
      } else {
        out += '[^/]*';
      }
    } else if (c === '?') {
      out += '[^/]';
    } else {
      out += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
    }
  }
  return new RegExp(`^${out}$`, IS_WIN ? 'i' : '');
}

export function matchesPathSpec(spec, rel) {
  const s = normRel(spec);
  const r = normRel(rel);
  return hasGlob(s) ? globToRegExp(s).test(r) : samePath(s, r);
}
