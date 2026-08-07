<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import { useProjectsStore } from '../stores/projects'

const AppShell = defineAsyncComponent(() => import('../components/AppShell.vue'))
const AgentDock = defineAsyncComponent(() => import('../components/AgentDock.vue'))
const CrossCulturalRecreationStudio = defineAsyncComponent(
  () => import('../components/CrossCulturalRecreationStudio.vue'),
)
const NovelStudio = defineAsyncComponent(() => import('../components/NovelStudio.vue'))
const ScriptStudio = defineAsyncComponent(() => import('../components/ScriptStudio.vue'))
const TranslationStudio = defineAsyncComponent(() => import('../components/TranslationStudio.vue'))

const route = useRoute()
const projects = useProjectsStore()
const projectId = computed(() => String(route.params.projectId))
const project = computed(() => projects.items.find((item) => item.id === projectId.value))
onMounted(() => { void projects.load() })

const isCrossCulturalProject = computed(() => project.value?.workflow_kind === 'cross_cultural_recreation')
const isScriptProject = computed(() => project.value?.medium === 'script')
const isNovelProject = computed(() => project.value?.medium === 'novel')
const isTranslationProject = computed(() => project.value?.medium === 'translation')
</script>

<template>
  <AppShell title="创作现场" eyebrow="创作工作区">
    <CrossCulturalRecreationStudio
      v-if="isCrossCulturalProject"
      :project-id="projectId"
      :direction="project!.direction"
    />
    <ScriptStudio v-else-if="isScriptProject" :project-id="projectId" :source-mode="project!.source_mode" />
    <NovelStudio v-else-if="isNovelProject" :project-id="projectId" :source-mode="project!.source_mode" />
    <TranslationStudio
      v-else-if="isTranslationProject"
      :project-id="projectId"
      :source-language="project!.direction.source_language"
      :target-language="project!.direction.target_language"
    />
    <AgentDock v-if="project?.medium !== 'translation'" :project-id="projectId" />
  </AppShell>
</template>
