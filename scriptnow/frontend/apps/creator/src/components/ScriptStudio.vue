<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import ReviewPanel from './ReviewPanel.vue'
import ScriptDeliveryPanel from './ScriptDeliveryPanel.vue'
import ScriptStoryMapEditor from './ScriptStoryMapEditor.vue'
import { fieldDisplayLabel, scriptBlueprintCategory } from '../semanticLabels'
import SourceCitations from './SourceCitations.vue'
import { pickCreativeCopy } from '../creativeCopy'
import { useDockStore } from '../stores/dock'
import { useLayoutStore } from '../stores/layout'
import { useReviewStore } from '../stores/review'
import { useScriptStore, type ScriptState } from '../stores/script'

const props = defineProps<{ projectId: string; sourceMode?: 'original' | 'adaptation' }>()
const script = useScriptStore()
const review = useReviewStore()
const dock = useDockStore()
const layout = useLayoutStore()
const feedback = ref('')
const blueprintFeedback = ref('')
const blueprintFeedbackCategory = ref('世界观')
const revisingBlueprint = ref(false)
const sideTab = ref<'context' | 'review'>('context')
const editingStructure = ref(false)
const ideationVision = pickCreativeCopy('scriptIdeation')
const storyMapVision = pickCreativeCopy('scriptStoryMap')
const writerReadyVision = pickCreativeCopy('scriptWriterReady')
const tab = ref<'worldview' | 'character' | 'arc' | 'character_arc' | 'event' | 'foreshadow'>('worldview')
const activeCores = computed(() => script.state?.story_cores.filter((item) => item.status !== 'expired') ?? [])
const hasPlaceholderCores = computed(() => activeCores.value.some((item) => item.concept.includes('建立第 ') || item.title.includes('方向 ')))
const detailLabels: Record<string, string> = { narrative_engine: '叙事推进机制', viewpoint_anchor: '视角与信息策略', pacing_recipe: '关键节奏路径', market_judgement: '优势与创作风险' }
const adoptedCore = computed(() => script.state?.story_cores.find((item) => item.status === 'adopted'))
const blueprintCandidate = computed(() => script.state?.blueprint_candidates.find((item) => item.status === 'active'))
const storyMapCandidate = computed(() => script.state?.story_map_candidates.find((item) => item.status === 'active'))
const visibleBlueprintAnchors = computed(() => blueprintCandidate.value?.anchors ?? script.state?.blueprint?.anchors ?? [])
const visibleEpisodes = computed(() => storyMapCandidate.value?.episodes ?? script.state?.story_map.episodes ?? [])
const adoptedDocuments = computed(
  () => script.state?.documents.filter((item) => item.status === 'adopted') ?? [],
)
const adoptedSceneIds = computed(() => new Set(adoptedDocuments.value.map((item) => item.scene_id)))
const focusedUnitId = ref('scene-1')
const focusedDocument = computed(() => adoptedDocuments.value.find((item) => item.scene_id === focusedUnitId.value))
const focusedCandidate = computed(() =>
  script.state?.documents
    .filter((item) => item.scene_id === focusedUnitId.value && item.status === 'candidate')
    .sort((left, right) => right.revision_number - left.revision_number)[0],
)
const visibleDocument = computed(() => focusedCandidate.value ?? focusedDocument.value)
const focusedScene = computed(() => script.state?.story_map.episodes.flatMap((episode) => episode.scenes).find((scene) => scene.id === focusedUnitId.value))
const reviewElements = computed(() => focusedDocument.value?.blocks.map((item) => ({ id: item.para_id, text: item.text, type: item.type })) ?? [])
const severityByElement = computed(() => Object.fromEntries(review.items.filter((item) => item.status === 'open').map((item) => [item.element_id, item.severity])))
const selection = ref<{ elementId: string; excerpt: string; nonce: number; x: number; y: number }>()
const reviewSelection = ref<{ elementId: string; excerpt: string; nonce: number }>()

function captureSelection() {
  const value = window.getSelection()
  const excerpt = value?.toString().trim() ?? ''
  const parent = value?.anchorNode?.parentElement?.closest<HTMLElement>('[data-element-id]')
  const blockType = focusedDocument.value?.blocks.find((block) => block.para_id === parent?.dataset.elementId)?.type
  if (excerpt.length < 2 || !parent || !['action', 'dialogue'].includes(blockType ?? '')) { selection.value = undefined; return }
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
    medium: 'script', operation, unit_id: focusedDocument.value.scene_id,
    revision_id: focusedDocument.value.id, element_id: selection.value.elementId,
    excerpt: selection.value.excerpt,
  })
  selection.value = undefined
}

