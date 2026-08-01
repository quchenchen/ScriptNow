<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '../api'
import AppShell from '../components/AppShell.vue'
import { useProjectsStore } from '../stores/projects'

interface Cover {
  image_url: string
  status: string
}

const projects = useProjectsStore()
const router = useRouter()
const projectCovers = ref<Record<string, string>>({})

async function loadProjectCovers() {
  const entries = await Promise.all(
    projects.items.map(async (project) => {
      try {
        const covers = await api<Cover[]>(`/projects/${project.id}/packaging/covers`)
        const cover = covers.find((item) => item.status === 'candidate') ?? covers[0]
        return cover?.image_url ? ([project.id, cover.image_url] as const) : undefined
      } catch {
        return undefined
      }
    }),
  )
  projectCovers.value = Object.fromEntries(entries.filter((entry) => entry !== undefined))
}

onMounted(async () => {
  await projects.load()
  if (!projects.items.length) await router.replace('/welcome')
  else await loadProjectCovers()
})
</script>

<template>
  <AppShell title="你的故事" eyebrow="创作项目">
    <template #heading>
      <div class="dashboard-actions">
        <RouterLink class="secondary link-button" to="/review-agent">独立评审</RouterLink>
        <RouterLink class="primary link-button" to="/new">新建项目</RouterLink>
      </div>
    </template>
    <p v-if="projects.loading" class="muted">正在读取创作现场…</p>
    <section v-else class="project-grid" aria-label="项目列表">
      <RouterLink
        v-for="project in projects.items"
        :key="project.id"
        :to="`/projects/${project.id}`"
        class="project-card"
        :class="{ 'has-cover': projectCovers[project.id] }"
      >
        <img
          v-if="projectCovers[project.id]"
          class="project-card-cover"
          :src="projectCovers[project.id]"
          alt=""
          loading="lazy"
        />
        <span v-if="projectCovers[project.id]" class="project-card-scrim" aria-hidden="true"></span>
        <div class="project-card-content">
          <div class="project-card-chips"><span class="medium-chip">{{ project.medium === 'script' ? '剧本' : '小说' }}</span><span class="source-chip">{{ project.source_mode === 'adaptation' ? '改编' : '原创' }}</span></div>
          <h2 data-i18n-skip>{{ project.name }}</h2>
          <span class="card-arrow">进入 →</span>
        </div>
      </RouterLink>
    </section>
  </AppShell>
</template>

<style scoped>
.dashboard-actions{display:flex;gap:10px;flex-wrap:wrap}
</style>
