<script setup lang="ts">
type ProjectCard = {
  id: number
  title: string
  goal_type: string
  goal_label: string
  pulse: null | { state: string; needs_user: boolean; headline: string }
}

defineProps<{ projects: ProjectCard[] }>()
defineEmits<{ create: []; open: [project: ProjectCard] }>()
</script>

<template>
  <section class="dashboard">
    <div class="hero">
      <p class="kicker">AI AGENT CREATIVE STUDIO</p>
      <h1>让故事持续长出来</h1>
      <p>你负责意图与判断，Agent Team 负责准备、执行、校验和追踪。</p>
      <button class="primary" @click="$emit('create')">创建新项目</button>
    </div>
    <div v-if="projects.length" class="projects">
      <div class="projects-head"><h2>继续创作</h2><span>{{ projects.filter(project => project.pulse?.needs_user).length }} 项等待判断</span></div>
      <button v-for="project in projects" :key="project.id" class="project" @click="$emit('open', project)">
        <div><strong>{{ project.title }}</strong><span>{{ project.goal_label }}</span></div>
        <div class="project-next"><b :class="['pulse-state', project.pulse?.state]">{{ project.pulse?.needs_user ? '等待你的判断' : project.pulse?.state === 'working' ? 'Agent 工作中' : '可继续' }}</b><small>{{ project.pulse?.headline }}</small></div>
      </button>
    </div>
  </section>
</template>
