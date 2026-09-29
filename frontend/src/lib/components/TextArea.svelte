<script lang="ts">
  export let value = '';
  export let disabled = false;
  export let className = '';
</script>

<textarea {disabled} bind:value class={`app-field app-text-area ${className}`} {...$$restProps} on:input on:change on:focus on:blur></textarea>
