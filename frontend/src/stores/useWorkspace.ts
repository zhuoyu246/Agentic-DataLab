import { defineStore } from 'pinia'
import { api, openEventStream, type AgentEvent, type ArtifactEnvelope, type DatasetMeta, type SessionState, type WorkspaceSettings } from '../api/client'

function defaultSettings(): WorkspaceSettings {
  return {
    tenant_id: 'default',
    user_id: 'local-user',
    provider: 'vllm',
    model: null,
    use_large_planner: true,
    use_small_react_model: true,
    proactive_workflow_mode: true,
    recursion_limit: 12,
    enable_memory: true,
    require_human_approval: true,
    allow_write_sql: false,
    mlflow_enabled: true,
    h2o_enabled: true,
  }
}

export const useWorkspace = defineStore('workspace', {
  state: () => ({
    session: null as SessionState | null,
    settings: defaultSettings(),
    events: [] as AgentEvent[],
    selectedDatasetId: null as string | null,
    selectedArtifact: null as ArtifactEnvelope | null,
    busy: false,
    error: null as string | null,
    eventSource: null as EventSource | null,
    liveAssistantMessageId: null as string | null,
    liveLines: [] as string[],
  }),
  getters: {
    datasets(state): DatasetMeta[] {
      return state.session ? Object.values(state.session.datasets) : []
    },
    artifacts(state): ArtifactEnvelope[] {
      return state.session?.artifacts ?? []
    },
    pipeline(state) {
      return state.session?.pipeline ?? { nodes: [], edges: [] }
    },
  },
  actions: {
    async ensureSession() {
      if (this.session) return
      this.session = await api.createSession(this.settings)
      this.selectedDatasetId = this.session.pipeline.active_dataset_id ?? null
      this.connectEvents()
    },
    connectEvents() {
      if (!this.session || this.eventSource) return
      this.eventSource = openEventStream(this.session.id, (event) => {
        this.events.unshift(event)
        this.events = this.events.slice(0, 300)
        this.applyLiveEvent(event)
      })
    },
    applyLiveEvent(event: AgentEvent) {
      if (!this.busy || !this.session || !this.liveAssistantMessageId) return
      const line = this.formatEventLine(event)
      if (line) {
        this.liveLines.push(line)
        this.liveLines = this.liveLines.slice(-18)
        const message = this.session.messages.find((item) => item.id === this.liveAssistantMessageId)
        if (message) {
          message.content = this.liveLines.join('\n')
          message.metadata = {
            ...message.metadata,
            run_id: event.run_id ?? message.metadata.run_id,
            live: event.type !== 'done',
          }
        }
      }

      if (event.type === 'done') {
        api.getSession(this.session.id).then(session => {
          this.session = session
          this.selectedDatasetId = session.pipeline.active_dataset_id ?? this.selectedDatasetId
          this.liveAssistantMessageId = null
          this.liveLines = []
          this.busy = false
        }).catch(err => {
          this.error = String(err)
          this.liveAssistantMessageId = null
          this.liveLines = []
          this.busy = false
        })
      }
    },
    formatEventLine(event: AgentEvent) {
      const agent = event.agent_name ? `[${event.agent_name}] ` : ''
      if (event.type === 'status') return `${agent}${event.message}`
      if (event.type === 'agent_start') return `${agent}开始：${event.message}`
      if (event.type === 'agent_end') return `${agent}完成：${event.message}`
      if (event.type === 'artifact') return `${agent}产物：${event.message}`
      if (event.type === 'approval_required') return `${agent}需要审批：${event.message}`
      if (event.type === 'warning') return `${agent}降级/警告：${event.message}`
      if (event.type === 'error') return `${agent}错误：${event.message}`
      if (event.type === 'done') return `${agent}完成：${event.message}`
      return ''
    },
    async upload(file: File) {
      await this.ensureSession()
      if (!this.session) return
      this.busy = true
      this.error = null
      try {
        const res = await api.uploadDataset(this.session.id, file)
        this.session.datasets[res.dataset.id] = res.dataset
        this.selectedDatasetId = res.dataset.id
        this.session = await api.getSession(this.session.id)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.busy = false
      }
    },
    async send(prompt: string) {
      await this.ensureSession()
      if (!this.session || !prompt.trim()) return
      this.busy = true
      this.error = null
      try {
        this.session.messages.push({
          id: crypto.randomUUID(),
          role: 'user',
          content: prompt,
          created_at: new Date().toISOString(),
          metadata: {},
        })
        const liveId = crypto.randomUUID()
        this.liveAssistantMessageId = liveId
        this.liveLines = ['[supervisor] 已提交任务，等待调度...']
        this.session.messages.push({
          id: liveId,
          role: 'assistant',
          content: this.liveLines.join('\n'),
          created_at: new Date().toISOString(),
          agent_name: 'supervisor',
          metadata: { live: true },
        })
        // The endpoint now uses BackgroundTasks and returns immediately.
        // We do not wait for the final response here.
        await api.chat(this.session.id, prompt, this.selectedDatasetId, this.settings)
        // Note: busy=false is handled by applyLiveEvent when event.type === 'done'
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        this.liveAssistantMessageId = null
        this.liveLines = []
        this.busy = false
      }
    },
  },
})
