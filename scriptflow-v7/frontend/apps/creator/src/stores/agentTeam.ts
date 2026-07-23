import { defineStore } from 'pinia'

import { api } from '../api'
import type { CreatorModel } from './account'

export interface AgentTeamMember {
  role_key: string
  system_name: string
  custom_name: string | null
  soul_base: string
  soul_override: string | null
  model_id: string
  default_model_id: string
}

export const useAgentTeamStore = defineStore('creator-agent-team', {
  state: () => ({ members: [] as AgentTeamMember[], models: [] as CreatorModel[], busy: '' }),
  actions: {
    async load(projectId: string) {
      [this.members, this.models] = await Promise.all([
        api<AgentTeamMember[]>(`/projects/${projectId}/agent-team`),
        api<CreatorModel[]>(`/projects/${projectId}/models`),
      ])
    },
    async save(projectId: string, member: AgentTeamMember) {
      this.busy = member.role_key
      try {
        await api(`/projects/${projectId}/agent-team/${member.role_key}`, {
          method: 'PUT',
          body: JSON.stringify({
            custom_name: member.custom_name || null,
            soul_override: member.soul_override || null,
            model_id: member.model_id,
          }),
        })
        await this.load(projectId)
      } finally { this.busy = '' }
    },
    async reset(projectId: string, roleKey: string) {
      this.busy = roleKey
      try {
        await api(`/projects/${projectId}/agent-team/${roleKey}`, { method: 'DELETE' })
        await this.load(projectId)
      } finally { this.busy = '' }
    },
  },
})
