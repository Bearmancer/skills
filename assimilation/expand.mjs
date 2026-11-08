// Expands answer records (ids and ranges) into a map from unit id to its answer. Read-only helper.
export function expandAnswers(units, answers) {
  const byId = new Map(units.map((u) => [u.id, u]));
  const files = new Map();
  for (const u of units) {
    const k = u.source + ":" + u.skill + "/" + u.file;
    if (!files.has(k)) files.set(k, []);
    files.get(k).push(u);
  }
  for (const l of files.values()) l.sort((a, b) => a.seq - b.seq);
  const answered = new Map();
  for (const { rec } of answers) {
    if (!rec) continue;
    let ids = [];
    if (rec.id !== undefined) ids = byId.has(rec.id) ? [rec.id] : [];
    else if (Array.isArray(rec.range)) {
      const a = byId.get(rec.range[0]);
      const b = byId.get(rec.range[1]);
      if (a && b && a.source === b.source && a.skill === b.skill && a.file === b.file && a.seq <= b.seq) {
        ids = files.get(a.source + ":" + a.skill + "/" + a.file).slice(a.seq, b.seq + 1).map((u) => u.id);
      }
    }
    for (const id of ids) if (!answered.has(id)) answered.set(id, rec);
  }
  return { byId, answered };
}
