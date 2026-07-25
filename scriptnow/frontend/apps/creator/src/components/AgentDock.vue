<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import AgentMessage from './AgentMessage.vue'
import { creativeRoleLabel } from '../creativeRoles'
import { eventBody, isDockVisibleStreamBlock, useDockStore, type DockFilter } from '../stores/dock'
import { useRuntimeStore } from '../stores/runtime'

const props = defineProps<{ projectId: string }>()
const dock = useDockStore()
const runtime = useRuntimeStore()
const input = ref('')
const feed = ref<HTMLElement>()
const showScrollAnchor = ref(false)
const requiresConfirmation = ref(false)
let refreshTimer: ReturnType<typeof window.setInterval> | undefined
let resizeStart: { x: number; y: number; width: number; height: number } | undefined
const filters: Array<{ key: DockFilter; label: string }> = [
  { key: 'focus', label: '重点' }, { key: 'chat', label: '对话' }, { key: 'decision', label: '确认' },
  { key: 'node', label: '过程' }, { key: 'system', label: '运行' },
]
const activityCountLabel = computed(() => dock.filter === 'focus' ? `${dock.visibleEvents.length} 条重点动态` : `${dock.visibleEvents.length} 条${filters.find((item) => item.key === dock.filter)?.label ?? '动态'}`)
const operationLabel = computed(() => ({ expand: '扩写', shorten: '缩写', polish: '润色', revise: '修订' })[dock.quote?.operation ?? 'revise'])
const roleLabel = computed(() => creativeRoleLabel(dock.role))
const runtimeRole = computed(() => dock.role === 'editor' ? 'reviewer' : dock.role as 'director' | 'architect' | 'writer')
const activeRuntime = computed(() => runtime.status?.roles[runtimeRole.value])

const activeRunCount = computed(() => (runtime.status?.active_runs || []).filter(r => r.status === 'queued' || r.status === 'running').length)
const activeRunStatus = computed(() => {
  const runs = (runtime.status?.active_runs || []).filter(r => r.status === 'queued' || r.status === 'running')
  if (runs.length === 0) return ''
  return runs.length === 1 ? `1 个任务 ${runs[0].status === 'queued' ? '排队中' : '执行中'}` : `${runs.length} 个任务执行中`
})
const roleProgressLabel = computed(() => {
  if (!activeRuntime.value?.connected) return '未连接'
  if (activeRunCount.value > 0) return `🔄 ${activeRunStatus.value}`
  return '✓ 就绪'
})
const actionLabels: Record<string, string> = {
  'story_core.adopt': '已采纳创意方向', 'blueprint.propose': '蓝图候选已生成',
  'blueprint.revise': '蓝图修订候选已生成', 'blueprint.adopt': '已采纳蓝图',
  'story_map.adopt': '已确认 StoryMap',
  'novel_story_core.propose': '三个小说创意方向', 'novel_story_core.history_restored': '创意方向与选择已恢复', 'novel_story_core.adopt': '采用小说创意方向', 'novel_blueprint.adopt': '采用小说蓝图',
  'novel_blueprint.propose': '小说蓝图候选已生成',
  'novel_story_map.propose': '小说卷章结构候选已生成',
  'novel_story_map.adopt': '采用小说 StoryMap', 'novel_document.adopt': '采用章节修订',
  'novel_snapshot.created': '创建小说快照', 'novel.exported': '导出小说',
  'script_story_core.propose': '三个剧本创意方向', 'script_story_core.adopt': '采用剧本创意方向', 'script_blueprint.adopt': '采用剧本蓝图',
  'script_story_map.adopt': '采用剧本 StoryMap', 'script_document.adopt': '采用场景修订',
  'script_snapshot.created': '创建剧本快照', 'script.exported': '导出剧本',
  'review_finding.create': '发现审读问题', 'review_finding.accept': '接受审读建议',
  'review_finding.dismiss': '忽略审读建议', 'context.compress': '压缩 Agent 上下文',
}
const eventKindLabels: Record<string, string> = { chat: '对话', decision: '已确认', node: '执行过程', system: '运行信息' }
const streamBlockLabels: Record<string, string> = { thinking: '思考摘要', tool: '能力调用', data: '项目上下文', text: '正文预览', system: '运行信息' }
const visibleStream = computed(() => dock.stream
  .filter(isDockVisibleStreamBlock)
  .filter((block) => dock.filter !== 'focus' || block.block === 'thinking' || block.block === 'tool' || block.block === 'system'))
