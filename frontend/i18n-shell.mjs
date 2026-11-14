import { readFileSync } from 'node:fs';

const load = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const languages = load('../backend/app/locales/languages.json');
const catalogs = Object.fromEntries(Object.keys(languages).map(language => [language, load(`../backend/app/locales/${language}.json`)]));
const manifest = load('./manifest.webmanifest');
const template = readFileSync(new URL('./offline.html', import.meta.url), 'utf8');

export function shellAssets() {
  const assets = {};
  for (const [language, catalog] of Object.entries(catalogs)) {
    assets[`manifest.${language}.webmanifest`] = JSON.stringify({...manifest,
      name: catalog['ui.app.nextTask'], short_name: catalog['ui.app.nextTask'],
      description: catalog['shell.description'], lang: language});
  }
  assets['manifest.webmanifest'] = assets['manifest.en.webmanifest'];
  const messages = Object.fromEntries(Object.entries(catalogs).map(([language, catalog]) => [language,
    Object.fromEntries(['title', 'heading', 'description', 'retry'].map(key => [key, catalog[`offline.${key}`]]))]));
  const data = JSON.stringify(messages).replaceAll('<', '\u003c');
  const script = `const messages = ${data};
    let language;
    try { language = localStorage.getItem('next-task-active-language') || localStorage.getItem('next-task-language'); } catch {}
    const supported = value => typeof value === 'string' && Object.keys(messages).find(key => key.toLowerCase() === value.toLowerCase() || key === 'en' && /^en-[a-z0-9-]+$/i.test(value));
    language = supported(language) || (navigator.languages || [navigator.language]).map(supported).find(Boolean) || 'en';
    const copy = messages[language]; document.documentElement.lang = language;
    document.title = copy.title;
    for (const [selector, key] of [['h1', 'heading'], ['p', 'description'], ['button', 'retry']]) document.querySelector(selector).textContent = copy[key];`;
  assets['offline.html'] = template.replace('__TITLE__', messages.en.title).replace('__HEADING__', messages.en.heading)
    .replace('__DESCRIPTION__', messages.en.description).replace('__RETRY__', messages.en.retry).replace('__TRANSLATIONS__', script);
  return assets;
}

// Generate install/offline copy from the same catalogs in development and production.
export function localizedShell() {
  return {
    name: 'localized-shell',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const asset = shellAssets()[request.url?.split('?')[0].slice(1)];
        if (!asset) return next();
        response.setHeader('Content-Type', request.url.startsWith('/manifest') ? 'application/manifest+json' : 'text/html; charset=utf-8');
        response.end(asset);
      });
    },
    generateBundle() {
      for (const [fileName, source] of Object.entries(shellAssets())) this.emitFile({type: 'asset', fileName, source});
    }
  };
}
