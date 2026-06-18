import type { AgentEvent } from './api'

export interface Session {
  session_id: string
  title: string
  created_at: string
  updated_at: string
  status: 'active' | 'archived'
  project_id?: string
}

export interface SessionDetail extends Session {
  events: AgentEvent[]
  context: {
    datasets: string[]
    artifacts: Record<string, any>
  }
}
