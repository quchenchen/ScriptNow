import { defineStore } from 'pinia'

import { api, ApiError } from '../api'

export type DockEventType = 'chat' | 'node' | 'decision' | 'system'
export type DockFilter = 'focus' | DockEventType

const DOCK_WIDTH_KEY = 'scriptnow-ui-agent-dock-width'
const DOCK_HEIGHT_KEY = 'scriptnow-ui-agent-dock-height'
const LEGACY_PREFIX = 'scriptflow-ui-'

function storedDockSize(key: string, fallback: number, minimum: number, maximum: number): number {
  if (typeof window === 'undefined') return fallback
  const legacyKey = key.replace('scriptnow-ui-', LEGACY_PREFIX)
  const stored = window.localStorage.getItem(key) ?? window.localStorage.getItem(legacyKey)
  if (stored !== null && !window.localStorage.getItem(key)) {
    window.localStorage.setItem(key, stored)
    window.localStorage.removeItem(legacyKey)
  }
  const value = Number(stored)
  return Number.isFinite(value) && value >= minimum && value <= maximum ? value : fallback
}

export interface DockEvent {
  id: string
  run_id?: string
  type: DockEventType
  title: string
  payload: Record<string, unknown>
  occurred_at: string
  group_key?: string
  count: number
  cursor_id?: string
}

export function isFocusEvent(event: DockEvent): boolean {
  return event.type === 'chat' || event.type === 'decision' || ['failed', 'waiting'].includes(String(event.payload.status ?? ''))
}

export function eventBody(title: string, content: unknown): string | undefined {
  if (typeof content !== 'string') return undefined
  const body = content.trim()
  const heading = title.trim()
  if (!body || body === heading) return undefined
  return body
}

export interface DockRun {
  id: string
  status: 'queued' | 'running' | 'waiting' | 'succeeded' | 'failed' | 'cancelled'
  waiting_reason?: string
  state_version: number
  created_at: string
}

export interface StreamBlock {
  id: string
  type: string
  block: 'thinking' | 'tool' | 'data' | 'text' | 'system'
  phase?: string
  title?: string
  text?: string
  data?: Record<string, unknown>
  runtime?: string
  duration_ms?: number
}

export interface DockQuote {
  medium: 'script' | 'novel'
  operation: 'expand' | 'shorten' | 'polish' | 'revise'
  unit_id: string
  revision_id: string
  element_id: string
  excerpt: string
}

interface Transparency {
  context_tokens: number
  context_limit: number
  context_percent: number | null
  memory_entries: number
  role: string
  connected: boolean
}

interface SelectionProposal {
  id: string
  medium: 'script' | 'novel'
  unit_id: string
  base_revision_id: string
  element_id: string
  operation: DockQuote['operation']
  excerpt: string
  status: string
  diff: { before: string; after: string }
}

function parseSse(raw: string): StreamBlock[] {
  return raw.split('\n\n').flatMap((frame) => {
    if (!frame.trim()) return []
    const lines = frame.split('\n')
    const id = lines.find((line) => line.startsWith('id:'))?.slice(3).trim() ?? ''
    const type = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() ?? 'system'
    const data = lines.find((line) => line.startsWith('data:'))?.slice(5).trim()
    if (!data) return []
    const payload = JSON.parse(data) as Record<string, unknown>
    return [{
      id,
      type,
      block: String(payload.block ?? 'system') as StreamBlock['block'],
      phase: payload.phase ? String(payload.phase) : undefined,
      title: payload.title ? String(payload.title) : undefined,
      text: payload.delta ? String(payload.delta) : undefined,
      data: payload.data && typeof payload.data === 'object' ? payload.data as Record<string, unknown> : undefined,
      runtime: payload.runtime ? String(payload.runtime) : undefined,
      duration_ms: typeof payload.duration_ms === 'number' ? payload.duration_ms : undefined,
    }]
  })
}

