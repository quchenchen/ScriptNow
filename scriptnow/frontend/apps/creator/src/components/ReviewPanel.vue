<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { useReviewStore, type Finding } from '../stores/review'

const props = defineProps<{
  projectId: string
  medium: 'script' | 'novel'
  unitId: string
  revisionId: string
  elements: Array<{ id: string; text: string; type: string }>
  anchors: Array<{ id: string; kind: string; name: string }>
  selection?: { elementId: string; excerpt: string; nonce: number }
}>()
const emit = defineEmits<{ locate: [elementId: string, findingId: string]; changed: [] }>()
const review = useReviewStore()
const mode = ref<'severity' | 'domain' | 'unit'>('severity')
const source = ref<'all' | 'ai' | 'human'>('all')
const expanded = ref('')
const showHuman = ref(false)
const showTimeline = ref(false)
const human = ref({ elementId: '', domain: 'character', severity: 'minor', diagnosis: '', suggestion: '' })
const open = computed(() => review.items.filter((item) => item.status === 'open'))
const visible = computed(() => open.value.filter((item) =>
  (source.value === 'all' || item.source === source.value) &&
  (mode.value !== 'unit' || item.unit_id === props.unitId),
).sort((a, b) => ['blocker','major','minor'].indexOf(a.severity) - ['blocker','major','minor'].indexOf(b.severity)))
const counts = computed(() => Object.fromEntries(['worldview','character','arc','event','foreshadow'].map(
  (key) => [key, open.value.filter((item) => item.domain === key).length],
)))
const selectedElement = computed(() => props.elements.find((item) => item.id === human.value.elementId))
const selectedExcerpt = ref('')
const scrollTop = ref(0)
const rowHeight = 92
const virtualStart = computed(() => Math.max(0, Math.floor(scrollTop.value / rowHeight) - 2))
const virtualItems = computed(() => visible.value.slice(virtualStart.value, virtualStart.value + 10))
const virtualBefore = computed(() => virtualStart.value * rowHeight)
const virtualAfter = computed(() => Math.max(0, (visible.value.length - virtualStart.value - virtualItems.value.length) * rowHeight))

watch(() => props.selection, (value) => {
  if (!value) return
  human.value.elementId = value.elementId
  selectedExcerpt.value = value.excerpt
  showHuman.value = true
})

onMounted(() => review.load(props.projectId))

async function accept(item: Finding) {
  await review.accept(props.projectId, item.id)
  emit('changed')
}
async function addHuman() {
  const element = selectedElement.value
  const anchor = props.anchors[0]
  if (!element || !anchor) return
  await review.human(props.projectId, {
    unit_id: props.unitId, base_revision_id: props.revisionId, element_id: element.id,
    original_excerpt: selectedExcerpt.value || element.text.slice(0, 60), domain: human.value.domain,
    severity: human.value.severity, anchor_type: anchor.kind, anchor_id: anchor.id,
    diagnosis: human.value.diagnosis, suggestion: human.value.suggestion,
    suggested_patch: { expected_text: element.text, replacement: [{
      [props.medium === 'novel' ? 'block_id' : 'para_id']: element.id,
      type: element.type, text: human.value.suggestion || element.text,
    }] },
  })
  showHuman.value = false
}
async function openTimeline() {
  await review.loadTimeline(props.projectId)
  showTimeline.value = true
}
</script>

<template>
  <aside class="review-panel">
    <header><div><p class="eyebrow">修订面板</p><h3>{{ open.length }} 条待处理</h3></div><button class="secondary" @click="review.scan(projectId, unitId)">审读本{{ unitId.startsWith('scene') ? '场' : '章' }}</button></header>
    <div v-if="review.busy" class="review-busy">{{ review.busy }}</div><div v-if="review.error" class="error">{{ review.error }}</div>
    <nav class="review-modes"><button v-for="item in ([['severity','严重度'],['domain','维度'],['unit','当前单元']] as const)" :key="item[0]" :class="{ active: mode === item[0] }" @click="mode = item[0]">{{ item[1] }}</button></nav>
    <div v-if="mode === 'domain'" class="domain-counts"><span v-for="(count, key) in counts" :key="key">{{ key }} <b>{{ count }}</b></span></div>
    <div class="source-filter"><button v-for="item in ([['all','全部'],['human','🙋 人工'],['ai','🤖 AI']] as const)" :key="item[0]" :class="{ active: source === item[0] }" @click="source = item[0]">{{ item[1] }}</button></div>
    <div class="finding-list" role="list" @scroll="scrollTop = ($event.target as HTMLElement).scrollTop">
      <div :style="{ height: `${virtualBefore}px` }" aria-hidden="true" />
      <article v-for="item in virtualItems" :key="item.id" class="finding-card" :class="`severity-${item.severity}`" role="listitem">
        <button class="finding-summary" @click="expanded = expanded === item.id ? '' : item.id"><i /><span>{{ item.domain }}</span><b>{{ item.source === 'ai' ? 'AI' : '人工' }}</b><small>{{ item.diagnosis }}</small></button>
        <div v-if="expanded === item.id" class="finding-detail"><p class="anchor-chip">{{ item.anchor_type }} · {{ item.anchor_id }}</p><blockquote>{{ item.original_excerpt }}</blockquote><p>{{ item.diagnosis }}</p><p class="suggestion">建议：{{ item.suggestion }}</p><small>置信度 {{ item.confidence }} · {{ item.author }}</small><div><button @click="emit('locate', item.element_id, item.id)">📍定位</button><button class="accept" @click="accept(item)">✓ 采纳</button><button @click="review.dismiss(projectId, item.id)">✗ 忽略</button></div></div>
      </article>
      <div :style="{ height: `${virtualAfter}px` }" aria-hidden="true" />
      <p v-if="!visible.length" class="muted">当前筛选下没有待处理修订。</p>
    </div>
    <div class="review-footer-actions"><button class="secondary" @click="showHuman = !showHuman">＋ 人工意见</button><button class="secondary" @click="openTimeline">修订时间线</button></div>
    <form v-if="showHuman" class="human-form" @submit.prevent="addHuman"><select v-model="human.elementId" required><option value="">选择正文块</option><option v-for="item in elements" :key="item.id" :value="item.id">{{ item.text.slice(0, 24) }}</option></select><div><select v-model="human.domain"><option v-for="item in ['worldview','character','arc','event','foreshadow']" :key="item">{{ item }}</option></select><select v-model="human.severity"><option v-for="item in ['blocker','major','minor']" :key="item">{{ item }}</option></select></div><textarea v-model="human.diagnosis" required placeholder="诊断" /><textarea v-model="human.suggestion" required placeholder="建议稿" /><button class="primary">保存意见</button></form>
    <div v-if="showTimeline" class="timeline-backdrop" @click.self="showTimeline = false"><section class="timeline-modal"><header><h2>修订时间线</h2><button @click="showTimeline = false">关闭</button></header><ol><li v-for="event in review.timeline" :key="event.id"><b>{{ event.payload.action }}</b><time>{{ new Date(event.occurred_at).toLocaleString() }}</time></li></ol><p v-if="!review.timeline.length" class="muted">还没有修订事件。</p></section></div>
  </aside>
</template>
