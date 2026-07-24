import { defineStore } from 'pinia'

import { api } from '../api'

export interface AccountSummary {
  tenant_name: string
  tier_code: string
  tier_name: string
  monthly_price: number
  monthly_quota: number
  monthly_remaining: number
  monthly_used: number
  credits_available: number
  currency: string
  period_key: string
}

export interface CreatorModel {
  id: string
  key: string
  display_name: string
  provider_name: string
  minimum_tier: string
  available: boolean
  reason?: 'disabled' | 'provider_unavailable' | 'upgrade_required'
}

export const useAccountStore = defineStore('creator-account', {
  state: () => ({ summary: null as AccountSummary | null, models: [] as CreatorModel[], busy: false }),
  actions: {
    async load(projectId?: string) {
      this.busy = true
      try {
        this.summary = await api<AccountSummary>('/account/summary')
        this.models = projectId ? await api<CreatorModel[]>(`/projects/${projectId}/models`) : []
      } finally {
        this.busy = false
      }
    },
  },
})
