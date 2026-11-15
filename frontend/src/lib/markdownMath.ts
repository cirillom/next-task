import DOMPurify from 'dompurify';

export function renderVisibleMath(root: HTMLElement, maths: Map<string, { source: string; display: boolean }>) {
  let alive = true;
  const observer = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) {
      observer?.unobserve(entry.target);
      void render(entry.target as HTMLElement);
    }
  }, {rootMargin: '200px'});

  async function render(element: HTMLElement) {
    const math = maths.get(element.dataset.markdownMath || '');
    if (!math || math.source.length > 10000) return;
    try {
      const {default: katex} = await import('katex');
      if (!alive || !root.contains(element)) return;
      const html = katex.renderToString(math.source, {displayMode: math.display, output: 'mathml', throwOnError: false, trust: false, maxExpand: 100, maxSize: 50});
      const safe = DOMPurify.sanitize(html, {RETURN_DOM_FRAGMENT: true, USE_PROFILES: {mathMl: true}, FORBID_ATTR: ['style']});
      if (safe.querySelector('math')) element.replaceChildren(safe);
    } catch {
      // The original math source remains available when rendering fails.
    }
  }

  for (const element of root.querySelectorAll<HTMLElement>('[data-markdown-math]')) {
    if (!maths.has(element.dataset.markdownMath || '')) continue;
    if (observer) observer.observe(element); else void render(element);
  }
  return () => {alive = false; observer?.disconnect();};
}
