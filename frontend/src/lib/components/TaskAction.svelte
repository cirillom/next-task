<script lang="ts">
  export let label: string;
  export let icon: 'finish' | 'reopen' | 'worked' | 'block' | 'abandon' | 'restore';
  export let disabled = false;
  export let active = false;
  export let compact = true;
  export let title = '';
  export let ariaLabel = '';
  export let className = '';
</script>

<button type="button" class={`task-action ${icon} ${className}`} class:active class:compact {disabled} title={title || label} aria-label={ariaLabel || label} on:click>
  <svg viewBox="0 0 24 24" aria-hidden="true">
    {#if icon === 'finish'}
      <path d="m5 12.5 4.2 4.2L19 7" />
    {:else if icon === 'reopen' || icon === 'restore'}
      <path d="M4.8 9A8 8 0 1 1 4 14M4 4v5h5" />
    {:else if icon === 'worked'}
      <circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3.2 2" />
    {:else if icon === 'block'}
      <circle cx="12" cy="12" r="8.5" /><path d="M6 18 18 6" />
    {:else}
      <path d="M3 4h18v4H3zM5 8v12h14V8M10 12h4" />
    {/if}
  </svg>
  <span>{label}</span>
</button>

<style>
  .task-action { display: inline-flex; align-items: center; justify-content: center; gap: .38rem; flex-shrink: 0; height: var(--task-action-height, 2rem); border: 1px solid #cbc8be; border-radius: .55rem; background: #fff; color: var(--ink); padding: 0 var(--task-action-padding, .62rem); font-size: var(--task-action-font-size, .78rem); font-weight: 700; line-height: 1; white-space: nowrap; }
  .task-action:hover:not(:disabled) { border-color: #aaa69c; background: #f7f5ef; }
  .task-action:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; }
  svg { width: 1rem; height: 1rem; flex: 0 0 1rem; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
  .finish { border-color: var(--forest); background: var(--forest); color: #fff; font-weight: 800; }
  .finish:hover:not(:disabled) { border-color: var(--forest-2); background: var(--forest-2); }
  .reopen { border-color: #b9c3bd; color: var(--forest-2); }
  .worked { color: var(--forest-2); }
  .block { color: #8a4d36; }
  .block.active { border-color: #d8b5a6; background: #fff4ee; }
  @media (max-width: 600px) {
    .compact { width: var(--task-action-height, 2rem); padding: 0; }
    .compact span { display: none; }
  }
</style>
