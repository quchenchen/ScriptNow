export type Medium = 'script' | 'novel' | 'translation'
export type SourceMode = 'original' | 'adaptation'

export interface Session {
  tenant_id: string
  user_id: string
}

export interface Project {
  id: string
  name: string
  medium: Medium
  source_mode: SourceMode
  direction: Record<string, string>
}

export interface RunResult {
  id: string
  status: string
  config_fingerprint: string
  billed_tokens: number
}

export interface WorkspaceFile {
  id: string
  original_name: string
  media_type: string
  byte_size: number
  status: 'ready' | 'quarantined'
}
