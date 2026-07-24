import { defineStore } from 'pinia'

import { api } from '../api'

export interface NovelState {
  phase: string
  creative_language: string
  story_cores: Array<{
    id: string
    ordinal: number
    title: string
    premise: string
    point_of_view: string
    narrative_constraints: string[]
    angles: string[]
    status: 'active' | 'adopted' | 'expired'
  }>
  blueprint: null | {
    id: string
    version: number
    anchors: Array<{ id: string; kind: string; name: string; payload: Record<string, unknown> }>
  }
  blueprint_candidates: Array<{
    id: string
    status: 'active' | 'adopted' | 'expired'
    anchors: Array<{ id: string; kind: string; name: string; payload: Record<string, unknown> }>
  }>
  story_map: {
    id: string
    version: number
    volumes: Array<{
      id: string
      ordinal: number
      title: string
      chapters: Array<{
        id: string
        ordinal: number
        title: string
        target_words: number
        point_of_view?: string
        beats?: Array<{ id: string; objective: string; anchor_ids: string[] }>
      }>
    }>
  }
  story_map_candidates: Array<{
    id: string
    status: 'active' | 'adopted' | 'expired'
    base_version: number
    volumes: NovelState['story_map']['volumes']
    impact: { added_units: number; removed_units: number; retained_units: number }
  }>
  documents: Array<{
    id: string
    chapter_id: string
    revision_number: number
    parent_revision_id?: string | null
    source?: 'agent' | 'human'
    status: string
    blocks: Array<{ block_id: string; type: string; text: string }>
  }>
}

interface CandidateResponse { id: string; status: string }

export function selectChapterDocument(documents: NovelState['documents'], chapterId: string) {
  const matching = documents.filter((item) => item.chapter_id === chapterId)
  const latestCandidate = matching
    .filter((item) => item.status === 'candidate' || item.status === 'active')
    .sort((left, right) => right.revision_number - left.revision_number)[0]
  const latestAdopted = matching
    .filter((item) => item.status === 'adopted')
    .sort((left, right) => right.revision_number - left.revision_number)[0]
  return latestCandidate && (!latestAdopted || latestCandidate.revision_number > latestAdopted.revision_number)
    ? latestCandidate
    : latestAdopted
}

export const useNovelStore = defineStore('novel-domain', {
  state: () => ({ state: null as NovelState | null, busy: '', error: '' }),
  actions: {
    async load(projectId: string) {
      this.state = await api<NovelState>(`/novel/projects/${projectId}/state`)
    },
    async perform(projectId: string, label: string, action: () => Promise<unknown>) {
      this.busy = label
      this.error = ''
      try {
        const result = await action()
        await this.load(projectId)
        return result
      } catch (error) {
        this.error = error instanceof Error ? error.message : '操作失败'
        throw error
      } finally {
        this.busy = ''
      }
    },
    generateCores(projectId: string, feedback?: string) {
      return this.perform(projectId, '灵感导演正在发散三个小说方向…', () =>
        api(`/novel/projects/${projectId}/story-cores/generate`, {
          method: 'POST',
          body: JSON.stringify({ idempotency_key: crypto.randomUUID(), feedback: feedback || null }),
        }),
      )
    },
    adoptCore(projectId: string, candidateId: string) {
      return this.perform(projectId, '正在锁定小说方向…', () =>
        api(`/novel/projects/${projectId}/story-cores/${candidateId}/adopt`, { method: 'POST' }),
      )
    },
    generateBlueprint(projectId: string, feedback?: string) {
      return this.perform(projectId, feedback ? '故事建筑师正在根据反馈重构蓝图…' : '故事建筑师正在建立小说蓝图候选…', () =>
        api<CandidateResponse>(`/novel/projects/${projectId}/blueprints/generate`, {
          method: 'POST', body: JSON.stringify({ idempotency_key: crypto.randomUUID(), feedback: feedback || null }),
        }),
      )
    },
    adoptBlueprint(projectId: string, candidateId: string) {
      return this.perform(projectId, '正在采纳小说蓝图…', () =>
        api(`/novel/projects/${projectId}/blueprints/${candidateId}/adopt`, { method: 'POST' }),
      )
    },
    generateStoryMap(projectId: string, feedback?: string) {
      return this.perform(projectId, '正在规划卷与章节候选…', () =>
        api<CandidateResponse>(`/novel/projects/${projectId}/story-map/generate`, {
          method: 'POST', body: JSON.stringify({ idempotency_key: crypto.randomUUID(), feedback: feedback || null }),
        }),
      )
    },
    adoptStoryMap(projectId: string, candidateId: string) {
      return this.perform(projectId, '正在确认卷章 StoryMap…', () =>
        api(`/novel/projects/${projectId}/story-map/${candidateId}/adopt`, { method: 'POST' }),
      )
    },
    proposeStoryMap(
      projectId: string,
      expectedVersion: number,
      volumes: NovelState['story_map']['volumes'],
    ) {
      return this.perform(projectId, '正在保存卷章调整候选…', () =>
        api<CandidateResponse>(`/novel/projects/${projectId}/story-map/propose`, {
          method: 'POST',
          body: JSON.stringify({
            expected_version: expectedVersion,
            volumes,
            idempotency_key: crypto.randomUUID(),
          }),
        }),
      )
    },
    generateChapter(
      projectId: string,
      chapterId: string,
      options: { feedback?: string; sourceRevisionId?: string } = {},
    ) {
      return this.perform(projectId, '主笔正在写作章节…', async () => {
        return api<CandidateResponse>(
          `/novel/projects/${projectId}/chapters/${chapterId}/generate`,
          {
            method: 'POST',
            body: JSON.stringify({
              idempotency_key: crypto.randomUUID(),
              feedback: options.feedback,
              source_revision_id: options.sourceRevisionId,
            }),
          },
        )
      })
    },
    adoptChapter(projectId: string, chapterId: string, revisionId: string) {
      return this.perform(projectId, '正在采纳章节修订…', () =>
        api(`/novel/projects/${projectId}/chapters/${chapterId}/revisions/${revisionId}/adopt`, {
          method: 'POST',
        }),
      )
    },
    saveManualChapterRevision(
      projectId: string,
      chapterId: string,
      revisionId: string,
      blocks: NovelState['documents'][number]['blocks'],
    ) {
      return this.perform(projectId, '正在保存人工修订版本…', () =>
        api<CandidateResponse>(
          `/novel/projects/${projectId}/chapters/${chapterId}/revisions/${revisionId}/manual`,
          {
            method: 'POST',
            body: JSON.stringify({ idempotency_key: crypto.randomUUID(), blocks }),
          },
        ),
      )
    },
  },
})
