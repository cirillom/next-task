<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { NextScope, Tag } from '../api/types';
  import { emptyTagScope, withExcludedTags, withIncludedTags } from '../tagScope';
  import TagPicker from './TagPicker.svelte';

  export let tags: Tag[] = [];
  export let scope: NextScope;
  export let matchName = 'tag-scope-match';
  export let disabled = false;

  const dispatch = createEventDispatcher<{ change: NextScope }>();

  function change(next: NextScope) {
    dispatch('change', next);
  }
</script>

<div class="tag-scope-filters">
  <div class="tag-filter-heading">
    <strong>Tag filters</strong>
    <button type="button" disabled={disabled || (!scope.include_tag_ids.length && !scope.exclude_tag_ids.length && scope.tag_match === 'all')} on:click={() => change(emptyTagScope())}>Clear filters</button>
  </div>

  <div class="tag-filter-field">
    <span class="field-label">Include tags</span>
    <TagPicker {tags} selectedIds={scope.include_tag_ids} selectedLabel="Included tags" searchLabel="Search included tags" allowCreate={false} {disabled} on:change={(event) => change(withIncludedTags(scope, event.detail))} />
  </div>

  <fieldset class="tag-match" {disabled}>
    <legend>Match included tags</legend>
    <label><input type="radio" name={matchName} value="all" checked={scope.tag_match === 'all'} on:change={() => change({ ...scope, tag_match: 'all' })} /> All</label>
    <label><input type="radio" name={matchName} value="any" checked={scope.tag_match === 'any'} on:change={() => change({ ...scope, tag_match: 'any' })} /> Any</label>
  </fieldset>

  <div class="tag-filter-field">
    <span class="field-label">Exclude tags</span>
    <TagPicker {tags} selectedIds={scope.exclude_tag_ids} selectedLabel="Excluded tags" searchLabel="Search excluded tags" allowCreate={false} {disabled} on:change={(event) => change(withExcludedTags(scope, event.detail))} />
  </div>
</div>

<style>
  .tag-scope-filters, .tag-filter-field { display: grid; gap: .45rem; min-width: 0; }
  .tag-filter-heading { display: flex; align-items: center; justify-content: space-between; gap: .75rem; }
  .tag-filter-heading strong { font-size: .82rem; }
  .tag-filter-heading button { border: 0; background: transparent; color: var(--forest-2); padding: .2rem; font-size: .75rem; font-weight: 750; }
  .tag-filter-heading button:not(:disabled):hover { text-decoration: underline; }
  .tag-filter-heading button:disabled { opacity: .45; }
  .tag-match { display: flex; align-items: center; gap: .8rem; border: 0; margin: .1rem 0; padding: 0; }
  .tag-match legend { float: left; margin-right: .25rem; color: var(--muted); font-size: .72rem; font-weight: 700; }
  .tag-match label { display: inline-flex; align-items: center; gap: .3rem; font-size: .75rem; font-weight: 650; }
  .tag-match input { width: auto; margin: 0; }
</style>
