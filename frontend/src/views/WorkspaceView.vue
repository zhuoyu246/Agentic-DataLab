<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Database, GitBranch, MessageSquareText, LogOut } from 'lucide-vue-next'
import SidebarPanel from '../components/SidebarPanel.vue'
import ChatPanel from '../components/ChatPanel.vue'
import PipelineGraph from '../components/PipelineGraph.vue'
import ArtifactTabs from '../components/ArtifactTabs.vue'
import EventTimeline from '../components/EventTimeline.vue'
import { useWorkspace } from '../stores/useWorkspace'
import { useAuthStore } from '../stores/useAuth'

const workspace = useWorkspace()
const authStore = useAuthStore()
const router = useRouter()

onMounted(() => {
  workspace.ensureSession()
})

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <main class="app-shell">
    <aside class="sidebar">
      <SidebarPanel />
    </aside>

    <section class="workbench">
      <header class="topbar">
        <div>
          <h1>Agentic DataLab</h1>
          <p>Private multi-agent data science workspace</p>
        </div>
        <div class="api-config">
          <label>API Key</label>
          <input
            v-model="workspace.apiKey"
            type="password"
            placeholder="Optional: Enter custom API key"
            :disabled="workspace.busy"
            class="api-key-field"
          />
        </div>
        <div class="user-section">
          <span class="username">{{ authStore.user?.username }}</span>
          <button @click="handleLogout" class="logout-btn" title="登出">
            <LogOut :size="18" />
          </button>
        </div>
        <div class="status-pill" :data-busy="workspace.busy">
          {{ workspace.busy ? 'Running' : workspace.pendingApprovals.length ? 'Approval' : 'Ready' }}
        </div>
      </header>

      <div class="workspace-grid">
        <section class="panel chat-panel">
          <div class="panel-title">
            <MessageSquareText :size="18" />
            <span>Chat</span>
          </div>
          <ChatPanel />
        </section>

        <section class="panel graph-panel">
          <div class="panel-title">
            <GitBranch :size="18" />
            <span>Pipeline</span>
          </div>
          <PipelineGraph />
        </section>

        <section class="panel artifact-panel">
          <div class="panel-title">
            <Database :size="18" />
            <span>Artifacts</span>
          </div>
          <ArtifactTabs />
        </section>

        <section class="panel event-panel">
          <EventTimeline />
        </section>
      </div>
    </section>
  </main>
</template>
