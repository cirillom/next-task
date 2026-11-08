import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/api/client.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
}).outputText;
const { request, ApiError } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
);

for (const [detail, expected] of [
  ['Wait one minute before sending another email', 'Wait one minute before sending another email'],
  [[{ msg: 'Value error, Enter a valid email address' }], 'Enter a valid email address'],
  [null, 'Request failed (422)']
]) {
  test(`API error shows ${expected}`, async (t) => {
    t.mock.method(globalThis, 'fetch', async () => new Response(
      JSON.stringify({ detail }), { status: 422 }
    ));
    await assert.rejects(request('/api/auth/email'), (error) =>
      error instanceof ApiError && error.status === 422 && error.message === expected
    );
  });
}
