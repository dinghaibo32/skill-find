<script setup lang="ts">
import HealthStatus from "./components/HealthStatus.vue";
</script>

<template>
  <header>
    <h1>skill-find</h1>
    <p class="subtitle">FastAPI + Vue 3 + TypeScript skeleton</p>
  </header>
  <main>
    <HealthStatus />
  </main>
</template>

<style scoped>
h1 {
  margin: 0 0 0.25rem;
  font-size: 1.75rem;
}

.subtitle {
  margin: 0 0 2rem;
  opacity: 0.65;
}
</style>