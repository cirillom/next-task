<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { t } from '../i18n';
  import { dialog } from '../keyboard';
  import AppButton from './AppButton.svelte';
  const dispatch = createEventDispatcher<{close: void}>();
  const shortcuts = [
    ['N', 'keyboard.newTask'], ['/', 'keyboard.search'], ['?', 'keyboard.showHelp'],
    ['keyboard.keyEscape', 'keyboard.escape'], ['keyboard.saveKeys', 'keyboard.save'],
    ['keyboard.enterKeys', 'keyboard.primary']
  ];
</script>

<div class="modal-backdrop" role="presentation" on:click|self={() => dispatch('close')}>
  <div class="shortcut-dialog panel" role="dialog" aria-modal="true" aria-labelledby="shortcut-title" use:dialog={{close: () => dispatch('close')}}>
    <header><h2 id="shortcut-title">{$t('keyboard.help')}</h2><AppButton className="icon-button" aria-label={$t('ui.blockTaskModal.close')} on:click={() => dispatch('close')}>×</AppButton></header>
    <p class="muted">{$t('keyboard.alwaysEnabled')}</p>
    <dl>{#each shortcuts as [key, description]}<div><dt><kbd>{key.startsWith('keyboard.') ? $t(key) : key}</kbd></dt><dd>{$t(description)}</dd></div>{/each}</dl>
    <p class="help">{$t('keyboard.multiline')}</p>
  </div>
</div>

<style>
  .shortcut-dialog { width: min(100%, 40rem); max-height: calc(100vh - 2rem); overflow: auto; }
  header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 1rem; }
  h2 { margin: 0; }
  dl > div { grid-template-columns: minmax(7rem, auto) 1fr; align-items: start; border-top: 1px solid var(--line); padding: .65rem 0; }
  kbd { font-size: .8rem; font-family: inherit; font-weight: 700; }
  .help { margin: 1rem 0 0; }
</style>
