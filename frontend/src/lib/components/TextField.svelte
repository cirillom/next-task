<script lang="ts">
  export let value = '';
  export let type: 'text' | 'search' | 'password' | 'email' = 'text';
  export let className = '';
  export let disabled = false;
</script>

<input {type} {disabled} bind:value class={`app-field app-text-field ${className}`} {...$$restProps} on:input on:change on:focus on:blur on:keydown />
