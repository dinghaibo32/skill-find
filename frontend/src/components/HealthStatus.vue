<script setup lang="ts">
import { ref } from "vue";
import { fetchHealth } from "../api/health";
import type { HealthResponse } from "../types/health";

type CheckState = "idle" | "loading" | "success" | "error";

const state = ref<CheckState>("idle");
const health = ref<HealthResponse | null>(null);
const errorMessage = ref("");

async function checkHealth(): Promise<void> {
  state.value = "loading";
  errorMessage.value = "";
  try {
    health.value = await fetchHealth();
    state.value = "success";
  } catch (error) {
    health.value = null;
    errorMessage.value = error instanceof Error ? error.message : String(error);
    state.value = "error";
  }
}
</script>

<template>
  <section class="card">
    <h2>Backend health</h2>
    <p>Calls <code>GET /health</code> through the Vite dev proxy.</p>

    <button :disabled="state === 'loading'" @click="checkHealth">
      {{ state === "loading" ? "Checking..." : "Check backend health" }}
    </button>

    <p v-if="state === 'success' && health" class="result success">
      status: <strong>{{ health.status }}</strong> · service: {{ health.service }} · version:
      {{ health.version }}
    </p>
    <p v-else-if="state === 'error'" class="result error">{{ errorMessage }}</p>
  </section>
</template>

<style scoped>
.card {
  border: 1px solid rgba(128, 128, 128, 0.3);
  border-radius: 10px;
  padding: 1.5rem;
}

h2 {
  margin: 0 0 0.5rem;
  font-size: 1.2rem;
}

button {
  margin-top: 0.75rem;
  padding: 0.5rem 1.1rem;
  border: none;
  border-radius: 6px;
  background: #3b82f6;
  color: #fff;
  font-size: 0.95rem;
  cursor: pointer;
}

button:hover:not(:disabled) {
  background: #2563eb;
}

button:disabled {
  opacity: 0.6;
  cursor: wait;
}

.result {
  margin: 1rem 0 0;
  padding: 0.6rem 0.9rem;
  border-radius: 6px;
  font-size: 0.95rem;
}

.success {
  background: rgba(34, 197, 94, 0.15);
}

.error {
  background: rgba(239, 68, 68, 0.15);
}
</style>