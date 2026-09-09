import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import ts from 'typescript';

// Use the project's TypeScript compiler so tests also run on the CI Node 22 runtime.
const source = readFileSync(new URL('../src/lib/format.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`;

const zones = [
  ['UTC', '09/09/2026, 01:05', '2026-09-09T01:05', '2026-09-09T14:30:00.000Z'],
  ['America/Sao_Paulo', '08/09/2026, 22:05', '2026-09-08T22:05', '2026-09-09T17:30:00.000Z'],
  ['America/New_York', '08/09/2026, 21:05', '2026-09-08T21:05', '2026-09-09T18:30:00.000Z'],
  ['Asia/Kolkata', '09/09/2026, 06:35', '2026-09-09T06:35', '2026-09-09T09:00:00.000Z']
];

for (const [zone, display, local, saved] of zones) {
  test(`fixed date/time format and UTC round trips in ${zone} with US locale`, () => {
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', `
      import assert from 'node:assert/strict';
      import { formatDate, formatDateTime, localDate, localDateTime, formatDateInput,
        parseDateInput, dateInputError, daysSince, formatRelativeTime } from '${moduleUrl}';
      const instant = '2026-09-09T01:05:00Z';
      assert.equal(formatDateTime(instant), ${JSON.stringify(display)});
      assert.equal(formatDateTime('2026-09-08T22:05:00-03:00'), ${JSON.stringify(display)});
      assert.equal(formatDate(instant), ${JSON.stringify(display.split(',')[0])});
      assert.equal(localDateTime(instant), ${JSON.stringify(local)});
      assert.equal(localDate(instant), ${JSON.stringify(local.slice(0, 10))});
      assert.equal('2026-09-08' < localDate(instant), ${local.startsWith('2026-09-09')});
      assert.equal(formatDate('2026-09-09'), '09/09/2026');
      assert.equal(formatDateTime(new Date('2026-09-09T00:00')), '09/09/2026, 00:00');
      assert.equal(formatDateInput(${JSON.stringify(local)}, true), ${JSON.stringify(display.replace(',', ''))});
      assert.equal(formatDateInput('2026-09-09'), '09/09/2026');
      assert.equal(parseDateInput('09/09/2026'), '2026-09-09');
      assert.equal(parseDateInput('09/09/2026 14:30', true), '2026-09-09T14:30');
      assert.equal(new Date(parseDateInput('09/09/2026 14:30', true)).toISOString(), ${JSON.stringify(saved)});
      assert.equal(parseDateInput('29/02/2024'), '2024-02-29');
      for (const invalid of ['29/02/2025', '31/04/2026', '09/13/2026', '00/09/2026',
        '09/00/2026', '09/09/0000', '09/09/26', '2026-09-09']) {
        assert.equal(parseDateInput(invalid), null, invalid);
        assert.ok(dateInputError(invalid));
      }
      for (const invalid of ['09/09/2026 24:00', '09/09/2026 23:60', '09/09/2026 2:30',
        '09/09/2026 02:30 PM', '09/09/2026']) assert.equal(parseDateInput(invalid, true), null);
      assert.equal(parseDateInput('', true), '');
      assert.equal(formatDateInput('', true), '');
      assert.equal(dateInputError('', true), '');
      assert.ok(dateInputError('09/09/2026 14:29', true, '2026-09-09T14:30'));
      assert.equal(dateInputError('09/09/2026 14:30', true, '2026-09-09T14:30'), '');
      assert.equal(daysSince(instant, Date.parse('2026-09-10T01:05:00Z')), 1);
      assert.equal(formatRelativeTime(instant, Date.parse('2026-09-09T02:05:00Z')), '1h ago');
      if (process.env.TZ === 'America/New_York') {
        assert.equal(parseDateInput('08/03/2026 02:30', true), null);
        assert.equal(parseDateInput('01/11/2026 01:30', true), '2026-11-01T01:30');
        assert.equal(formatDateTime('2026-01-09T14:00:00Z'), '09/01/2026, 09:00');
        assert.equal(formatDateTime('2026-07-09T14:00:00Z'), '09/07/2026, 10:00');
      }
    `], { encoding: 'utf8', env: { ...process.env, TZ: zone, LANG: 'en_US.UTF-8' } });
    assert.equal(result.status, 0, result.stderr || result.stdout);
  });
}