function eventTitle(event: { title: string; payload: Record<string, unknown> }) {
  const action = String(event.payload.action ?? event.title)
  return actionLabels[action] ?? event.title
}
function eventFacts(payload: Record<string, unknown>) {
  const facts: string[] = []
  if (payload.chapter_id) facts.push(`章节 ${payload.chapter_id}`)
  if (payload.scene_id) facts.push(`场景 ${payload.scene_id}`)
  if (payload.version) facts.push(`版本 ${payload.version}`)
  if (Array.isArray(payload.scope)) facts.push(`${payload.scope.length} 个单元`)
  if (payload.source) facts.push(`来源 ${payload.source}`)
  if (payload.status) facts.push(`状态 ${payload.status}`)
  if (payload.generation) facts.push(`第 ${payload.generation} 轮发散`)
  return facts.join(' · ')
}

interface CreativeCandidate {
  id: string
  ordinal?: number
  title: string
  summary: string
  point_of_view?: string
  angles?: string[]
}

const creativeAngleLabels: Record<string, string> = {
  'protagonist desire': '主角欲望',
  'opposing force': '对抗力量',
  'emotional promise': '情感承诺',
  'moral dilemma': '道德困境',
  'ending cost': '结局代价',
}

function creativeAngle(value: string): { label: string; content: string } {
  const separator = value.indexOf(':')
  if (separator < 0) return { label: '创作维度', content: value.trim() }
  const key = value.slice(0, separator).trim().toLowerCase()
  return {
    label: creativeAngleLabels[key] ?? value.slice(0, separator).trim(),
    content: value.slice(separator + 1).trim(),
  }
}

function creativeCandidates(payload: Record<string, unknown>): CreativeCandidate[] {
  const source = Array.isArray(payload.candidates)
    ? payload.candidates
    : payload.candidate && typeof payload.candidate === 'object'
      ? [payload.candidate]
      : []
  return source.flatMap((value) => {
    if (!value || typeof value !== 'object') return []
    const item = value as Record<string, unknown>
    if (!item.title || !item.summary) return []
    return [{
      id: String(item.id ?? item.title),
      ordinal: typeof item.ordinal === 'number' ? item.ordinal : undefined,
      title: String(item.title),
      summary: String(item.summary),
      point_of_view: item.point_of_view ? String(item.point_of_view) : undefined,
      angles: Array.isArray(item.angles) ? item.angles.map(String) : undefined,
    }]
  })
}

function isSelectedCandidate(payload: Record<string, unknown>, candidateId: string): boolean {
  const selected = payload.selected_candidate_id
  const adopted = payload.candidate && typeof payload.candidate === 'object'
    ? String((payload.candidate as Record<string, unknown>).id ?? '')
    : ''
  return String(selected ?? adopted) === candidateId
}

function scrollToLatest() {
  feed.value?.scrollTo({ top: feed.value.scrollHeight, behavior: 'smooth' })
}

function onFeedScroll() {
  const el = feed.value
  if (!el) return
  showScrollAnchor.value = el.scrollHeight - el.scrollTop - el.clientHeight > 200
}

async function send() {
  const content = input.value
  input.value = ''
  await dock.send(props.projectId, content, requiresConfirmation.value)
  requiresConfirmation.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() }
}

function resizeDock(event: PointerEvent) {
  if (!resizeStart) return
  dock.setSize(
    resizeStart.width + resizeStart.x - event.clientX,
    resizeStart.height + resizeStart.y - event.clientY,
  )
}

function stopResize() {
  resizeStart = undefined
  document.body.classList.remove('resizing-agent-dock')
  window.removeEventListener('pointermove', resizeDock)
  window.removeEventListener('pointerup', stopResize)
}

