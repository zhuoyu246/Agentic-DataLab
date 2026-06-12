export type RunStatus =
  | 'queued'
  | 'running'
  | 'waiting_approval'
  | 'succeeded'
  | 'degraded'
  | 'failed'
  | 'cancelled'

export interface ChatMessage {
  id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  created_at: string
  agent_name?: string | null
  metadata: Record<string, unknown>
}

export interface WorkspaceSettings {
  tenant_id: string
  user_id: string
  provider: 'vllm' | 'openai-compatible' | 'mock'
  model?: string | null
  use_large_planner: boolean
  use_small_react_model: boolean
  proactive_workflow_mode: boolean
  recursion_limit: number
  enable_memory: boolean
  require_human_approval: boolean
  allow_write_sql: boolean
  mlflow_enabled: boolean
  h2o_enabled: boolean
}

export interface DatasetMeta {
  id: string
  label: string
  stage: string
  tenant_id: string
  shape: [number, number]
  columns: string[]
  hot: boolean
  uri?: string | null
  parent_ids: string[]
  created_by: string
  created_at: string
}

export interface DatasetPreview {
  dataset_id: string
  columns: string[]
  rows: Record<string, unknown>[]
  shape: [number, number]
  profile: Record<string, unknown>
}

export interface ArtifactEnvelope {
  id: string
  kind: string
  title: string
  dataset_id?: string | null
  payload: Record<string, unknown>
  uri?: string | null
  degraded: boolean
  error?: string | null
}

export interface PipelineNode {
  id: string
  label: string
  stage: string
  dataset_id?: string | null
  status: RunStatus
  metrics: Record<string, unknown>
}

export interface PipelineEdge {
  id: string
  source: string
  target: string
  label?: string | null
}

export interface PipelineGraph {
  nodes: PipelineNode[]
  edges: PipelineEdge[]
  active_dataset_id?: string | null
  pipeline_hash?: string | null
}

export interface SessionState {
  id: string
  name: string
  settings: WorkspaceSettings
  messages: ChatMessage[]
  datasets: Record<string, DatasetMeta>
  artifacts: ArtifactEnvelope[]
  pipeline: PipelineGraph
}

export interface AgentEvent {
  id: string
  session_id: string
  run_id?: string | null
  type: string
  status?: RunStatus | null
  agent_name?: string | null
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export interface ChatResponse {
  session_id: string
  run_id: string
  status: RunStatus
  message: ChatMessage
  artifacts: ArtifactEnvelope[]
  pipeline: PipelineGraph
  datasets: DatasetMeta[]
}

const API_PREFIX = '/api/v1'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_PREFIX}${url}`, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return (await res.json()) as T
}

export const api = {
  createSession(settings?: Partial<WorkspaceSettings>) {
    return request<SessionState>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ settings }),
    })
  },
  getSession(sessionId: string) {
    return request<SessionState>(`/sessions/${sessionId}`)
  },
  uploadDataset(sessionId: string, file: File) {
    const body = new FormData()
    body.append('file', file)
    return request<{ dataset: DatasetMeta; preview: DatasetPreview }>(
      `/sessions/${sessionId}/datasets/upload`,
      { method: 'POST', body },
    )
  },
  previewDataset(sessionId: string, datasetId: string, rows = 50) {
    return request<DatasetPreview>(`/sessions/${sessionId}/datasets/${datasetId}/preview?rows=${rows}`)
  },
  chat(sessionId: string, prompt: string, activeDatasetId?: string | null, settings?: WorkspaceSettings) {
    return request<ChatResponse>(`/sessions/${sessionId}/chat`, {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        active_dataset_id: activeDatasetId,
        settings,
        idempotency_key: crypto.randomUUID(),
      }),
    })
  },
  approve(sessionId: string, approvalId: string, approved: boolean, comment?: string) {
    return request(`/sessions/${sessionId}/approvals`, {
      method: 'POST',
      body: JSON.stringify({ approval_id: approvalId, approved, comment }),
    })
  },
}

export function openEventStream(sessionId: string, onEvent: (event: AgentEvent) => void) {
  const source = new EventSource(`${API_PREFIX}/sessions/${sessionId}/events`)
  const eventTypes = [
    'status',
    'agent_start',
    'agent_end',
    'artifact',
    'approval_required',
    'warning',
    'error',
    'done',
  ]
  for (const type of eventTypes) {
    source.addEventListener(type, (message) => {
      onEvent(JSON.parse((message as MessageEvent).data) as AgentEvent)
    })
  }
  return source
}

