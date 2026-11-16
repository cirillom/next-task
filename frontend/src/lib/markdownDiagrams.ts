import DOMPurify from 'dompurify';

let library: Promise<typeof import('mermaid')['default']> | null = null;
let sequence = 0;

function mermaid() {
  if (!library) library = import('mermaid').then(({default: instance}) => {
    instance.initialize({startOnLoad: false, securityLevel: 'strict', suppressErrorRendering: true, maxTextSize: 5000, maxEdges: 100, htmlLabels: false});
    return instance;
  });
  return library;
}

export function renderVisibleDiagrams(root: HTMLElement, diagrams: Map<string, string>) {
  let alive = true;
  const observer = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) {
      observer?.unobserve(entry.target);
      void render(entry.target as HTMLElement);
    }
  }, {rootMargin: '200px'});

  async function render(element: HTMLElement) {
    const source = diagrams.get(element.dataset.markdownDiagram || '');
    if (!source || source.length > 5000 || source.split('\n').length > 100 || /%%\s*\{|^\s*---|@\{|\b(?:click|href|javascript|https?|style|classDef|linkStyle|url|image)\b|</im.test(source)) return;
    try {
      const instance = await mermaid();
      if (!alive || !root.contains(element)) return;
      const result = await instance.render(`markdown-diagram-${++sequence}`, source);
      if (!alive || !root.contains(element)) return;
      const safe = DOMPurify.sanitize(result.svg, {
        RETURN_DOM_FRAGMENT: true,
        USE_PROFILES: {svg: true, svgFilters: true},
        FORBID_TAGS: ['script', 'style', 'foreignObject', 'a', 'image', 'iframe'],
        FORBID_ATTR: ['style', 'href', 'xlink:href', 'src']
      });
      for (const node of safe.querySelectorAll('*')) {
        for (const attribute of [...node.attributes]) {
          if (/url\(\s*['"]?(?!#)/i.test(attribute.value)) node.removeAttribute(attribute.name);
        }
      }
      if (safe.querySelector('svg')) element.replaceChildren(safe);
    } catch {
      // The original code block remains available when a diagram cannot render.
    }
  }

  for (const element of root.querySelectorAll<HTMLElement>('[data-markdown-diagram]')) {
    if (!diagrams.has(element.dataset.markdownDiagram || '')) continue;
    if (observer) observer.observe(element); else void render(element);
  }
  return () => { alive = false; observer?.disconnect(); };
}
