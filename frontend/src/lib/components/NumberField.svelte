<script lang="ts">
  export let value = 0;
  export let disabled = false;
</script>

<input type="number" {disabled} bind:value class="app-field" {...$$restProps} on:input on:change on:focus on:blur />
