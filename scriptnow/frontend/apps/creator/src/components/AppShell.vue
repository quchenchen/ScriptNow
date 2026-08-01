<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocale, useTheme } from '@scriptnow/shared'
import { PhMagnifyingGlass, PhMoon, PhSealCheck, PhSun } from '@phosphor-icons/vue'

import { useDockStore } from '../stores/dock'
import { useLayoutStore } from '../stores/layout'
import { useProjectsStore } from '../stores/projects'
import NovelDeliveryPanel from './NovelDeliveryPanel.vue'
import ScriptDeliveryPanel from './ScriptDeliveryPanel.vue'

const props = defineProps<{ title: string; eyebrow?: string }>()
const route = useRoute()
const router = useRouter()
const projects = useProjectsStore()
const layout = useLayoutStore()
const dock = useDockStore()
const { isEnglish, t, toggleLocale } = useLocale()
const { resolvedTheme, toggleTheme } = useTheme()
const dragging = ref(false)
const deliveryMode = ref<'export' | 'history'>()
const deleteDialogOpen = ref(false)
const deleteConfirmation = ref('')
const deleteBusy = ref(false)
const deleteError = ref('')

function openExport() { deliveryMode.value = 'export' }
function openHistory() { deliveryMode.value = 'history' }
function openTranslationImport() {
  window.dispatchEvent(new CustomEvent('scriptnow:translation-import'))
}
function openTranslationHistory() {
  window.dispatchEvent(new CustomEvent('scriptnow:translation-history'))
}
async function selectRecreationStage(stage: number) {
  layout.mobileOpen = false
  await router.replace({
    path: `/projects/${projectId.value}`,
    query: { ...route.query, recreationStage: String(stage) },
  })
}
async function openProjectReviewer() {
  if (!projectId.value) return
  layout.mobileOpen = false
  if (route.path !== `/projects/${projectId.value}`) {
    await router.push(`/projects/${projectId.value}`)
  }
  dock.openReviewer(dock.reviewCheckpoint)
}
async function consumeReviewRoute() {
  if (!projectId.value || route.query.review !== 'checkpoint') return
  dock.openReviewer(dock.reviewCheckpoint)
  const query = { ...route.query }
  delete query.review
  await router.replace({ path: route.path, query })
}
function openRecreationExport() {
  window.dispatchEvent(new CustomEvent('scriptnow:recreation-export'))
}
function openDeleteDialog() {
  deleteConfirmation.value = ''
  deleteError.value = ''
  deleteDialogOpen.value = true
}
function closeDeleteDialog() {
  if (deleteBusy.value) return
  deleteDialogOpen.value = false
}
async function confirmDeleteProject() {
  if (!project.value || deleteConfirmation.value !== project.value.name) return
  deleteBusy.value = true
  deleteError.value = ''
  try {
    await projects.remove(project.value.id, deleteConfirmation.value)
    deleteDialogOpen.value = false
    await router.replace('/')
  } catch (caught) {
    deleteError.value = caught instanceof Error ? caught.message : '删除项目失败'
  } finally {
    deleteBusy.value = false
  }
}
const englishPageCopy: Record<string, string> = {
  '你的故事': 'Your stories', '创作团队': 'Creative team', '作品包装': 'Work packaging', '账户中心': 'Account',
  '创作现场': 'Creative studio', '种下新故事': 'Plant a new story', '创作项目': 'Creative projects',
  '项目角色配置': 'Project roles', '书名 · 简介 · 标签 · 封面': 'Title · Blurb · Tags · Cover',
  '创作工作区': 'Creative workspace', '四步创作向导': 'Four-step creation guide',
}
const localizedTitle = computed(() => isEnglish.value ? (englishPageCopy[props.title] ?? props.title) : props.title)
const localizedEyebrow = computed(() => props.eyebrow && isEnglish.value ? (englishPageCopy[props.eyebrow] ?? props.eyebrow) : props.eyebrow)
const projectId = computed(() => String(route.params.projectId ?? ''))
const project = computed(() => projects.items.find((item) => item.id === projectId.value))
const isCrossCulturalRecreation = computed(
  () => project.value?.workflow_kind === 'cross_cultural_recreation',
)
const recreationStage = computed(() => {
  const value = Number(route.query.recreationStage)
  return value >= 1 && value <= 6 ? value : 1
})
const shellStyle = computed(() => ({
  '--creator-sidebar-width': `${layout.sidebarWidth}px`,
  '--creator-sidebar-current': layout.sidebarHidden ? '0px' : `${layout.sidebarWidth}px`,
}))

