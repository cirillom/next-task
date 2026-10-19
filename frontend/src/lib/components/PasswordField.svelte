<script lang="ts">
  import TextField from './TextField.svelte';

  export let id: string;
  export let label: string;
  export let value = '';
  export let autocomplete: 'current-password' | 'new-password';
  export let minlength: number | undefined = undefined;
  export let required = false;
  export let disabled = false;

  let visible = false;
</script>

<div class="password-control">
  <label for={id}>{label}</label>
  <div class="password-entry">
    <TextField
      {id}
      type={visible ? 'text' : 'password'}
      bind:value
      {autocomplete}
      {minlength}
      {required}
      {disabled}
    />
    <button
      type="button"
      class="visibility-toggle"
      aria-label={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`}
      aria-pressed={visible}
      title={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`}
      {disabled}
      on:click={() => (visible = !visible)}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z" />
        <circle cx="12" cy="12" r="3" />
        {#if visible}<path d="M3 21 21 3" />{/if}
      </svg>
    </button>
  </div>
</div>

<style>
  .password-control { display: grid; gap: .4rem; }
  .password-entry { position: relative; }
  .password-entry :global(input) { padding-right: 3rem; }
  .visibility-toggle {
    position: absolute;
    right: .35rem;
    top: 50%;
    transform: translateY(-50%);
    display: grid;
    place-items: center;
    width: 2.3rem;
    height: 2.3rem;
    border: 0;
    border-radius: .4rem;
    background: transparent;
    color: var(--muted);
  }
  .visibility-toggle:hover { color: var(--forest-2); background: rgba(29, 69, 52, .08); }
  .visibility-toggle:focus-visible { outline: 2px solid var(--gold); }
  svg { width: 1.2rem; height: 1.2rem; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
</style>
