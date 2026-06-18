export interface User {
  id: number
  username: string
  email: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface SessionState {
  session_id: string
  user_id: string
  project_id?: string
  created_at: string
  updated_at: string
  status: 'active' | 'paused' | 'completed'
}

export interface AgentEvent {
  event_type: 'message' | 'error' | 'thinking' | 'tool_call' | 'artifact'
  timestamp: string
  agent?: string
  content?: string
  metadata?: Record<string, any>
}

export interface DatasetMeta {
  name: string
  path: string
  rows: number
  columns: number
  size_mb: number
  format: 'csv' | 'parquet' | 'json'
}

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy'
  services?: Record<string, boolean>
  timestamp?: string
}

export interface ErrorResponse {
  error: string
  message: string
  details?: Record<string, any>
  path: string
}
