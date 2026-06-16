<script setup lang="ts">
import { onMounted } from 'vue'
import { Database, GitBranch, MessageSquareText } from 'lucide-vue-next'
import SidebarPanel from './components/SidebarPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import PipelineGraph from './components/PipelineGraph.vue'
import ArtifactTabs from './components/ArtifactTabs.vue'
import EventTimeline from './components/EventTimeline.vue'
import { useWorkspace } from './stores/useWorkspace'

const workspace = useWorkspace()

onMounted(() => {
  workspace.ensureSession()
})
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