async function reviseBlueprint() {
  const instruction = blueprintFeedback.value.trim()
  if (!instruction || revisingBlueprint.value) return
  revisingBlueprint.value = true
  try {
    dock.setCreativeRole('architect')
    dock.expanded = true
    await script.generateBlueprint(props.projectId, `${blueprintFeedbackCategory.value}: ${instruction}`)
    await dock.load(props.projectId)
    blueprintFeedback.value = ''
  } finally {
    revisingBlueprint.value = false
  }
}

function selectScene(sceneId: string) {
  focusedUnitId.value = sceneId
  dock.setFocus('script', sceneId)
}

async function saveStoryMapDraft(episodes: ScriptState['story_map']['episodes']) {
  await script.proposeStoryMap(props.projectId, script.state!.story_map.version, episodes)
  editingStructure.value = false
}

async function locate(elementId: string) {
  await nextTick()
  const element = document.querySelector(`[data-element-id="${CSS.escape(elementId)}"]`)
  element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  element?.classList.add('finding-pulse')
  window.setTimeout(() => element?.classList.remove('finding-pulse'), 1800)
}

const reloadDocument = () => script.load(props.projectId)
const closeSelection = () => { selection.value = undefined }
const closeSelectionOnKey = (event: KeyboardEvent) => { if (event.key === 'Escape') closeSelection() }
const closeSelectionOutside = (event: PointerEvent) => {
  if (selection.value && !(event.target as Element).closest('.selection-popover')) closeSelection()
}
onMounted(() => {
  void script.load(props.projectId)
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
watch(() => script.state?.phase, (phase) => {
  if (phase === 'seeded') layout.setStudioView('ideation')
  else if (phase === 'story_core_adopted') layout.setStudioView('blueprint')
  else if (phase === 'blueprint_adopted') layout.setStudioView('storymap')
  else if (phase) layout.setStudioView('writer')
  dock.setCreativeRole(phase === 'seeded' ? 'director' : phase === 'story_core_adopted' || phase === 'blueprint_adopted' ? 'architect' : 'writer')
  void dock.loadTransparency(props.projectId)
}, { immediate: true })
watch(() => script.state?.story_map.episodes, (episodes) => {
  const scenes = episodes?.flatMap((episode) => episode.scenes) ?? []
  if (scenes.length && !scenes.some((scene) => scene.id === focusedUnitId.value)) {
    focusedUnitId.value = scenes[0].id
  }
  if (focusedUnitId.value) dock.setFocus('script', focusedUnitId.value)
}, { immediate: true })
</script>

<template>
  <div v-if="!script.state" class="studio-loading">正在读取 Script 创作状态…</div>
  <div v-else class="script-studio">
    <div v-if="script.busy" class="run-banner" aria-live="polite"><i />{{ script.busy }} <span>领域工作流</span></div>
    <div v-if="script.error" class="error" role="alert">{{ script.error }}</div>

    <section v-if="layout.studioView === 'ideation'" class="studio-stage">
      <header><p class="eyebrow">创意发散 · 灵感导演</p><h2>{{ ideationVision }}</h2><p>比较三种真正不同的故事发动方式；选择的是完整故事方向，而不是标题偏好。</p></header>
      <button v-if="hasPlaceholderCores && !adoptedCore" class="primary core-repair" @click="script.generateCores(projectId, '替换占位候选，生成具有实质差异且可比较的完整方向')">重新生成可比较候选</button>
      <button v-if="!activeCores.length" class="primary" :disabled="script.state.phase !== 'seeded'" @click="script.generateCores(projectId)">{{ script.state.phase === 'seeded' ? '生成三个 StoryCore' : '本项目尚无可回看的发散候选' }}</button>
      <div v-else class="core-grid">
        <article v-for="core in activeCores" :key="core.id" class="core-card" :class="{ adopted: core.status === 'adopted' }">
          <span class="candidate-index">0{{ core.ordinal }}</span><h3>{{ core.title }}</h3><p>{{ core.concept }}</p>
          <div class="chip-row"><span v-for="angle in core.angles" :key="angle">{{ angle }}</span></div>
          <section class="core-comparison"><dl><template v-for="(values, key) in core.details" :key="key"><dt>{{ detailLabels[key] ?? key }}</dt><dd><span v-for="value in values" :key="value">{{ value }}</span></dd></template></dl></section>
          <button class="primary" :disabled="Boolean(adoptedCore)" @click="script.adoptCore(projectId, core.id)">{{ core.status === 'adopted' ? '已采用' : '采用此方向' }}</button>
        </article>
      </div>
      <form v-if="activeCores.length && !adoptedCore" class="revision-request" @submit.prevent="script.generateCores(projectId, feedback); feedback = ''"><label>请求修订<input v-model="feedback" required placeholder="例如：更私人、更少类型套路" /></label><button class="secondary">重新发散</button></form>
    </section>

    <section v-else-if="layout.studioView === 'blueprint'" class="studio-stage planning-workspace">
      <header class="planning-header"><div><p class="eyebrow">蓝图规划 · 故事建筑师</p><h2>{{ adoptedCore?.title ?? '等待创意方向' }}</h2><p>故事建筑师只提交候选。请逐类检查设定后再明确采纳。</p></div><span class="candidate-state">{{ blueprintCandidate ? '候选待决策' : script.state.blueprint ? '已采纳' : '尚未生成' }}</span></header>
      <template v-if="visibleBlueprintAnchors.length">
        <nav class="blueprint-tabs" aria-label="蓝图类别"><button v-for="item in ([['worldview','世界观'],['character','人物'],['arc','叙事弧线'],['character_arc','人物弧线'],['event','关键事件'],['foreshadow','伏笔网络']] as const)" :key="item[0]" :class="{ active: tab === item[0] }" @click="tab = item[0]">{{ item[1] }}</button></nav>
        <div class="anchor-grid candidate-grid"><article v-for="anchor in visibleBlueprintAnchors.filter((item) => scriptBlueprintCategory(item.kind) === tab)" :key="anchor.id"><h3>{{ anchor.name }}</h3><p>{{ anchor.payload.description ?? '由故事建筑师根据已采用 StoryCore 建立的创作锚点。' }}</p><dl class="blueprint-meta"><template v-for="(value, key) in anchor.payload" :key="key"><div v-if="key !== 'description'"><dt>{{ fieldDisplayLabel(String(key)) }}</dt><dd>{{ Array.isArray(value) ? value.join(' · ') : value }}</dd></div></template></dl></article></div>
        <form v-if="blueprintCandidate" class="blueprint-feedback" @submit.prevent="reviseBlueprint">
          <header><div><strong>反馈给故事建筑师</strong><small>故事建筑师会读取当前候选与项目事实，答复会进入创作搭档；随后生成新候选并使本版过期。</small></div></header>
          <div><label>反馈范围<select v-model="blueprintFeedbackCategory"><option>世界观</option><option>人物</option><option>叙事弧线</option><option>人物弧线</option><option>关键事件</option><option>伏笔网络</option><option>整套蓝图</option></select></label><label>修订要求<textarea v-model="blueprintFeedback" rows="3" required placeholder="例如：世界规则过于通用，需要体现硅基人格、记忆复制与所有权冲突" /></label></div>
          <button class="secondary" :disabled="revisingBlueprint || !blueprintFeedback.trim()">{{ revisingBlueprint ? '故事建筑师正在修订…' : '发送反馈并生成新版' }}</button>
        </form>
        <div v-if="blueprintCandidate" class="decision-bar"><div><strong>蓝图候选</strong><small>确认内容已满足创作方向后，才会成为 StoryMap 与审读引用的项目事实。</small></div><button class="primary" @click="script.adoptBlueprint(projectId, blueprintCandidate.id)">确认并采纳整套蓝图</button></div>
        <div v-else class="adopted-notice"><strong>已采纳蓝图 v{{ script.state.blueprint?.version }}</strong><span>这些锚点正在被 StoryMap、正文上下文与审读引用。</span></div>
      </template>
      <div v-else class="planning-empty"><p>采用 StoryCore 后，可生成世界观、人物、叙事弧线、人物弧线、关键事件与伏笔网络六类候选。</p><button class="primary" :disabled="!adoptedCore" @click="script.generateBlueprint(projectId)">生成蓝图候选</button></div>
    </section>

    <section v-else-if="layout.studioView === 'storymap'" class="studio-stage planning-workspace">
      <header class="planning-header"><div><p class="eyebrow">StoryMap · 故事建筑师</p><h2>{{ storyMapVision }}</h2><p>从蓝图规划分集、场次与 Story Beat；确认影响后才进入逐场写作。</p></div><span class="candidate-state">蓝图 v{{ script.state.blueprint?.version }}</span></header>
      <nav class="blueprint-tabs"><button v-for="item in ([['worldview','世界观'],['character','人物'],['arc','叙事弧线'],['character_arc','人物弧线'],['event','关键事件'],['foreshadow','伏笔网络']] as const)" :key="item[0]" :class="{ active: tab === item[0] }" @click="tab = item[0]">{{ item[1] }}</button></nav>
      <div class="anchor-grid"><article v-for="anchor in script.state.blueprint?.anchors.filter((item) => scriptBlueprintCategory(item.kind) === tab)" :key="anchor.id"><h3>{{ anchor.name }}</h3></article></div>
      <ScriptStoryMapEditor v-if="editingStructure" :episodes="visibleEpisodes" @save="saveStoryMapDraft" @cancel="editingStructure = false" />
      <template v-else-if="visibleEpisodes.length">
        <section class="storymap-candidate"><div class="storymap-heading"><div><p class="eyebrow">{{ storyMapCandidate ? '结构候选' : '已采纳结构' }}</p><h3>Episode → Scene → Story Beat</h3></div><span>版本 {{ storyMapCandidate?.base_version ?? script.state.story_map.version }}</span></div><article v-for="episode in visibleEpisodes" :key="episode.id" class="storymap-group"><header><strong>第 {{ episode.ordinal }} 集 · {{ episode.title }}</strong><small>{{ episode.scenes.length }} 场</small></header><div v-for="scene in episode.scenes" :key="scene.id" class="storymap-unit"><span>{{ episode.ordinal }}-{{ scene.ordinal }}</span><div><strong>{{ scene.title }}</strong><p v-for="beat in scene.beats ?? []" :key="beat.id">{{ beat.objective }}</p></div><small>{{ scene.duration_seconds_target }} 秒</small></div></article></section>
        <div v-if="storyMapCandidate" class="decision-bar"><div><strong>影响确认</strong><small>新增 {{ storyMapCandidate.impact.added_units }} · 删除 {{ storyMapCandidate.impact.removed_units }} · 保留 {{ storyMapCandidate.impact.retained_units }}</small></div><div class="decision-actions"><button class="secondary" @click="editingStructure = true">调整候选</button><button class="primary" @click="script.adoptStoryMap(projectId, storyMapCandidate.id)">确认 StoryMap 并进入写作</button></div></div>
        <div v-else class="adopted-notice"><div><strong>StoryMap 已采纳</strong><span>点击左侧逐场写作进入主笔工作区；调整将形成新候选。</span></div><button class="secondary" @click="editingStructure = true">提出结构调整</button></div>
      </template>
      <div v-else class="planning-empty"><p>采纳蓝图后生成结构，生成前不会改变当前目录；生成后可检查每一场及其 Story Beat。</p><button class="primary" :disabled="!script.state.blueprint" @click="script.generateStoryMap(projectId)">生成 StoryMap 候选</button></div>
    </section>

    <template v-else-if="script.state.story_map.episodes.length">
    <ScriptDeliveryPanel :project-id="projectId" />
    <section class="studio-stage writing-stage" :class="{ 'sidecar-hidden': layout.writerSidecarHidden }" @mouseup="captureSelection">
      <aside class="script-outline"><p class="eyebrow">Script StoryMap</p><article v-for="episode in script.state.story_map.episodes" :key="episode.id"><h3>第 {{ episode.ordinal }} 集 · {{ episode.title }}</h3><button v-for="scene in episode.scenes" :key="scene.id" class="scene-row" :class="{ adopted: adoptedSceneIds.has(scene.id), active: focusedUnitId === scene.id }" :disabled="Boolean(script.busy)" @click="selectScene(scene.id)"><span>{{ scene.ordinal }}</span><strong>{{ scene.title }}</strong><small>{{ adoptedSceneIds.has(scene.id) ? '已采纳' : `${scene.duration_seconds_target} 秒` }}</small></button></article></aside>
      <div class="script-editor">
        <div v-if="focusedCandidate" class="chapter-candidate-toolbar"><div><strong>场次候选稿 · 修订 {{ focusedCandidate.revision_number }}</strong><small>候选只读。确认后才成为本场正文并进入后续场次上下文。</small></div><div><button class="secondary" @click="script.generateSceneCandidate(projectId, focusedUnitId, '基于当前候选重新创作，强化动作、冲突与视听节奏')">生成新版候选</button><button class="primary" @click="script.adoptSceneCandidate(projectId, focusedUnitId, focusedCandidate.id)">确认采用</button></div></div>
        <article v-if="visibleDocument" :key="visibleDocument.id" class="screenplay-page" :class="`format-${script.state.script_format}`"><p v-for="block in visibleDocument.blocks" :key="block.para_id" :class="[`screenplay-${block.type}`, severityByElement[block.para_id] && `finding-mark severity-${severityByElement[block.para_id]}`]" :data-element-id="block.para_id">{{ block.text }}</p></article>
        <div v-else class="writer-empty"><p class="eyebrow">主笔</p><h2>{{ focusedScene?.title ?? writerReadyVision }}</h2><p>先生成场次候选；候选完成后只读预览，明确确认后才成为正文。</p><button class="primary" :disabled="Boolean(script.busy)" @click="script.generateSceneCandidate(projectId, focusedUnitId)">{{ script.busy ? '生成中…' : '生成当前场候选稿' }}</button></div>
      </div>
      <button v-if="layout.writerSidecarHidden" class="sidecar-restore" aria-label="显示上下文与审读面板" @click="layout.setWriterSidecarHidden(false)">显示上下文 / 审读</button>
      <aside v-else class="writer-sidecar">
        <nav class="sidecar-tabs" aria-label="写作辅助"><button :class="{ active: sideTab === 'context' }" @click="sideTab = 'context'">上下文</button><button :class="{ active: sideTab === 'review' }" @click="sideTab = 'review'">审读</button><button class="sidecar-hide" aria-label="隐藏上下文与审读面板" @click="layout.setWriterSidecarHidden(true)">隐藏</button></nav>
        <section v-if="sideTab === 'context'" class="context-sidecar"><p class="eyebrow">当前场</p><h3>{{ focusedScene?.title ?? focusedUnitId }}</h3><dl><div><dt>目标时长</dt><dd>{{ focusedScene?.duration_seconds_target ?? '—' }} 秒</dd></div><div><dt>正文修订</dt><dd>v{{ focusedDocument?.revision_number ?? 0 }}</dd></div><div><dt>剧本格式</dt><dd>{{ script.state.script_format === 'chinese' ? '中文剧本' : 'Hollywood' }}</dd></div></dl><p class="eyebrow">蓝图锚点</p><div class="sidecar-anchors"><span v-for="anchor in script.state.blueprint?.anchors.slice(0, 8)" :key="anchor.id">{{ anchor.name }}</span></div><SourceCitations v-if="sourceMode === 'adaptation'" :project-id="projectId" :query="focusedScene?.title" /></section>
        <ReviewPanel v-else-if="focusedDocument" medium="script" :project-id="projectId" :unit-id="focusedDocument.scene_id" :revision-id="focusedDocument.id" :elements="reviewElements" :anchors="script.state.blueprint?.anchors ?? []" :selection="reviewSelection" @locate="locate" @changed="script.load(projectId)" />
        <section v-else class="context-sidecar"><p>生成当前场后即可开始审读。</p></section>
      </aside>
      <div v-if="selection" class="selection-popover" :style="{ left: `${selection.x}px`, top: `${selection.y}px` }"><button @click="useSelection('expand')">扩写</button><button @click="useSelection('shorten')">缩写</button><button @click="useSelection('polish')">润色</button><button @click="useSelection('revise')">修订</button></div>
    </section>
    </template>
    <section v-else class="studio-stage planning-empty"><p>完成 StoryMap 并明确采纳后，逐场写作才会开放。</p><button class="secondary" @click="layout.setStudioView('storymap')">返回 StoryMap</button></section>
  </div>
</template>
