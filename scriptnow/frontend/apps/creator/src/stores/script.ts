import { defineStore } from 'pinia'

import { api } from '../api'

export interface ScriptCore {
  id: string
  generation: number
  ordinal: number
  title: string
  concept: string
  angles: string[]
  details: Record<string, string[]>
  status: 'active' | 'adopted' | 'expired'
  revision_feedback?: string
}

export interface ScriptState {
  phase: string
  script_format: 'chinese' | 'hollywood'
  story_cores: ScriptCore[]
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
    episodes: Array<{
      id: string
      ordinal: number
      title: string
      scenes: Array<{
        id: string
        ordinal: number
        title: string
        duration_seconds_target: number
        beats?: Array<{ id: string; objective: string; anchor_ids: string[] }>
      }>
    }>
  }
  story_map_candidates: Array<{
    id: string
    status: 'active' | 'adopted' | 'expired'
    base_version: number
    episodes: ScriptState['story_map']['episodes']
    impact: { added_units: number; removed_units: number; retained_units: number }
  }>
  documents: Array<{
    id: string
    scene_id: string
    revision_number: number
    status: string
    blocks: Array<{ para_id: string; type: string; text: string }>
  }>
}

interface AdoptResponse {
  id: string
  status: string
}

interface SceneRunResponse extends AdoptResponse {
  run_id: string
  operation_id: string
  creative_session_id: string
}

interface SceneRunState {
  id: string
  status: 'queued' | 'running' | 'waiting' | 'succeeded' | 'failed' | 'cancelled'
  error_code?: string | null
}

const SCENE_RUN_POLL_INTERVAL_MS = 500
const SCENE_RUN_TIMEOUT_MS = 10 * 60 * 1000

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds))

export const useScriptStore = defineStore('script-domain', {
  state: () => ({ state: null as ScriptState | null, busy: '', error: '' }),
  actions: {
    async load(projectId: string) {
      this.state = await api<ScriptState>(`/script/projects/${projectId}/state`)
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
      return this.perform(projectId, '正在发散三个方向…', () =>
        api(`/script/projects/${projectId}/story-cores/generate`, {
          method: 'POST',
          body: JSON.stringify({ idempotency_key: crypto.randomUUID(), feedback: feedback || null }),
        }),
      )
    },
    adoptCore(projectId: string, candidateId: string) {
      return this.perform(projectId, '正在采纳故事方向…', () =>
        api(`/script/projects/${projectId}/story-cores/${candidateId}/adopt`, { method: 'POST' }),
      )
    },
    generateBlueprint(projectId: string, feedback?: string) {
      return this.perform(projectId, feedback ? '故事建筑师正在根据反馈修订蓝图…' : '故事建筑师正在规划蓝图候选…', () =>
        api<AdoptResponse>(`/script/projects/${projectId}/blueprints/generate`, {
          method: 'POST',
          body: JSON.stringify({ idempotency_key: crypto.randomUUID(), feedback: feedback || null }),
        }),
      )
    },
    adoptBlueprint(projectId: string, candidateId: string) {
      return this.perform(projectId, '正在采纳蓝图…', () =>
        api(`/script/projects/${projectId}/blueprints/${candidateId}/adopt`, { method: 'POST' }),
      )
    },
    generateStoryMap(projectId: string) {
      return this.perform(projectId, '正在生成分集与场次候选…', () =>
        api<AdoptResponse>(`/script/projects/${projectId}/story-map/generate`, {
          method: 'POST',
          body: JSON.stringify({ idempotency_key: crypto.randomUUID() }),
        }),
      )
    },
    adoptStoryMap(projectId: string, candidateId: string) {
      return this.perform(projectId, '正在确认 StoryMap…', () =>
        api(`/script/projects/${projectId}/story-map/${candidateId}/adopt`, { method: 'POST' }),
      )
    },
    proposeStoryMap(
      projectId: string,
      expectedVersion: number,
      episodes: ScriptState['story_map']['episodes'],
    ) {
      return this.perform(projectId, '正在保存结构调整候选…', () =>
        api<AdoptResponse>(`/script/projects/${projectId}/story-map/propose`, {
          method: 'POST',
          body: JSON.stringify({
            expected_version: expectedVersion,
            episodes,
            idempotency_key: crypto.randomUUID(),
          }),
        }),
      )
    },
    generateSceneCandidate(projectId: string, sceneId: string, feedback?: string) {
      return this.perform(projectId, '主笔正在生成场景候选…', async () => {
        const queued = await api<SceneRunResponse>(
          `/script/projects/${projectId}/scenes/${sceneId}/generate?background=true`,
          {
            method: 'POST',
            body: JSON.stringify({
              idempotency_key: crypto.randomUUID(),
              feedback: feedback || null,
            }),
          },
        )
        const deadline = Date.now() + SCENE_RUN_TIMEOUT_MS
        while (Date.now() < deadline) {
          const run = await api<SceneRunState>(
            `/script/projects/${projectId}/runs/${queued.run_id}`,
          )
          if (run.status === 'succeeded') return queued
          if (run.status === 'failed') {
            throw new Error(`场次候选稿生成失败${run.error_code ? `：${run.error_code}` : ''}`)
          }
          if (run.status === 'cancelled') throw new Error('场次候选稿生成已取消')
          await wait(SCENE_RUN_POLL_INTERVAL_MS)
        }
        throw new Error('场次候选稿生成超时，请在创作搭档中检查运行状态')
      })
    },
    adoptSceneCandidate(projectId: string, sceneId: string, revisionId: string) {
      return this.perform(projectId, '正在确认场景正文…', () =>
        api(
          `/script/projects/${projectId}/scenes/${sceneId}/revisions/${revisionId}/adopt`,
          { method: 'POST' },
        ),
      )
    },
  },
})
