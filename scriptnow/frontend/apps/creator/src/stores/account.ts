import { defineStore } from 'pinia'

import { ApiError, api } from '../api'

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
  context_window: number
  available: boolean
  reason?: 'disabled' | 'provider_unavailable' | 'upgrade_required'
}

export const useAccountStore = defineStore('creator-account', {
  state: () => ({
    summary: null as AccountSummary | null,
    models: [] as CreatorModel[],
    summaryBusy: false,
    modelsBusy: false,
    summaryError: '',
    modelsError: '',
  }),
  getters: {
    busy: (state) => state.summaryBusy || state.modelsBusy,
  },
  actions: {
    async loadSummary() {
      this.summaryBusy = true
      this.summaryError = ''
      try {
        this.summary = await api<AccountSummary>('/account/summary')
      } catch (error) {
        this.summaryError = accountErrorMessage(error)
      } finally {
        this.summaryBusy = false
      }
    },
    async loadModels(projectId?: string) {
      this.modelsBusy = true
      this.modelsError = ''
      try {
        this.models = projectId ? await api<CreatorModel[]>(`/projects/${projectId}/models`) : []
      } catch {
        this.models = []
        this.modelsError = '模型池暂时无法读取，不影响账户额度信息。'
      } finally {
        this.modelsBusy = false
      }
    },
    setModelsError(message: string) {
      this.models = []
      this.modelsError = message
    },
    async load(projectId?: string) {
      await Promise.all([this.loadSummary(), this.loadModels(projectId)])
    },
  },
})

function accountErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return '账户额度尚未初始化，请联系管理员完成账户配置。'
    if (error.status === 401) return '登录状态已失效，请重新登录。'
  }
  return '账户信息暂时无法读取，请稍后重试。'
}
