import { defineStore } from 'pinia'

import { api } from '../api'

export interface Finding {
  id: string
  project_id: string
  unit_id: string
  base_revision_id: string
  element_id: string
  domain: 'worldview' | 'character' | 'arc' | 'event' | 'foreshadow'
  severity: 'blocker' | 'major' | 'minor'
  source: 'ai' | 'human'
  author: string
  anchor_type: string
  anchor_id: string
  anchor_note: string
  original_excerpt: string
  diagnosis: string
  suggestion: string
  suggested_patch: Record<string, unknown>
  confidence: 'high' | 'mid' | 'low'
  status: 'open' | 'accepted' | 'dismissed' | 'stale'
  stale_reason?: string
  superseded_by?: string
  created_at: string
}

export interface ReviewTimelineEvent {
  id: string
  sequence: number
  payload: { action: string; finding_id?: string; revision_id?: string }
  occurred_at: string
}

export const useReviewStore = defineStore('review-findings', {
  state: () => ({ items: [] as Finding[], timeline: [] as ReviewTimelineEvent[], busy: '', error: '' }),
  actions: {
    async load(projectId: string) {
      this.items = await api<Finding[]>(`/projects/${projectId}/findings`)
    },
    async loadTimeline(projectId: string) {
      this.timeline = await api<ReviewTimelineEvent[]>(`/projects/${projectId}/review/timeline`)
    },
    async run(projectId: string, label: string, action: () => Promise<unknown>) {
      this.busy = label
      this.error = ''
      try { await action(); await this.load(projectId) }
      catch (error) { this.error = error instanceof Error ? error.message : '修订操作失败'; throw error }
      finally { this.busy = '' }
    },
    scan(projectId: string, unitId: string) {
      return this.run(projectId, '审读编辑正在进行五维审读…', () => api(
        `/projects/${projectId}/units/${unitId}/review/scan`,
        { method: 'POST', body: JSON.stringify({ idempotency_key: crypto.randomUUID() }) },
      ))
    },
    accept(projectId: string, findingId: string) {
      return this.run(projectId, '正在原子应用结构化修订…', () => api(
        `/projects/${projectId}/findings/${findingId}/accept`, { method: 'POST' },
      ))
    },
    dismiss(projectId: string, findingId: string) {
      return this.run(projectId, '正在记录忽略决定…', () => api(
        `/projects/${projectId}/findings/${findingId}/dismiss`, { method: 'POST' },
      ))
    },
    human(projectId: string, payload: Record<string, unknown>) {
      return this.run(projectId, '正在保存人工修订意见…', () => api(
        `/projects/${projectId}/findings`, { method: 'POST', body: JSON.stringify({
          ...payload, idempotency_key: crypto.randomUUID(),
        }) },
      ))
    },
  },
})
