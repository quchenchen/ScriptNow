<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useLocale } from '@scriptnow/shared'

import ReviewPanel from './ReviewPanel.vue'
import NovelDeliveryPanel from './NovelDeliveryPanel.vue'
import NovelQualityPanel from './NovelQualityPanel.vue'
import NovelStoryMapEditor from './NovelStoryMapEditor.vue'
import NarrativeGraphPanel from './NarrativeGraphPanel.vue'
import SourceCitations from './SourceCitations.vue'
import SourceDistillationPanel from './SourceDistillationPanel.vue'
import { pickCreativeCopy } from '../creativeCopy'
import { fieldDisplayLabel } from '../semanticLabels'
import { manuscriptProgress } from '../manuscriptMetrics'
import { streamedCandidateBlocks } from '../streamingCandidate'
import { useDockStore } from '../stores/dock'
import { useLayoutStore } from '../stores/layout'
import { selectChapterDocument, useNovelStore, type NovelState } from '../stores/novel'
import { useReviewStore } from '../stores/review'

const props = defineProps<{ projectId: string; sourceMode?: 'original' | 'adaptation' }>()
const novel = useNovelStore()
const review = useReviewStore()
const dock = useDockStore()
const layout = useLayoutStore()
const { isEnglish, locale } = useLocale()
const ui = (zh: string, en: string) => isEnglish.value ? en : zh
const feedback = ref('')
const blueprintFeedback = ref('')
const blueprintFeedbackCategory = ref('整体蓝图')
const storyMapFeedback = ref('')
const revisingBlueprint = ref(false)
const ideationVision = computed(() => pickCreativeCopy('novelIdeation', locale.value))
const storyMapVision = computed(() => pickCreativeCopy('novelStoryMap', locale.value))
const writerReadyVision = computed(() => pickCreativeCopy('novelWriterReady', locale.value))
const blueprintTab = ref<'foundation' | 'character' | 'relationship' | 'arc' | 'plot' | 'foreshadow'>('foundation')
const sideTab = ref<'context' | 'review'>('context')
const editingStructure = ref(false)
const activeCores = computed(() => novel.state?.story_cores.filter((item) => item.status !== 'expired') ?? [])
const adoptedCore = computed(() => novel.state?.story_cores.find((item) => item.status === 'adopted'))
const blueprintCandidate = computed(() => novel.state?.blueprint_candidates.find((item) => item.status === 'active'))
const storyMapCandidate = computed(() => novel.state?.story_map_candidates.find((item) => item.status === 'active'))
async function regenerateCores() {
  const instruction = feedback.value.trim()
  if (!instruction || novel.busy) return
  try {
    await novel.generateCores(props.projectId, instruction)
    feedback.value = ''
  } catch {
    // The store exposes the actionable error above the candidates. Keep the writer's feedback.
  }
}
const visibleBlueprintAnchors = computed(() => blueprintCandidate.value?.anchors ?? novel.state?.blueprint?.anchors ?? [])
const blueprintGroups = [
  { key: 'foundation', label: '世界与母题', kinds: ['world', 'motif'] },
  { key: 'character', label: '人物', kinds: ['character'] },
  { key: 'relationship', label: '关系网络', kinds: ['relationship'] },
  { key: 'arc', label: '人物弧线', kinds: ['character_arc'] },
  { key: 'plot', label: '情节推进', kinds: ['plot', 'event'] },
  { key: 'foreshadow', label: '伏笔与回收', kinds: ['foreshadow'] },
] as const
const visibleBlueprintGroup = computed(() => blueprintGroups.find((item) => item.key === blueprintTab.value)!)
const filteredBlueprintAnchors = computed(() => visibleBlueprintAnchors.value.filter((item) => visibleBlueprintGroup.value.kinds.includes(item.kind as never)))
const blueprintCoverage = computed(() => blueprintGroups.map((group) => ({
  ...group,
  count: visibleBlueprintAnchors.value.filter((item) => group.kinds.includes(item.kind as never)).length,
})))
const blueprintCoverageScore = computed(() => blueprintCoverage.value.filter((item) => item.count > 0).length)
const visibleVolumes = computed(() => storyMapCandidate.value?.volumes ?? novel.state?.story_map.volumes ?? [])
const adoptedDocuments = computed(() => novel.state?.documents.filter((item) => item.status === 'adopted') ?? [])
const adoptedChapterIds = computed(() => new Set(adoptedDocuments.value.map((item) => item.chapter_id)))
const focusedUnitId = ref('chapter-1')
const focusedDocument = computed(() => selectChapterDocument(novel.state?.documents ?? [], focusedUnitId.value))
const focusedDocumentIsAdopted = computed(() => focusedDocument.value?.status === 'adopted')
const focusedChapter = computed(() => novel.state?.story_map.volumes.flatMap((volume) => volume.chapters).find((chapter) => chapter.id === focusedUnitId.value))
const focusedContentBlocks = computed(() => focusedDocument.value?.blocks.filter((block, index) => !(index === 0 && block.type === 'heading')) ?? [])
type EditableNovelBlock = NovelState['documents'][number]['blocks'][number]
const liveCandidateBlocks = computed(() => streamedCandidateBlocks(
  dock.stream.filter((block) => block.block === 'text' && block.text).map((block) => block.text).join(''),
))
const editingCandidate = ref(false)
const draftBlocks = ref<EditableNovelBlock[]>([])
function beginCandidateEdit() {
  if (!focusedDocument.value || focusedDocumentIsAdopted.value || novel.busy) return
  draftBlocks.value = focusedDocument.value.blocks.map((block) => ({ ...block }))
  editingCandidate.value = true
  void nextTick(() => document.querySelectorAll<HTMLTextAreaElement>('.editor-block textarea').forEach(resizeEditorBlock))
}
function resizeEditorBlock(target: HTMLTextAreaElement | Event) {
  const input = target instanceof HTMLTextAreaElement ? target : target.currentTarget as HTMLTextAreaElement
  input.style.height = 'auto'
  input.style.height = `${input.scrollHeight}px`
}
function cancelCandidateEdit() {
  editingCandidate.value = false
  draftBlocks.value = []
}
function insertEditorBlock(afterIndex: number, type = 'prose', text = '') {
  draftBlocks.value.splice(afterIndex + 1, 0, {
    block_id: `human-${crypto.randomUUID()}`,
    type,
    text,
  })
  void nextTick(() => document.querySelectorAll<HTMLTextAreaElement>('.editor-block textarea')[afterIndex + 1]?.focus())
}
function removeEditorBlock(index: number) {
  if (index === 0 || draftBlocks.value.length <= 3) return
  draftBlocks.value.splice(index, 1)
}
function handleEditorKeydown(event: KeyboardEvent, index: number) {
  const input = event.currentTarget as HTMLTextAreaElement
  if (event.key === 'Enter' && !event.shiftKey && draftBlocks.value[index].type !== 'quote') {
    event.preventDefault()
    const start = input.selectionStart
    const end = input.selectionEnd
    const current = draftBlocks.value[index]
    const remainder = current.text.slice(end)
    current.text = current.text.slice(0, start)
    insertEditorBlock(index, 'prose', remainder)
  } else if (event.key === 'Backspace' && input.selectionStart === 0 && input.selectionEnd === 0 && index > 1) {
    event.preventDefault()
    const previous = draftBlocks.value[index - 1]
    const current = draftBlocks.value[index]
    const joinAt = previous.text.length
    previous.text += current.text
    draftBlocks.value.splice(index, 1)
    void nextTick(() => {
      const target = document.querySelectorAll<HTMLTextAreaElement>('.editor-block textarea')[index - 1]
      target?.focus()
      target?.setSelectionRange(joinAt, joinAt)
    })
  }
}
async function saveCandidateEdit() {
  if (!focusedDocument.value || !editingCandidate.value || novel.busy) return
  if (!draftBlocks.value.every((block) => block.type === 'divider' || block.text.trim())) return
  const revisionId = focusedDocument.value.id
  const savedDraft = draftBlocks.value.map((block) => ({ ...block, text: block.text.trim() }))
  editingCandidate.value = false
  try {
    await novel.saveManualChapterRevision(
      props.projectId,
      focusedUnitId.value,
      revisionId,
      savedDraft,
    )
    draftBlocks.value = []
  } catch {
    editingCandidate.value = true
    draftBlocks.value = savedDraft
    void nextTick(() => document.querySelectorAll<HTMLTextAreaElement>('.editor-block textarea').forEach(resizeEditorBlock))
  }
}
const reviewElements = computed(() => focusedDocument.value?.blocks.map((item) => ({ id: item.block_id, text: item.text, type: item.type })) ?? [])
const severityByElement = computed(() => Object.fromEntries(review.items.filter((item) => item.status === 'open').map((item) => [item.element_id, item.severity])))
const selection = ref<{ elementId: string; excerpt: string; nonce: number; x: number; y: number }>()
const reviewSelection = ref<{ elementId: string; excerpt: string; nonce: number }>()
function captureSelection() {
  const value = window.getSelection()
  const excerpt = value?.toString().trim() ?? ''
  const parent = value?.anchorNode?.parentElement?.closest<HTMLElement>('[data-element-id]')
  const blockType = focusedDocument.value?.blocks.find((block) => block.block_id === parent?.dataset.elementId)?.type
  if (excerpt.length < 2 || !parent || !['prose', 'dialogue', 'quote'].includes(blockType ?? '')) { selection.value = undefined; return }
  const range = value!.getRangeAt(0).getBoundingClientRect()
  selection.value = { elementId: parent.dataset.elementId!, excerpt: excerpt.slice(0, 120), nonce: Date.now(), x: range.left + range.width / 2, y: range.top - 8 }
}
function useSelection(operation: 'expand' | 'shorten' | 'polish' | 'revise') {
  if (!selection.value || !focusedDocument.value) return
  if (operation === 'revise') {
    reviewSelection.value = { elementId: selection.value.elementId, excerpt: selection.value.excerpt, nonce: Date.now() }
    selection.value = undefined
    return
  }
  dock.setQuote({
    medium: 'novel', operation, unit_id: focusedDocument.value.chapter_id,
    revision_id: focusedDocument.value.id, element_id: selection.value.elementId,
    excerpt: selection.value.excerpt,
  })
  selection.value = undefined
}
function selectChapter(chapterId: string) {
  cancelCandidateEdit()
  focusedUnitId.value = chapterId
  dock.setFocus('novel', chapterId)
}
async function saveStoryMapDraft(volumes: NovelState['story_map']['volumes']) {
  await novel.proposeStoryMap(props.projectId, novel.state!.story_map.version, volumes)
  editingStructure.value = false
}
async function reviseBlueprint() {
  const instruction = blueprintFeedback.value.trim()
  if (!instruction || revisingBlueprint.value) return
  revisingBlueprint.value = true
  try {
    dock.role = 'architect'
    dock.expanded = true
    await novel.generateBlueprint(props.projectId, `${blueprintFeedbackCategory.value}: ${instruction}`)
    blueprintFeedback.value = ''
  } finally {
    revisingBlueprint.value = false
  }
}
async function reviseStoryMap() {
  const instruction = storyMapFeedback.value.trim()
  if (!instruction) return
  dock.role = 'architect'
  dock.expanded = true
  storyMapFeedback.value = ''
  await novel.generateStoryMap(props.projectId, instruction)
}
async function generateChapterCandidate() {
  if (!focusedUnitId.value || novel.busy) return
  dock.role = 'writer'
  dock.expanded = true
  const chapter = focusedChapter.value
  const brief = chapter ? `生成第 ${focusedUnitId.value} 章「${chapter.title}」候选稿` : `生成章节候选稿`
  // Notify dock so the generation trace is visible in conversation history
  dock.send(props.projectId, brief).catch(() => undefined)
  try {
    await novel.generateChapter(props.projectId, focusedUnitId.value)
  } catch {
    // The store keeps the actionable failure visible while the confirmed draft remains intact.
  } finally {
    dock.expanded = false
  }
}
async function condenseChapterCandidate() {
  if (!focusedUnitId.value || !focusedDocument.value || novel.busy) return
  const target = focusedChapter.value?.target_words
  if (!target) return
  dock.role = 'writer'
  dock.expanded = true
  dock.send(props.projectId, `精简第 ${focusedUnitId.value} 章候选稿`).catch(() => undefined)
  const current = focusedProgress.value.count
  const desiredMinimum = Math.round(target * 0.8)
  const desiredMaximum = Math.round(target * 0.95)
  const reduction = Math.max(20, Math.round((1 - desiredMaximum / current) * 100))
  try {
    await novel.generateChapter(props.projectId, focusedUnitId.value, {
      sourceRevisionId: focusedDocument.value.id,
      feedback: `这是严格的编辑型精简，不是重新创作。将当前 ${current} words 候选稿压缩至少 ${reduction}%，最终控制在 ${desiredMinimum}–${desiredMaximum} words。禁止增加新场景、新情节或新解释；优先删除重复情绪说明、背景解释、过渡与次要描写，合并相邻动作。必须保留完整因果链、人物选择、高潮与结局，不得机械截断。输出前自行复核字数。`,
    })
  } catch {
    // The source revision remains available if generation does not complete.
  } finally {
    dock.expanded = false
  }
}
const writingProgress = (blocks: Array<{ text: string }>) => manuscriptProgress(
  blocks,
  novel.state?.creative_language ?? 'zh-CN',
  focusedChapter.value?.target_words,
)
const targetRange = computed(() => {
  const target = focusedChapter.value?.target_words
  return target ? `${Math.round(target * 0.8)}–${Math.round(target * 1.2)}` : '—'
})
const focusedProgress = computed(() => writingProgress(
  editingCandidate.value ? draftBlocks.value : focusedDocument.value?.blocks ?? [],
))

