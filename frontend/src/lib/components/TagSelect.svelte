<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { TagSummary } from '../api/types';
  import TagBadge from './TagBadge.svelte';

  export let options: { tag: TagSummary; depth?: number; context?: string }[] = [];
  export let value: number | '' = 0;
  export let emptyValue: number | '' = 0;
  export let emptyLabel = 'Choose a tag';
  export let disabled = false;
  export let label = 'Tag';

  const dispatch = createEventDispatcher<{ change: number | '' }>();
  let open = false;
  let root: HTMLDivElement;
  $: selectedOption = options.find(({ tag }) => tag.id === Number(value));

  function choose(next: number | '') {
    value = next;
    open = false;
    dispatch('change', next);
  }

  function closeOnBlur(event: FocusEvent) {
    if (!root.contains(event.relatedTarget as Node | null)) open = false;
  }

  function closeOnOutsideClick(event: MouseEvent) {
    if (open && root && !root.contains(event.target as Node)) open = false;
  }
</script>

<svelte:window on:click={closeOnOutsideClick} />

<div class="tag-select-control" bind:this={root} on:focusout={closeOnBlur}>
  <button type="button" class="tag-select-trigger" {disabled} aria-label={label} aria-expanded={open} aria-haspopup="listbox" on:click={() => (open = !open)} on:keydown={(event) => { if (event.key === 'Escape') open = false; }}>
    {#if selectedOption}<span class="option-copy"><TagBadge tag={selectedOption.tag} />{#if selectedOption.context && selectedOption.context !== selectedOption.tag.name}<small>{selectedOption.context}</small>{/if}</span>{:else}<span>{emptyLabel}</span>{/if}
    <span aria-hidden="true">⌄</span>
  </button>
  {#if open && !disabled}
    <div class="tag-select-options" role="listbox" aria-label={label}>
      <button type="button" role="option" aria-selected={value === emptyValue} class:chosen={value === emptyValue} on:click={() => choose(emptyValue)} on:keydown={(event) => { if (event.key === 'Escape') open = false; }}>{emptyLabel}</button>
      {#each options as option}
        <button type="button" role="option" aria-selected={value === option.tag.id} class:chosen={value === option.tag.id} style:--depth={`${option.depth || 0}rem`} on:click={() => choose(option.tag.id)} on:keydown={(event) => { if (event.key === 'Escape') open = false; }}><span class="option-copy"><TagBadge tag={option.tag} selected={value === option.tag.id} />{#if option.context && option.context !== option.tag.name}<small>{option.context}</small>{/if}</span></button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .tag-select-control { position: relative; min-width: 0; }
  .tag-select-trigger { display: flex; width: 100%; min-height: 2.55rem; align-items: center; justify-content: space-between; gap: .5rem; border: 1px solid #cfcbbf; border-radius: .55rem; background: #fff; color: var(--ink); padding: .35rem .65rem; text-align: left; }
  .tag-select-trigger:focus-visible, .tag-select-options button:focus-visible { outline: 2px solid var(--gold); outline-offset: 1px; }
  .tag-select-options { position: absolute; z-index: 15; top: calc(100% + .2rem); right: 0; left: 0; max-height: 16rem; overflow-y: auto; border: 1px solid var(--line); border-radius: .55rem; background: #fff; padding: .3rem; box-shadow: var(--shadow); }
  .tag-select-options button { display: flex; width: 100%; align-items: center; border: 0; border-radius: .35rem; background: transparent; color: var(--ink); padding: .35rem .5rem .35rem calc(.5rem + var(--depth)); text-align: left; }
  .tag-select-options button:hover, .tag-select-options button.chosen { background: #f2f3ef; }
  .option-copy { display: grid; min-width: 0; gap: .12rem; justify-items: start; }
  .option-copy small { overflow: hidden; max-width: 100%; color: var(--muted); font-size: .68rem; text-overflow: ellipsis; white-space: nowrap; }
</style>