function appendUniqueStream(current: StreamBlock[], incoming: StreamBlock[]): StreamBlock[] {
  const result = [...current]
  const seen = new Set(current.map((block) => block.id))
  for (const block of incoming) {
    if (seen.has(block.id)) continue
    seen.add(block.id)
    if ((block.block === 'text' || block.block === 'thinking') && block.phase === 'delta') {
      let previousDelta = -1
      for (let index = result.length - 1; index >= 0; index -= 1) {
        const item = result[index]!
        if (item.block === block.block && item.phase === block.phase && item.title === block.title) {
          previousDelta = index
          break
        }
      }
      if (previousDelta >= 0) {
        const previous = result[previousDelta]!
        result.splice(previousDelta, 1)
        result.push({
          ...previous,
          id: block.id,
          text: `${previous.text ?? ''}${block.text ?? ''}`,
        })
        continue
      }
    }
    if (block.block === 'system' && block.title) {
      const repeatedStatus = result.findIndex((item) =>
        item.block === block.block && item.phase === block.phase && item.title === block.title,
      )
      if (repeatedStatus >= 0) {
        result.splice(repeatedStatus, 1)
        result.push(block)
        continue
      }
    }
    result.push(block)
  }
  return result
}

export function isDockVisibleStreamBlock(block: StreamBlock): boolean {
  // Manuscript deltas belong to the primary candidate editor. Repeating the raw
  // JSON delivery stream in the Dock creates dozens of fragments and duplicates
  // the work surface; the Dock remains responsible for reasoning and operations.
  return !(block.block === 'text' && block.title === '章节候选稿只读预览')
}

