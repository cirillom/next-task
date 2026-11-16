import DOMPurify from 'dompurify';
import { Marked, Renderer, type Token, type Tokens } from 'marked';
import { GFM, parser } from '@lezer/markdown';
import footnote from 'marked-footnote';
import hljs from 'highlight.js/lib/core';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import python from 'highlight.js/lib/languages/python';
import json from 'highlight.js/lib/languages/json';
import bash from 'highlight.js/lib/languages/bash';
import sql from 'highlight.js/lib/languages/sql';
import type { ReferenceKey } from './referenceResolver';

const markdown = new Marked({ gfm: true });
const taskParser = parser.configure(GFM);
for (const [name, language] of Object.entries({javascript, typescript, python, json, bash, sql})) hljs.registerLanguage(name, language);
const escapeHtml = (value: string) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
markdown.use(footnote(), {extensions: [{
  name: 'reference', level: 'inline',
  start: source => source.indexOf('[['),
  tokenizer(source) {
    const match = /^\[\[(task|tag):([1-9]\d{0,15})(?:\|([^\]\r\n]*))?\]\]/.exec(source);
    if (match && Number.isSafeInteger(Number(match[2]))) return {type: 'reference', raw: match[0], kind: match[1], id: Number(match[2]), alias: match[3]};
  },
  renderer(token) { return `<a data-markdown-reference="${token.key}" aria-disabled="true">${escapeHtml(token.alias || token.raw)}</a>`; }
}, {
  name: 'inlineMath', level: 'inline',
  start: source => source.indexOf('$'),
  tokenizer(source) {
    const match = /^(\${1,2})(?!\$)((?:\\.|[^\\\n$])*?(?:\\.|[^\\\n$]))\1(?=[\s?!.,:]|$)/.exec(source);
    if (match) return {type: 'inlineMath', raw: match[0], text: match[2].trim(), display: match[1].length === 2};
  },
  renderer(token) { return `<span data-markdown-math="${token.key}">${escapeHtml(token.raw)}</span>`; }
}, {
  name: 'blockMath', level: 'block',
  tokenizer(source) {
    const match = /^(\${1,2})\n((?:\\[^]|[^\\])+?)\n\1(?:\n|$)/.exec(source);
    if (match) return {type: 'blockMath', raw: match[0], text: match[2].trim(), display: match[1].length === 2};
  },
  renderer(token) { return `<div data-markdown-math="${token.key}">${escapeHtml(token.raw)}</div>`; }
}, {
  name: 'highlight', level: 'inline',
  start: source => source.indexOf('=='),
  tokenizer(source) {
    const match = /^==(?=\S)([\s\S]*?\S)==/.exec(source);
    if (match) return {type: 'highlight', raw: match[0], tokens: this.lexer.inlineTokens(match[1])};
  },
  renderer(token) { return `<mark>${this.parser.parseInline(token.tokens || [])}</mark>`; }
}]});

function lex(source: string) {
  const tokens = markdown.lexer(source);
  if (markdown.defaults.walkTokens) markdown.walkTokens(tokens, markdown.defaults.walkTokens);
  // marked-footnote retains its counter between lex-only calls.
  const footnotes = new Map<string, string>();
  markdown.walkTokens(tokens, token => {
    if (token.type !== 'footnoteRef' || typeof token.label !== 'string') return;
    if (!footnotes.has(token.label)) footnotes.set(token.label, String(footnotes.size + 1));
    token.id = footnotes.get(token.label);
  });
  return tokens;
}

export function parsedReferences(source: string): (ReferenceKey & {raw: string; alias: string | null})[] {
  const result: (ReferenceKey & {raw: string; alias: string | null})[] = [];
  markdown.walkTokens(lex(source), token => {
    if (token.type === 'reference' && (token.kind === 'task' || token.kind === 'tag') && typeof token.id === 'number') {
      result.push({kind: token.kind, id: token.id, raw: token.raw, alias: typeof token.alias === 'string' ? token.alias : null});
    }
  });
  return result;
}

export function parsedHighlights(source: string): string[] {
  const result: string[] = [];
  markdown.walkTokens(lex(source), token => { if (token.type === 'highlight') result.push(token.raw); });
  return result;
}

