<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import AgentDock from '../components/AgentDock.vue'
import CrossCulturalRecreationStudio from '../components/CrossCulturalRecreationStudio.vue'
import NovelStudio from '../components/NovelStudio.vue'
import ScriptStudio from '../components/ScriptStudio.vue'
import TranslationStudio from '../components/TranslationStudio.vue'
import { useProjectsStore } from '../stores/projects'

const route = useRoute()
const projects = useProjectsStore()
const projectId = computed(() => String(route.params.projectId))
const project = computed(() => projects.items.find((item) => item.id === projectId.value))
onMounted(() => { void projects.load() })
</script>

<template>
  <AppShell title="创作现场" eyebrow="创作工作区">
    <CrossCulturalRecreationStudio
      v-if="project?.workflow_kind === 'cross_cultural_recreation'"
      :project-id="projectId"
      :direction="project.direction"
    />
    <ScriptStudio v-else-if="project?.medium === 'script'" :project-id="projectId" :source-mode="project.source_mode" />
    <NovelStudio v-else-if="project?.medium === 'novel'" :project-id="projectId" :source-mode="project.source_mode" />
    <TranslationStudio
      v-else-if="project?.medium === 'translation'"
      :project-id="projectId"
      :source-language="project.direction.source_language"
      :target-language="project.direction.target_language"
    />
    <AgentDock v-if="project?.medium !== 'translation'" :project-id="projectId" />
  </AppShell>
</template>