export const useDockStore = defineStore('agent-dock', {
  state: () => ({
    events: [] as DockEvent[],
    runs: [] as DockRun[],
    stream: [] as StreamBlock[],
    streamRunId: undefined as string | undefined,
    quote: undefined as DockQuote | undefined,
    focus: undefined as { medium: 'script' | 'novel'; unit_id: string } | undefined,
    proposal: undefined as SelectionProposal | undefined,
    transparency: { context_tokens: 0, context_limit: 0, context_percent: null, memory_entries: 0, role: 'writer', connected: false } as Transparency,
    role: 'writer',
    busy: false,
    // The creation surface is primary. Keep the collaborator available as a
    // status bar, and only open it through explicit user intent (or setQuote).
    expanded: false,
    width: storedDockSize(DOCK_WIDTH_KEY, 430, 340, 760),
    height: storedDockSize(DOCK_HEIGHT_KEY, 620, 320, typeof window === 'undefined' ? 900 : window.innerHeight - 56),
    filter: 'focus' as DockFilter,
    error: '',
    notice: '',
    feedConnected: false,
    lastSyncAt: undefined as string | undefined,
  }),
  getters: {
    visibleEvents(state): DockEvent[] {
      return state.filter === 'focus' ? state.events.filter(isFocusEvent) : state.events.filter((event) => event.type === state.filter)
    },
    activeRun(state): DockRun | undefined {
      return state.runs.find((run) => ['queued', 'running', 'waiting'].includes(run.status))
    },
    waitingRun(state): DockRun | undefined {
      return state.runs.find((run) => run.status === 'waiting')
    },
  },
  actions: {
    setQuote(quote: DockQuote) {
      this.quote = { ...quote, excerpt: quote.excerpt.slice(0, 60) }
      this.expanded = true
      this.notice = '选区已引用到创作搭档'
      window.setTimeout(() => { this.notice = '' }, 1800)
    },
    clearQuote() { this.quote = undefined },
    setFocus(medium: 'script' | 'novel', unitId: string) {
      this.focus = { medium, unit_id: unitId }
    },
    setSize(width: number, height: number) {
      this.width = Math.max(340, Math.min(760, Math.round(width)))
      this.height = Math.max(320, Math.min(window.innerHeight - 56, Math.round(height)))
      window.localStorage.setItem(DOCK_WIDTH_KEY, String(this.width))
      window.localStorage.setItem(DOCK_HEIGHT_KEY, String(this.height))
    },
    async load(projectId: string, incremental = false) {
      try {
        const priorActiveRunId = this.activeRun?.id
        const after = incremental ? (this.events.at(-1)?.cursor_id ?? this.events.at(-1)?.id) : undefined
        const query = after ? `?after_id=${encodeURIComponent(after)}` : ''
        const incoming = await api<DockEvent[]>(`/projects/${projectId}/events${query}`)
        this.events = incremental ? [...this.events, ...incoming.filter((event) => !this.events.some((item) => item.id === event.id))] : incoming
        await Promise.all([this.loadRuns(projectId), this.loadTransparency(projectId)])
        const active = this.runs.find((run) => ['queued', 'running', 'waiting'].includes(run.status))
        const streamRunId = active?.id ?? priorActiveRunId
        if (streamRunId) await this.reconnect(projectId, streamRunId)
        this.feedConnected = true
        this.lastSyncAt = new Date().toISOString()
      } catch (error) {
        this.feedConnected = false
        throw error
      }
    },
    async loadRuns(projectId: string) {
      this.runs = await api<DockRun[]>(`/projects/${projectId}/runs`)
    },
    async loadTransparency(projectId: string) {
      this.transparency = await api<Transparency>(`/projects/${projectId}/agents/${this.role}/transparency`)
    },
    async send(projectId: string, content: string, requiresConfirmation = false) {
      if (!content.trim()) return
      this.busy = true
      this.error = ''
      this.stream = []
      try {
        const quote = this.quote
        const run = await api<DockRun>(`/projects/${projectId}/agents/${this.role}/messages`, {
          method: 'POST',
          body: JSON.stringify({
            content: content.trim(),
            quote: this.quote,
            focus: this.focus,
            requires_confirmation: requiresConfirmation,
            idempotency_key: crypto.randomUUID(),
          }),
        })
        await this.reconnect(projectId, run.id)
        if (quote) {
          const domain = quote.medium === 'script' ? 'script' : 'novel'
          const unit = quote.medium === 'script' ? 'scenes' : 'chapters'
          this.proposal = await api<SelectionProposal>(`/${domain}/projects/${projectId}/${unit}/${quote.unit_id}/selection-edits`, {
            method: 'POST',
            body: JSON.stringify({
              revision_id: quote.revision_id,
              element_id: quote.element_id,
              excerpt: quote.excerpt,
              operation: quote.operation,
              instruction: content.trim(),
              idempotency_key: crypto.randomUUID(),
            }),
          })
        }
        this.quote = undefined
        await this.load(projectId)
      } catch (error) {
        this.error = error instanceof ApiError && error.status === 402 ? '本周期额度不足，请前往用量中心。' : error instanceof Error ? error.message : '发送失败'
      } finally { this.busy = false }
    },
    async reconnect(projectId: string, runId: string) {
      if (this.streamRunId !== runId) {
        this.stream = []
        this.streamRunId = runId
      }
      const cursor = this.stream.at(-1)?.id
      const params = new URLSearchParams({ run_id: runId })
      if (cursor) params.set('after_id', cursor)
      const response = await fetch(`/api/projects/${projectId}/agents/${this.role}/stream?${params}`, { credentials: 'include' })
      if (!response.ok) throw new ApiError(response.status, '恢复 Agent 输出失败')
      this.stream = appendUniqueStream(this.stream, parseSse(await response.text()))
    },
    async confirm(projectId: string, runId: string, approved: boolean) {
      this.busy = true
      this.error = ''
      try {
        await api(`/projects/${projectId}/agents/${this.role}/confirm`, {
          method: 'POST',
          body: JSON.stringify({ run_id: runId, approved, idempotency_key: `dock-confirm-${runId}` }),
        })
        await this.reconnect(projectId, runId)
        await this.load(projectId)
      } catch (error) { this.error = error instanceof Error ? error.message : '确认失败' }
      finally { this.busy = false }
    },
    async cancel(projectId: string, runId: string) {
      await api(`/projects/${projectId}/runs/${runId}/cancel`, { method: 'POST' })
      await this.load(projectId)
    },
    async adoptProposal(projectId: string) {
      if (!this.proposal) return
      const proposal = this.proposal
      const domain = proposal.medium === 'script' ? 'script' : 'novel'
      const unit = proposal.medium === 'script' ? 'scenes' : 'chapters'
      await api(`/${domain}/projects/${projectId}/${unit}/${proposal.unit_id}/revisions/${proposal.id}/adopt`, { method: 'POST' })
      this.proposal = undefined
      await this.load(projectId)
      window.dispatchEvent(new CustomEvent('scriptnow:document-changed'))
    },
    continueProposal() {
      if (!this.proposal) return
      this.quote = {
        medium: this.proposal.medium,
        operation: 'revise',
        unit_id: this.proposal.unit_id,
        revision_id: this.proposal.base_revision_id,
        element_id: this.proposal.element_id,
        excerpt: this.proposal.excerpt,
      }
      this.proposal = undefined
    },
  },
})

export { appendUniqueStream, parseSse }
