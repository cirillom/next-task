<script lang="ts">
  import { dateInputError, formatDateInput, parseDateInput } from '../format';

  export let value = '';
  export let includeTime = false;
  export let disabled = false;
  export let min = '';
  export let required = false;
  let input: HTMLInputElement;
  let textValue = '';

  $: textValue = formatDateInput(value, includeTime);
  $: if (input) input.setCustomValidity(dateInputError(textValue, includeTime, min));

  export function focus() {
    input?.focus();
  }

  function update(event: Event) {
    textValue = (event.currentTarget as HTMLInputElement).value;
    const parsed = parseDateInput(textValue, includeTime);
    if (parsed !== null) value = parsed;
    input.setCustomValidity(dateInputError(textValue, includeTime, min));
  }

  function selectFromPicker(event: Event) {
    value = (event.currentTarget as HTMLInputElement).value;
    textValue = formatDateInput(value, includeTime);
    input.setCustomValidity(dateInputError(textValue, includeTime, min));
  }

  function openPicker(event: MouseEvent) {
    const picker = event.currentTarget as HTMLInputElement;
    if (typeof picker.showPicker !== 'function') return;
    try {
      picker.showPicker();
      event.preventDefault();
    } catch {
      // Let the browser's default date-input interaction handle unsupported contexts.
    }
  }
</script>

<div class="date-time-input">
  <!-- Keep the explicit text format; the native control is used only as a visual picker. -->
  <input
    bind:this={input}
    class="text-input"
    type="text"
    value={textValue}
    placeholder={includeTime ? 'dd/mm/yyyy HH:mm' : 'dd/mm/yyyy'}
    title={includeTime ? 'dd/mm/yyyy HH:mm · 24-hour time in your device timezone' : 'dd/mm/yyyy'}
    {disabled}
    {required}
    on:input={update}
    on:focus
  />
  <label class="picker-trigger" class:disabled title={includeTime ? 'Choose date and time' : 'Choose date'}>
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3.5" y="5.5" width="17" height="15" rx="2" />
      <path d="M8 3v5M16 3v5M3.5 10h17" />
    </svg>
    <input
      class="picker-source"
      type={includeTime ? 'datetime-local' : 'date'}
      value={value}
      {min}
      step={includeTime ? 60 : undefined}
      lang="pt-BR"
      aria-label={includeTime ? 'Choose date and time' : 'Choose date'}
      {disabled}
      on:click={openPicker}
      on:change={selectFromPicker}
      on:focus
    />
  </label>
</div>

<style>
  .date-time-input {
    display: grid;
    width: 100%;
    grid-template-columns: minmax(0, 1fr) 2.55rem;
    align-items: stretch;
  }

  .date-time-input > .text-input {
    min-width: 0;
    border-radius: .55rem 0 0 .55rem;
  }

  .picker-trigger {
    position: relative;
    display: grid;
    min-width: 2.55rem;
    place-items: center;
    border: 1px solid #cfcbbf;
    border-left: 0;
    border-radius: 0 .55rem .55rem 0;
    background: #f8f7f2;
    color: var(--forest-2);
    cursor: pointer;
  }

  .picker-trigger:hover:not(.disabled) { background: #eef2ef; }
  .picker-trigger:focus-within { outline: 2px solid rgba(215, 155, 47, .45); outline-offset: 1px; }
  .picker-trigger.disabled { cursor: not-allowed; opacity: .55; }

  .picker-trigger svg {
    width: 1.15rem;
    height: 1.15rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.7;
    pointer-events: none;
  }

  .picker-trigger > .picker-source {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    opacity: 0;
    padding: 0;
    cursor: pointer;
  }

  .picker-trigger > .picker-source:focus { outline: 0; }
</style>
