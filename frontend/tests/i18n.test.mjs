import assert from 'node:assert/strict';
import { get } from 'svelte/store';
import test from 'node:test';
import { sourceModule } from './sourceModule.mjs';
const i18n = await import(sourceModule(new URL('../src/lib/i18n/index.ts', import.meta.url)));
const {setLanguage, resolveLanguage, initialLanguage, supportedLanguage, t, text, numeric, message} = i18n;

test('regional variants and unsupported values use the allowed locale registry', () => {
  for (const value of ['en', 'en-US', 'en-GB']) assert.equal(supportedLanguage(value), 'en');
  assert.equal(supportedLanguage('PT-br'), 'pt-BR');
  for (const value of ['pt', 'pt-PT', 'fr', '../en', '', null, {}, ['en']]) assert.equal(supportedLanguage(value), null);
  assert.equal(resolveLanguage('pt-BR', 'en'), 'pt-BR');
  assert.equal(resolveLanguage('fr', 'en-US'), 'en');
  assert.equal(resolveLanguage(), 'en');
});
test('signed-out selection takes precedence over link and browser hints; blocked storage is optional', (test) => {
  const replace = (name, value) => {
    const previous = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, {value, configurable: true, writable: true});
    test.after(() => previous ? Object.defineProperty(globalThis, name, previous) : delete globalThis[name]);
  };
  replace('window', {});
  replace('location', {hash: '#/accept-invite?lang=pt-BR'});
  replace('navigator', {languages: ['en-US']});
  replace('localStorage', {getItem: () => 'en', setItem() {throw new Error('blocked');}});
  assert.equal(initialLanguage(), 'en');
  globalThis.localStorage.getItem = () => {throw new Error('blocked');};
  assert.equal(initialLanguage(), 'pt-BR');
  globalThis.location.hash = '';
  globalThis.navigator.languages = ['pt-PT', 'pt-BR'];
  assert.equal(initialLanguage(), 'pt-BR');
  assert.doesNotThrow(() => setLanguage('en'));
});
test('ICU plurals, nested error parameters, locale numbers, readable fallback, and live descriptors', () => {
  const notice = message('ui.blockTaskModal.historyCount', {count: 2});
  setLanguage('en', false);
  assert.equal(get(text)(notice), '2 entries');
  assert.equal(get(t)('ui.blockTaskModal.historyCount', {count: 1}), '1 entry');
  assert.equal(get(numeric)(1234.5), '1,234.5');
  setLanguage('pt-BR', false);
  assert.equal(get(text)(notice), '2 registros');
  assert.equal(get(t)('ui.blockTaskModal.historyCount', {count: 1}), '1 registro');
  assert.equal(get(numeric)(1234.5), '1.234,5');
  assert.match(get(t)('api.scoringFallback', {reason: {key: 'api.formulaArithmeticFailed'}}), /operação aritmética/);
  assert.equal(get(t)('constructor'), get(t)('common.unavailable'));
  assert.equal(get(t)('does.not.exist'), get(t)('common.unavailable'));
  assert.equal(get(t)('validation.minLength'), get(t)('common.unavailable'));
});
