<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchEvalResults, runEvals } from "../api/evals";
import type { EvalReport } from "../types/skill";

const report = ref<EvalReport | null>(null);
const status = ref<"idle" | "loading" | "error">("idle");
const errorMessage = ref("");

onMounted(async () => {
  try {
    report.value = await fetchEvalResults();
  } catch {
    // cached results are optional on first load
  }
});

async function run() {
  status.value = "loading";
  errorMessage.value = "";
  try {
    report.value = await runEvals();
    status.value = "idle";
  } catch (err) {
    status.value = "error";
    errorMessage.value = err instanceof Error ? err.message : String(err);
  }
}
</script>

<template>
  <section class="eval-table">
    <div class="header">
      <h2>路由评测</h2>
      <button :disabled="status === 'loading'" @click="run">
        {{ status === "loading" ? "评测中（20 条真实调用）…" : "运行评测" }}
      </button>
    </div>
    <p v-if="status === 'error'" class="error">{{ errorMessage }}</p>
    <template v-if="report && report.results.length">
      <p class="summary">
        通过 {{ report.summary.passed }} / {{ report.summary.total }}
        （{{ (report.summary.accuracy * 100).toFixed(1) }}%）
        <span v-for="(bucket, category) in report.summary.by_category" :key="category" class="cat">
          {{ category }}: {{ bucket.passed }}/{{ bucket.total }}
        </span>
      </p>
      <table>
        <thead>
          <tr><th>#</th><th>请求</th><th>类别</th><th>期望</th><th>实际</th><th>结果</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in report.results" :key="row.id">
            <td>{{ row.id }}</td>
            <td class="query">{{ row.query }}</td>
            <td>{{ row.category }}</td>
            <td>{{ row.expected_skill ?? "（无/澄清）" }}</td>
            <td>
              <template v-if="row.actual">{{ row.actual.action }}<template v-if="row.actual.skill">: {{ row.actual.skill }}</template></template>
              <template v-else>error</template>
            </td>
            <td :class="row.passed ? 'pass' : 'fail'">{{ row.passed ? "✓" : "✗" }}</td>
          </tr>
        </tbody>
      </table>
    </template>
    <p v-else-if="status !== 'loading'" class="muted">尚无评测结果，点击「运行评测」发起 20 条真实路由评测。</p>
  </section>
</template>

<style scoped>
.eval-table { border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 0.75rem; }
.header { display: flex; align-items: center; justify-content: space-between; }
.header button { padding: 0.35rem 0.9rem; cursor: pointer; }
.summary { font-size: 0.85rem; }
.cat { margin-left: 0.6rem; opacity: 0.7; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th, td { border-bottom: 1px solid #eee; padding: 0.3rem 0.4rem; text-align: left; }
.query { max-width: 320px; }
.pass { color: #1a7f37; font-weight: bold; }
.fail { color: #c0392b; font-weight: bold; }
.error { color: #c0392b; }
.muted { opacity: 0.6; font-size: 0.85rem; }
</style>
