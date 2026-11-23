<script setup lang="ts">
import type { InjectionInfo } from "../types/skill";

defineProps<{
  injection: InjectionInfo | null;
  simulating: boolean;
  busy: boolean;
}>();

const emit = defineEmits<{
  rescan: [];
  "toggle-simulate": [enabled: boolean];
}>();

const strategyLabels: Record<string, string> = {
  full: "完整描述",
  truncated: "截断描述",
  names_only: "仅名字",
};
</script>

<template>
  <section class="debug-panel">
    <h2>调试面板</h2>
    <div class="controls">
      <button :disabled="busy" @click="emit('rescan')">重新扫描</button>
      <label class="switch">
        <input
          type="checkbox"
          :checked="simulating"
          :disabled="busy"
          @change="emit('toggle-simulate', ($event.target as HTMLInputElement).checked)"
        />
        模拟 200 个 skill
      </label>
    </div>
    <dl v-if="injection" class="stats">
      <div><dt>注入 token（估算）</dt><dd>{{ injection.tokens }} / {{ injection.budget }}</dd></div>
      <div><dt>降级档位</dt><dd>{{ strategyLabels[injection.strategy] ?? injection.strategy }}</dd></div>
      <div><dt>参与注入 skill 数</dt><dd>{{ injection.skill_count }}</dd></div>
    </dl>
  </section>
</template>

<style scoped>
.debug-panel { border-top: 1px solid #ddd; padding-top: 0.75rem; margin-top: 0.75rem; }
.controls { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
button { padding: 0.35rem 0.9rem; cursor: pointer; }
.switch { display: flex; gap: 0.35rem; align-items: center; font-size: 0.85rem; }
.stats { margin: 0.75rem 0 0; font-size: 0.85rem; }
.stats div { display: flex; justify-content: space-between; padding: 0.15rem 0; }
.stats dt { opacity: 0.7; }
.stats dd { margin: 0; font-variant-numeric: tabular-nums; }
</style>
