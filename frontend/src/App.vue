<script setup lang="ts">
import { onMounted, ref } from "vue";
import HealthStatus from "./components/HealthStatus.vue";
import SkillList from "./components/SkillList.vue";
import DebugPanel from "./components/DebugPanel.vue";
import ChatPanel from "./components/ChatPanel.vue";
import EvalTable from "./components/EvalTable.vue";
import { fetchSkills, rescanSkills, setSimulate } from "./api/skills";
import type { SkillsResponse } from "./types/skill";

const sessionId = crypto.randomUUID();
const skillsData = ref<SkillsResponse | null>(null);
const simulating = ref(false);
const busy = ref(false);
const loadError = ref("");

async function refresh() {
  try {
    skillsData.value = await fetchSkills(sessionId);
    loadError.value = "";
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err);
  }
}

async function handleRescan() {
  busy.value = true;
  try {
    skillsData.value = await rescanSkills(sessionId);
    loadError.value = "";
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

async function handleSimulate(enabled: boolean) {
  busy.value = true;
  try {
    skillsData.value = await setSimulate(enabled, sessionId);
    simulating.value = enabled;
    loadError.value = "";
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

onMounted(refresh);
</script>

<template>
  <header>
    <div>
      <h1>skill-find</h1>
      <p class="subtitle">Skill 系统演示：发现 · 注入 · 按需加载 · 热更新</p>
    </div>
    <HealthStatus />
  </header>
  <p v-if="loadError" class="load-error">Skill 列表加载失败：{{ loadError }}</p>
  <main class="layout">
    <aside>
      <SkillList :data="skillsData" />
      <DebugPanel
        :injection="skillsData?.injection ?? null"
        :simulating="simulating"
        :busy="busy"
        @rescan="handleRescan"
        @toggle-simulate="handleSimulate"
      />
    </aside>
    <section class="right">
      <ChatPanel :session-id="sessionId" @turn-complete="refresh" />
      <EvalTable />
    </section>
  </main>
</template>

<style scoped>
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
h1 { margin: 0 0 0.25rem; font-size: 1.75rem; }
.subtitle { margin: 0 0 1rem; opacity: 0.65; }
.layout { display: grid; grid-template-columns: 360px 1fr; gap: 1.5rem; align-items: start; }
.load-error { color: #c0392b; }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
}
</style>
