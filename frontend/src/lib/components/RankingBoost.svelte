<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Task } from '../api/types';

  export let task: Task;

  const dispatch = createEventDispatcher<{ open: number }>();
</script>

{#if task.ranking_source_task_id !== null && task.ranking_source_score !== null}
  <button
    type="button"
    class="ranking-boost"
    title={`Open ancestor #${task.ranking_source_task_id}. This task is ranked with that ancestor's score ${task.ranking_source_score.toFixed(1)} because unfinished descendants must appear before their ancestors.`}
    on:click={() => dispatch('open', task.ranking_source_task_id!)}
  >↑ from #{task.ranking_source_task_id} · {task.ranking_source_score.toFixed(1)}</button>
{/if}

<style>
  .ranking-boost { border: 0; border-radius: .4rem; background: transparent; color: var(--forest-2); padding: .25rem .32rem; font-size: .72rem; font-weight: 750; white-space: nowrap; }
  .ranking-boost:hover, .ranking-boost:focus-visible { background: rgba(36, 88, 68, .08); text-decoration: underline; text-underline-offset: .12rem; }
  @media (max-width: 600px) {
    .ranking-boost { font-size: .67rem; }
  }
</style>
