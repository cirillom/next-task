<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Task } from '../api/types';
  import { daysSince, formatDate } from '../format';

  export let tasks: Task[] = [];
  export let startRank = 1;
  export let currentTaskId: number | null = null;
  export let allowFocus = false;
  export let allowUnblock = false;
  export let busyTaskId: number | null = null;

  const dispatch = createEventDispatcher<{ open: number; focus: Task; unblock: Task }>();

  function idleDays(task: Task): number {
    return daysSince(task.last_worked_at || task.created_at);
  }
</script>

<div class="queue-list">
  {#each tasks as task, index (task.id)}
    <article class:current={task.id === currentTaskId} class:blocked={!!task.current_block} class="queue-row">
      <span class="queue-rank" title={`Rank ${startRank + index}`}>{startRank + index}</span>
      <div class="queue-main">
        <button class="queue-title" on:click={() => dispatch('open', task.id)}>
          <span>{task.title}</span>
          <span class="task-id">#{task.id}</span>
        </button>
        <div class="queue-meta">
          {#if task.id === currentTaskId}<span class="current-chip">Current</span>{/if}
          {#if task.current_block}<span class="blocked-chip">Blocked</span>{/if}
          <span>Due {task.due_date ? formatDate(task.due_date) : '—'}</span>
          <span>Idle {idleDays(task)}d</span>
          <span>Priority {task.priority}</span>
          <span>{task.status.name}</span>
          <span>Score {task.score.toFixed(1)}</span>
        </div>
      </div>
      <div class="queue-actions">
        {#if allowFocus && !task.current_block && task.id !== currentTaskId}
          <button
            type="button"
            class="queue-action"
            aria-label={`Focus on ${task.title}`}
            title="Make this the current Pomodoro task"
            on:click={() => dispatch('focus', task)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 7 8 5-8 5Z" /></svg>
            <span>Focus</span>
          </button>
        {/if}
        {#if allowUnblock && task.current_block}
          <button
            type="button"
            class="queue-action"
            disabled={busyTaskId !== null}
            aria-label={`Unblock ${task.title}`}
            title="Unblock task"
            on:click={() => dispatch('unblock', task)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M7 10V8a5 5 0 0 1 9.5-2" />
              <rect x="5" y="10" width="14" height="10" rx="2" />
            </svg>
            <span>{busyTaskId === task.id ? 'Unblocking…' : 'Unblock'}</span>
          </button>
        {/if}
      </div>
    </article>
  {/each}
</div>

<style>
  .queue-list {
    display: grid;
    gap: .45rem;
  }

  .queue-row {
    display: grid;
    grid-template-columns: 2rem minmax(0, 1fr) auto;
    align-items: center;
    gap: .7rem;
    border: 1px solid rgba(100, 95, 80, .14);
    border-radius: .65rem;
    background: rgba(255, 255, 255, .62);
    padding: .7rem .8rem;
  }

  .queue-row.current {
    border-color: rgba(45, 105, 80, .35);
    box-shadow: inset 3px 0 0 var(--forest);
  }

  .queue-row.blocked {
    opacity: .78;
  }

  .queue-rank {
    display: grid;
    width: 1.75rem;
    height: 1.75rem;
    place-items: center;
    border-radius: 999px;
    background: #eeeae0;
    color: var(--muted);
    font-size: .72rem;
    font-weight: 850;
    font-variant-numeric: tabular-nums;
  }

  .queue-main {
    min-width: 0;
  }

  .queue-title {
    display: flex;
    max-width: 100%;
    align-items: baseline;
    gap: .4rem;
    overflow: hidden;
    border: 0;
    background: transparent;
    color: var(--ink);
    padding: 0;
    font: inherit;
    font-weight: 750;
    text-align: left;
  }

  .queue-title > span:first-child {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .queue-title:hover {
    color: var(--forest-2);
    text-decoration: underline;
    text-underline-offset: .15rem;
  }

  .task-id {
    flex: 0 0 auto;
    color: var(--muted);
    font-size: .7rem;
    font-weight: 750;
    opacity: .72;
  }

  .queue-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .3rem .5rem;
    margin-top: .2rem;
    color: var(--muted);
    font-size: .7rem;
  }

  .queue-meta > span {
    white-space: nowrap;
  }

  .queue-meta > span + span::before {
    content: '·';
    margin-right: .5rem;
    color: #b8b3a8;
    font-weight: 700;
  }

  .queue-meta .current-chip::before,
  .queue-meta .blocked-chip::before,
  .queue-meta .current-chip + span::before,
  .queue-meta .blocked-chip + span::before {
    content: none;
    margin: 0;
  }

  .current-chip,
  .blocked-chip {
    border-radius: 999px;
    padding: .15rem .38rem;
    font-weight: 800;
  }

  .current-chip {
    background: rgba(45, 105, 80, .1);
    color: var(--forest-2);
  }

  .blocked-chip {
    background: rgba(166, 80, 56, .1);
    color: #8e4b37;
  }

  .queue-actions {
    display: flex;
    align-items: center;
    gap: .35rem;
  }

  .queue-action {
    display: inline-flex;
    align-items: center;
    gap: .28rem;
    border: 1px solid rgba(45, 105, 80, .25);
    border-radius: .45rem;
    background: rgba(255, 255, 255, .72);
    color: var(--forest-2);
    padding: .3rem .45rem;
    font-size: .68rem;
    font-weight: 800;
    line-height: 1;
  }

  .queue-action:hover:not(:disabled) {
    border-color: rgba(45, 105, 80, .45);
    background: #fff;
  }

  .queue-action svg {
    width: .8rem;
    height: .8rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .queue-action:first-child svg {
    fill: currentColor;
    stroke: none;
  }

  @media (max-width: 720px) {
    .queue-row {
      grid-template-columns: 2rem minmax(0, 1fr);
      align-items: start;
    }

    .queue-actions {
      grid-column: 2;
    }
  }
</style>
