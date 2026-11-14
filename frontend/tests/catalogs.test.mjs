import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';
import { parse as parseComponent } from 'svelte/compiler';
import { IntlMessageFormat } from 'intl-messageformat';

const catalogsRoot = new URL('../../backend/app/locales/', import.meta.url);
const languages = JSON.parse(readFileSync(new URL('languages.json', catalogsRoot), 'utf8'));
const catalogs = Object.fromEntries(Object.keys(languages).map(language => [language,
  JSON.parse(readFileSync(new URL(`${language}.json`, catalogsRoot), 'utf8'))]));
function signature(nodes, result = new Map()) {
  for (const node of nodes) {
    if (node.value && node.type !== 0) {
      // plural/select cases vary by language; their parameter and kind must agree.
      result.set(node.value, node.type);
    }
    if (node.options) for (const option of Object.values(node.options)) signature(option.value, result);
    if (node.children) signature(node.children, result);
  }
  return [...result].sort(([a], [b]) => a.localeCompare(b));
}

test('all registered catalogs have the same keys and ICU parameter contracts', () => {
  const keys = Object.keys(catalogs.en).sort();
  for (const [language, catalog] of Object.entries(catalogs)) {
    assert.deepEqual(Object.keys(catalog).sort(), keys, language);
    assert.doesNotMatch(languages[language], /\p{L}\?\p{L}/u, 'Native language name must retain its accents');
    for (const key of keys) {
      assert.doesNotMatch(catalog[key], /\p{L}\?\p{L}/u, `${language}: ${key} has damaged encoding`);
      assert.ok(catalog[key].trim(), `${language}: ${key} is blank`);
      const formatter = new IntlMessageFormat(catalog[key], language, undefined, {ignoreTag: true});
      const english = new IntlMessageFormat(catalogs.en[key], 'en', undefined, {ignoreTag: true});
      assert.deepEqual(signature(formatter.getAst()), signature(english.getAst()), `${language}: ${key}`);
    }
  }
});
function files(directory) {
  return readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory);
    return entry.isDirectory() ? files(url) : [url];
  });
}
const frontendFiles = files(new URL('../src/', import.meta.url));
function walk(node, visit) {
  if (!node || typeof node !== 'object') return;
  visit(node);
  for (const [key, value] of Object.entries(node)) {
    if (['css', 'loc', 'start', 'end'].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(child => walk(child, visit));
    else if (value && typeof value === 'object') walk(value, visit);
  }
}
test('every frontend message reference exists in each catalog', () => {
  for (const file of frontendFiles.filter(file => /\.(svelte|ts)$/.test(file.pathname))) {
    const source = readFileSync(file, 'utf8');
    for (const match of source.matchAll(/['"]((?:ui|api|format|language|common|password|markdown|validation)\.[A-Za-z0-9.]+)['"]/g)) {
      for (const [language, catalog] of Object.entries(catalogs)) {
        assert.ok(Object.hasOwn(catalog, match[1]), `${file.pathname}: ${language}: ${match[1]}`);
      }
    }
  }
});
test('frontend text and accessible attribute literals live in JSON catalogs', () => {
  const failures = [];
  for (const file of frontendFiles.filter(file => file.pathname.endsWith('.svelte'))) {
    const source = readFileSync(file, 'utf8');
    const component = parseComponent(source);
    function check(node) {
      if (!node || typeof node !== 'object') return;
      if (node.type === 'Text' && /[A-Za-z\u00c0-\u024f]{2}/.test(node.data)) {
        failures.push(`${file.pathname}: ${node.data.trim()}`);
      }
      if (node.type === 'Attribute') {
        if (['title', 'aria-label', 'placeholder', 'label', 'emptyLabel', 'submitLabel', 'busyLabel', 'cancelLabel', 'pickerLabel', 'pickerText', 'selectedLabel', 'searchLabel', 'draftSubmitLabel', 'draftBusyLabel'].includes(node.name)) {
          for (const value of node.value || []) if (value.type === 'Text' && value.data.trim()) failures.push(`${file.pathname}: ${node.name}=${value.data}`);
        }
        return; // class names, URLs, SVG paths and protocol values are not copy.
      }
      if (node.type === 'Comment') return;
      for (const [key, value] of Object.entries(node)) {
        if (['attributes', 'expression'].includes(key)) {
          if (key === 'attributes') value.forEach(check);
          continue;
        }
        if (Array.isArray(value)) value.forEach(check);
        else if (value && typeof value === 'object') check(value);
      }
    }
    check(component.html);
    walk(component.instance, node => {
      if (node.type === 'Literal' && typeof node.value === 'string' && (/[A-Za-z]{2,}[ ]+[A-Za-z]{2,}/.test(node.value) || /^[A-Z]{2,}$/.test(node.value) && !['TEXTAREA', 'INPUT', 'BUTTON', 'DIV', 'GET', 'POST', 'PUT', 'DELETE', 'PATCH'].includes(node.value)) && !/^(?:https?:|\.|#|\[|<|--)/.test(node.value)) {
        failures.push(`${file.pathname}: script: ${node.value}`);
      }
    });
  }
  assert.deepEqual(failures, []);
});
