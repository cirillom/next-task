<script lang="ts">
  export let message: string | null = null;
</script>

{#if message}
  <p class="scoring-warning" role="alert">
    {message} <a href="#/settings">Edit scoring formula</a>
  </p>
{/if}

<style>
  .scoring-warning {
    border: 1px solid #dfb777;
    border-radius: .65rem;
    background: #fff4e5;
    color: #523b1e;
    padding: .8rem 1rem;
    margin: .75rem 0 1rem;
  }
  .scoring-warning a { color: inherit; font-weight: 700; text-decoration: underline; }
</style>
