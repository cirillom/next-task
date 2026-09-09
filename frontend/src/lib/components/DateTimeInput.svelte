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
</script>

<!-- Native date/time controls follow browser/OS locale even when lang is set. -->
<input
  bind:this={input}
  type="text"
  value={textValue}
  placeholder={includeTime ? 'dd/mm/yyyy HH:mm' : 'dd/mm/yyyy'}
  title={includeTime ? 'dd/mm/yyyy HH:mm · 24-hour time in your device timezone' : 'dd/mm/yyyy'}
  {disabled}
  {required}
  on:input={update}
  on:focus
/>