async function switchProject(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  if (value === 'new') await router.push('/new')
  else if (value) await router.push(`/projects/${value}`)
  else await router.push('/')
}
function onKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === 'b') {
    if (['INPUT', 'TEXTAREA'].includes((document.activeElement as HTMLElement | null)?.tagName ?? '')) return
    event.preventDefault()
    layout.toggleSidebar()
  }
}
function startDrag(event: PointerEvent) {
  if (layout.sidebarHidden) return
  dragging.value = true
  const origin = event.clientX
  const width = layout.sidebarWidth
  const move = (next: PointerEvent) => layout.setWidth(width + next.clientX - origin)
  const stop = () => { dragging.value = false; window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop) }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop)
}
onMounted(() => {
  if (!projects.items.length) void projects.load()
  window.addEventListener('keydown', onKeydown)
})
watch(
  () => [route.params.projectId, route.query.review],
  () => { void consumeReviewRoute() },
  { immediate: true },
)
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="creator-shell" :class="{ 'sidebar-hidden': layout.sidebarHidden, 'writer-focus': layout.writerFocus, dragging }" :style="shellStyle">
    <aside class="creator-sidebar" :class="{ open: layout.mobileOpen }">
      <RouterLink to="/" class="sidebar-brand"><img class="growth-mark small" src="/scriptnow-mark.svg" alt="" /><span><strong>ScriptNow</strong><small>{{ t('brand.tagline') }}</small></span></RouterLink>
      <section class="project-switch"><label for="project-switch">{{ t('creator.currentProject') }}</label><select id="project-switch" :value="projectId" @change="switchProject"><option value="">{{ t('creator.console') }}</option><option v-for="item in projects.items" :key="item.id" :value="item.id">{{ item.name }}</option><option value="new">＋ {{ t('creator.newProject') }}</option></select></section>
      <template v-if="project">
        <nav v-if="isCrossCulturalRecreation" class="shell-nav" aria-label="归化创作导航">
          <p>归化创作</p>
          <button :class="{ active: recreationStage === 1 }" @click="selectRecreationStage(1)">01 读懂原作</button>
          <button :class="{ active: recreationStage === 2 }" @click="selectRecreationStage(2)">02 确认目标</button>
          <button :class="{ active: recreationStage === 3 }" @click="selectRecreationStage(3)">03 选择策略</button>
          <button :class="{ active: recreationStage === 4 }" @click="selectRecreationStage(4)">04 试写验证</button>
          <button :class="{ active: recreationStage === 5 }" @click="selectRecreationStage(5)">05 整书蓝图</button>
          <button :class="{ active: recreationStage === 6 }" @click="selectRecreationStage(6)">06 逐章生产</button>
          <p>{{ t('creator.project') }}</p>
          <RouterLink to="/">◈ {{ t('creator.dashboard') }}</RouterLink>
          <RouterLink :to="`/projects/${projectId}/agents`">◎ {{ t('creator.team') }}</RouterLink>
          <button type="button" @click="openProjectReviewer"><PhSealCheck />{{ isEnglish ? 'Review editor' : '审读编辑' }}</button>
          <button type="button" @click="openRecreationExport">↓ 导出归化稿</button>
          <button class="project-delete-trigger" type="button" @click="openDeleteDialog">⌫ 删除项目</button>
        </nav>
        <nav v-else-if="project.medium !== 'translation'" class="shell-nav" aria-label="创作导航">
          <p>{{ t('creator.creation') }}</p>
          <button :class="{ active: layout.studioView === 'ideation' }" @click="layout.setStudioView('ideation')">◇ {{ t('creator.ideation') }}</button>
          <button :class="{ active: layout.studioView === 'blueprint' }" @click="layout.setStudioView('blueprint')">▦ {{ t('creator.blueprint') }}</button>
          <button v-if="project.medium === 'novel'" :class="{ active: layout.studioView === 'graph' }" @click="layout.setStudioView('graph')">◎ {{ t('creator.storyGraph') }}</button>
          <button :class="{ active: layout.studioView === 'storymap' }" @click="layout.setStudioView('storymap')">⊞ {{ t('creator.storyMap') }}</button>
          <button :class="{ active: layout.studioView === 'writer' }" @click="layout.setStudioView('writer')">▸ {{ project.medium === 'script' ? t('creator.sceneWriting') : t('creator.chapterWriting') }}</button>
          <p>{{ t('creator.project') }}</p>
          <RouterLink to="/">◈ {{ t('creator.dashboard') }}</RouterLink>
          <RouterLink :to="`/projects/${projectId}/agents`">◎ {{ t('creator.team') }}</RouterLink>
          <button type="button" @click="openProjectReviewer"><PhSealCheck />{{ isEnglish ? 'Review editor' : '审读编辑' }}</button>
          <RouterLink :to="`/projects/${projectId}/packaging`">▣ {{ t('creator.packaging') }}</RouterLink>
          <button @click="openExport">↓ {{ t('creator.export') }}</button>
          <button @click="openHistory">↺ {{ t('creator.history') }}</button>
          <button class="project-delete-trigger" type="button" @click="openDeleteDialog">⌫ 删除项目</button>
        </nav>
        <nav v-else class="shell-nav" aria-label="翻译导航">
          <p>翻译</p>
          <RouterLink :to="`/projects/${projectId}`">文 译文工作台</RouterLink>
          <button type="button" @click="openTranslationImport">↑ 导入译文</button>
          <button type="button" @click="openTranslationHistory">↺ 历史版本</button>
          <p>{{ t('creator.project') }}</p>
          <RouterLink to="/">◈ {{ t('creator.dashboard') }}</RouterLink>
          <button class="project-delete-trigger" type="button" @click="openDeleteDialog">⌫ 删除项目</button>
        </nav>
        <RouterLink to="/new" class="create-project-btn">✦ {{ t('creator.create') }}</RouterLink>
      </template>
      <template v-else>
        <nav class="shell-nav">
          <p>{{ t('creator.workspace') }}</p>
          <RouterLink to="/">◈ {{ t('creator.dashboard') }}</RouterLink>
          <RouterLink to="/review-agent"><PhMagnifyingGlass />{{ isEnglish ? 'Independent review' : '独立评审' }}</RouterLink>
        </nav>
        <RouterLink to="/new" class="create-project-btn">✦ {{ t('creator.create') }}</RouterLink>
      </template>
      <RouterLink to="/account" class="sidebar-account"><span>帐</span><span><strong>{{ t('creator.account') }}</strong><small>{{ t('creator.accountHint') }}</small></span></RouterLink>
    </aside>
    <div class="sidebar-overlay" :class="{ show: layout.mobileOpen }" @click="layout.mobileOpen = false" />
    <div class="sidebar-drag" title="拖拽或双击收起侧栏 (⌘B)" @pointerdown="startDrag" @dblclick="layout.setManualHidden(true)" />
    <button v-if="layout.sidebarHidden" class="sidebar-reopen" aria-label="展开侧栏" @click="layout.setManualHidden(false)">›</button>
    <section class="creator-main">
      <header class="creator-topbar"><button class="mobile-menu" :aria-label="t('common.menu')" @click="layout.mobileOpen = true">☰</button><span>{{ localizedTitle }}</span><div><small><i /> {{ t('common.saved') }}</small><div class="interface-controls"><button class="theme-switch" type="button" :aria-label="resolvedTheme === 'dark' ? t('theme.light') : t('theme.dark')" :title="resolvedTheme === 'dark' ? t('theme.light') : t('theme.dark')" @click="toggleTheme"><PhSun v-if="resolvedTheme === 'dark'" /><PhMoon v-else /></button><button class="locale-switch" type="button" :aria-label="t('locale.label')" :title="t('locale.label')" @click="toggleLocale">{{ t('locale.action') }}</button></div><button class="usage-pill">{{ project?.medium === 'script' ? t('creator.script') : project?.medium === 'novel' ? t('creator.novel') : 'Creator' }}</button></div></header>
      <main class="page-shell">
        <header class="page-heading"><p v-if="localizedEyebrow" class="eyebrow">{{ localizedEyebrow }}</p><h1>{{ localizedTitle }}</h1><slot name="heading" /></header>
        <slot />
      </main>
    </section>
    <Teleport to="body">
      <NovelDeliveryPanel
        v-if="deliveryMode && project?.medium === 'novel'"
        :key="deliveryMode"
        :project-id="projectId"
        :initial-mode="deliveryMode"
        :show-toolbar="false"
        @close="deliveryMode = undefined"
      />
      <ScriptDeliveryPanel
        v-if="deliveryMode && project?.medium === 'script'"
        :key="deliveryMode"
        :project-id="projectId"
        :initial-mode="deliveryMode"
        :show-toolbar="false"
        @close="deliveryMode = undefined"
      />
      <div v-if="deleteDialogOpen && project" class="project-delete-backdrop" @click.self="closeDeleteDialog">
        <form class="project-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-project-title" @submit.prevent="confirmDeleteProject">
          <p class="eyebrow">危险操作</p>
          <h2 id="delete-project-title">确认删除项目</h2>
          <p>删除后项目将进入回收状态并从工作区隐藏；原稿、版本、运行记录与审计证据不会被物理清除。</p>
          <p class="project-delete-name">{{ project.name }}</p>
          <label for="delete-project-confirmation">请输入完整项目名称以确认</label>
          <input id="delete-project-confirmation" v-model="deleteConfirmation" :placeholder="project.name" autocomplete="off" autofocus />
          <p v-if="deleteError" class="error" role="alert">{{ deleteError }}</p>
          <footer>
            <button class="secondary" type="button" :disabled="deleteBusy" @click="closeDeleteDialog">取消</button>
            <button class="project-delete-confirm" type="submit" :disabled="deleteBusy || deleteConfirmation !== project.name">{{ deleteBusy ? '正在删除…' : '确认删除项目' }}</button>
          </footer>
        </form>
      </div>
    </Teleport>
  </div>
</template>
