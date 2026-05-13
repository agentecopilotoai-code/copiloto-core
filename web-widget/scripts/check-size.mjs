#!/usr/bin/env node
// Fails CI if the built widget artefacts exceed the size budget defined in
// TASK-0070 (widget.js ≤ 30 KB gzipped, widget.css ≤ 5 KB gzipped). Run after
// `npm run build`.
import { readFile } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

const BUDGETS = [
  { file: 'dist/widget.js', maxGzipKb: 30 },
  { file: 'dist/widget.css', maxGzipKb: 5 },
];

let failed = false;
for (const { file, maxGzipKb } of BUDGETS) {
  const path = resolve(ROOT, file);
  let raw;
  try {
    raw = await readFile(path);
  } catch (e) {
    console.error(`[size] ${file}: missing — run \`npm run build\` first (${e.code || e.message}).`);
    failed = true;
    continue;
  }
  const gzip = gzipSync(raw);
  const gzipKb = gzip.length / 1024;
  const rawKb = raw.length / 1024;
  const ok = gzipKb <= maxGzipKb;
  const status = ok ? 'OK ' : 'FAIL';
  console.log(
    `[size] ${status} ${file}: ${rawKb.toFixed(2)} KB raw / ${gzipKb.toFixed(2)} KB gzip (budget ${maxGzipKb} KB gzip)`
  );
  if (!ok) failed = true;
}

if (failed) {
  console.error('[size] Bundle size budget exceeded.');
  process.exit(1);
}
