<script setup lang="ts">
import { ref } from "vue";
import { sendChat } from "../api/agent";
import type { AgentChatResponse } from "../types/skill";

const props = defineProps<{ sessionId: string }>();
const emit = defineEmits<{ "turn-complete": [] }>();

interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  meta?: AgentChatResponse;
  error?: boolean;
}

const turns = ref<ChatTurn[]>([]);
const input = ref("");
const status = ref<"idle" | "loading">("idle");

async function submit() {
  const message = input.value.trim();
  if (!message || status.value === "loading") return;
  turns.value.push({ role: "user", content: message });
  input.value = "";
  status.value = "loading";
  try {
    const result = await sendChat(props.sessionId, message);
    turns.value.push({ role: "assistant", content: result.reply, meta: result });
    emit("turn-complete");
  } catch (err) {
    turns.value.push({
      role: "assistant",
      content: err instanceof Error ? err.message : String(err),
      error: true,
    });
  } finally {
    status.value = "idle";
  }
}
</script>

<template>
  <section class="chat-panel">
    <h2>对话</h2>
    <div class="turns">
      <p v-if="!turns.length" class="muted">
        试试：「写一个 8 集的逆袭短剧剧本」或「帮我写这次提交的 commit message」
      </p>
      <div v-for="(turn, index) in turns" :key="index" :class="['turn', turn.role, { error: turn.error }]">
        <p class="content">{{ turn.content }}</p>
        <div v-if="turn.meta" class="meta">
          <span v-for="(event, i) in turn.meta.events" :key="i"
                :class="['chip', { fail: !event.ok }]">
            {{ event.type === "load_skill" ? "加载 skill" : "读取文件" }}:
            {{ event.skill }}<template v-if="event.path"> / {{ event.path }}</template>
            <template v-if="!event.ok">（{{ event.error }}）</template>
          </span>
          <span class="usage">
            注入 {{ turn.meta.injection_tokens }} tok · 本轮 {{ turn.meta.usage.total_tokens }} tok
            · ¥{{ turn.meta.usage.cost.toFixed(6) }} · tool 轮次 {{ turn.meta.tool_rounds }}
          </span>
        </div>
      </div>
      <p v-if="status === 'loading'" class="muted">思考中…</p>
    </div>
    <form class="composer" @submit.prevent="submit">
      <input v-model="input" :disabled="status === 'loading'" placeholder="输入请求…" />
      <button type="submit" :disabled="status === 'loading' || !input.trim()">发送</button>
    </form>
  </section>
</template>

<style scoped>
.chat-panel { display: flex; flex-direction: column; }
.turns { min-height: 200px; max-height: 45vh; overflow-y: auto; display: flex; flex-direction: column; gap: 0.5rem; }
.turn { border-radius: 8px; padding: 0.5rem 0.75rem; max-width: 90%; }
.turn.user { align-self: flex-end; background: #e8f0fe; color: #1f2328; }
.turn.assistant { align-self: flex-start; background: #f4f4f4; color: #1f2328; }
.turn.error { background: #fdecea; color: #c0392b; }
.content { margin: 0; white-space: pre-wrap; }
.meta { margin-top: 0.4rem; display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
.chip { font-size: 0.72rem; border: 1px solid #1a7f37; color: #1a7f37; border-radius: 4px; padding: 0 0.3rem; }
.chip.fail { border-color: #c0392b; color: #c0392b; }
.usage { font-size: 0.72rem; opacity: 0.65; }
.composer { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
.composer input { flex: 1; padding: 0.45rem 0.6rem; }
.composer button { padding: 0.45rem 1rem; cursor: pointer; }
.muted { opacity: 0.6; font-size: 0.85rem; }
</style>
