<script lang="ts">
  export let variant: 'primary' | 'secondary' | 'danger' | 'danger-solid' = 'secondary';
  export let type: 'button' | 'submit' | 'reset' = 'button';
  export let disabled = false;
  export let className = '';
</script>

<button {type} {disabled} class={`app-button ${variant} ${className}`} {...$$restProps} on:click><slot /></button>

<style>
  .app-button { display: inline-flex; align-items: center; justify-content: center; gap: .35rem; min-height: 2.35rem; border: 1px solid #cbc8be; border-radius: .55rem; background: #fff; color: var(--ink); padding: .48rem .8rem; font-weight: 700; line-height: 1.2; text-align: center; }
  .app-button:hover:not(:disabled) { background: #f7f5ef; }
  .app-button:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; }
  .app-button.primary { border-color: var(--forest); background: var(--forest); color: #fff; }
  .app-button.primary:hover:not(:disabled) { border-color: var(--forest-2); background: var(--forest-2); }
  .app-button.danger { border-color: #d8aaa5; color: var(--danger); }
  .app-button.danger:hover:not(:disabled) { background: #fff2f0; }
  .app-button.danger-solid { border-color: var(--danger); background: var(--danger); color: #fff; }
  .app-button.danger-solid:hover:not(:disabled) { background: #8d332b; }
</style>
