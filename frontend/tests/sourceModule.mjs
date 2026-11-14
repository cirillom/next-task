import { existsSync, readFileSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const modules = new Map();

// Compile source modules without a second build or a Node-version-specific TS loader.
export function sourceModule(file) {
  const url = file instanceof URL ? file : pathToFileURL(file);
  if (modules.has(url.href)) return modules.get(url.href);
  if (url.pathname.endsWith('.json')) return asModule(`export default ${readFileSync(url, 'utf8')}`);
  let source = ts.transpileModule(readFileSync(url, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
  }).outputText;
  source = source.replace(/(from\s*|import\s*)['"]([^'"]+)['"]/g, (match, prefix, name) => {
    if (!name.startsWith('.')) return `${prefix}${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`;
    let dependency = new URL(name, url);
    if (!existsSync(dependency) || statSync(dependency).isDirectory()) {
      dependency = new URL(name + (existsSync(new URL(name + '.ts', url)) ? '.ts' : '/index.ts'), url);
    }
    return `${prefix}${JSON.stringify(sourceModule(dependency))}`;
  });
  const compiled = asModule(source);
  modules.set(url.href, compiled);
  return compiled;
}
function asModule(source) { return `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`; }
