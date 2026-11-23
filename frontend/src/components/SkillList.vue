<script setup lang="ts">
import type { SkillsResponse } from "../types/skill";

defineProps<{ data: SkillsResponse | null }>();

const sourceLabels: Record<string, string> = {
  skills: "内置",
  "skills-extra": "团队共享",
  synthetic: "模拟",
};

function sourceLabel(dir: string): string {
  return sourceLabels[dir] ?? dir;
}
</script>

<template>
  <section class="skill-list">
    <h2>Skill 列表</h2>
    <p v-if="!data" class="muted">加载中…</p>
    <template v-else>
      <ul>
        <li v-for="skill in data.skills" :key="`${skill.source_dir}/${skill.name}`"
            :class="{ overridden: skill.status === 'overridden' }">
          <div class="row">
            <strong>{{ skill.name }}</strong>
            <span class="tag">{{ sourceLabel(skill.source_dir) }}</span>
            <span v-if="skill.status === 'overridden'" class="tag warn">
              被覆盖 ← {{ skill.overridden_by }}
            </span>
            <span v-if="skill.loaded" class="tag ok">已加载</span>
            <span class="tokens">{{ skill.tokens }} tok</span>
          </div>
          <p class="desc">{{ skill.description }}</p>
        </li>
      </ul>
      <div v-if="data.issues.length" class="issues">
        <h3>跳过的 skill（{{ data.issues.length }}）</h3>
        <div v-for="issue in data.issues" :key="issue.path" class="issue">
          <code>{{ issue.path }}</code>
          <p>{{ issue.reason }}</p>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.skill-list ul { list-style: none; margin: 0; padding: 0; max-height: 45vh; overflow-y: auto; }
.skill-list li { border: 1px solid #ddd; border-radius: 6px; padding: 0.5rem 0.75rem; margin-bottom: 0.5rem; }
.skill-list li.overridden { opacity: 0.6; border-style: dashed; }
.row { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.tag { font-size: 0.72rem; border: 1px solid #bbb; border-radius: 4px; padding: 0 0.3rem; }
.tag.warn { color: #a05a00; border-color: #a05a00; }
.tag.ok { color: #1a7f37; border-color: #1a7f37; }
.tokens { margin-left: auto; font-size: 0.75rem; opacity: 0.7; }
.desc { margin: 0.3rem 0 0; font-size: 0.8rem; opacity: 0.75; }
.muted { opacity: 0.6; }
.issues { margin-top: 0.75rem; }
.issue { border-left: 3px solid #c0392b; padding-left: 0.5rem; margin-bottom: 0.5rem; font-size: 0.8rem; }
.issue code { word-break: break-all; }
.issue p { margin: 0.2rem 0 0; color: #c0392b; }
</style>
