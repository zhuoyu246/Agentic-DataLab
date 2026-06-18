import { defineStore } from 'pinia'
import {
  api,
  openEventStream,
  type AgentEvent,
  type ApprovalRequest,
  type ArtifactEnvelope,
  type DatasetMeta,
  type SessionState,
  type WorkspaceSettings,
} from '../api/client'

function defaultSettings(): WorkspaceSettings {
  return {
    tenant_id: 'default',
    user_id: 'local-user',
    provider: 'vllm',
    model: null,
    api_key: null,
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
    targetColumn: '' as string,
    busy: false,
    error: null as string | null,
    eventSource: null as EventSource | null,
    liveAssistantMessageId: null as string | null,
    liveLines: [] as string[],
    apiKey: '' as string,
  }),
  getters: {
    datasets(state): DatasetMeta[] {
      return state.session ? Object.values(state.session.datasets) : []
    },
    artifacts(state): ArtifactEnvelope[] {
      return state.session?.artifacts ?? []
    },
    selectedDataset(state): DatasetMeta | null {
      if (!state.session || !state.selectedDatasetId) return null
      return state.session.datasets[state.selectedDatasetId] ?? null
    },
    targetOptions(state): string[] {
      if (!state.session || !state.selectedDatasetId) return []
      return state.session.datasets[state.selectedDatasetId]?.columns ?? []
    },
    pendingApprovals(state): ApprovalRequest[] {
      return state.session?.pending_approvals ?? []
    },
    pipeline(state) {
      return state.session?.pipeline ?? { nodes: [], edges: [] }
    },
  },
  actions: {
    async ensureSession() {
      if (this.session) return
      const settings = { ...this.settings, api_key: this.apiKey || null }
      this.session = await api.createSession(settings)
      this.selectedDatasetId = this.session.pipeline.active_dataset_id ?? null
      this.ensureTargetColumn()
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
    async refreshSession() {
      if (!this.session) return
      const session = await api.getSession(this.session.id)
      this.session = session
      this.selectedDatasetId = session.pipeline.active_dataset_id ?? this.selectedDatasetId
      this.ensureTargetColumn()
    },
    ensureTargetColumn() {
      const dataset = this.selectedDataset
      if (!dataset) {
        this.targetColumn = ''
        return
      }
      if (this.targetColumn && dataset.columns.includes(this.targetColumn)) return
      const candidates = ['target', 'label', 'y', 'churn', 'class', 'diagnosis', 'cancer', 'outcome', 'result', 'risk', 'disease']
      const found = dataset.columns.find((column) => {
        const lower = column.toLowerCase()
        return candidates.some((candidate) => lower === candidate || lower.includes(candidate))
      })
      this.targetColumn = found ?? dataset.columns[dataset.columns.length - 1] ?? ''
    },
    selectDataset(datasetId: string) {
      this.selectedDatasetId = datasetId
      this.targetColumn = ''
      this.ensureTargetColumn()
    },
    applyLiveEvent(event: AgentEvent) {
      if (event.type === 'approval_required' && this.session) {
        this.refreshSession().catch((err) => {
          this.error = String(err)
        })
      }

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
        this.refreshSession()
          .catch((err) => {
            this.error = String(err)
          })
          .finally(() => {
            this.liveAssistantMessageId = null
            this.liveLines = []
            this.busy = false
          })
      }
    },
    formatEventLine(event: AgentEvent) {
      const agent = event.agent_name ? `[${event.agent_name}] ` : ''
      if (event.type === 'status') return `${agent}${event.message}`
      const labels: Record<string, string> = {
        agent_start: 'started',
        agent_end: 'finished',
        artifact: 'artifact',
        approval_required: 'approval required',
        warning: 'warning',
        error: 'error',
        done: 'done',
      }
      if (labels[event.type]) return `${agent}${labels[event.type]}: ${event.message}`
      return ''
    },
    async decideApproval(approvalId: string, approved: boolean) {
      if (!this.session || this.busy) return
      this.error = null
      try {
        const sessionId = this.session.id
        await api.approve(sessionId, approvalId, approved)
        await this.refreshSession()
        if (approved && this.session) {
          this.busy = true
          const liveId = crypto.randomUUID()
          this.liveAssistantMessageId = liveId
          this.liveLines = ['[hitl] Approval accepted; resuming workflow...']
          this.session.messages.push({
            id: liveId,
            role: 'assistant',
            content: this.liveLines.join('\n'),
            created_at: new Date().toISOString(),
            agent_name: 'hitl',
            metadata: { live: true },
          })
        }
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        this.busy = false
      }
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
        this.targetColumn = ''
        await this.refreshSession()
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
        this.liveLines = ['[supervisor] Task queued; waiting for scheduler...']
        this.session.messages.push({
          id: liveId,
          role: 'assistant',
          content: this.liveLines.join('\n'),
          created_at: new Date().toISOString(),
          agent_name: 'supervisor',
          metadata: { live: true },
        })
        await api.chat(this.session.id, prompt, this.selectedDatasetId, { ...this.settings, api_key: this.apiKey || null })
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        this.liveAssistantMessageId = null
        this.liveLines = []
        this.busy = false
      }
    },
    async runWorkflow(kind: string) {
      await this.ensureSession()
      if (!this.session || !this.selectedDatasetId) {
        this.error = 'Upload or select a dataset first.'
        return
      }
      this.ensureTargetColumn()
      const target = this.targetColumn || this.targetOptions[this.targetOptions.length - 1] || ''
      const prompts: Record<string, string> = {
        eda: 'Run EDA profiling and generate data quality artifacts.',
        charts: 'Generate a visualization suite with distributions, relationships, box plots, missingness, and correlation charts.',
        features: target
          ? `Create adaptive feature engineering report target=${target}.`
          : 'Create adaptive feature engineering report.',
        classification: target
          ? `Train a classification model target=${target} and generate full diagnostics.`
          : 'Train a classification model and generate full diagnostics.',
        regression: target
          ? `Train a regression model target=${target} and generate residual diagnostics.`
          : 'Train a regression model and generate residual diagnostics.',
        clustering: 'Cluster the records into useful segments and generate cluster diagnostics.',
        anomaly: 'Detect anomalies and outliers and generate anomaly diagnostics.',
        mlflow: 'Show MLflow experiment summary and latest model run information.',
      }
      await this.send(prompts[kind] ?? kind)
    },
  },
})
