import { derived, get, writable } from 'svelte/store';
import { IntlMessageFormat } from 'intl-messageformat';
import DOMPurify from 'dompurify';
import en from '../../../../backend/app/locales/en.json';
import ptBR from '../../../../backend/app/locales/pt-BR.json';
import languageNames from '../../../../backend/app/locales/languages.json';

export type Language = keyof typeof languageNames;
export type Values = Record<string, string | number | boolean | null | undefined | { key: string; values?: Values }>;
export type Message = string | { key: string; values?: Values };
export const languages: Record<Language, string> = languageNames;
const dictionaries: Record<Language, Record<string, string>> = { en, 'pt-BR': ptBR };
const storageKey = 'next-task-language';

export function supportedLanguage(value: unknown): Language | null {
  if (typeof value !== 'string') return null;
  const normalized = value.toLowerCase();
  const exact = (Object.keys(languages) as Language[]).find(key => key.toLowerCase() === normalized);
  if (exact) return exact;
  // English regional variants share a catalog; other Portuguese variants do not.
  return /^en-[a-z0-9-]+$/.test(normalized) ? 'en' : null;
}

export function resolveLanguage(...preferences: unknown[]): Language {
  return preferences.map(supportedLanguage).find((language): language is Language => language !== null) ?? 'en';
}

export function initialLanguage(): Language {
  if (typeof window === 'undefined') return 'en';
  try {
    const explicit = supportedLanguage(localStorage.getItem(storageKey));
    if (explicit) return explicit;
  } catch { /* Storage is optional in private/embedded browsers. */ }
  const query = location.hash.split('?', 2)[1];
  const hint = new URLSearchParams(query).get('lang');
  return resolveLanguage(hint, ...(navigator.languages ?? [navigator.language]));
}

export const locale = writable<Language>(initialLanguage());
locale.subscribe(language => {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = language;
  const manifest = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
  if (manifest) manifest.href = `/manifest.${language}.webmanifest`;
  try { localStorage.setItem('next-task-active-language', language); }
  catch { /* Offline copy falls back to the browser. */ }
});

export function setLanguage(language: Language, persist = true): void {
  locale.set(language);
  if (persist && typeof localStorage !== 'undefined') {
    try { localStorage.setItem(storageKey, language); }
    catch { /* Keep the in-memory choice. */ }
  }
}

export function message(key: string, values?: Values): Message { return { key, values }; }
const cache = new Map<string, IntlMessageFormat>();

function format(language: Language, key: string, values: Values = {}): string {
  const dictionary = dictionaries[language];
  const source = Object.hasOwn(dictionary, key) ? dictionary[key] : Object.hasOwn(en, key) ? en[key as keyof typeof en] : undefined;
  const fallback = dictionary['common.unavailable'];
  if (source === undefined) return fallback;
  try {
    const cacheKey = `${language}:${key}`;
    let formatter = cache.get(cacheKey);
    if (!formatter) {
      formatter = new IntlMessageFormat(source, language, undefined, { ignoreTag: true });
      cache.set(cacheKey, formatter);
    }
    const resolved = Object.fromEntries(Object.entries(values).map(([name, value]) => [name,
      value && typeof value === 'object' ? format(language, value.key, value.values) : value ?? ''
    ]));
    return String(formatter.format(resolved));
  } catch { return fallback; }
}

export const t = derived(locale, language => (key: string, values?: Values) => format(language, key, values));
export const text = derived(locale, language => (value: Message): string => {
  if (typeof value === 'string') return Object.hasOwn(en, value) ? format(language, value) : value;
  return format(language, value.key, value.values);
});
// Functions called from markup can hide their store dependencies from Svelte's compiler.
export const localized = derived<typeof locale, { <T>(value: T): T }>(locale, () => <T>(value: T): T => value);
export const numeric = derived(locale, language => (value: number, options?: Intl.NumberFormatOptions): string =>
  new Intl.NumberFormat(language, options).format(value));

function escape(value: string): string {
  const entities: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return value.replace(/[&<>"']/g, character => entities[character]);
}
export const rich = derived(locale, language => (key: string, values: Values = {}): string => {
  const escaped = Object.fromEntries(Object.entries(values).map(([name, value]) => {
    const resolved = value && typeof value === 'object' ? format(language, value.key, value.values) : value;
    return [name, typeof resolved === 'string' ? escape(resolved) : resolved];
  }));
  return DOMPurify.sanitize(format(language, key, escaped));
});
export function translate(key: string, values?: Values): string { return get(t)(key, values); }

export class LocalizedError extends Error {
  constructor(public translation: Message) {
    super(typeof translation === 'string' ? translation : get(text)(translation));
  }
}
export function errorMessage(reason: unknown, fallback: string): Message {
  return reason instanceof LocalizedError ? reason.translation : message(fallback);
}
