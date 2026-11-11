#!/usr/bin/env node
// Claude Code hook entry: stdin JSON -> adapter -> stdout JSON. Fails open.
let raw = '';
try {
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) raw += chunk;
} catch (err) {
  process.stderr.write(`plan-rigorously: could not read stdin (${err.message})\n`);
}

if (raw.trim() !== '') {
  try {
    const input = JSON.parse(raw);
    const { formatOutput, handleHook } = await import('./lib/claude-code.mjs');
    const result = handleHook(input);
    if (result.note) process.stderr.write(`${result.note}\n`);
    const out = formatOutput(input, result);
    if (out) process.stdout.write(`${JSON.stringify(out)}\n`);
  } catch (err) {
    process.stderr.write(`plan-rigorously: ignored an unexpected error (${err.message})\n`);
  }
}
