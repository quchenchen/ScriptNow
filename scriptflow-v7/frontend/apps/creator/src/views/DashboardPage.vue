<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { useProjectsStore } from '../stores/projects'

const projects = useProjectsStore()
const router = useRouter()
onMounted(async () => {
  await projects.load()
  if (!projects.items.length) await router.replace('/welcome')
})
</script>

<template>
  <AppShell title="你的故事" eyebrow="创作项目">
    <template #heading><RouterLink class="primary link-button" to="/new">新建项目</RouterLink></template>
    <p v-if="projects.loading" class="muted">正在读取创作现场…</p>
    <section v-else class="project-grid" aria-label="项目列表">
      <RouterLink v-for="project in projects.items" :key="project.id" :to="`/projects/${project.id}`" class="project-card">
        <div class="project-card-chips"><span class="medium-chip">{{ project.medium === 'script' ? '剧本' : '小说' }}</span><span class="source-chip">{{ project.source_mode === 'adaptation' ? '改编' : '原创' }}</span></div>
        <h2>{{ project.name }}</h2>
        <p>继续进入创作团队协作现场</p>
        <span class="card-arrow">进入 →</span>
      </RouterLink>
    </section>
  </AppShell>
</template>