async function locate(elementId: string) {
  await nextTick()
  const element = document.querySelector(`[data-element-id="${CSS.escape(elementId)}"]`)
  element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  element?.classList.add('finding-pulse')
  window.setTimeout(() => element?.classList.remove('finding-pulse'), 1800)
}

const reloadDocument = () => novel.load(props.projectId)
const closeSelection = () => { selection.value = undefined }
const closeSelectionOnKey = (event: KeyboardEvent) => { if (event.key === 'Escape') closeSelection() }
const closeSelectionOutside = (event: PointerEvent) => {
  if (selection.value && !(event.target as Element).closest('.selection-popover')) closeSelection()
}
onMounted(() => {
  void novel.load(props.projectId)
  window.addEventListener('scriptnow:document-changed', reloadDocument)
  window.addEventListener('keydown', closeSelectionOnKey)
  window.addEventListener('scroll', closeSelection, true)
  window.addEventListener('pointerdown', closeSelectionOutside)
})
onUnmounted(() => {
  layout.leaveWriter()
  window.removeEventListener('scriptnow:document-changed', reloadDocument)
  window.removeEventListener('keydown', closeSelectionOnKey)
  window.removeEventListener('scroll', closeSelection, true)
  window.removeEventListener('pointerdown', closeSelectionOutside)
})
watch(() => novel.state?.phase, (phase) => {
  if (phase === 'seeded') layout.setStudioView('ideation')
  else if (phase === 'story_core_adopted') layout.setStudioView('blueprint')
  else if (phase === 'blueprint_adopted') layout.setStudioView('storymap')
  else if (phase) layout.setStudioView('writer')
  dock.role = phase === 'seeded' ? 'director' : phase === 'story_core_adopted' || phase === 'blueprint_adopted' ? 'architect' : 'writer'
  void dock.loadTransparency(props.projectId)
}, { immediate: true })
watch(() => novel.state?.story_map.volumes, (volumes) => {
  const chapters = volumes?.flatMap((volume) => volume.chapters) ?? []
  if (chapters.length && !chapters.some((chapter) => chapter.id === focusedUnitId.value)) {
    focusedUnitId.value = chapters[0].id
  }
  if (focusedUnitId.value) dock.setFocus('novel', focusedUnitId.value)
}, { immediate: true })
watch(() => focusedDocument.value?.id, () => cancelCandidateEdit())
</script>

