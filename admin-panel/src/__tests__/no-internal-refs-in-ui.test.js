import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { cwd } from 'node:process';

/**
 * Anti-regresión — strings visibles en la UI no deben contener referencias
 * internas de desarrollo. Antes este panel mostraba copy del tipo
 * "Suscripciones a resúmenes (TASK-0067)" o nombres internos de plantillas
 * de WhatsApp (digest_daily_v1), que sólo tienen sentido para el equipo
 * técnico y rompen la experiencia para el cliente final.
 *
 * Este test escanea todos los .js / .jsx de admin-panel/src/ (excluyendo
 * tests y fixtures), elimina los comentarios y verifica que no queden
 * literales de string con códigos internos de tarea / bug, nombres de
 * plantilla con sufijo _vN, ni jerga puramente técnica.
 */

// El test corre desde admin-panel/ vía vitest, por eso resolvemos absoluto.
const SRC_DIR = resolve(cwd(), 'src');

const EXCLUDED_DIRS = new Set([
  '__tests__',
  'node_modules',
]);

const EXCLUDED_FILE_PATTERNS = [
  /\.test\.(js|jsx)$/,
  /vitest\.setup\.js$/,
];

// Códigos internos de tarea / bug / seguridad / UI que aparecen en
// texto visible — con o sin paréntesis. Ej. "Suscripciones (TASK-0067)"
// o "para medir TASK-0039". BUG-233 (codex P2 sobre PR #16) — el regex
// original requería `(` antes del código y dejaba pasar el unparenthesized
// pattern, así que regresiones del mismo tipo no se bloqueaban.
//
// Usamos `\b` (word boundary) para no matchear substrings dentro de
// identificadores como `xtask_001` o `mybug-12-tracker.txt`.
const TASK_CODE_RE = /\b(?:TASK|BUG|SEC|UI)-\d+/i;

// Nombres internos de plantillas WhatsApp con sufijo _vN — ej.
// "digest_daily_v1", "subscription_payment_failed_v1".
const TEMPLATE_NAME_RE = /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+_v\d+\b/;

// Jerga puramente técnica que no debe aparecer en la UI. Lista corta y
// conservadora — no bloquea palabras que sí pueden aparecer en contextos
// legítimos para el usuario (ej. "email", "WhatsApp", "API").
const FORBIDDEN_JARGON = [
  /\bJWT\b/,
  /\bRLS\b/,
  /\brequire_min_role\b/,
  /\bensure_tenant_role\b/,
  /\bpermission_overrides\b/,
  /\bauthenticate_request\b/,
  /\brequire_platform_owner\b/,
];

function listSourceFiles(dir) {
  const entries = readdirSync(dir);
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      if (EXCLUDED_DIRS.has(entry)) continue;
      files.push(...listSourceFiles(full));
      continue;
    }
    if (!/\.(js|jsx)$/.test(entry)) continue;
    if (EXCLUDED_FILE_PATTERNS.some((pat) => pat.test(entry))) continue;
    files.push(full);
  }
  return files;
}

/**
 * Quita comentarios `/* ... *\/` y `// ...` de un fuente JS/JSX. La
 * implementación es deliberadamente simple: no parsea strings perfectamente
 * (no maneja "//" dentro de un string), pero alcanza para nuestro objetivo
 * — queremos que los códigos internos no aparezcan en NINGÚN literal de
 * string, así que falsos positivos en comentarios serían más graves que
 * falsos negativos al limpiarlos.
 */
function stripComments(source) {
  let out = source.replace(/\/\*[\s\S]*?\*\//g, '');
  out = out
    .split('\n')
    .map((line) => line.replace(/(^|[^:])\/\/.*$/, '$1'))
    .join('\n');
  return out;
}

describe('UI copy — referencias internas prohibidas', () => {
  const files = listSourceFiles(SRC_DIR);

  it('encuentra archivos para escanear', () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it('ningún .js/.jsx contiene códigos TASK/BUG/SEC/UI en strings visibles', () => {
    const violations = [];
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      const cleaned = stripComments(source);
      const match = cleaned.match(TASK_CODE_RE);
      if (match) {
        const rel = relative(SRC_DIR, file);
        const lineNumber = cleaned.slice(0, match.index).split('\n').length;
        const snippet = cleaned.split('\n')[lineNumber - 1]?.trim().slice(0, 120);
        violations.push(`${rel}:${lineNumber} → ${snippet}`);
      }
    }
    expect(
      violations,
      `Strings visibles con código interno de tarea/bug. Reescribir en lenguaje de negocio:\n  ${violations.join('\n  ')}`,
    ).toEqual([]);
  });

  it('ningún .js/.jsx expone nombres internos de plantillas WhatsApp (`_vN`)', () => {
    const violations = [];
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      const cleaned = stripComments(source);
      const match = cleaned.match(TEMPLATE_NAME_RE);
      if (match) {
        const rel = relative(SRC_DIR, file);
        const lineNumber = cleaned.slice(0, match.index).split('\n').length;
        const snippet = cleaned.split('\n')[lineNumber - 1]?.trim().slice(0, 120);
        violations.push(`${rel}:${lineNumber} → ${match[0]} (${snippet})`);
      }
    }
    expect(
      violations,
      `Strings visibles con nombre interno de plantilla. Reescribir como descripción:\n  ${violations.join('\n  ')}`,
    ).toEqual([]);
  });

  it('ningún .js/.jsx expone jerga técnica (JWT, RLS, helpers internos) en strings', () => {
    const violations = [];
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      const cleaned = stripComments(source);
      for (const pattern of FORBIDDEN_JARGON) {
        const match = cleaned.match(pattern);
        if (match) {
          const rel = relative(SRC_DIR, file);
          const lineNumber = cleaned.slice(0, match.index).split('\n').length;
          const snippet = cleaned.split('\n')[lineNumber - 1]?.trim().slice(0, 120);
          violations.push(`${rel}:${lineNumber} → ${match[0]} (${snippet})`);
        }
      }
    }
    expect(
      violations,
      `Strings visibles con jerga técnica. Reescribir en lenguaje de negocio:\n  ${violations.join('\n  ')}`,
    ).toEqual([]);
  });
});