export function parsedInlineMath(source: string): {raw: string; source: string; display: boolean}[] {
  const result: {raw: string; source: string; display: boolean}[] = [];
  markdown.walkTokens(lex(source), token => {
    if (token.type === 'inlineMath' && typeof token.text === 'string') result.push({raw: token.raw, source: token.text, display: !!token.display});
  });
  return result;
}

export function parsedFootnotes(source: string) {
  const references: {raw: string; label: string; id: string}[] = [];
  const definitions: {raw: string; label: string}[] = [];
  markdown.walkTokens(lex(source), token => {
    if (token.type === 'footnoteRef' && typeof token.label === 'string' && typeof token.id === 'string') references.push({raw: token.raw, label: token.label, id: token.id});
    if (token.type === 'footnote' && typeof token.label === 'string') definitions.push({raw: token.raw, label: token.label});
  });
  const positions = new Map<string, number>();
  taskParser.parse(source).iterate({enter(node) {
    if (node.name !== 'Paragraph' && node.name !== 'LinkReference') return;
    const text = source.slice(node.from, node.to).replace(/\r\n?/g, '\n');
    const definition = definitions.find(item => item.raw.trimEnd() === text.trimEnd());
    if (definition && !positions.has(definition.label)) positions.set(definition.label, node.from);
  }});
  return {references, positions};
}

export function checklistOffsets(source: string, tokens: Token[] = lex(source)): Map<Tokens.ListItem, number> {
  const markedItems: Tokens.ListItem[] = [];
  markdown.walkTokens(tokens, (token) => {
    if (token.type === 'list_item') markedItems.push(token as Tokens.ListItem);
  });
  const parsed: { firstLine: string; marker: number | null }[] = [];
  taskParser.parse(source).iterate({ enter(node) {
    if (node.name !== 'ListItem') return;
    const mark = node.node.getChild('ListMark');
    const marker = node.node.getChild('Task')?.getChild('TaskMarker');
    if (!mark) return;
    const end = source.indexOf('\n', mark.from);
    parsed.push({
      firstLine: source.slice(mark.from, end < 0 ? source.length : end).replace(/\r$/, ''),
      marker: marker ? marker.from + 1 : null
    });
  }});
  const offsets = new Map<Tokens.ListItem, number>();
  if (markedItems.length !== parsed.length) return offsets;
  for (let i = 0; i < markedItems.length; i++) {
    const item = markedItems[i];
    const found = parsed[i];
    if (item.raw.split('\n', 1)[0].replace(/\r$/, '') !== found.firstLine || item.task !== (found.marker !== null)) {
      return new Map();
    }
    if (item.task && found.marker !== null) {
      if (!' xX'.includes(source[found.marker]) || !!item.checked !== (source[found.marker] !== ' ')) return new Map();
      offsets.set(item, found.marker);
    }
  }
  return offsets;
}

export function editChecklist(source: string, base: string, offset: number, checked: boolean): string | null {
  if (source !== base || !Number.isInteger(offset) || offset < 1 || !' xX'.includes(source[offset] || '') || source[offset - 1] !== '[' || source[offset + 1] !== ']') return null;
  if ((source[offset] !== ' ') === checked) return source;
  return source.slice(0, offset) + (checked ? 'x' : ' ') + source.slice(offset + 1);
}