<template>
  <div v-if="!novel.state" class="studio-loading">{{ ui('正在读取 Novel 创作状态…', 'Loading the novel workspace…') }}</div>
  <div v-else class="novel-studio">
    <div v-if="novel.busy" class="run-banner" aria-live="polite"><i />{{ novel.busy }}<span>领域工作流</span></div>
    <div v-if="novel.error" class="error" role="alert">{{ novel.error }}</div>

    <section v-if="layout.studioView === 'ideation'" class="studio-stage">
      <header><p class="eyebrow">{{ ui('小说发散 · 灵感导演', 'Novel ideation · Creative director') }}</p><h2>{{ ideationVision }}</h2><p>{{ ui('比较三个故事方向，选择最值得继续生长的一条。', 'Compare three distinct story directions and choose the one worth growing.') }}</p></header>
      <SourceDistillationPanel v-if="sourceMode === 'adaptation'" :project-id="projectId" />
      <button v-if="!activeCores.length" class="primary" :disabled="novel.state.phase !== 'seeded'" @click="novel.generateCores(projectId)">{{ novel.state.phase === 'seeded' ? '生成三个小说方向' : '本项目尚无可回看的发散候选' }}</button>
      <div v-else class="core-grid">
        <article v-for="core in activeCores" :key="core.id" class="core-card" :class="{ adopted: core.status === 'adopted' }">
          <span class="candidate-index">0{{ core.ordinal }}</span><h3>{{ core.title }}</h3><p>{{ core.premise }}</p>
          <p class="novel-pov">视角 · {{ core.point_of_view }}</p><div class="chip-row"><span v-for="angle in core.angles" :key="angle">{{ angle }}</span></div>
          <button class="primary" :disabled="Boolean(adoptedCore)" @click="novel.adoptCore(projectId, core.id)">{{ core.status === 'adopted' ? '已采用' : '采用此方向' }}</button>
        </article>
      </div>
      <form v-if="activeCores.length && !adoptedCore" class="revision-request" @submit.prevent="regenerateCores"><label>请求修订<input v-model="feedback" required placeholder="例如：加强内心冲突，降低情节密度" /></label><button class="secondary" :disabled="Boolean(novel.busy)">重新发散</button></form>
    </section>

    <section v-else-if="layout.studioView === 'blueprint'" class="studio-stage planning-workspace">
      <header class="planning-header"><div><p class="eyebrow">{{ ui('小说蓝图 · 故事建筑师', 'Novel blueprint · Story architect') }}</p><h2>{{ adoptedCore?.title ?? ui('等待小说方向', 'Waiting for a story direction') }}</h2><p>{{ ui('逐层检查人物为何行动、关系如何变化、情节怎样升级，以及承诺如何回收。', 'Examine motivation, relationships, escalation, and payoff as separate creative layers.') }}</p></div><span class="candidate-state">{{ blueprintCandidate ? ui('候选待决策', 'Candidate awaiting decision') : novel.state.blueprint ? ui('已采纳', 'Adopted') : ui('尚未生成', 'Not generated') }}</span></header>
      <template v-if="visibleBlueprintAnchors.length">
        <section class="blueprint-health" :class="{ incomplete: blueprintCoverageScore < blueprintGroups.length }"><div><strong>蓝图完整性 {{ blueprintCoverageScore }}/{{ blueprintGroups.length }}</strong><span>{{ blueprintCoverageScore === blueprintGroups.length ? '关键创作层已覆盖，可逐类审阅。' : '仍有创作层缺失，建议反馈给故事建筑师补全后再进入结构规划。' }}</span></div><div><span v-for="item in blueprintCoverage" :key="item.key" :class="{ missing: !item.count }">{{ item.label }} {{ item.count || '缺失' }}</span></div></section>
        <nav class="blueprint-tabs" aria-label="小说蓝图类别"><button v-for="item in blueprintGroups" :key="item.key" :class="{ active: blueprintTab === item.key }" @click="blueprintTab = item.key">{{ item.label }}<small>{{ blueprintCoverage.find((coverage) => coverage.key === item.key)?.count ?? 0 }}</small></button></nav>
        <div v-if="filteredBlueprintAnchors.length" class="anchor-grid candidate-grid"><article v-for="anchor in filteredBlueprintAnchors" :key="anchor.id"><h3>{{ anchor.name }}</h3><p>{{ anchor.payload.description ?? '服务于长篇人物变化与叙述约束的小说锚点。' }}</p><dl class="blueprint-meta"><template v-for="(value, key) in anchor.payload" :key="key"><div v-if="key !== 'description'"><dt>{{ fieldDisplayLabel(String(key)) }}</dt><dd>{{ Array.isArray(value) ? value.join(' · ') : value }}</dd></div></template></dl></article></div>
        <div v-else class="blueprint-gap"><strong>{{ visibleBlueprintGroup.label }}尚未形成</strong><p>这一层会直接影响后续章节因果与审读，请让故事建筑师补充，而不是用其他卡片代替。</p></div>
        <form class="blueprint-feedback" @submit.prevent="reviseBlueprint"><header><div><strong>反馈给故事建筑师</strong><small>基于当前版本和项目事实生成新版候选，原蓝图不会被直接覆盖。</small></div></header><div><label>反馈范围<select v-model="blueprintFeedbackCategory"><option v-for="item in blueprintGroups" :key="item.key">{{ item.label }}</option><option>整体蓝图</option></select></label><label>修订要求<textarea v-model="blueprintFeedback" rows="3" required placeholder="例如：目前缺少推动中段转折的事件链，并补齐两条可以在结尾回收的伏笔" /></label></div><button class="secondary" :disabled="revisingBlueprint || !blueprintFeedback.trim()">{{ revisingBlueprint ? '故事建筑师正在重构…' : '发送反馈并生成新版' }}</button></form>
        <div v-if="blueprintCandidate" class="decision-bar"><div><strong>小说蓝图候选</strong><small>{{ blueprintCoverageScore === blueprintGroups.length ? '确认各层内容满足创作方向后，再作为 StoryMap 与审读的项目事实。' : '蓝图尚有缺失，可先反馈修订；仍可由你决定是否采纳。' }}</small></div><button class="primary" @click="novel.adoptBlueprint(projectId, blueprintCandidate.id)">确认并采纳整套蓝图</button></div><div v-else class="adopted-notice"><strong>已采纳小说蓝图 v{{ novel.state.blueprint?.version }}</strong><span>这些锚点正在被卷章结构、正文上下文和小说审读引用。</span></div>
      </template>
      <div v-else class="planning-empty"><p>采用 StoryCore 后，可生成角色、关系、世界压力、人物内在弧线和母题候选。</p><button class="primary" :disabled="!adoptedCore" @click="novel.generateBlueprint(projectId)">生成小说蓝图候选</button></div>
    </section>

    <NarrativeGraphPanel v-else-if="layout.studioView === 'graph'" :project-id="projectId" />

    <section v-else-if="layout.studioView === 'storymap'" class="studio-stage planning-workspace">
      <header class="planning-header"><div><p class="eyebrow">{{ ui('小说 StoryMap · 故事建筑师', 'Novel StoryMap · Story architect') }}</p><h2>{{ storyMapVision }}</h2><p>{{ ui('规划卷、章与 Story Beat；小说结构不复用剧本的场次或时长语义。', 'Plan volumes, chapters, and story beats using the novel domain model.') }}</p></div><span class="candidate-state">{{ ui('蓝图', 'Blueprint') }} v{{ novel.state.blueprint?.version }}</span></header>
      <div class="anchor-grid"><article v-for="anchor in novel.state.blueprint?.anchors" :key="anchor.id"><h3>{{ anchor.name }}</h3></article></div>
      <NovelStoryMapEditor v-if="editingStructure" :volumes="visibleVolumes" @save="saveStoryMapDraft" @cancel="editingStructure = false" />
      <template v-else-if="visibleVolumes.length"><section class="storymap-candidate"><div class="storymap-heading"><div><p class="eyebrow">{{ storyMapCandidate ? '结构候选' : '已采纳结构' }}</p><h3>卷 → 章 → 故事节拍</h3></div><span>候选 #{{ novel.state.story_map_candidates.length }} · 基于 StoryMap v{{ storyMapCandidate?.base_version ?? novel.state.story_map.version }}</span></div><article v-for="volume in visibleVolumes" :key="volume.id" class="storymap-group"><header><strong>第 {{ volume.ordinal }} 卷 · {{ volume.title }}</strong><small>{{ volume.chapters.length }} 章</small></header><div v-for="chapter in volume.chapters" :key="chapter.id" class="storymap-unit novel-map-unit"><span>{{ volume.ordinal }}-{{ chapter.ordinal }}</span><div><strong>{{ chapter.title }}</strong><p v-for="beat in chapter.beats ?? []" :key="beat.id">{{ beat.objective }}</p></div><small>{{ chapter.target_words }} 字 · {{ chapter.point_of_view }}</small></div></article></section><div v-if="storyMapCandidate" class="decision-bar"><div><strong>影响确认</strong><small>新增 {{ storyMapCandidate.impact.added_units }} · 删除 {{ storyMapCandidate.impact.removed_units }} · 保留 {{ storyMapCandidate.impact.retained_units }}</small></div><div class="decision-actions"><button class="secondary" @click="editingStructure = true">调整候选</button><button class="primary" @click="novel.adoptStoryMap(projectId, storyMapCandidate.id)">确认 StoryMap 并进入写作</button></div></div><div v-else class="adopted-notice"><div><strong>小说 StoryMap 已采纳</strong><span>点击左侧逐章写作进入主笔工作区；调整将形成新候选。</span></div><button class="secondary" @click="editingStructure = true">提出结构调整</button></div><form class="blueprint-feedback storymap-feedback" @submit.prevent="reviseStoryMap"><header><div><strong>反馈给故事建筑师</strong><small>基于当前版本和项目事实生成新版候选，原卷章结构不会被直接覆盖。</small></div></header><div class="feedback-row"><label>修订要求<textarea v-model="storyMapFeedback" rows="3" required placeholder="例如：第一卷的章节太少无法承载设定的角色数量，或结局代价与 Emotion Promise 不匹配" /></label></div><button class="secondary" :disabled="Boolean(novel.busy) || !storyMapFeedback.trim()">{{ novel.busy ? '故事建筑师正在重构…' : '发送反馈并生成新版' }}</button></form></template>
      <div v-else class="planning-empty"><p>采纳蓝图后生成结构；生成前不会改变当前卷章目录，生成后可逐章检查目标字数、视角与 Story Beat。</p><button class="primary" :disabled="!novel.state.blueprint" @click="novel.generateStoryMap(projectId)">生成卷章 StoryMap 候选</button></div>
    </section>

    <template v-else-if="novel.state.story_map.volumes.length">
    <NovelDeliveryPanel :project-id="projectId" />
    <section class="studio-stage novel-writing-stage" :class="{ 'sidecar-hidden': layout.writerSidecarHidden }" @mouseup="captureSelection">
      <aside class="novel-outline"><p class="eyebrow">Novel StoryMap</p><article v-for="volume in novel.state.story_map.volumes" :key="volume.id"><h3>{{ isEnglish ? `Volume ${volume.ordinal}` : `第 ${volume.ordinal} 卷` }} · {{ volume.title }}</h3><button v-for="chapter in volume.chapters" :key="chapter.id" class="chapter-row" :class="{ adopted: adoptedChapterIds.has(chapter.id), active: focusedUnitId === chapter.id }" :aria-current="focusedUnitId === chapter.id ? 'true' : undefined" :aria-label="`${chapter.ordinal}. ${chapter.title}`" :disabled="Boolean(novel.busy)" @click="selectChapter(chapter.id)"><span>{{ chapter.ordinal }}</span><strong>{{ chapter.title }}</strong></button></article></aside>
      <main class="novel-editor">
        <article v-if="focusedDocument" :key="focusedDocument.id" class="novel-page" :lang="novel.state.creative_language" :class="{ 'candidate-editing': editingCandidate }">
          <h2>{{ focusedChapter?.title ?? `第 ${focusedChapter?.ordinal ?? ''} 章` }}</h2>
          <div v-if="!focusedDocumentIsAdopted" class="chapter-candidate-notice">
            <div><strong>章节候选稿 · 修订 {{ focusedDocument.revision_number }} · {{ focusedDocument.source === 'human' ? '人工修订' : 'Agent 原稿' }}</strong><span>{{ editingCandidate ? '保存后将形成新的人工修订版本，当前版本不会被覆盖。' : '候选稿已完成校验，可以人工修订或确认采纳。' }}</span><span v-if="focusedProgress.status !== 'on-target'" class="length-guidance" :class="`length-${focusedProgress.status}`">当前 {{ focusedProgress.count }} {{ focusedProgress.unit }}；建议区间 {{ targetRange }} {{ focusedProgress.unit }}。内容不会被拦截，可保留有效段落后调整篇幅。</span></div>
            <div v-if="editingCandidate" class="chapter-decision-actions"><button class="secondary" :disabled="Boolean(novel.busy)" @click="cancelCandidateEdit">取消</button><button class="primary" :disabled="Boolean(novel.busy)" @click="saveCandidateEdit">另存人工修订</button></div>
            <div v-else class="chapter-decision-actions"><button class="secondary" :disabled="Boolean(novel.busy)" @click="generateChapterCandidate">重新生成</button><button v-if="focusedProgress.status === 'over'" class="secondary" :disabled="Boolean(novel.busy)" @click="condenseChapterCandidate">智能精简</button><button class="secondary" :disabled="Boolean(novel.busy)" @click="beginCandidateEdit">人工修订</button><button class="primary" :disabled="Boolean(novel.busy)" @click="novel.adoptChapter(projectId, focusedUnitId, focusedDocument.id)">确认此版正文</button></div>
          </div>
          <div v-else class="chapter-adopted-toolbar"><span>当前为已确认正文，选择章节不会改变确认状态。</span><button class="secondary" :disabled="Boolean(novel.busy)" @click="generateChapterCandidate">生成新版候选</button></div>
          <section v-if="editingCandidate" class="candidate-block-editor" aria-label="候选稿编辑器">
            <article v-for="(block, index) in draftBlocks" :key="block.block_id" class="editor-block" :class="`editor-${block.type}`">
              <div class="block-toolbar"><button v-if="index > 0" type="button" title="在下方新增段落" @click="insertEditorBlock(index)">＋</button><span>{{ index === 0 ? '章节标题' : `段落 ${index}` }}</span><select v-model="block.type" :disabled="index === 0" aria-label="内容块类型"><option value="heading">标题</option><option value="prose">正文</option><option value="dialogue">对话</option><option value="quote">引文 / 书信</option><option value="divider">分隔</option></select><button v-if="index > 0" type="button" title="删除此段落" @click="removeEditorBlock(index)">×</button></div>
              <textarea v-if="block.type !== 'divider'" v-model="block.text" :class="`block-${block.type}`" :aria-label="index === 0 ? '章节标题' : `正文段落 ${index}`" spellcheck="true" @input="resizeEditorBlock" @keydown="handleEditorKeydown($event, index)" />
              <button v-else type="button" class="divider-preview" @click="block.type = 'prose'">＊ ＊ ＊</button>
            </article>
            <button type="button" class="add-final-block" @click="insertEditorBlock(draftBlocks.length - 1)">＋ 添加段落</button>
          </section>
          <template v-else v-for="block in focusedContentBlocks" :key="block.block_id"><h3 v-if="block.type === 'heading'" :data-element-id="block.block_id" :class="severityByElement[block.block_id] && `finding-mark severity-${severityByElement[block.block_id]}`">{{ block.text }}</h3><hr v-else-if="block.type === 'divider'" :data-element-id="block.block_id" /><blockquote v-else-if="block.type === 'quote'" :data-element-id="block.block_id" :class="severityByElement[block.block_id] && `finding-mark severity-${severityByElement[block.block_id]}`">{{ block.text }}</blockquote><p v-else :data-element-id="block.block_id" :class="severityByElement[block.block_id] && `finding-mark severity-${severityByElement[block.block_id]}`">{{ block.text }}</p></template>
          <footer :class="`length-${writingProgress(editingCandidate ? draftBlocks : focusedDocument.blocks).status}`">{{ writingProgress(editingCandidate ? draftBlocks : focusedDocument.blocks).count }} / {{ focusedChapter?.target_words ?? '—' }} {{ writingProgress(editingCandidate ? draftBlocks : focusedDocument.blocks).unit }} · 修订 {{ focusedDocument.revision_number }} · {{ editingCandidate ? '编辑中（未保存）' : focusedDocumentIsAdopted ? '正文已确认' : '候选待确认' }}</footer>
        </article>
        <article v-else-if="liveCandidateBlocks.length" class="novel-page streaming-candidate" :lang="novel.state.creative_language" aria-live="polite">
          <div class="chapter-candidate-notice"><div><strong>{{ novel.busy ? '候选稿生成中 · 只读预览' : '未完成的生成草稿 · 只读' }}</strong><span>{{ novel.busy ? '完整结构校验通过前不可编辑或采纳；断线重连后会按事件游标恢复。' : '本次生成没有形成可采纳候选，已完成的段落仅供检查；可重新生成。' }}</span></div><button v-if="!novel.busy" class="secondary" @click="generateChapterCandidate">重新生成</button></div>
          <template v-for="block in liveCandidateBlocks" :key="block.block_id"><h3 v-if="block.type === 'heading'">{{ block.text }}</h3><hr v-else-if="block.type === 'divider'" /><blockquote v-else-if="block.type === 'quote'">{{ block.text }}</blockquote><p v-else>{{ block.text }}</p></template>
          <footer :class="`length-${writingProgress(liveCandidateBlocks).status}`">{{ writingProgress(liveCandidateBlocks).count }} / {{ focusedChapter?.target_words ?? '—' }} {{ writingProgress(liveCandidateBlocks).unit }} · {{ novel.busy ? '正在生成与校验' : '未完成，不可采纳' }}</footer>
        </article>
        <div v-else class="writer-empty"><p class="eyebrow">主笔</p><h2>{{ focusedChapter?.title ?? writerReadyVision }}</h2><p>{{ novel.busy ? '主笔正在生成候选稿。正文段落将在形成后以只读方式出现。' : '尚未生成本章正文。生成后先作为候选稿展示，不会自动确认。' }}</p><button class="primary" :disabled="Boolean(novel.busy)" @click="generateChapterCandidate">{{ novel.busy ? '生成中…' : '生成当前章候选稿' }}</button></div>
      </main>
      <button v-if="layout.writerSidecarHidden" class="sidecar-restore" aria-label="显示上下文与审读面板" @click="layout.setWriterSidecarHidden(false)">显示上下文 / 审读</button>
      <aside v-else class="writer-sidecar">
        <nav class="sidecar-tabs" aria-label="写作辅助"><button :class="{ active: sideTab === 'context' }" @click="sideTab = 'context'">上下文</button><button :class="{ active: sideTab === 'review' }" @click="sideTab = 'review'">审读</button><button class="sidecar-hide" aria-label="隐藏上下文与审读面板" @click="layout.setWriterSidecarHidden(true)">隐藏</button></nav>
        <section v-if="sideTab === 'context'" class="context-sidecar"><p class="eyebrow">当前章</p><h3>{{ focusedChapter?.title ?? focusedUnitId }}</h3><dl><div><dt>叙述视角</dt><dd>{{ focusedChapter?.point_of_view ?? '—' }}</dd></div><div><dt>目标篇幅</dt><dd>{{ focusedChapter?.target_words ?? '—' }} {{ writingProgress([]).unit }}</dd></div><div><dt>可接受区间</dt><dd>{{ targetRange }} {{ writingProgress([]).unit }}</dd></div><div><dt>当前篇幅</dt><dd>{{ focusedDocument ? writingProgress(focusedDocument.blocks).count : 0 }} {{ writingProgress([]).unit }}</dd></div><div><dt>正文修订</dt><dd>v{{ focusedDocument?.revision_number ?? 0 }}</dd></div></dl><p class="eyebrow">小说蓝图锚点</p><div class="sidecar-anchors"><span v-for="anchor in novel.state.blueprint?.anchors.slice(0, 8)" :key="anchor.id">{{ anchor.name }}</span></div><SourceCitations v-if="sourceMode === 'adaptation'" :project-id="projectId" :query="focusedChapter?.title" /></section>
        <section v-else-if="focusedDocument" class="novel-review-sidecar"><NovelQualityPanel :project-id="projectId" :chapter-id="focusedDocument.chapter_id" :revision-id="focusedDocument.id" /><ReviewPanel medium="novel" :project-id="projectId" :unit-id="focusedDocument.chapter_id" :revision-id="focusedDocument.id" :elements="reviewElements" :anchors="novel.state.blueprint?.anchors ?? []" :selection="reviewSelection" @locate="locate" @changed="novel.load(projectId)" /></section>
        <section v-else class="context-sidecar"><p>生成当前章后即可开始审读。</p></section>
      </aside>
      <div v-if="selection" class="selection-popover" :style="{ left: `${selection.x}px`, top: `${selection.y}px` }"><button @click="useSelection('expand')">扩写</button><button @click="useSelection('shorten')">缩写</button><button @click="useSelection('polish')">润色</button><button @click="useSelection('revise')">修订</button></div>
    </section>
    </template>
    <section v-else class="studio-stage planning-empty"><p>完成 Novel StoryMap 并明确采纳后，逐章写作才会开放。</p><button class="secondary" @click="layout.setStudioView('storymap')">返回 StoryMap</button></section>
  </div>
</template>