function startResize(event: PointerEvent) {
  resizeStart = { x: event.clientX, y: event.clientY, width: dock.width, height: dock.height }
  document.body.classList.add('resizing-agent-dock')
  window.addEventListener('pointermove', resizeDock)
  window.addEventListener('pointerup', stopResize)
}

watch(() => [dock.events.length, dock.stream.length], async () => {
  await nextTick()
  const el = feed.value
  if (!el) return
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
  if (nearBottom) {
    showScrollAnchor.value = false
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }
})
watch(() => props.projectId, (projectId) => {
  void dock.load(projectId).catch(() => undefined)
  void runtime.load(projectId).catch(() => undefined)
}, { immediate: true })
const refresh = (force = false) => {
  if (!force && (!dock.feedConnected || document.hidden)) return
  void dock.load(props.projectId, true).catch(() => undefined)
}
const onFocus = () => refresh(true)
onMounted(() => {
  window.addEventListener('focus', onFocus)
  refreshTimer = window.setInterval(() => refresh(), 1500)
})
onUnmounted(() => {
  stopResize()
  window.removeEventListener('focus', onFocus)
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<template>
  <aside class="agent-dock" :class="{ collapsed: !dock.expanded }" :style="dock.expanded ? { width: `${dock.width}px`, height: `${dock.height}px` } : undefined" aria-label="创作搭档">
    <button v-if="dock.expanded" class="dock-resize-grip" aria-label="拖拽调整创作搭档大小" title="拖拽调整大小" @pointerdown.prevent="startResize" />
    <button class="dock-handle" :aria-expanded="dock.expanded" @click="dock.expanded = !dock.expanded">
      <span><i :class="{ active: dock.activeRun }" /> 创作搭档</span>
      <small>{{ dock.activeRun ? `${roleLabel}正在处理` : activityCountLabel }}</small>
    </button>
    <template v-if="dock.expanded">
      <header class="dock-header">
        <div><p class="eyebrow">创作协作 · {{ dock.feedConnected ? '已同步' : '同步中断' }}</p><h2>{{ roleLabel }}</h2></div>
        <button class="dock-close" aria-label="收起创作搭档" @click="dock.expanded = false">×</button>
      </header>
      <nav class="dock-filters" aria-label="活动类型">
        <button v-for="item in filters" :key="item.key" :class="{ active: dock.filter === item.key }" @click="dock.filter = item.key">{{ item.label }}</button>
      </nav>
      <div ref="feed" class="dock-feed" aria-live="polite" @scroll="onFeedScroll">
        <button v-if="showScrollAnchor" class="scroll-anchor" aria-label="回到底部" title="回到最新消息" @click="scrollToLatest">↓ 回到最新</button>
        <article v-for="event in dock.visibleEvents" :key="event.id" class="dock-event" :class="`event-${event.type}`">
          <span class="event-kind">{{ eventKindLabels[event.type] }}</span><time>{{ new Date(event.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}</time>
          <strong>{{ eventTitle(event) }}</strong>
          <p v-if="eventFacts(event.payload)" class="event-facts">{{ eventFacts(event.payload) }}</p>
          <blockquote v-if="event.payload.quote">"{{ (event.payload.quote as Record<string, unknown>).excerpt }}"</blockquote>
          <AgentMessage v-if="eventBody(eventTitle(event), event.payload.content)" :text="eventBody(eventTitle(event), event.payload.content)!" />
          <section v-if="creativeCandidates(event.payload).length" class="dock-creative-directions" :class="{ adopted: Boolean(event.payload.candidate) }">
            <article v-for="candidate in creativeCandidates(event.payload)" :key="candidate.id" :class="{ selected: isSelectedCandidate(event.payload, candidate.id) }">
              <span v-if="candidate.ordinal">方向 {{ candidate.ordinal }}</span>
              <strong>{{ candidate.title }}</strong>
              <p>{{ candidate.summary }}</p>
              <small v-if="candidate.point_of_view">叙述视角 · {{ candidate.point_of_view }}</small>
              <dl v-if="candidate.angles?.length" class="creative-angle-list">
                <div v-for="angle in candidate.angles" :key="angle">
                  <dt>{{ creativeAngle(angle).label }}</dt>
                  <dd>{{ creativeAngle(angle).content }}</dd>
                </div>
              </dl>
              <b v-if="isSelectedCandidate(event.payload, candidate.id)">最终选择</b>
            </article>
          </section>
          <a v-if="event.payload.memory_deep_link" class="memory-link" :href="String(event.payload.memory_deep_link)">查看记忆治理 →</a>
          <small v-if="event.count > 1">连续同类节点 × {{ event.count }}</small>
        </article>
        <section v-if="visibleStream.length" class="stream-stack">
          <p class="eyebrow">本次协作</p>
          <article v-for="block in visibleStream" :key="`${block.id}-${block.phase}`" :class="`stream-${block.block}`">
            <span>{{ streamBlockLabels[block.block] ?? '运行信息' }}</span><strong v-if="block.title">{{ block.title }}</strong><AgentMessage v-if="block.text" :text="block.text" />
            <dl v-if="block.data" class="stream-data"><div><dt>阶段</dt><dd>{{ block.data.phase }}</dd></div><div><dt>结构单元</dt><dd>{{ block.data.story_units }}</dd></div><div><dt>已采纳</dt><dd>{{ block.data.adopted_units }}</dd></div><div><dt>待审读</dt><dd>{{ block.data.open_findings }}</dd></div></dl>
          </article>
        </section>
        <article v-if="dock.proposal" class="edit-proposal">
          <p class="eyebrow">替换候选 · {{ dock.proposal.medium }}</p>
          <div class="diff-line removed"><span>−</span>{{ dock.proposal.diff.before }}</div>
          <div class="diff-line added"><span>+</span>{{ dock.proposal.diff.after }}</div>
          <footer><button @click="dock.continueProposal">继续反馈</button><button class="approve" @click="dock.adoptProposal(projectId)">采纳替换</button></footer>
        </article>
        <p v-if="!dock.visibleEvents.length" class="dock-empty">这里会显示需要关注的 Agent 回复与创作决定。</p>
      </div>
      <section v-if="dock.waitingRun" class="confirm-card">
        <strong>需要你确认工具调用</strong><p>Agent 请求写入项目工作区。刷新页面后仍可继续处理。</p>
        <div><button :disabled="dock.busy" @click="dock.confirm(projectId, dock.waitingRun!.id, false)">拒绝</button><button class="approve" :disabled="dock.busy" @click="dock.confirm(projectId, dock.waitingRun!.id, true)">允许并继续</button></div>
      </section>
      <form class="dock-composer" @submit.prevent="send">
        <div v-if="dock.quote" class="quote-chip"><span>{{ operationLabel }} · {{ dock.quote.medium }}</span><q>{{ dock.quote.excerpt }}</q><button type="button" aria-label="移除引用" @click="dock.clearQuote">×</button></div>
        <textarea v-model="input" rows="3" :placeholder="dock.quote ? `补充${operationLabel}要求（可直接发送）…` : `告诉${roleLabel}你希望怎样调整…`" :disabled="dock.busy" @keydown="onKeydown" />
        <div class="composer-actions"><label><input v-model="requiresConfirmation" type="checkbox" /> 操作前确认</label><button v-if="dock.activeRun && dock.activeRun.status !== 'waiting'" type="button" @click="dock.cancel(projectId, dock.activeRun.id)">取消运行</button><button class="send-button" :disabled="dock.busy || !input.trim()">{{ dock.busy ? '处理中…' : '发送 ↵' }}</button></div>
      </form>
      <p v-if="dock.error" class="dock-error" role="alert">{{ dock.error }}</p>
      <p v-if="dock.notice" class="dock-notice" role="status">{{ dock.notice }}</p>
      <footer class="dock-status">
        <span :title="activeRuntime?.model_key ?? undefined">{{ activeRuntime?.connected ? `${roleLabel} · 模型可用` : dock.stream.length ? '项目事实已读取（未调用模型）' : `${roleLabel} · 模型未连接` }}</span><span>{{ dock.transparency.connected ? `本次上下文 ${dock.transparency.context_tokens} / ${dock.transparency.context_limit}` : '本次上下文尚未建立' }}</span><span>长期记忆 {{ dock.transparency.memory_entries }} 条</span>
      </footer>
    </template>
  </aside>
</template>