export function renderMarkdown(source: string, interactive = false, checkboxLabel = '') {
  try {
    const tokens = lex(source);
    const offsets = checklistOffsets(source, tokens);
    const nonce = Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16)).join('-');
    const controls = new Map<string, number>();
    const generated = new Set<string>();
    const diagrams = new Map<string, string>();
    const maths = new Map<string, { source: string; display: boolean }>();
    const references = new Map<string, ReferenceKey & { alias: string | null }>();
    const tables = new Map<string, {from: number; to: number; html: string}>();
    const callouts = new Map<string, {from: number; to: number; html: string}>();
    const diagramBlocks = new Map<string, {from: number; to: number; html: string}>();
    const codeBlocks = new Map<string, {from: number; to: number; html: string}>();
    const mathBlocks = new Map<string, {from: number; to: number; html: string}>();
    const inlineLinks = new Map<string, {from: number; to: number; html: string}>();
    const linkKeys = new Map<Token, string>();
    const tableKeys = new Map<Tokens.Table, string>();
    const calloutPositions = new Map<Tokens.Blockquote, {from: number; to: number}>();
    const codePositions = new Map<Tokens.Code, {from: number; to: number}>();
    const mathPositions = new Map<Token, {from: number; to: number}>();
    const markedTables: Tokens.Table[] = [];
    const parsedTables: {from: number; to: number; firstLine: string}[] = [];
    markdown.walkTokens(tokens, token => { if (token.type === 'table') markedTables.push(token as Tokens.Table); });
    taskParser.parse(source).iterate({enter(node) {
      if (node.name !== 'Table') return;
      const end = source.indexOf('\n', node.from);
      parsedTables.push({from: node.from, to: node.to, firstLine: source.slice(node.from, end < 0 ? source.length : end).replace(/\r$/, '')});
    }});
    if (markedTables.length === parsedTables.length && markedTables.every((table, index) => table.raw.split('\n', 1)[0].replace(/\r$/, '') === parsedTables[index].firstLine)) {
      markedTables.forEach((table, index) => {
        const key = `${nonce}-${index}`;
        tableKeys.set(table, key);
        tables.set(key, {...parsedTables[index], html: ''});
      });
    }
    function locateBlocks<T extends Tokens.Blockquote | Tokens.Code>(kind: 'blockquote' | 'code', names: string[], output: Map<T, {from: number; to: number}>) {
      const markedBlocks: T[] = [];
      const parsedBlocks: {from: number; to: number; firstLine: string}[] = [];
      markdown.walkTokens(tokens, token => { if (token.type === kind) markedBlocks.push(token as T); });
      taskParser.parse(source).iterate({enter(node) {
        if (!names.includes(node.name)) return;
        const end = source.indexOf('\n', node.from);
        parsedBlocks.push({from: node.from, to: node.to, firstLine: source.slice(node.from, end < 0 ? source.length : end).replace(/\r$/, '')});
      }});
      if (markedBlocks.length === parsedBlocks.length && markedBlocks.every((block, index) => block.raw.split('\n', 1)[0].replace(/\r$/, '') === parsedBlocks[index].firstLine)) {
        markedBlocks.forEach((block, index) => output.set(block, parsedBlocks[index]));
      }
    }
    if (source.includes('[!')) locateBlocks('blockquote', ['Blockquote'], calloutPositions);
    if (/```|~~~|^ {4}/m.test(source)) locateBlocks('code', ['FencedCode', 'CodeBlock'], codePositions);
    if (source.includes(']')) {
      const markedLinks: Token[] = [];
      const parsedLinks: {from: number; to: number; raw: string}[] = [];
      markdown.walkTokens(tokens, token => {if (token.type === 'link' || token.type === 'image') markedLinks.push(token);});
      taskParser.parse(source).iterate({enter(node) {
        if (node.name === 'Link' || node.name === 'Image') {
          const raw = source.slice(node.from, node.to);
          if (!/^\[\^[^\]\n]+\]$/.test(raw)) parsedLinks.push({from: node.from, to: node.to, raw});
        }
      }});
      if (markedLinks.length === parsedLinks.length && markedLinks.every((link, index) => link.raw === parsedLinks[index].raw)) {
        markedLinks.forEach((link, index) => {
          const key = `${nonce}-${index}`;
          linkKeys.set(link, key);
          inlineLinks.set(key, {...parsedLinks[index], html: ''});
        });
      }
    }
    if (source.includes('$')) {
      const markedBlocks: Token[] = [];
      const parsedBlocks: {from: number; to: number; raw: string}[] = [];
      markdown.walkTokens(tokens, token => {if (token.type === 'blockMath') markedBlocks.push(token);});
      taskParser.parse(source).iterate({enter(node) {
        if (node.name !== 'Paragraph') return;
        const raw = source.slice(node.from, node.to).replace(/\r\n?/g, '\n');
        if (/^\${1,2}\n/.test(raw)) parsedBlocks.push({from: node.from, to: node.to, raw});
      }});
      if (markedBlocks.length === parsedBlocks.length && markedBlocks.every((block, index) => block.raw.trimEnd() === parsedBlocks[index].raw.trimEnd())) {
        markedBlocks.forEach((block, index) => mathPositions.set(block, parsedBlocks[index]));
      }
    }
    let nextControl = 0;
    markdown.walkTokens(tokens, token => {
      if ((token.type === 'inlineMath' || token.type === 'blockMath') && typeof token.text === 'string') {
        const key = `${nonce}-${maths.size}`;
        token.key = key;
        maths.set(key, {source: token.text, display: !!token.display});
        const position = mathPositions.get(token);
        if (position) mathBlocks.set(key, {...position, html: ''});
      }
      if (token.type === 'reference' && (token.kind === 'task' || token.kind === 'tag') && typeof token.id === 'number') {
        const key = `${nonce}-${references.size}`;
        token.key = key;
        references.set(key, {kind: token.kind, id: token.id, alias: typeof token.alias === 'string' ? token.alias : null});
      }
    });
    const renderer = new Renderer();
    const table = renderer.table;
    renderer.table = function (token) {
      const html = table.call(this, token);
      const key = tableKeys.get(token);
      return key ? `<div data-markdown-table="${key}">${html}</div>` : html;
    };
    const blockquote = renderer.blockquote;
    renderer.blockquote = function (token) {
      const first = token.tokens[0];
      if (first?.type !== 'paragraph') return blockquote.call(this, token);
      const match = /^\[!(note|abstract|info|todo|tip|success|question|warning|failure|danger|bug|example|quote)\]([+-]?)[ \t]*([^\n]*)(?:\n|$)/i.exec(first.raw);
      if (!match) return blockquote.call(this, token);
      const remaining = first.raw.slice(match[0].length);
      const items = [...token.tokens.slice(1)];
      if (remaining) {
        if (!first.tokens) return blockquote.call(this, token);
        const initial = first.tokens[0];
        if (initial?.type !== 'text' || !initial.raw.startsWith(match[0]) || !initial.text.startsWith(match[0])) return blockquote.call(this, token);
        const inline = [...first.tokens];
        inline[0] = {...initial, raw: initial.raw.slice(match[0].length), text: initial.text.slice(match[0].length)};
        items.unshift({...first, raw: remaining, text: first.text.slice(match[0].length), tokens: inline});
      }
      const title = escapeHtml(match[3].trim() || match[1]);
      const body = this.parser.parse(items);
      const position = calloutPositions.get(token);
      const key = `${nonce}-${callouts.size}`;
      if (position) callouts.set(key, {...position, html: ''});
      const attribute = position ? ` data-markdown-callout="${key}"` : '';
      if (match[2]) return `<details class="callout"${attribute}${match[2] === '+' ? ' open' : ''}><summary>${title}</summary>${body}</details>`;
      return `<aside class="callout"${attribute}><strong>${title}</strong>${body}</aside>`;
    };
    const code = renderer.code;
    renderer.code = function (token) {
      const language = token.lang?.trim().split(/\s+/, 1)[0]?.toLowerCase();
      if (language === 'mermaid') {
        const key = `${nonce}-${diagrams.size}`;
        diagrams.set(key, token.text);
        const position = codePositions.get(token);
        if (position) diagramBlocks.set(key, {...position, html: ''});
        return `<pre data-markdown-diagram="${key}"><code>${escapeHtml(token.text)}</code></pre>\n`;
      }
      const html = !language || !hljs.getLanguage(language) ? code.call(this, token)
        : `<pre><code class="hljs language-${escapeHtml(language)}">${hljs.highlight(token.text, {language}).value}</code></pre>\n`;
      const position = codePositions.get(token);
      if (!position) return html;
      const key = `${nonce}-${codeBlocks.size}`;
      codeBlocks.set(key, {...position, html: ''});
      return `<div data-markdown-code="${key}">${html}</div>`;
    };
    const link = renderer.link;
    renderer.link = function (token) {
      const html = link.call(this, token);
      const key = linkKeys.get(token);
      return key ? html.replace('<a ', `<a data-markdown-link="${key}" `) : html;
    };
    const image = renderer.image;
    renderer.image = function (token) {
      const key = linkKeys.get(token);
      return image.call(this, token).replace('<img ', `<img loading="lazy" ${key ? `data-markdown-link="${key}" ` : ''}`);
    };
    const safeLabel = checkboxLabel.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    renderer.checkbox = ({ checked }) => `<input ${checked ? 'checked="" ' : ''}disabled="" type="checkbox" aria-label="${safeLabel}">`;
    const listitem = renderer.listitem;
    renderer.listitem = function (item) {
      const html = listitem.call(this, item);
      if (!item.task) return html;
      const offset = offsets.get(item);
      const key = `${nonce}-${nextControl++}`;
      generated.add(key);
      if (offset !== undefined) controls.set(key, offset);
      return html.replace(/<input ([^>]*?)>/, (_match, attributes: string) =>
        `<input data-markdown-control="${key}" ${interactive && offset !== undefined ? attributes.replace('disabled="" ', '') : attributes}>`);
    };
    const fragment = DOMPurify.sanitize(markdown.parser(tokens, { ...markdown.defaults, renderer }) as string, {
      RETURN_DOM_FRAGMENT: true,
      FORBID_TAGS: ['form', 'button', 'textarea', 'select', 'option', 'style', 'script', 'iframe', 'object', 'embed', 'svg', 'math', 'audio', 'video', 'source', 'link', 'meta', 'base'],
      FORBID_ATTR: ['style']
    });
    for (const input of fragment.querySelectorAll('input')) {
      if (!generated.has(input.dataset.markdownControl || '')) input.remove();
    }
    for (const element of fragment.querySelectorAll<HTMLAnchorElement | HTMLImageElement>('a[href], img[src]')) {
      const attribute = element.tagName === 'A' ? 'href' : 'src';
      const value = element.getAttribute(attribute) || '';
      try {
        const url = new URL(value, document.baseURI);
        if (!(attribute === 'href' ? ['http:', 'https:', 'mailto:', 'tel:'] : ['http:', 'https:']).includes(url.protocol)) element.removeAttribute(attribute);
      } catch {
        element.removeAttribute(attribute);
      }
      if (attribute === 'href') element.setAttribute('rel', 'noopener noreferrer');
    }
    for (const element of fragment.querySelectorAll<HTMLElement>('[data-markdown-reference]')) {
      if (!references.has(element.dataset.markdownReference || '')) element.removeAttribute('data-markdown-reference');
    }
    for (const element of fragment.querySelectorAll('[id^="footnote-"]')) element.id = `${nonce}-${element.id}`;
    for (const anchor of fragment.querySelectorAll('a[href^="#footnote-"]')) anchor.setAttribute('href', `#${nonce}-${anchor.getAttribute('href')!.slice(1)}`);
    for (const element of fragment.querySelectorAll('[aria-describedby="footnote-label"]')) element.setAttribute('aria-describedby', `${nonce}-footnote-label`);
    for (const [key, entry] of tables) {
      const element = fragment.querySelector(`[data-markdown-table="${key}"]`);
      if (element) entry.html = element.outerHTML;
    }
    for (const [key, entry] of callouts) {
      const element = fragment.querySelector(`[data-markdown-callout="${key}"]`);
      if (element) entry.html = element.outerHTML;
    }
    for (const [key, entry] of diagramBlocks) {
      const element = fragment.querySelector(`[data-markdown-diagram="${key}"]`);
      if (element) entry.html = element.outerHTML;
    }
    for (const [key, entry] of codeBlocks) {
      const element = fragment.querySelector(`[data-markdown-code="${key}"]`);
      if (element) entry.html = element.outerHTML;
    }
    for (const [key, entry] of mathBlocks) {
      const element = fragment.querySelector(`[data-markdown-math="${key}"]`);
      if (element) entry.html = element.outerHTML;
    }
    for (const [key, entry] of inlineLinks) {
      const element = fragment.querySelector(`[data-markdown-link="${key}"]`);
      if (element) entry.html = element.outerHTML;
    }
    const container = document.createElement('div');
    container.append(fragment);
    return { html: container.innerHTML, controls, diagrams, maths, references, tables, callouts, diagramBlocks, codeBlocks, mathBlocks, inlineLinks, footnotePrefix: `${nonce}-footnote-` };
  } catch {
    return {
      html: `<pre>${escapeHtml(source)}</pre>`,
      controls: new Map<string, number>(),
      diagrams: new Map<string, string>(),
      maths: new Map<string, {source: string; display: boolean}>(),
      references: new Map<string, ReferenceKey & {alias: string | null}>(),
      tables: new Map<string, {from: number; to: number; html: string}>(),
      callouts: new Map<string, {from: number; to: number; html: string}>(),
      diagramBlocks: new Map<string, {from: number; to: number; html: string}>(),
      codeBlocks: new Map<string, {from: number; to: number; html: string}>(),
      mathBlocks: new Map<string, {from: number; to: number; html: string}>(),
      inlineLinks: new Map<string, {from: number; to: number; html: string}>(),
      footnotePrefix: ''
    };
  }
}
