import { defineStore } from 'pinia'

import { api } from '../api'

export interface RuntimeRoleStatus {
  connected: boolean
  model_key: string | null
  provider_key: string | null
  reason: string
}

export interface ActiveRun {
  run_id: string
  status: string
  created_at: string | null
}

export interface RuntimeStatus {
  connected: boolean
  roles: Record<'director' | 'architect' | 'writer' | 'reviewer', RuntimeRoleStatus>
  active_runs?: ActiveRun[]
}

export const useRuntimeStore = defineStore('agent-runtime-status', {
  state: () => ({ status: undefined as RuntimeStatus | undefined, loading: false }),
  actions: {
    async load(projectId: string) {
      this.loading = true
      try {
        this.status = await api<RuntimeStatus>(`/projects/${projectId}/agents/runtime-status`)
      } finally {
        this.loading = false
      }
    },
  },
})
