<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocale, useTheme } from '@scriptnow/shared'
import { PhMoon, PhSun } from '@phosphor-icons/vue'

import { useLayoutStore } from '../stores/layout'
import { useProjectsStore } from '../stores/projects'
import NovelDeliveryPanel from './NovelDeliveryPanel.vue'

const props = defineProps<{ title: string; eyebrow?: string }>()
const route = useRoute()
const router = useRouter()
const projects = useProjectsStore()
const layout = useLayoutStore()
const { isEnglish, t, toggleLocale } = useLocale()
const { resolvedTheme, toggleTheme } = useTheme()
const dragging = ref(false)
const showExport = ref(false)
const showHistory = ref(false)

function openExport() { showExport.value = true }
function openHistory() { showHistory.value = true }
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
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="creator-shell" :class="{ 'sidebar-hidden': layout.sidebarHidden, 'writer-focus': layout.writerFocus, dragging }" :style="shellStyle">
    <aside class="creator-sidebar" :class="{ open: layout.mobileOpen }">
      <RouterLink to="/" class="sidebar-brand"><img class="growth-mark small" src="/scriptnow-mark.svg" alt="" /><span><strong>ScriptNow</strong><small>{{ t('brand.tagline') }}</small></span></RouterLink>
      <section class="project-switch"><label for="project-switch">{{ t('creator.currentProject') }}</label><select id="project-switch" :value="projectId" @change="switchProject"><option value="">{{ t('creator.console') }}</option><option v-for="item in projects.items" :key="item.id" :value="item.id">{{ item.name }}</option><option value="new">＋ {{ t('creator.newProject') }}</option></select></section>
      <template v-if="project">
        <nav class="shell-nav" aria-label="创作导航">
          <p>{{ t('creator.creation') }}</p><button :class="{ active: layout.studioView === 'ideation' }" @click="layout.setStudioView('ideation')">◇ {{ t('creator.ideation') }}</button><button :class="{ active: layout.studioView === 'blueprint' }" @click="layout.setStudioView('blueprint')">▦ {{ t('creator.blueprint') }}</button><button v-if="project.medium === 'novel'" :class="{ active: layout.studioView === 'graph' }" @click="layout.setStudioView('graph')">◎ {{ t('creator.storyGraph') }}</button><button :class="{ active: layout.studioView === 'storymap' }" @click="layout.setStudioView('storymap')">⊞ {{ t('creator.storyMap') }}</button><button :class="{ active: layout.studioView === 'writer' }" @click="layout.setStudioView('writer')">▸ {{ project.medium === 'script' ? t('creator.sceneWriting') : t('creator.chapterWriting') }}</button>
          <p>{{ t('creator.project') }}</p><RouterLink to="/">◈ {{ t('creator.dashboard') }}</RouterLink><RouterLink :to="`/projects/${projectId}/agents`">◎ {{ t('creator.team') }}</RouterLink><RouterLink :to="`/projects/${projectId}/packaging`">▣ {{ t('creator.packaging') }}</RouterLink><button @click="openExport">↓ {{ t('creator.export') }}</button><button @click="openHistory">↺ {{ t('creator.history') }}</button>
        </nav>
        <RouterLink to="/new" class="create-project-btn">✦ {{ t('creator.create') }}</RouterLink>
      </template>
      <template v-else>
        <nav class="shell-nav"><p>{{ t('creator.workspace') }}</p><RouterLink to="/">◈ {{ t('creator.dashboard') }}</RouterLink></nav>
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
      <div v-if="showExport" class="modal-overlay" @click.self="showExport = false">
        <div class="modal-panel" style="max-width:680px">
          <header><h2>导出作品</h2><button @click="showExport = false">✕</button></header>
          <NovelDeliveryPanel v-if="project?.medium === 'novel'" :project-id="projectId" />
          <p v-else class="muted" style="padding:20px">剧本导出即将推出。</p>
        </div>
      </div>
      <div v-if="showHistory" class="modal-overlay" @click.self="showHistory = false">
        <div class="modal-panel" style="max-width:680px">
          <header><h2>历史版本</h2><button @click="showHistory = false">✕</button></header>
          <div style="padding:20px">
            <p class="muted">项目快照功能即将推出。当前可前往包装页面导出完整作品。</p>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
