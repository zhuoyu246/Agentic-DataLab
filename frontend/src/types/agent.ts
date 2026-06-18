export interface AgentContext {
  session_id: string
  datasets: string[]
  workspace_path: string
  artifacts: Record<string, any>
}

export interface AgentResult {
  message: string
  degraded: boolean
  artifacts?: Record<string, any>
  next_agent?: string
}

export type AgentType =
  | 'supervisor'
  | 'sql'
  | 'eda'
  | 'automl'
  | 'mlflow'
  | 'viz'

export interface AgentNode {
  id: string
  type: AgentType
  label: string
  status: 'idle' | 'running' | 'completed' | 'error'
}
