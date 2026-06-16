<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { Check, SendHorizontal, X } from 'lucide-vue-next'
import { useWorkspace } from '../stores/useWorkspace'

const workspace = useWorkspace()
const prompt = ref('')
const listRef = ref<HTMLElement | null>(null)

async function send() {
  const text = prompt.value.trim()
  if (!text) return
  prompt.value = ''
  await workspace.send(text)
  await nextTick()
  listRef.value?.scrollTo({ top: listRef.value.scrollHeight, behavior: 'smooth' })
}

watch(
  () => workspace.session?.messages.map((m) => m.content).join('\n---\n'),
  async () => {
    await nextTick()
    listRef.value?.scrollTo({ top: listRef.value.scrollHeight, behavior: 'smooth' })
  },
)
</script>

<template>
  <div class="chat-layout">
    <div ref="listRef" class="messages">
      <article
        v-for="message in workspace.session?.messages ?? []"
        :key="message.id"
        class="message"
        :data-role="message.role"
        :data-live="message.metadata?.live === true"
      >
        <span>{{ message.role === 'user' ? 'You' : message.agent_name || 'DataLab' }}</span>
        <p>{{ message.content }}</p>
      </article>
    </div>

    <div v-if="workspace.pendingApprovals.length" class="approval-dock">
      <article
        v-for="approval in workspace.pendingApprovals"
        :key="approval.id"
        class="approval-card"
      >
        <header>
          <strong>{{ approval.tool_name }}</strong>
          <span>waiting approval</span>
        </header>
        <p>{{ approval.reason }}</p>
        <dl>
          <template
            v-for="[key, value] in Object.entries(approval.proposed_action).filter(([key]) => key !== 'resume_request')"
            :key="key"
          >
            <dt>{{ key }}</dt>
            <dd>{{ String(value) }}</dd>
          </template>
        </dl>
        <div class="approval-actions">
          <button type="button" title="Approve" :disabled="workspace.busy" @click="workspace.decideApproval(approval.id, true)">
            <Check :size="16" />
            Approve
          </button>
          <button type="button" title="Reject" :disabled="workspace.busy" @click="workspace.decideApproval(approval.id, false)">
            <X :size="16" />
            Reject
          </button>
        </div>
      </article>
    </div>

    <form class="composer" @submit.prevent="send">
      <textarea
        v-model="prompt"
        rows="3"
        placeholder="Ask for cleaning, EDA, SQL, visualization, AutoML, MLflow..."
        @keydown.ctrl.enter.prevent="send"
      />
      <button type="submit" :disabled="workspace.busy || !prompt.trim()" title="Send">
        <SendHorizontal :size="18" />
      </button>
    </form>
  </div>
</template>
