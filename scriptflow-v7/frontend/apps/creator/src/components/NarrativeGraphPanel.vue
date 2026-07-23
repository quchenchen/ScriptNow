<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useLocale } from '@scriptflow/shared'
import dagre from '@dagrejs/dagre'
import { MarkerType, VueFlow, useVueFlow, type Edge, type Node } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { api } from '../api'
import {
  canonicalNarrativeNodeType,
  narrativeNodeTypeLabel,
  narrativeRelationTypeLabel,
  type NarrativeNodeType,
  type NarrativeRelationType,
} from '../narrativeGraphSchema'

type Evidence = { unit_id: string; label: string }
type GraphNode = { id: string; type: NarrativeNodeType; label: string; summary: string; chapters?: string[]; unit_count?: number; evidence?: Evidence[]; evidence_count?: number }
type GraphEdge = { id: string; type: NarrativeRelationType; source: string; target: string; label: string; inference: boolean }
type GraphResponse = { status: 'not_built' | 'structure_ready' | 'ready'; extraction_status?: 'not_started' | 'queued' | 'running' | 'ready' | 'failed'; extraction_progress?: { completed: number; total: number }; index?: { version: number; source_name: string }; chapters: GraphNode[]; nodes: GraphNode[]; edges: GraphEdge[] }

const props = defineProps<{ projectId: string }>()
const { isEnglish } = useLocale()
const graph = ref<GraphResponse | null>(null)
const loading = ref(true)
const error = ref('')
const selectedId = ref('')
const selectedType = ref<NarrativeNodeType | 'all'>('all')
const neighborFocus = ref(true)
const expanded = ref(false)
const viewMode = ref<'network' | 'timeline'>('network')
const evidence = ref<{ chapter: string; label: string; excerpt: string } | null>(null)
let refreshTimer: number | undefined
const ui = (zh: string, en: string) => isEnglish.value ? en : zh
const { fitView, zoomIn, zoomOut } = useVueFlow()
const NODE_PALETTES: Record<NarrativeNodeType, { accent: string; tint: string }> = {
  character: { accent: '#245547', tint: '#e7f0eb' },
  event: { accent: '#b14f2d', tint: '#f8e9e2' },
  organization: { accent: '#7a6841', tint: '#f1ecdf' },
  location: { accent: '#59715d', tint: '#e8efe7' },
  object: { accent: '#9a7629', tint: '#f6efd9' },
  concept: { accent: '#526a8b', tint: '#e8edf5' },
  relationship: { accent: '#8f5f78', tint: '#f3e8ee' },
  story_thread: { accent: '#75568d', tint: '#eee8f3' },
  chapter: { accent: '#6d665e', tint: '#eeebe6' },
}
const UNKNOWN_NODE_PALETTE = { accent: '#6d665e', tint: '#eeebe6' }
const relationTypes: NarrativeRelationType[] = [
  'causal',
  'emotional',
  'conflict',
  'foreshadowing',
  'constraint',
  'affiliation',
]
const normalizedNodes = computed<GraphNode[]>(() => (graph.value?.nodes ?? []).flatMap((node) => {
  const type = canonicalNarrativeNodeType(node.type)
  return type ? [{ ...node, type }] : []
}))
const types = computed(() => [...new Set(normalizedNodes.value.map((node) => node.type))])
const timelineChapters = computed(() => (graph.value?.chapters ?? []).map((chapter, index) => ({
  id: chapter.id,
  label: chapter.label,
  ordinal: index + 1,
  nodes: normalizedNodes.value.filter((node) =>
    ['event', 'relationship', 'story_thread'].includes(node.type)
    && node.chapters?.includes(chapter.label),
  ),
})))
const visibleNodes = computed(() => normalizedNodes.value.filter((node) => selectedType.value === 'all' || node.type === selectedType.value))
const selected = computed(() => visibleNodes.value.find((node) => node.id === selectedId.value) ?? visibleNodes.value[0] ?? null)
const connected = computed(() => {
  if (!selected.value || !graph.value) return []
  const byId = new Map(normalizedNodes.value.map((node) => [node.id, node]))
  return graph.value.edges.filter((edge) => edge.source === selected.value?.id || edge.target === selected.value?.id).map((edge) => ({ edge, node: byId.get(edge.source === selected.value?.id ? edge.target : edge.source) }))
})
const focusedNodeIds = computed(() => {
  if (!neighborFocus.value || !selected.value || !graph.value) return new Set(visibleNodes.value.map((node) => node.id))
  const byId = new Map(normalizedNodes.value.map((node) => [node.id, node]))
  const neighbors = graph.value.edges.flatMap((edge) => {
    const id = edge.source === selected.value?.id ? edge.target : edge.target === selected.value?.id ? edge.source : ''
    const node = byId.get(id)
    return node ? [{ id, score: (edge.inference ? 0 : 1000) + (node.evidence_count ?? 0) }] : []
  }).sort((left, right) => right.score - left.score).slice(0, 17)
  const ids = new Set([selected.value.id, ...neighbors.map((item) => item.id)])
  return ids
})
const canvasNodes = computed<Node[]>(() => {
  const items = visibleNodes.value.filter((node) => focusedNodeIds.value.has(node.id))
  const layout = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  layout.setGraph({ rankdir: 'LR', ranksep: 150, nodesep: 46, marginx: 42, marginy: 42 })
  for (const node of items) layout.setNode(node.id, { width: 210, height: 84 })
  for (const edge of graph.value?.edges ?? []) if (focusedNodeIds.value.has(edge.source) && focusedNodeIds.value.has(edge.target)) layout.setEdge(edge.source, edge.target)
  dagre.layout(layout)
  return items.map((node) => {
    const position = layout.node(node.id)
    const palette = nodePalette(node.type)
    return {
      id: node.id,
      position: { x: position.x - 105, y: position.y - 42 },
      data: { ...node, typeLabel: typeLabel(node.type) },
      class: [`graph-flow-node`, `node-${node.type}`, selected.value?.id === node.id ? 'is-selected' : ''],
      style: { '--node-accent': palette.accent, '--node-tint': palette.tint },
    }
  })
})
const canvasEdges = computed<Edge[]>(() => (graph.value?.edges ?? [])
  .filter((edge) => focusedNodeIds.value.has(edge.source) && focusedNodeIds.value.has(edge.target))
  .map((edge) => {
    const kind = relationKind(edge.type)
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      markerEnd: MarkerType.ArrowClosed,
      class: [edge.inference ? 'inferred-edge' : 'evidence-edge', `relation-${kind}`],
      animated: selected.value ? edge.source === selected.value.id || edge.target === selected.value.id : false,
    }
  }))

