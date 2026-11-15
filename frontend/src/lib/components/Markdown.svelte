<script lang="ts">
  import { afterUpdate, createEventDispatcher, getContext, onDestroy } from 'svelte';
  import { t } from '../i18n';
  import { editChecklist, renderMarkdown } from '../markdown';
  import { renderVisibleDiagrams } from '../markdownDiagrams';
  import { renderVisibleMath } from '../markdownMath';
  import { referenceNavigation, resolveReference, type ReferenceKey } from '../referenceResolver';

  export let source = '';
  export let editable = false;
  export let disabled = false;
  const dispatch = createEventDispatcher<{ input: string }>();
  const navigateReference = getContext<(target: ReferenceKey) => void>(referenceNavigation);
  let root: HTMLDivElement;
  let focusOffset: number | null = null;
  let stopDiagrams = () => {};
  let stopMath = () => {};
  $: renderedSource = source;
  $: rendered = renderMarkdown(renderedSource, editable && !disabled, $t('ui.markdownEditor.toggleChecklistItem'));

  function change(event: Event) {
    const input = event.target;
    if (!editable || disabled || !(input instanceof HTMLInputElement) || input.type !== 'checkbox') return;
    const offset = rendered.controls.get(input.dataset.markdownControl || '');
    if (offset === undefined) return;
    if (document.activeElement === input) focusOffset = offset;
    const checked = input.checked;
    input.checked = renderedSource[offset] !== ' ';
    const next = editChecklist(source, renderedSource, offset, checked);
    if (next !== null && next !== source) dispatch('input', next);
  }

  function click(event: MouseEvent) {
    const anchor = event.target instanceof Element ? event.target.closest('a') : null;
    const reference = anchor && rendered.references.get(anchor.dataset.markdownReference || '');
    if (reference) {
      event.preventDefault();
      if (anchor?.getAttribute('aria-disabled') !== 'true') navigateReference?.(reference);
      return;
    }
    const href = anchor?.getAttribute('href');
    if (!href?.startsWith(`#${rendered.footnotePrefix}`)) return;
    event.preventDefault();
    const target = document.getElementById(href.slice(1));
    if (target && root.contains(target)) {
      target.scrollIntoView({block: 'nearest'});
      target.setAttribute('tabindex', '-1');
      target.focus({preventScroll: true});
    }
  }

  function footnotes(node: HTMLDivElement) {
    node.addEventListener('click', click);
    return {destroy() { node.removeEventListener('click', click); }};
  }

  afterUpdate(() => {
    stopDiagrams();
    stopMath();
    stopDiagrams = renderVisibleDiagrams(root, rendered.diagrams);
    stopMath = renderVisibleMath(root, rendered.maths);
    if (focusOffset !== null) {
      const key = [...rendered.controls].find(([, offset]) => offset === focusOffset)?.[0];
      const input = [...root.querySelectorAll<HTMLInputElement>('input[data-markdown-control]')].find(item => item.dataset.markdownControl === key);
      if (input && !input.disabled) {
        if (document.activeElement === document.body || root.contains(document.activeElement)) input.focus();
        focusOffset = null;
      } else if (document.activeElement !== document.body && !root.contains(document.activeElement)) {
        focusOffset = null;
      }
    }
    const snapshot = rendered;
    for (const [key, reference] of snapshot.references) {
      void resolveReference(reference).then(result => {
        if (snapshot !== rendered || !root?.isConnected) return;
        const anchor = [...root.querySelectorAll<HTMLAnchorElement>('a[data-markdown-reference]')].find(item => item.dataset.markdownReference === key);
        if (!anchor) return;
        if (!result?.label) {
          anchor.textContent = reference.alias || $t('ui.markdownEditor.referenceUnavailable');
          return;
        }
        anchor.textContent = reference.alias || result.label;
        anchor.href = result.kind === 'task' ? `#/tasks?task=${result.id}` : `#/tags?tag=${result.id}`;
        anchor.removeAttribute('aria-disabled');
      });
    }
  });
  onDestroy(() => {stopDiagrams(); stopMath();});
</script>

<div bind:this={root} use:footnotes class="markdown" on:change={change}>{@html rendered.html}</div>

<style>
  .markdown :global(li:has(> input[type='checkbox'])) {
    list-style: none;
  }

  .markdown :global(input[type='checkbox']) {
    width: .95rem;
    height: .95rem;
    margin: 0 .45rem 0 -1.35rem;
    vertical-align: -.12rem;
    opacity: 1;
    accent-color: var(--forest);
  }
</style>
