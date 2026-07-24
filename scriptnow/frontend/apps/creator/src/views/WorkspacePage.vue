<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import AgentDock from '../components/AgentDock.vue'
import NovelStudio from '../components/NovelStudio.vue'
import ScriptStudio from '../components/ScriptStudio.vue'
import { useProjectsStore } from '../stores/projects'

const route = useRoute()
const projects = useProjectsStore()
const projectId = computed(() => String(route.params.projectId))
const project = computed(() => projects.items.find((item) => item.id === projectId.value))
onMounted(() => { void projects.load() })
</script>

<template>
  <AppShell title="创作现场" eyebrow="创作工作区">
    <ScriptStudio v-if="project?.medium === 'script'" :project-id="projectId" :source-mode="project.source_mode" />
    <NovelStudio v-else-if="project?.medium === 'novel'" :project-id="projectId" :source-mode="project.source_mode" />
    <AgentDock :project-id="projectId" />
  </AppShell>
</template>