function nodePalette(type: NarrativeNodeType | string) {
  const canonical = canonicalNarrativeNodeType(type)
  return canonical ? NODE_PALETTES[canonical] : UNKNOWN_NODE_PALETTE
}
function relationKind(type: NarrativeRelationType) {
  return type
}

function typeLabel(type: NarrativeNodeType | string) {
  const canonical = canonicalNarrativeNodeType(type)
  return canonical
    ? narrativeNodeTypeLabel(canonical, isEnglish.value)
    : ui('未分类', 'Unclassified')
}
function meaningLabel(type: NarrativeNodeType) {
  return ({
    chapter: ui('本章在整体中的作用', 'Role in the whole story'),
    character: ui('这个人物在推动什么', 'What this character drives'),
    event: ui('这件事改变了什么', 'What this event changes'),
    organization: ui('这个群体在争取什么', 'What this group is pursuing'),
    location: ui('这个地点为何重要', 'Why this place matters'),
    object: ui('这个物件承载了什么', 'What this object carries'),
    concept: ui('这个观念或规则约束了什么', 'What this concept or rule constrains'),
    relationship: ui('这段关系如何变化', 'How this relationship changes'),
    story_thread: ui('这条叙事线索承诺了什么', 'What this story thread promises'),
  } as Record<NarrativeNodeType, string>)[type]
}
function evidenceLabel(label: string) {
  const match = label.match(/^(.*?)\s*·\s*passage\s*(\d+)$/i)
  if (!match) return label === 'Front matter' ? ui('作品前置信息', 'Story setup') : label
  const chapter = match[1] === 'Front matter' ? ui('作品前置信息', 'Story setup') : match[1]
  return ui(`${chapter} · 原文片段 ${match[2]}`, `${chapter} · Source passage ${match[2]}`)
}
async function load() {
  loading.value = true; error.value = ''; evidence.value = null
  try {
    graph.value = await api<GraphResponse>(`/novel/projects/${props.projectId}/narrative-graph`)
    selectedId.value = normalizedNodes.value[0]?.id ?? ''
    neighborFocus.value = normalizedNodes.value.length > 24
    if (['queued', 'running'].includes(graph.value.extraction_status ?? '')) {
      window.clearTimeout(refreshTimer)
      refreshTimer = window.setTimeout(load, 2500)
    }
  } catch (cause) { error.value = cause instanceof Error ? cause.message : ui('故事图谱暂时无法读取。', 'The story graph is temporarily unavailable.') }
  finally {
    loading.value = false
    if (graph.value) await refitGraph()
  }
}
function selectNode(node: GraphNode) { selectedId.value = node.id; evidence.value = null }
async function selectCanvasNode(event: { node: Node }) {
  const node = normalizedNodes.value.find((item) => item.id === event.node.id)
  if (node) selectNode(node)
}
async function showNeighbors() {
  neighborFocus.value = !neighborFocus.value
  await refitGraph()
}
async function selectType(type: NarrativeNodeType | 'all') {
  viewMode.value = 'network'
  selectedType.value = type
  const first = visibleNodes.value[0]
  if (first) selectedId.value = first.id
  neighborFocus.value = type === 'all' && visibleNodes.value.length > 24
  await refitGraph()
}
async function showView(mode: 'network' | 'timeline') {
  viewMode.value = mode
  if (mode === 'timeline') {
    selectedType.value = 'all'
    return
  }
  await refitGraph()
}
async function refitGraph() {
  await nextTick()
  window.setTimeout(() => void fitView({ padding: neighborFocus.value ? 0.2 : 0.1, duration: 320 }), 80)
}
async function toggleExpanded() {
  expanded.value = !expanded.value
  await refitGraph()
}
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && expanded.value) {
    expanded.value = false
    void refitGraph()
  }
}
async function openEvidence(item: Evidence) { evidence.value = await api(`/novel/projects/${props.projectId}/narrative-graph/evidence/${item.unit_id}`) }
async function buildSemanticGraph() {
  error.value = ''
  await api(`/novel/projects/${props.projectId}/narrative-graph/extract`, { method: 'POST' })
  if (graph.value) graph.value.extraction_status = 'queued'
  refreshTimer = window.setTimeout(load, 1200)
}
onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  void load()
})
watch(() => props.projectId, load)
onUnmounted(() => {
  window.clearTimeout(refreshTimer)
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <section class="narrative-graph-workspace" :class="{ 'graph-expanded': expanded }">
    <header class="graph-heading"><div><p class="eyebrow">{{ ui('创作逻辑 · 素材图谱', 'Creative logic · Source graph') }}</p><h2>{{ ui('看清故事如何彼此牵动。', 'See how the story moves together.') }}</h2><p>{{ ui('从章节脉络进入人物、事件、关系与伏笔；每个结论都可以回到原始素材。', 'Move from chapter flow into characters, events, relationships, and promises, with every conclusion grounded in source evidence.') }}</p></div><div class="graph-heading-actions"><span v-if="graph?.index" class="graph-source">{{ graph.index.source_name }} · v{{ graph.index.version }}</span><button v-if="graph && graph.status !== 'not_built' && graph.extraction_status !== 'ready'" class="primary" :disabled="['queued', 'running'].includes(graph.extraction_status ?? '')" @click="buildSemanticGraph">{{ ['queued', 'running'].includes(graph.extraction_status ?? '') ? ui('正在构建语义图谱…', 'Building semantic graph…') : graph.extraction_status === 'failed' ? ui('重新构建', 'Build again') : ui('构建人物与事件关系', 'Build character and event graph') }}</button></div></header>
    <div v-if="loading" class="graph-empty">{{ ui('正在整理故事脉络…', 'Organizing the story logic…') }}</div>
    <div v-else-if="error" class="graph-empty error-banner">{{ error }} <button class="secondary" @click="load">{{ ui('重试', 'Retry') }}</button></div>
    <div v-else-if="graph?.status === 'not_built'" class="graph-empty"><strong>{{ ui('尚未建立素材图谱', 'No source graph yet') }}</strong><span>{{ ui('上传或解析小说素材后，这里会出现章节、人物与事件之间的联系。', 'Upload or parse a novel manuscript to reveal chapter, character, and event connections here.') }}</span></div>
    <div v-else class="graph-layout">
      <aside class="graph-filters"><p>{{ ui('查看范围', 'View') }}</p><button :class="{ active: selectedType === 'all' }" @click="selectType('all')"><span class="graph-filter-label"><i class="type-swatch all"></i>{{ ui('全部逻辑', 'All logic') }}</span><span>{{ normalizedNodes.length }}</span></button><button v-for="type in types" :key="type" :class="{ active: selectedType === type }" :style="{ '--node-accent': nodePalette(type).accent, '--node-tint': nodePalette(type).tint }" @click="selectType(type)"><span class="graph-filter-label"><i class="type-swatch"></i>{{ typeLabel(type) }}</span><span>{{ normalizedNodes.filter((node) => node.type === type).length }}</span></button><div class="graph-legend"><strong>{{ ui('关系线', 'Relationship lines') }}</strong><span v-for="relationType in relationTypes" :key="relationType"><i class="line-swatch" :class="relationType"></i>{{ narrativeRelationTypeLabel(relationType, isEnglish) }}</span><span><i class="line-swatch inferred"></i>{{ ui('虚线表示模型推断', 'Dashed means model-inferred') }}</span></div><div v-if="graph?.status === 'structure_ready' || ['queued', 'running'].includes(graph?.extraction_status ?? '')" class="graph-progress"><strong>{{ ['queued', 'running'].includes(graph?.extraction_status ?? '') ? ui(`已完成 ${graph?.extraction_progress?.completed ?? 0} / ${graph?.extraction_progress?.total ?? graph?.chapters.length ?? 0} 章`, `${graph?.extraction_progress?.completed ?? 0} / ${graph?.extraction_progress?.total ?? graph?.chapters.length ?? 0} chapters`) : ui('章节脉络已就绪', 'Chapter flow is ready') }}</strong><span>{{ ui('人物、事件和叙事线索会随章节抽取逐步出现，所有结论均保留原文依据。', 'Characters, events, and story threads appear chapter by chapter, with source evidence retained for every conclusion.') }}</span></div></aside>
      <main class="graph-canvas" aria-label="故事逻辑图谱">
        <div class="graph-canvas-title">
          <div>
            <strong v-if="viewMode === 'timeline'">{{ ui('故事时间线', 'Story timeline') }}</strong>
            <strong v-else>{{ neighborFocus && selected ? ui(`${selected.label} 的核心关系`, `${selected.label}'s core story network`) : selectedType === 'all' ? ui('故事全景', 'Story overview') : typeLabel(selectedType) }}</strong>
            <span v-if="viewMode === 'timeline'">{{ timelineChapters.length }} {{ ui('章', 'chapters') }}</span>
            <span v-else>{{ canvasNodes.length }} / {{ visibleNodes.length }} {{ ui('个节点', 'nodes') }}</span>
            <em>{{ viewMode === 'timeline' ? ui('沿章节查看事件、关系变化与叙事线索', 'Follow events, relationship changes, and story threads chapter by chapter') : ui('点选节点，在右侧阅读完整关系', 'Select a node to read full relationships on the right') }}</em>
          </div>
          <div class="graph-canvas-actions">
            <div class="graph-view-switch" role="group" :aria-label="ui('图谱视图', 'Graph view')">
              <button :class="{ active: viewMode === 'network' }" @click="showView('network')">{{ ui('关系图', 'Network') }}</button>
              <button :class="{ active: viewMode === 'timeline' }" @click="showView('timeline')">{{ ui('时间线', 'Timeline') }}</button>
            </div>
            <template v-if="viewMode === 'network'">
              <button class="secondary zoom-button" :aria-label="ui('缩小', 'Zoom out')" @click="zoomOut()">−</button>
              <button class="secondary zoom-button" :aria-label="ui('放大', 'Zoom in')" @click="zoomIn()">＋</button>
              <button class="secondary" @click="refitGraph">{{ ui('适配画布', 'Fit view') }}</button>
              <button class="secondary" :disabled="!selected" :class="{ active: neighborFocus }" @click="showNeighbors">{{ neighborFocus ? ui('显示完整全景', 'Show full story') : ui('查看核心关系', 'Show core relationships') }}</button>
            </template>
            <button class="secondary expand-graph" @click="toggleExpanded">{{ expanded ? ui('退出全屏', 'Exit full screen') : ui('全屏查看', 'Full screen') }}</button>
          </div>
        </div>
        <VueFlow v-if="viewMode === 'network'" class="story-graph-flow" :nodes="canvasNodes" :edges="canvasEdges" :min-zoom="0.08" :max-zoom="2.4" :fit-view-on-init="true" :nodes-draggable="true" :nodes-connectable="false" @node-click="selectCanvasNode"><template #node-default="{ data }"><article class="flow-node-card"><small><i></i>{{ data.typeLabel }}</small><strong>{{ data.label }}</strong><span v-if="data.evidence_count">{{ data.evidence_count }} {{ ui('处原文', 'source passages') }}</span></article></template></VueFlow>
        <section v-else class="story-timeline" :aria-label="ui('故事时间线', 'Story timeline')">
          <article v-for="chapter in timelineChapters" :key="chapter.id" class="timeline-chapter">
            <div class="timeline-marker"><span>{{ String(chapter.ordinal).padStart(2, '0') }}</span></div>
            <header><strong>{{ chapter.label }}</strong><small>{{ chapter.nodes.length ? ui(`${chapter.nodes.length} 个变化`, `${chapter.nodes.length} changes`) : ui('暂无已提取变化', 'No extracted changes yet') }}</small></header>
            <div v-if="chapter.nodes.length" class="timeline-items">
              <button v-for="node in chapter.nodes" :key="node.id" :class="[`timeline-${node.type}`, { selected: selected?.id === node.id }]" @click="selectNode(node)">
                <span>{{ typeLabel(node.type) }}</span><strong>{{ node.label }}</strong><p>{{ node.summary }}</p>
              </button>
            </div>
          </article>
        </section>
      </main>
      <aside class="graph-detail"><template v-if="selected"><p class="eyebrow">{{ typeLabel(selected.type) }}</p><h3>{{ selected.label }}</h3><section v-if="selected.summary" class="graph-meaning"><strong>{{ meaningLabel(selected.type) }}</strong><p>{{ selected.summary }}</p></section><section v-if="selected.chapters?.length" class="graph-appearances"><strong>{{ ui('出现在哪些章节', 'Where it appears') }}</strong><div><span v-for="chapter in selected.chapters" :key="chapter">{{ chapter }}</span></div></section><dl><div><dt>{{ ui('原文出现', 'Source appearances') }}</dt><dd>{{ selected.evidence?.length ?? selected.evidence_count ?? 0 }} {{ ui('处', 'places') }}</dd></div><div><dt>{{ ui('牵动要素', 'Story elements affected') }}</dt><dd>{{ connected.length }} {{ ui('个', 'items') }}</dd></div></dl><section v-if="connected.length" class="graph-relations"><strong>{{ ui('它牵动了什么', 'What it affects') }}</strong><button v-for="item in connected" :key="item.edge.id" @click="item.node && selectNode(item.node)"><span>{{ item.edge.label }}</span><b>{{ item.node?.label }}</b></button></section><section v-if="selected.evidence?.length" class="graph-evidence"><strong>{{ ui('查看原文依据', 'Read the source') }}</strong><button v-for="item in selected.evidence" :key="item.unit_id" @click="openEvidence(item)">{{ evidenceLabel(item.label) }}</button></section><article v-if="evidence" class="evidence-preview"><small>{{ evidence.chapter }}</small><strong>{{ evidenceLabel(evidence.label) }}</strong><p>{{ evidence.excerpt }}</p></article></template></aside>
    </div>
  </section>
</template>
